"""Recherche en ligne des citations célèbres sur Wikiquote (gratuit), puis placement dans le film."""

from pathlib import Path

import requests

from clippeur import cache
from clippeur.correspondance import placer_dans_le_film
from clippeur.transcription import Suivi
from clippeur.wikiquote import citations_wikiquote

POPULARITE_WIKIQUOTE = 4  # une réplique retenue sur Wikiquote est en général bien connue


def nom_cache(langue: str) -> str:
    return f"recherche_{langue}"


def rechercher(film: Path, fiche: dict, transcription: dict, suivi: Suivi, page: str | None = None) -> dict:
    """Renvoie {page, url, pages_possibles, resultats, avertissements} et le met en cache.

    `page` : page Wikiquote choisie par l'utilisateur ; sinon, la plus probable.
    Chaque résultat a un champ « retenue » : l'utilisateur peut écarter une citation du choix des extraits.
    """
    langue = transcription.get("langue", "fr")
    donnees = {"page": None, "url": None, "pages_possibles": [], "resultats": [], "avertissements": []}

    suivi("Recherche des citations sur Wikiquote...", None)
    try:
        wq = citations_wikiquote(fiche, langue, page)
    except requests.RequestException as e:
        donnees["avertissements"].append(f"Wikiquote injoignable ({e.__class__.__name__}) : vérifiez la connexion Internet.")
        wq = None

    if wq:
        donnees.update(page=wq["page"], url=wq["url"], pages_possibles=wq["pages_possibles"])
        if not wq["page"]:
            donnees["avertissements"].append(
                "Aucune page Wikiquote trouvée pour cette œuvre. Vérifiez son titre, ou choisissez une page dans la liste.")
        elif not wq["citations"]:
            donnees["avertissements"].append(f"La page « {wq['page']} » ne contient aucune citation exploitable.")
        resultats = [{
            "type": "citation",
            "titre": next((r for r in c["repliques"] if len(r.split()) >= 3), c["repliques"][0])[:80],
            "repliques": c["repliques"],
            "source": c["source"],
            "source_url": c["source_url"],
            "popularite": POPULARITE_WIKIQUOTE,
        } for c in wq["citations"]]

        suivi(f"{len(resultats)} citations trouvées. Recherche de ces citations dans les dialogues du film...", None)
        resultats = placer_dans_le_film(resultats, transcription["segments"])
        # Par défaut, toute citation retrouvée dans le film compte pour le choix des extraits.
        donnees["resultats"] = [r | {"retenue": r["position"] is not None} for r in resultats]
        trouves = sum(1 for r in resultats if r["position"])
        suivi(f"{trouves} citation(s) sur {len(resultats)} retrouvée(s) dans le film.", None)

    cache.ecrire(film, nom_cache(langue), donnees)
    return donnees


def choisir_citations(film: Path, langue: str, retenues: list[int]) -> dict:
    """Enregistre les citations que l'utilisateur garde (par leur rang dans la liste)."""
    donnees = recherche_en_cache(film, langue)
    if donnees is None:
        raise ValueError("Aucune recherche pour ce film.")
    for i, r in enumerate(donnees["resultats"]):
        r["retenue"] = i in retenues and r["position"] is not None
    cache.ecrire(film, nom_cache(langue), donnees)
    return donnees


def recherche_en_cache(film: Path, langue: str) -> dict | None:
    donnees = cache.lire(film, nom_cache(langue))
    # Les recherches faites avec l'ancienne version (IA) n'ont ni « retenue » ni « pages_possibles ».
    if donnees is not None and "pages_possibles" not in donnees:
        return None
    return donnees

"""Enchaîne les étapes pour proposer des extraits : transcription, analyse, sélection, miniatures."""

from pathlib import Path

from clippeur import cache
from clippeur.analyse import detecter_plans, duree_video, mesurer_volume
from clippeur.export import creer_miniature
from clippeur.recherche import recherche_en_cache
from clippeur.segments import Segment
from clippeur.selection import proposer_extraits
from clippeur.transcription import Suivi, transcrire


def proposer(film: Path, langue: str, nombre: int, suivi: Suivi, modele: str | None = None) -> dict:
    options = {"langue": langue} | ({"modele": modele} if modele else {})
    transcription = transcrire(film, suivi=suivi, **options)
    segments = [Segment.depuis_dict(s) for s in transcription["segments"]]

    suivi("Mesure du volume sonore...", None)
    volume = mesurer_volume(film)
    suivi("Détection des changements de plan (environ 2 min par heure de film)...", None)
    plans = detecter_plans(film, suivi)

    recherche = recherche_en_cache(film, transcription.get("langue", langue)) or {}
    retenues = sum(1 for r in recherche.get("resultats", []) if r.get("retenue"))
    if retenues:
        suivi(f"Prise en compte de {retenues} citation(s) culte(s) de Wikiquote.", None)
    else:
        suivi("Aucune citation culte retenue : choix sur les seuls indices locaux.", None)

    suivi("Choix des meilleurs moments...", None)
    extraits = proposer_extraits(segments, plans, volume, duree_video(film), nombre,
                                 references=recherche.get("resultats"))

    suivi("Création des miniatures...", None)
    dossier_miniatures = cache.dossier_du_film(film) / "miniatures"
    resultat = []
    for e in extraits:
        miniature = dossier_miniatures / f"{e.numero:02d}.jpg"
        creer_miniature(film, e.debut + min(e.duree / 2, 10), miniature)
        resultat.append(e.vers_dict() | {"miniature": str(miniature)})

    suivi(f"{len(resultat)} extraits proposés.", None)
    return {"film": film.name, "chemin": str(film), "extraits": resultat}

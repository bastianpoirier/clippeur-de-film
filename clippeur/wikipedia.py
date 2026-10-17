"""Fiche du film depuis Wikipédia en français et Wikidata (F5) : gratuit, sans clé ni compte.

Wikipédia donne le résumé et l'image de l'article ; Wikidata, base de données liée à Wikipédia,
donne l'année, la réalisation et la distribution (acteurs, et parfois leurs personnages).
"""

import re

import requests

from clippeur.correspondance import normaliser

ENTETES = {"User-Agent": "clippeur-de-film/0.1 (application personnelle ; https://github.com/bastianpoirier/clippeur-de-film)"}
URL_WIKIPEDIA = "https://fr.wikipedia.org/w/api.php"
URL_WIKIDATA = "https://www.wikidata.org/w/api.php"
NB_ACTEURS = 8
PHRASES_RESUME = 5

# Propriétés Wikidata utilisées
DISTRIBUTION, PERSONNAGE = "P161", "P453"
REALISATEUR, CREATEUR = "P57", "P170"
DATE_SORTIE, DEBUT = "P577", "P580"
TITRE_ORIGINAL = "P1476"


def _api(url: str, **parametres) -> dict:
    reponse = requests.get(url, params={"format": "json", **parametres}, headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    return reponse.json()


def chercher_candidats(titre: str, annee: int | None, type_: str) -> list[dict]:
    """Articles Wikipédia qui peuvent correspondre à l'œuvre, le plus probable en premier."""
    precision = "série télévisée" if type_ == "serie" else f"film {annee or ''}".strip()
    resultats = _api(URL_WIKIPEDIA, action="query", list="search", srsearch=f"{titre} {precision}",
                     srlimit=8, formatversion=2)["query"]["search"]
    # Les listes (« Liste des épisodes de… ») et les homonymies ne décrivent pas l'œuvre elle-même.
    resultats = [r for r in resultats if not r["title"].startswith("Liste ") and "homonymie" not in r["title"]]

    cherche = normaliser(titre)

    def pertinence(r: dict) -> int:
        """D'abord les articles qui portent le titre de l'œuvre (pas ceux de ses acteurs) ;
        puis ceux dont l'extrait parle d'un film (ou d'une série) et de la bonne année.
        « OSS 117 » désigne d'abord des romans : c'est l'article du film de 2006 qu'on veut."""
        texte = f"{r['title']} {re.sub(r'<[^>]+>', '', r.get('snippet', ''))}".lower()
        porte_le_titre = normaliser(r["title"]).startswith(cherche)
        genre = ("série" in texte) if type_ == "serie" else ("film" in texte or "comédie" in texte)
        return 4 * porte_le_titre + 2 * genre + (bool(annee) and str(annee) in texte)

    resultats.sort(key=pertinence, reverse=True)  # tri stable : à égalité, l'ordre de Wikipédia
    return [{"ref": r["title"], "type": type_, "titre": r["title"], "annee": None, "source": "Wikipédia"}
            for r in resultats[:6]]


def _valeurs(revendications: dict, propriete: str) -> list:
    return [r["mainsnak"].get("datavalue", {}).get("value") for r in revendications.get(propriete, [])
            if r["mainsnak"].get("datavalue")]


def _annee(revendications: dict) -> int | None:
    for propriete in (DATE_SORTIE, DEBUT):
        dates = [v["time"] for v in _valeurs(revendications, propriete) if isinstance(v, dict) and "time" in v]
        if dates:
            return int(min(dates)[1:5])  # « +1998-01-01T00:00:00Z » → 1998
    return None


def _libelles(identifiants: list[str]) -> dict[str, str]:
    """Noms en français (ou à défaut en anglais) des éléments Wikidata demandés."""
    libelles: dict[str, str] = {}
    for i in range(0, len(identifiants), 50):  # l'API accepte 50 éléments par requête
        entites = _api(URL_WIKIDATA, action="wbgetentities", ids="|".join(identifiants[i:i + 50]),
                       props="labels", languages="fr|en")["entities"]
        for qid, entite in entites.items():
            noms = entite.get("labels", {})
            libelles[qid] = (noms.get("fr") or noms.get("en") or {}).get("value", qid)
    return libelles


def fiche(page: str, type_: str, saison: int | None = None, episode: int | None = None) -> dict:
    """Fiche de l'œuvre, au même format que celle de TMDb."""
    article = _api(URL_WIKIPEDIA, action="query", prop="extracts|pageimages|pageprops", titles=page,
                   exintro=1, explaintext=1, exsentences=PHRASES_RESUME, piprop="thumbnail", pithumbsize=300,
                   redirects=1, formatversion=2)["query"]["pages"][0]
    qid = article.get("pageprops", {}).get("wikibase_item")
    revendications = {}
    if qid:
        revendications = _api(URL_WIKIDATA, action="wbgetentities", ids=qid, props="claims")["entities"][qid]["claims"]

    # Wikidata liste en général les rôles principaux en premier : on garde son ordre.
    acteurs = []
    for r in revendications.get(DISTRIBUTION, [])[:NB_ACTEURS]:
        acteur = r["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
        roles = [q["datavalue"]["value"]["id"] for q in r.get("qualifiers", {}).get(PERSONNAGE, []) if q.get("datavalue")]
        if acteur:
            acteurs.append((acteur, roles[0] if roles else None))
    realisation = [v["id"] for v in _valeurs(revendications, CREATEUR if type_ == "serie" else REALISATEUR)
                   if isinstance(v, dict) and "id" in v][:3]

    a_nommer = list(dict.fromkeys([a for a, _ in acteurs] + [p for _, p in acteurs if p] + realisation))
    noms = _libelles(a_nommer) if a_nommer else {}
    titres_originaux = [v["text"] for v in _valeurs(revendications, TITRE_ORIGINAL) if isinstance(v, dict)]

    return {
        "ref": page,
        "type": type_,
        "titre": re.sub(r"\s*\((?:film|série télévisée)[^)]*\)$", "", article.get("title", page)),
        "titre_original": titres_originaux[0] if titres_originaux else None,
        "annee": _annee(revendications),
        "synopsis": article.get("extract", ""),
        "realisation": ", ".join(noms.get(q, q) for q in realisation),
        "acteurs": [{"nom": noms.get(a, a), "personnage": noms.get(p, "") if p else ""} for a, p in acteurs],
        "affiche": article.get("thumbnail", {}).get("source"),
        "saison": saison,
        "episode": episode,
        "source": "Wikipédia",
        "url": f"https://fr.wikipedia.org/wiki/{article.get('title', page).replace(' ', '_')}",
    }

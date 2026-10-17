"""Les séries du moment, calculées une fois par jour.

Sans clé : les séries dont l'article Wikipédia en français a été le plus consulté ces 7 derniers jours
(statistiques publiques de Wikimedia), reconnues comme séries grâce à Wikidata.
Avec une clé TMDb : la liste « tendances de la semaine » de TMDb.
"""

import collections
import datetime
import time

import requests

from clippeur import cache, config
from clippeur.identification import URL_AFFICHES, _appel_tmdb

# Wikimedia demande que chaque application s'identifie, avec un moyen de contacter son auteur.
ENTETES = {"User-Agent": "clippeur-de-film/0.1 (https://github.com/bastianpoirier/clippeur-de-film) python-requests"}
URL_STATISTIQUES = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/fr.wikipedia/all-access"
URL_WIKIPEDIA = "https://fr.wikipedia.org/w/api.php"
URL_WIKIDATA = "https://www.wikidata.org/w/api.php"
NB_JOURS = 7
PAGES_EXAMINEES = 400  # les plus consultées, parmi lesquelles on cherche les séries
NB_SERIES = 24  # quelques émissions seront écartées ensuite : il en reste une vingtaine
PAUSE_ENTRE_REQUETES = 0.5  # secondes : on ménage les serveurs de Wikimedia

# Natures Wikidata (propriété « nature de l'élément ») qui désignent une série ou une saison de série.
NATURES_SERIE = {
    "Q5398426",  # série télévisée
    "Q581714",  # série télévisée d'animation
    "Q1259759",  # mini-série
    "Q526877",  # série web
    "Q63952888",  # série d'animation japonaise
    "Q3464665",  # saison de série télévisée
}


MOTS_EMISSION = ("émission de télévision", "téléréalité", "jeu télévisé", "édition spéciale de l'émission")


class ErreurTendances(Exception):
    pass


def _requete(methode: str, url: str, **options) -> dict:
    """Requête polie : en cas de « trop de requêtes » (429), on attend le délai demandé et on réessaie une fois."""
    for essai in range(2):
        reponse = requests.request(methode, url, headers=ENTETES, timeout=30, **options)
        if reponse.status_code == 429 and essai == 0:
            time.sleep(min(int(reponse.headers.get("retry-after", "10") or 10), 60))
            continue
        if reponse.status_code == 429:
            raise ErreurTendances("Wikipédia limite les requêtes pour le moment : réessayez dans quelques minutes.")
        reponse.raise_for_status()
        time.sleep(PAUSE_ENTRE_REQUETES)
        return reponse.json()
    raise ErreurTendances("Wikipédia ne répond pas.")


def _pages_les_plus_vues() -> collections.Counter:
    vues = collections.Counter()
    for jours in range(1, NB_JOURS + 1):  # hier et les 6 jours d'avant (aujourd'hui n'est pas encore compté)
        jour = datetime.date.today() - datetime.timedelta(days=jours)
        try:
            articles = _requete("GET", f"{URL_STATISTIQUES}/{jour:%Y/%m/%d}")["items"][0]["articles"]
        except requests.HTTPError:
            continue  # journée pas encore publiée
        for a in articles:
            if ":" not in a["article"] and a["article"] != "Wikipédia:Accueil_principal":
                vues[a["article"]] += a["views"]
    return vues


def series_wikipedia() -> list[dict]:
    vues = _pages_les_plus_vues()
    if not vues:
        raise ErreurTendances("Statistiques de Wikipédia indisponibles.")
    candidates = [titre for titre, _ in vues.most_common(PAGES_EXAMINEES)]
    series = []
    for i in range(0, len(candidates), 50):  # l'API accepte 50 articles par requête
        lot = candidates[i:i + 50]
        pages = _requete("POST", URL_WIKIPEDIA, data={
            "action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "titles": "|".join(lot),
            "format": "json", "formatversion": 2})["query"]["pages"]
        elements = {p["pageprops"]["wikibase_item"]: p["title"] for p in pages if p.get("pageprops")}
        if not elements:
            continue
        entites = _requete("GET", URL_WIKIDATA, params={
            "action": "wbgetentities", "ids": "|".join(elements), "props": "claims", "format": "json"})["entities"]
        for qid, entite in entites.items():
            natures = {r["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
                       for r in entite.get("claims", {}).get("P31", [])}
            if natures & NATURES_SERIE:
                titre = elements[qid]
                series.append({"titre": titre, "vues": vues[titre.replace(" ", "_")],
                               "url": f"https://fr.wikipedia.org/wiki/{titre.replace(' ', '_')}"})
    series = sorted(series, key=lambda s: -s["vues"])[:NB_SERIES]

    # Résumé et image des séries retenues, en une seule requête.
    if series:
        details = _requete("POST", URL_WIKIPEDIA, data={
            "action": "query", "prop": "extracts|pageimages", "exintro": 1, "explaintext": 1, "exsentences": 2,
            "exlimit": "max", "piprop": "thumbnail", "pithumbsize": 200, "pilimit": "max",
            "titles": "|".join(s["titre"] for s in series), "format": "json", "formatversion": 2})["query"]["pages"]
        par_titre = {p["title"]: p for p in details}
        for s in series:
            page = par_titre.get(s["titre"], {})
            s["resume"] = page.get("extract", "")
            s["image"] = page.get("thumbnail", {}).get("source")
        # Wikidata classe certaines émissions (téléréalité, jeux) parmi les séries : on les écarte.
        series = [s for s in series if not any(mot in s["resume"].lower() for mot in MOTS_EMISSION)]
    return series


def series_tmdb() -> list[dict]:
    resultats = _appel_tmdb("/trending/tv/week").get("results", [])[:NB_SERIES]
    return [{
        "titre": r.get("name"), "titre_original": r.get("original_name"),
        "resume": r.get("overview", ""), "image": f"{URL_AFFICHES}{r['poster_path']}" if r.get("poster_path") else None,
        "url": f"https://www.themoviedb.org/tv/{r['id']}", "popularite": round(r.get("popularity", 0)),
    } for r in resultats]


def series_du_moment(forcer: bool = False) -> dict:
    """Renvoie {source, date, series}, depuis le cache si la liste du jour a déjà été calculée."""
    nom = f"tendances_{datetime.date.today():%Y-%m-%d}"
    if not forcer:
        en_cache = cache.lire_global(nom)
        if en_cache:
            return en_cache
    if config.cle_tmdb():
        source, series = "TMDb (tendances de la semaine)", series_tmdb()
    else:
        source, series = f"Wikipédia (articles les plus consultés, {NB_JOURS} derniers jours)", series_wikipedia()
    resultat = {"source": source, "date": f"{datetime.date.today():%d/%m/%Y}", "series": series}
    cache.ecrire_global(nom, resultat)
    return resultat

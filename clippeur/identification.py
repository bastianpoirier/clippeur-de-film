"""Identification du film : titre deviné depuis le nom du fichier (F4), fiche TMDb en français (F5),
correction par l'utilisateur (F6)."""

from pathlib import Path

import requests

from clippeur import cache, config

URL_TMDB = "https://api.themoviedb.org/3"
URL_AFFICHES = "https://image.tmdb.org/t/p/w185"
LANGUE_TMDB = "fr-FR"
NB_ACTEURS = 8


class ErreurTMDb(Exception):
    pass


def deviner(film: Path) -> dict:
    """« Breaking.Bad.S01E01.Pilot.720p.mkv » → titre, type, saison, épisode (F4)."""
    from guessit import guessit  # chargement un peu lent, fait seulement ici

    def premier(valeur):  # « S01E01E02 » donne une liste d'épisodes : on garde le premier
        return valeur[0] if isinstance(valeur, list) else valeur

    g = guessit(film.name)
    est_episode = g.get("type") == "episode"
    return {
        "titre": str(premier(g.get("title")) or film.stem),
        "annee": premier(g.get("year")),
        "type": "serie" if est_episode else "film",
        "saison": premier(g.get("season")) if est_episode else None,
        "episode": premier(g.get("episode")) if est_episode else None,
    }


def verifier_cle_tmdb(cle: str) -> bool:
    """Teste une clé auprès de TMDb avant de l'enregistrer."""
    try:
        _appel_tmdb("/configuration", cle=cle)
        return True
    except ErreurTMDb:
        return False


def _appel_tmdb(chemin: str, cle: str | None = None, **parametres) -> dict:
    cle = cle or config.cle_tmdb()
    if not cle:
        raise ErreurTMDb("Pas de clé TMDb : saisissez-la dans la section « Recherche en ligne » pour avoir "
                         "la fiche complète du film (gratuit).")
    entetes = {}
    # Le « jeton d'accès en lecture » (v4) est long et commence par « eyJ » ; la clé v3 est courte.
    if cle.startswith("eyJ"):
        entetes["Authorization"] = f"Bearer {cle}"
    else:
        parametres["api_key"] = cle
    reponse = requests.get(f"{URL_TMDB}{chemin}", params={"language": LANGUE_TMDB, **parametres},
                           headers=entetes, timeout=20)
    if reponse.status_code == 401:
        raise ErreurTMDb("Clé TMDb refusée : vérifiez-la dans la section « Recherche en ligne ».")
    reponse.raise_for_status()
    return reponse.json()


def _annee(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None


def chercher_candidats(titre: str, annee: int | None, type_: str) -> list[dict]:
    """Les œuvres TMDb qui correspondent au titre, pour que l'utilisateur choisisse la bonne (F6)."""
    if type_ == "serie":
        resultats = _appel_tmdb("/search/tv", query=titre, **({"first_air_date_year": annee} if annee else {}))
    else:
        resultats = _appel_tmdb("/search/movie", query=titre, **({"year": annee} if annee else {}))
    candidats = []
    for r in resultats.get("results", [])[:6]:
        candidats.append({
            "tmdb_id": r["id"],
            "type": type_,
            "titre": r.get("title") or r.get("name"),
            "titre_original": r.get("original_title") or r.get("original_name"),
            "annee": _annee(r.get("release_date") or r.get("first_air_date")),
            "affiche": f"{URL_AFFICHES}{r['poster_path']}" if r.get("poster_path") else None,
        })
    return candidats


def _acteurs(credits: dict) -> list[dict]:
    return [{"nom": a["name"], "personnage": a.get("character") or ""}
            for a in credits.get("cast", [])[:NB_ACTEURS]]


def fiche_tmdb(tmdb_id: int, type_: str, saison: int | None = None, episode: int | None = None) -> dict:
    """Métadonnées en français : synopsis, personnages, acteurs (F5)."""
    if type_ == "serie":
        d = _appel_tmdb(f"/tv/{tmdb_id}", append_to_response="credits")
        fiche = {
            "titre": d.get("name"),
            "titre_original": d.get("original_name"),
            "annee": _annee(d.get("first_air_date")),
            "synopsis": d.get("overview") or "",
            "realisation": ", ".join(c["name"] for c in d.get("created_by", [])),
            "acteurs": _acteurs(d.get("credits", {})),
        }
        if saison and episode:
            e = _appel_tmdb(f"/tv/{tmdb_id}/season/{saison}/episode/{episode}", append_to_response="credits")
            fiche["titre_episode"] = e.get("name")
            fiche["synopsis_episode"] = e.get("overview") or ""
            fiche["acteurs"] += [a for a in _acteurs({"cast": e.get("guest_stars", [])})
                                 if a not in fiche["acteurs"]][:4]
    else:
        d = _appel_tmdb(f"/movie/{tmdb_id}", append_to_response="credits")
        fiche = {
            "titre": d.get("title"),
            "titre_original": d.get("original_title"),
            "annee": _annee(d.get("release_date")),
            "synopsis": d.get("overview") or "",
            "realisation": ", ".join(c["name"] for c in d.get("credits", {}).get("crew", []) if c.get("job") == "Director"),
            "acteurs": _acteurs(d.get("credits", {})),
        }
    affiche = d.get("poster_path")
    return fiche | {
        "tmdb_id": tmdb_id, "type": type_, "saison": saison, "episode": episode,
        "affiche": f"{URL_AFFICHES}{affiche}" if affiche else None,
        "source": "TMDb",
    }


def identifier(film: Path, correction: dict | None = None, forcer: bool = False) -> dict:
    """Renvoie {devine, candidats, fiche, avertissement}.

    `correction` (F6) contient ce que l'utilisateur a saisi ou choisi :
    titre, annee, type, saison, episode, et éventuellement tmdb_id.
    """
    if not forcer and not correction:
        en_cache = cache.lire(film, "identification")
        if en_cache:
            return en_cache

    devine = deviner(film)
    recherche = devine | {k: v for k, v in (correction or {}).items() if v not in (None, "")}
    for cle in ("annee", "saison", "episode", "tmdb_id"):
        if recherche.get(cle) is not None:
            recherche[cle] = int(recherche[cle])

    # Sans TMDb, la fiche se limite à ce qu'on a deviné ou saisi : l'application reste utilisable.
    fiche = {k: recherche.get(k) for k in ("titre", "annee", "type", "saison", "episode")} | {
        "source": "nom du fichier" if not correction else "saisie", "synopsis": "", "acteurs": []}
    candidats, avertissement = [], None
    try:
        candidats = chercher_candidats(recherche["titre"], recherche.get("annee"), recherche["type"])
        if not candidats and recherche.get("annee"):  # l'année du fichier est parfois fausse
            candidats = chercher_candidats(recherche["titre"], None, recherche["type"])
        tmdb_id = recherche.get("tmdb_id") or (candidats[0]["tmdb_id"] if candidats else None)
        if tmdb_id:
            fiche = fiche_tmdb(tmdb_id, recherche["type"], recherche.get("saison"), recherche.get("episode"))
        else:
            avertissement = f"Aucun résultat TMDb pour « {recherche['titre']} ». Corrigez le titre si besoin."
    except ErreurTMDb as e:
        avertissement = str(e)
    except requests.RequestException as e:
        avertissement = f"TMDb injoignable ({e.__class__.__name__}) : vérifiez la connexion Internet."

    resultat = {"devine": devine, "candidats": candidats, "fiche": fiche, "avertissement": avertissement}
    cache.ecrire(film, "identification", resultat)
    return resultat


def nom_complet(fiche: dict) -> str:
    """« Breaking Bad (2008), saison 1, épisode 1 « Pilot » »."""
    nom = fiche.get("titre") or "?"
    if fiche.get("titre_original") and fiche["titre_original"] != nom:
        nom += f" / {fiche['titre_original']}"
    if fiche.get("annee"):
        nom += f" ({fiche['annee']})"
    if fiche.get("type") == "serie" and fiche.get("saison"):
        nom += f", saison {fiche['saison']}, épisode {fiche.get('episode')}"
        if fiche.get("titre_episode"):
            nom += f" « {fiche['titre_episode']} »"
    return nom

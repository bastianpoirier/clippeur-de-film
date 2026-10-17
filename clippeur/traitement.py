"""Le parcours complet d'un film, d'un seul tenant : identification, langue, transcription,
citations Wikiquote, proposition des extraits (et export pour le traitement automatique).

Utilisé par la page (un film choisi à la main) et par la file d'attente (dossier « à traiter », saisons).
"""

from pathlib import Path
from typing import Callable

from clippeur.export import exporter
from clippeur.extraits import proposer
from clippeur.identification import identifier
from clippeur.recherche import recherche_en_cache, rechercher
from clippeur.sous_titres import LANGUES, langue_audio
from clippeur.transcription import LANGUE_PAR_DEFAUT, MODELE_PAR_DEFAUT, Suivi, transcrire

LANGUES_LISIBLES = {"fr": "français", "en": "anglais"}
NOMBRE_MAX = 30


def choisir_langue(film: Path, demandee: str | None) -> str:
    """La langue choisie par l'utilisateur, sinon celle de la piste audio du fichier."""
    if demandee in LANGUES:
        return demandee
    return langue_audio(film) or LANGUE_PAR_DEFAUT


def analyser_film(
    film: Path,
    suivi: Suivi,
    langue: str | None = None,
    modele: str = MODELE_PAR_DEFAUT,
    nombre: int = 10,
    avec_sons: bool = True,
    etape: Callable[[str, dict], None] = lambda nom, resultat: None,
) -> dict:
    """Enchaîne toutes les étapes ; `etape(nom, résultat)` est appelé dès qu'un résultat est prêt."""
    suivi("Identification du film...", None)
    identification = identifier(film)
    etape("identification", identification)

    langue = choisir_langue(film, langue)
    suivi(f"Langue des dialogues : {LANGUES_LISIBLES[langue]}.", None)
    transcription = transcrire(film, modele=modele or MODELE_PAR_DEFAUT, langue=langue, suivi=suivi)
    etape("transcription", transcription)

    # Une recherche déjà faite garde les choix de l'utilisateur (citations cochées, page choisie).
    recherche = recherche_en_cache(film, langue) or rechercher(film, identification["fiche"], transcription, suivi)
    etape("recherche", recherche)

    proposition = proposer(film, langue=langue, nombre=max(1, min(int(nombre), NOMBRE_MAX)), suivi=suivi,
                           modele=modele or MODELE_PAR_DEFAUT, avec_sons=avec_sons)
    etape("proposition", proposition)
    return {"identification": identification, "transcription": transcription,
            "recherche": recherche, "proposition": proposition}


def traiter_film(film: Path, reglages: dict, suivi: Suivi) -> dict:
    """Traitement automatique : analyse, puis export de tous les extraits proposés avec le montage choisi."""
    resultat = analyser_film(film, suivi, langue=reglages.get("langue"), nombre=reglages.get("nombre", 5),
                             avec_sons=reglages.get("avec_sons", True))
    extraits = resultat["proposition"]["extraits"]
    exports = exporter(film, extraits, reglages["montage"], suivi) if extraits else []
    return resultat | {"exports": exports}

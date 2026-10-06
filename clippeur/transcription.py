"""Transcription horodatée des dialogues d'un film.

Ordre de priorité, du plus rapide au plus lent :
1. fichier .srt placé à côté du film ;
2. piste de sous-titres intégrée au fichier ;
3. reconnaissance vocale locale avec Whisper (sur le processeur, sans carte graphique).
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

from clippeur import cache
from clippeur.segments import Segment, format_horodatage
from clippeur.sous_titres import extraire_piste_integree, trouver_srt_adjacent
from clippeur.srt import lire_fichier_srt

MODELE_PAR_DEFAUT = "small"
LANGUE_PAR_DEFAUT = "fr"
FREQUENCE_WHISPER = 16000  # Whisper attend du son mono à 16 kHz

# Fonction appelée pour signaler l'avancement : (message, pourcentage ou None).
Suivi = Callable[[str, float | None], None]


class FilmIllisible(Exception):
    """Le fichier n'est pas une vidéo lisible (fichier abîmé ou téléchargement pas terminé)."""


def verifier_lisible(film: Path) -> None:
    resultat = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(film)],
        capture_output=True, text=True, errors="replace",
    )
    if resultat.returncode != 0:
        raise FilmIllisible(
            f"Impossible de lire « {film.name} » : ce n'est pas une vidéo valide. "
            "Le fichier est peut-être abîmé, ou son téléchargement n'est pas terminé."
        )


def afficher_dans_terminal(message: str, pourcentage: float | None) -> None:
    if pourcentage is None:
        print(message)
    else:
        fin = "\n" if pourcentage >= 100 else ""
        print(f"\r  {pourcentage:5.1f} %  {message}".ljust(70), end=fin, flush=True)


def extraire_audio(film: Path) -> "numpy.ndarray":
    """Décode la bande-son du film avec FFmpeg, au format attendu par Whisper.

    Pour un film de 2 h, cela occupe environ 460 Mo de mémoire.
    """
    import numpy

    resultat = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(film), "-map", "0:a:0", "-vn",
         "-ac", "1", "-ar", str(FREQUENCE_WHISPER), "-f", "s16le", "-"],
        capture_output=True, check=True,
    )
    return numpy.frombuffer(resultat.stdout, numpy.int16).astype(numpy.float32) / 32768.0


def transcrire_avec_whisper(film: Path, modele: str, langue: str, suivi: Suivi) -> list[Segment]:
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel  # import lent, fait seulement si nécessaire

    suivi("Extraction de la bande-son...", None)
    audio = extraire_audio(film)
    suivi(f"Chargement du modèle Whisper « {modele} » (téléchargé au premier lancement)...", None)
    whisper = WhisperModel(modele, device="cpu", compute_type="int8")
    morceaux, info = whisper.transcribe(audio, language=langue, vad_filter=True)

    segments = []
    depart = time.monotonic()
    for morceau in morceaux:
        texte = morceau.text.strip()
        if texte:
            segments.append(Segment(round(morceau.start, 2), round(morceau.end, 2), texte))
        pourcentage = min(99.9, morceau.end / info.duration * 100) if info.duration else 0
        ecoule = format_horodatage(time.monotonic() - depart)
        suivi(f"{format_horodatage(morceau.end)} du film transcrit, {ecoule} écoulé", pourcentage)
    # Le dernier morceau de dialogue finit souvent avant la fin du film : on termine à 100 %.
    suivi(f"terminé en {format_horodatage(time.monotonic() - depart)}", 100)
    return segments


def transcrire(
    film: Path,
    modele: str = MODELE_PAR_DEFAUT,
    langue: str = LANGUE_PAR_DEFAUT,
    forcer: bool = False,
    suivi: Suivi = afficher_dans_terminal,
) -> dict:
    """Renvoie la transcription du film, depuis le cache si elle a déjà été faite."""
    if not forcer:
        en_cache = cache.lire(film, f"transcription_{langue}")
        if en_cache:
            suivi("Transcription déjà faite, lecture depuis le cache.", None)
            return en_cache

    verifier_lisible(film)
    srt = trouver_srt_adjacent(film, langue)
    if srt:
        suivi(f"Sous-titres trouvés : {srt.name}", None)
        source, segments = f"fichier {srt.name}", lire_fichier_srt(srt)
    else:
        suivi("Recherche d'une piste de sous-titres dans le fichier...", None)
        segments = extraire_piste_integree(film, langue)
        if segments:
            suivi("Piste de sous-titres trouvée dans le fichier.", None)
            source = "piste intégrée"
        else:
            suivi("Aucun sous-titre dans cette langue : transcription avec Whisper. Cela peut prendre un moment.", None)
            source, segments = f"whisper {modele}", transcrire_avec_whisper(film, modele, langue, suivi)

    resultat = {
        "film": film.name,
        "langue": langue,
        "source": source,
        "segments": [s.vers_dict() for s in segments],
    }
    cache.ecrire(film, f"transcription_{langue}", resultat)
    return resultat

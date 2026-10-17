"""Recherche des sous-titres d'un film dans une langue donnée : fichier .srt à côté, ou piste intégrée."""

import json
import subprocess
from pathlib import Path

from clippeur.segments import Segment
from clippeur.srt import lire_fichier_srt, lire_srt

# Pour chaque langue : suffixes possibles du fichier .srt et codes de langue des pistes.
LANGUES = {
    "fr": {"suffixes": ["", ".fr", ".fre", ".fra", ".french", ".vf"], "codes": {"fre", "fra", "fr", "french"}},
    "en": {"suffixes": ["", ".en", ".eng", ".english", ".vo"], "codes": {"eng", "en", "english"}},
}
# Pistes texte convertibles en SRT. Les sous-titres en image (PGS des Blu-ray,
# VobSub des DVD) ne peuvent pas être lus sans reconnaissance de caractères.
_CODECS_TEXTE = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}


def langue_audio(film: Path) -> str | None:
    """Langue de la première piste audio (« fr » ou « en »), d'après les informations du fichier."""
    resultat = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream_tags=language",
         "-of", "csv=p=0", str(film)],
        capture_output=True, text=True, errors="replace",
    )
    code = resultat.stdout.strip().lower()
    return next((langue for langue, infos in LANGUES.items() if code in infos["codes"]), None)


def trouver_srt_adjacent(film: Path, langue: str = "fr") -> Path | None:
    """Cherche film.srt, film.fr.srt (ou film.en.srt...) dans le même dossier que le film."""
    for suffixe in LANGUES[langue]["suffixes"]:
        candidat = film.with_name(f"{film.stem}{suffixe}.srt")
        if candidat.is_file():
            return candidat
    return None


def _pistes_sous_titres(film: Path) -> list[dict]:
    resultat = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "s",
            "-show_entries", "stream=index,codec_name:stream_tags=language:stream_disposition=forced",
            "-of", "json", str(film),
        ],
        capture_output=True, text=True, check=True,
    )
    return json.loads(resultat.stdout).get("streams", [])


def choisir_piste(pistes: list[dict], langue: str = "fr") -> dict | None:
    """Choisit la piste complète dans la langue voulue, à défaut une piste sans langue indiquée.

    Les pistes « forcées » sont ignorées : elles ne traduisent que quelques passages.
    """
    utilisables = [
        p for p in pistes
        if p.get("codec_name") in _CODECS_TEXTE and not p.get("disposition", {}).get("forced")
    ]
    for p in utilisables:
        if p.get("tags", {}).get("language", "").lower() in LANGUES[langue]["codes"]:
            return p
    for p in utilisables:
        if not p.get("tags", {}).get("language") or p["tags"]["language"] == "und":
            return p
    return None


def extraire_piste_integree(film: Path, langue: str = "fr") -> list[Segment] | None:
    """Extrait la piste de sous-titres intégrée au fichier dans la langue voulue, s'il y en a une."""
    piste = choisir_piste(_pistes_sous_titres(film), langue)
    if piste is None:
        return None
    resultat = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(film), "-map", f"0:{piste['index']}", "-f", "srt", "-"],
        capture_output=True, check=True,
    )
    segments = lire_srt(resultat.stdout.decode("utf-8", errors="replace"))
    return segments or None

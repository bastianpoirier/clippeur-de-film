"""Lecture des fichiers de sous-titres au format SRT."""

import re
from pathlib import Path

from clippeur.segments import Segment

_HORAIRE = re.compile(
    r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})"
)
# Balises de mise en forme : <i>, </font>, {\an8}...
_BALISES = re.compile(r"<[^>]+>|\{[^}]*\}")


def _secondes(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def lire_srt(contenu: str) -> list[Segment]:
    """Transforme le texte d'un fichier SRT en liste de segments."""
    segments = []
    blocs = re.split(r"\n\s*\n", contenu.replace("\r\n", "\n").lstrip("﻿"))
    for bloc in blocs:
        lignes = bloc.strip().split("\n")
        for i, ligne in enumerate(lignes):
            horaire = _HORAIRE.search(ligne)
            if horaire:
                texte = " ".join(_BALISES.sub("", l).strip() for l in lignes[i + 1 :])
                texte = " ".join(texte.split())
                if texte:
                    g = horaire.groups()
                    segments.append(Segment(_secondes(*g[:4]), _secondes(*g[4:]), texte))
                break
    segments.sort(key=lambda seg: seg.debut)
    return segments


def lire_fichier_srt(chemin: Path) -> list[Segment]:
    """Lit un fichier SRT. Les sous-titres français sont souvent en Windows-1252."""
    brut = chemin.read_bytes()
    try:
        contenu = brut.decode("utf-8-sig")
    except UnicodeDecodeError:
        contenu = brut.decode("cp1252", errors="replace")
    return lire_srt(contenu)

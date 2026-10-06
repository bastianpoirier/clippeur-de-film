"""Cache des résultats intermédiaires, pour ne pas refaire une transcription déjà faite."""

import hashlib
import json
import re
from pathlib import Path

DOSSIER_CACHE = Path(__file__).resolve().parent.parent / "cache"


def dossier_du_film(film: Path) -> Path:
    """Un dossier de cache par film.

    La clé utilise le nom, la taille et la date de modification du fichier :
    c'est instantané, alors que lire plusieurs Go pour calculer une empreinte prendrait du temps.
    """
    info = film.stat()
    empreinte = hashlib.sha1(f"{film.name}|{info.st_size}|{info.st_mtime_ns}".encode()).hexdigest()[:10]
    nom = re.sub(r"[^\w-]+", "_", film.stem)[:40]
    return DOSSIER_CACHE / f"{nom}_{empreinte}"


def lire(film: Path, nom: str) -> dict | None:
    chemin = dossier_du_film(film) / f"{nom}.json"
    if not chemin.is_file():
        return None
    return json.loads(chemin.read_text(encoding="utf-8"))


def ecrire(film: Path, nom: str, donnees: dict) -> Path:
    dossier = dossier_du_film(film)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.json"
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin

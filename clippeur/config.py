"""Clé d'API TMDb (gratuite), lue dans le fichier .env à la racine du projet (exclu de Git)."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ENV = RACINE / ".env"


def recharger() -> None:
    """Relit .env : permet d'ajouter une clé sans redémarrer l'application."""
    load_dotenv(FICHIER_ENV, override=True)


def cle_tmdb() -> str | None:
    recharger()
    return os.environ.get("TMDB_API_KEY") or None


def enregistrer_cle_tmdb(cle: str) -> None:
    """Écrit la clé dans .env, en remplaçant l'ancienne s'il y en a une."""
    lignes = FICHIER_ENV.read_text(encoding="utf-8").splitlines() if FICHIER_ENV.exists() else []
    lignes = [l for l in lignes if not re.match(r"\s*TMDB_API_KEY\s*=", l)]
    lignes.append(f"TMDB_API_KEY={cle}")
    FICHIER_ENV.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    os.environ["TMDB_API_KEY"] = cle


def etat_des_cles() -> dict:
    return {"tmdb": cle_tmdb() is not None}

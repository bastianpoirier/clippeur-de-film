"""Analyse de l'image et du son : changements de plan et volume sonore seconde par seconde."""

import math
import re
import subprocess
import tempfile
from pathlib import Path

from clippeur import cache
from clippeur.transcription import Suivi

SEUIL_CHANGEMENT_PLAN = 0.3  # 0 = images identiques, 1 = images totalement différentes
FREQUENCE_ANALYSE_SON = 8000  # suffisant pour mesurer un volume, et 2 fois plus léger que pour Whisper


def duree_video(film: Path) -> float:
    resultat = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(film)],
        capture_output=True, text=True, check=True,
    )
    return float(resultat.stdout.strip())


def detecter_plans(film: Path, suivi: Suivi) -> list[float]:
    """Renvoie les instants (en secondes) où l'image change de plan.

    L'image est réduite à 192 pixels de large : c'est assez pour repérer un changement
    de plan, et beaucoup plus rapide sur un processeur sans carte graphique.
    """
    en_cache = cache.lire(film, "plans")
    if en_cache:
        return en_cache["plans"]

    duree = duree_video(film)
    with tempfile.TemporaryDirectory() as dossier, open(Path(dossier) / "erreurs.txt", "w+", errors="replace") as erreurs:
        # FFmpeg n'accepte pas les « : » de « C:\ » dans les options de filtre : on passe un nom relatif.
        # Ses messages d'erreur vont dans un fichier : un tuyau non lu pourrait se remplir et bloquer FFmpeg.
        processus = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-nostats", "-i", str(film), "-an", "-sn",
             "-vf", f"scale=192:-2,select='gt(scene,{SEUIL_CHANGEMENT_PLAN})',metadata=print:file=plans.txt",
             "-progress", "pipe:1", "-f", "null", "-"],
            cwd=dossier, stdout=subprocess.PIPE, stderr=erreurs, text=True, errors="replace",
        )
        for ligne in processus.stdout:
            if ligne.startswith("out_time_us=") and ligne.strip() != "out_time_us=N/A":
                secondes = int(ligne.split("=")[1]) / 1_000_000
                suivi("Détection des changements de plan", min(99.9, secondes / duree * 100))
        if processus.wait() != 0:
            erreurs.seek(0)
            raise subprocess.CalledProcessError(processus.returncode, processus.args, stderr=erreurs.read()[-2000:])
        texte = (Path(dossier) / "plans.txt").read_text(errors="replace") if (Path(dossier) / "plans.txt").exists() else ""
    suivi("Détection des changements de plan", 100)

    plans = [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", texte)]
    cache.ecrire(film, "plans", {"plans": plans})
    return plans


def mesurer_volume(film: Path) -> list[float]:
    """Volume sonore de chaque seconde du film, en décibels (0 = le maximum possible)."""
    en_cache = cache.lire(film, "volume")
    if en_cache:
        return en_cache["volume"]

    import numpy

    resultat = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(film), "-map", "0:a:0", "-vn",
         "-ac", "1", "-ar", str(FREQUENCE_ANALYSE_SON), "-f", "s16le", "-"],
        capture_output=True, check=True,
    )
    son = numpy.frombuffer(resultat.stdout, numpy.int16).astype(numpy.float32) / 32768.0
    nb_secondes = len(son) // FREQUENCE_ANALYSE_SON
    par_seconde = son[: nb_secondes * FREQUENCE_ANALYSE_SON].reshape(nb_secondes, FREQUENCE_ANALYSE_SON)
    rms = numpy.sqrt(numpy.mean(par_seconde ** 2, axis=1))
    volume = [round(20 * math.log10(max(float(v), 1e-5)), 1) for v in rms]

    cache.ecrire(film, "volume", {"volume": volume})
    return volume

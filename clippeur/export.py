"""Découpe des extraits dans le film et export en MP4."""

import json
import subprocess
from pathlib import Path

from clippeur.segments import format_horodatage
from clippeur.selection import nom_de_fichier
from clippeur.transcription import Suivi

DOSSIER_SORTIE = Path(__file__).resolve().parent.parent / "output"

# Les films ont des dialogues mixés bas (souvent -25 à -30 LUFS) : on remonte le volume au niveau
# visé par TikTok, Instagram et YouTube (-14 LUFS), sans dépasser -1,5 dB en crête.
NORMALISATION_SON = ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000"]


def dossier_de_sortie(film: Path) -> Path:
    return DOSSIER_SORTIE / nom_de_fichier(film.stem, longueur_max=60)


def creer_miniature(film: Path, instant: float, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(instant), "-i", str(film),
         "-frames:v", "1", "-vf", "scale=320:-2", str(destination)],
        capture_output=True, check=True,
    )


def creer_apercu(film: Path, extrait: dict, destination: Path) -> None:
    """Version légère d'un extrait (360p) pour le regarder dans la page avant de l'exporter.

    Le navigateur ne sait pas lire tous les formats de film (HEVC 10 bits, MKV...) :
    on réencode en H.264, le plus vite possible, en sacrifiant la qualité.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaire = destination.with_suffix(".tmp.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-ss", str(extrait["debut"]), "-i", str(film), "-t", str(extrait["fin"] - extrait["debut"]),
         "-map", "0:v:0", "-map", "0:a:0", "-sn", "-vf", "scale=-2:360",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
         *NORMALISATION_SON, "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(temporaire)],
        capture_output=True, check=True,
    )
    # Renommage à la fin seulement : un aperçu interrompu ne passe jamais pour un aperçu complet.
    temporaire.replace(destination)


def exporter_extrait(film: Path, extrait: dict, destination: Path, suivi_clip=None) -> None:
    """Découpe un extrait et le réencode en H.264 + AAC (lisible partout, y compris les réseaux sociaux).

    Le réencodage permet de couper à l'image près. `-pix_fmt yuv420p` convertit les vidéos
    10 bits, que les navigateurs et les téléphones ne savent pas toujours lire.
    """
    duree = extrait["fin"] - extrait["debut"]
    processus = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-nostats", "-y",
         "-ss", str(extrait["debut"]), "-i", str(film), "-t", str(duree),
         "-map", "0:v:0", "-map", "0:a:0", "-sn",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         *NORMALISATION_SON, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
         "-progress", "pipe:1", str(destination)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
    )
    for ligne in processus.stdout:
        if suivi_clip and ligne.startswith("out_time_us=") and ligne.strip() != "out_time_us=N/A":
            suivi_clip(min(1.0, int(ligne.split("=")[1]) / 1_000_000 / duree))
    if processus.wait() != 0:
        raise subprocess.CalledProcessError(processus.returncode, processus.args, stderr=processus.stderr.read())


def exporter(film: Path, extraits: list[dict], suivi: Suivi) -> list[dict]:
    """Exporte les extraits dans output/<film>/ et y écrit un récapitulatif JSON."""
    dossier = dossier_de_sortie(film)
    dossier.mkdir(parents=True, exist_ok=True)
    base = nom_de_fichier(film.stem, longueur_max=30)

    fichiers = []
    for rang, extrait in enumerate(extraits):
        nom = f"{base}_{extrait['numero']:02d}_{nom_de_fichier(extrait['titre'])}.mp4"
        destination = dossier / nom

        def suivi_clip(avancement: float, rang: int = rang) -> None:
            suivi(f"Export de l'extrait {rang + 1}/{len(extraits)}", (rang + avancement) / len(extraits) * 100)

        suivi(f"Export de l'extrait {rang + 1}/{len(extraits)} : {nom}", None)
        exporter_extrait(film, extrait, destination, suivi_clip)
        fichiers.append(extrait | {"fichier": nom})

    recapitulatif = {
        "film": film.name,
        "extraits": [
            f | {"debut_lisible": format_horodatage(f["debut"]), "fin_lisible": format_horodatage(f["fin"])}
            for f in fichiers
        ],
    }
    (dossier / "extraits.json").write_text(json.dumps(recapitulatif, ensure_ascii=False, indent=2), encoding="utf-8")
    suivi(f"{len(fichiers)} extraits exportés dans {dossier}", 100)
    return fichiers

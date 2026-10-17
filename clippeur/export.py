"""Découpe des extraits dans le film, mise en forme (format vertical, musique) et export en MP4."""

import json
import subprocess
import tempfile
from pathlib import Path

from clippeur.segments import format_horodatage
from clippeur.selection import nom_de_fichier
from clippeur.transcription import Suivi

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_SORTIE = RACINE / "output"
DOSSIER_MUSIQUES = RACINE / "musiques"
EXTENSIONS_MUSIQUE = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}

# Les films ont des dialogues mixés bas (souvent -25 à -30 LUFS) : on remonte le volume au niveau
# visé par TikTok, Instagram et YouTube (-14 LUFS), sans dépasser -1,5 dB en crête.
NORMALISATION_SON = "loudnorm=I=-14:TP=-1.5:LRA=11"

# Format vertical 9:16 (F24), en 1080×1920 comme TikTok, Instagram Reels et YouTube Shorts.
LARGEUR_VERTICALE, HAUTEUR_VERTICALE = 1080, 1920
FORMATS = {
    "original": "format et résolution d'origine",
    "flou": "vertical 9:16, film entier sur fond flou",
    "recadre": "vertical 9:16, recadré au centre",
}

VOLUME_MUSIQUE_DEFAUT = 20  # en % : un fond sonore discret, sous les dialogues
FONDU_MUSIQUE = 2.0  # secondes de fondu au début et à la fin de la musique

MONTAGE_PAR_DEFAUT = {"format": "original", "musique": None, "volume_musique": VOLUME_MUSIQUE_DEFAUT}


def dossier_de_sortie(film: Path) -> Path:
    return DOSSIER_SORTIE / nom_de_fichier(film.stem, longueur_max=60)


def lister_musiques() -> list[str]:
    """Les morceaux de la banque de musiques (dossier « musiques » du projet), par ordre alphabétique."""
    if not DOSSIER_MUSIQUES.is_dir():
        return []
    return sorted((f.name for f in DOSSIER_MUSIQUES.iterdir()
                   if f.is_file() and f.suffix.lower() in EXTENSIONS_MUSIQUE), key=str.lower)


def montage_valide(montage: dict | None) -> dict:
    """Complète et vérifie les réglages de montage envoyés par la page."""
    m = MONTAGE_PAR_DEFAUT | {k: v for k, v in (montage or {}).items() if v is not None}
    if m["format"] not in FORMATS:
        raise ValueError(f"Format inconnu : {m['format']}")
    # Seul un nom de la banque est accepté : pas de chemin vers un autre dossier du PC.
    if m["musique"] and m["musique"] not in lister_musiques():
        raise ValueError(f"Musique introuvable dans la banque : {m['musique']}")
    m["volume_musique"] = max(0, min(int(m["volume_musique"]), 100))
    return m


# Aperçus : assez grands pour juger la netteté et le cadrage dans la page, mais plus rapides que l'export.
VERSION_APERCU = 2  # à augmenter quand le rendu des aperçus change : les anciens, en cache, sont refaits
HAUTEUR_APERCU_ORIGINAL = 720
HAUTEUR_APERCU_VERTICAL = 1280
# Lanczos : le redimensionnement le plus fin de FFmpeg (le « bicubic » par défaut adoucit l'image).
ECHELLE = "flags=lanczos"
# Le recadrage vertical agrandit beaucoup l'image (×2,7 pour un film en 720p) : un léger renforcement
# de la netteté, sur la luminosité seulement, compense le flou de l'agrandissement sans faire de halos.
NETTETE = "unsharp=5:5:0.6:5:5:0.0"


def _filtre_video(format_: str, apercu: bool) -> str:
    """Filtre FFmpeg de l'image ; l'aperçu garde le même cadrage, en plus petit."""
    if format_ == "original":
        # Jamais agrandi : un film plus petit que 720p garde sa taille.
        return f"scale=-2:'min(ih,{HAUTEUR_APERCU_ORIGINAL})':{ECHELLE}" if apercu else "null"
    l, h = LARGEUR_VERTICALE, HAUTEUR_VERTICALE
    if apercu:
        l, h = round(l * HAUTEUR_APERCU_VERTICAL / h / 2) * 2, HAUTEUR_APERCU_VERTICAL
    if format_ == "recadre":
        return f"scale=-2:{h}:{ECHELLE},crop={l}:{h},{NETTETE}"
    # Fond flou : l'image agrandie et floutée remplit l'écran, le film entier est posé au milieu.
    # Le flou est calculé sur une image 4 fois plus petite, puis agrandie : même rendu, 10 fois plus rapide.
    pl, ph = round(l / 8) * 2, round(h / 8) * 2
    return (f"split=2[fond][avant];"
            f"[fond]scale={pl}:{ph}:force_original_aspect_ratio=increase,crop={pl}:{ph},boxblur=6:2,"
            f"scale={l}:{h}[flou];"
            f"[avant]scale={l}:-2:{ECHELLE}[net];[flou][net]overlay=(W-w)/2:(H-h)/2")


def _commande(film: Path, debut: float, fin: float, montage: dict, destination: Path, apercu: bool) -> list[str]:
    """Commande FFmpeg qui découpe, met en forme et encode un extrait."""
    duree = fin - debut
    # « -t » avant « -i » : la durée s'applique au film (placée après, elle viserait l'entrée suivante, la musique).
    entrees = ["-ss", str(debut), "-t", str(duree), "-i", str(film)]
    video = f"[0:v:0]{_filtre_video(montage['format'], apercu)},format=yuv420p[v]"
    if montage["musique"]:
        # La musique tourne en boucle si elle est plus courte que l'extrait, avec un fondu au début et à la fin.
        entrees += ["-stream_loop", "-1", "-i", str(DOSSIER_MUSIQUES / montage["musique"])]
        fin_fondu = max(0.0, duree - FONDU_MUSIQUE)
        son = (f"[1:a]atrim=0:{duree},volume={montage['volume_musique'] / 100},"
               f"afade=t=in:d={FONDU_MUSIQUE},afade=t=out:st={fin_fondu}:d={FONDU_MUSIQUE}[musique];"
               f"[0:a:0][musique]amix=inputs=2:duration=first:normalize=0,{NORMALISATION_SON}[a]")
    else:
        son = f"[0:a:0]{NORMALISATION_SON}[a]"
    # CRF : plus le nombre est bas, meilleure est l'image (18 est quasiment indiscernable de la source).
    # Un « preset » plus lent compresse mieux à qualité égale ; « film » préserve le grain et les détails.
    qualite = (["-preset", "veryfast", "-crf", "23", "-b:a", "128k"] if apercu
               else ["-preset", "medium", "-crf", "18", "-tune", "film", "-profile:v", "high", "-b:a", "192k"])
    return ["ffmpeg", "-v", "error", "-nostats", "-y",
            # Conversions automatiques (10 bits → 8 bits, couleurs) faites avec précision, sans adoucir l'image.
            "-sws_flags", "lanczos+accurate_rnd+full_chroma_int", *entrees,
            "-filter_complex", f"{video};{son}", "-map", "[v]", "-map", "[a]", "-sn",
            "-c:v", "libx264", "-c:a", "aac", "-ar", "48000", *qualite,
            "-movflags", "+faststart", "-progress", "pipe:1", str(destination)]


def _lancer(commande: list[str], duree: float, suivi_clip=None) -> None:
    # Messages d'erreur dans un fichier temporaire : un tuyau non lu pourrait se remplir et bloquer FFmpeg.
    with tempfile.TemporaryFile("w+", errors="replace") as erreurs:
        processus = subprocess.Popen(commande, stdout=subprocess.PIPE, stderr=erreurs, text=True, errors="replace")
        for ligne in processus.stdout:
            if suivi_clip and ligne.startswith("out_time_us=") and ligne.strip() != "out_time_us=N/A":
                suivi_clip(min(1.0, int(ligne.split("=")[1]) / 1_000_000 / duree))
        if processus.wait() != 0:
            erreurs.seek(0)
            raise subprocess.CalledProcessError(processus.returncode, commande, stderr=erreurs.read()[-2000:])


def creer_miniature(film: Path, instant: float, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(instant), "-i", str(film),
         "-frames:v", "1", "-vf", "scale=320:-2", str(destination)],
        capture_output=True, check=True,
    )


def creer_apercu(film: Path, extrait: dict, montage: dict, destination: Path) -> None:
    """Version allégée d'un extrait (720p, ou 720×1280 en vertical), avec le même montage que l'export.

    Le navigateur ne sait pas lire tous les formats de film (HEVC 10 bits, MKV...) :
    on réencode en H.264, le plus vite possible, en sacrifiant la qualité.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaire = destination.with_suffix(".tmp.mp4")
    _lancer(_commande(film, extrait["debut"], extrait["fin"], montage, temporaire, apercu=True),
            extrait["fin"] - extrait["debut"])
    # Renommage à la fin seulement : un aperçu interrompu ne passe jamais pour un aperçu complet.
    temporaire.replace(destination)


def exporter_extrait(film: Path, extrait: dict, montage: dict, destination: Path, suivi_clip=None) -> None:
    """Découpe un extrait et l'encode en H.264 + AAC (lisible partout, y compris sur les réseaux sociaux).

    Le réencodage permet de couper à l'image près ; « yuv420p » convertit les vidéos 10 bits,
    que les navigateurs et les téléphones ne savent pas toujours lire.
    """
    _lancer(_commande(film, extrait["debut"], extrait["fin"], montage, destination, apercu=False),
            extrait["fin"] - extrait["debut"], suivi_clip)


def exporter(film: Path, extraits: list[dict], montage: dict, suivi: Suivi) -> list[dict]:
    """Exporte les extraits dans output/<film>/ et y écrit un récapitulatif JSON."""
    dossier = dossier_de_sortie(film)
    dossier.mkdir(parents=True, exist_ok=True)
    base = nom_de_fichier(film.stem, longueur_max=30)
    suffixe = "" if montage["format"] == "original" else "_vertical"

    fichiers = []
    for rang, extrait in enumerate(extraits):
        nom = f"{base}_{extrait['numero']:02d}_{nom_de_fichier(extrait['titre'])}{suffixe}.mp4"

        def suivi_clip(avancement: float, rang: int = rang) -> None:
            suivi(f"Export de l'extrait {rang + 1}/{len(extraits)}", (rang + avancement) / len(extraits) * 100)

        suivi(f"Export de l'extrait {rang + 1}/{len(extraits)} : {nom}", None)
        exporter_extrait(film, extrait, montage, dossier / nom, suivi_clip)
        fichiers.append(extrait | {"fichier": nom})

    recapitulatif = {
        "film": film.name,
        "montage": montage | {"format_lisible": FORMATS[montage["format"]]},
        "extraits": [
            f | {"debut_lisible": format_horodatage(f["debut"]), "fin_lisible": format_horodatage(f["fin"])}
            for f in fichiers
        ],
    }
    (dossier / "extraits.json").write_text(json.dumps(recapitulatif, ensure_ascii=False, indent=2), encoding="utf-8")
    suivi(f"{len(fichiers)} extraits exportés dans {dossier}", 100)
    return fichiers

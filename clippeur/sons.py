"""Reconnaissance des sons marquants (F13) : rires, musique, cris, explosions et coups de feu.

Le modèle AST (Audio Spectrogram Transformer), entraîné sur les 527 catégories de sons d'AudioSet,
tourne en local sur le processeur, gratuitement. Sa version compressée (90 Mo) est téléchargée
une seule fois. Le film est analysé par tranches de 10 secondes.
"""

import json
import math
import os
from pathlib import Path

import numpy as np

from clippeur import cache
from clippeur.transcription import FREQUENCE_WHISPER, Suivi, extraire_audio

DEPOT_MODELE = "onnx-community/ast-finetuned-audioset-10-10-0.4593-ONNX"
FICHIER_MODELE = "onnx/model_quantized.onnx"
DUREE_TRANCHE = 10  # secondes analysées d'un coup ; le modèle accepte jusqu'à 10,24 s
TRANCHES_PAR_LOT = 8

# Spectrogramme attendu par AST : celui de Kaldi, 128 bandes de fréquence, une colonne toutes les 10 ms.
NB_BANDES, NB_COLONNES = 128, 1024
LONGUEUR_FENETRE, PAS_FENETRE, TAILLE_FFT = 400, 160, 512  # 25 ms et 10 ms à 16 kHz
MOYENNE_AST, ECART_TYPE_AST = -4.2677393, 4.5689974  # normalisation utilisée à l'entraînement

# Catégories d'AudioSet regroupées en quatre familles de sons utiles pour repérer un moment fort.
FAMILLES = {
    "rires": ["Laughter", "Giggle", "Snicker", "Belly laugh", "Chuckle, chortle", "Baby laughter"],
    "cris": ["Screaming", "Shout", "Yell", "Battle cry", "Children shouting", "Crying, sobbing", "Wail, moan"],
    "explosions": ["Explosion", "Gunshot, gunfire", "Machine gun", "Fusillade", "Artillery fire", "Boom",
                   "Burst, pop", "Eruption", "Smash, crash", "Glass"],
    "musique": ["Music"],
}
NOMS_FAMILLES = {"rires": "rires", "cris": "cris", "explosions": "explosions ou coups de feu", "musique": "musique"}


def _frequence_vers_mel(f):
    return 1127.0 * np.log(1.0 + np.asarray(f) / 700.0)


def _bandes_mel() -> np.ndarray:
    """Filtres triangulaires de Kaldi sur l'échelle mel, de 20 Hz à 8 kHz."""
    nb_frequences = TAILLE_FFT // 2
    mel_bas, mel_haut = _frequence_vers_mel(20.0), _frequence_vers_mel(FREQUENCE_WHISPER / 2)
    pas = (mel_haut - mel_bas) / (NB_BANDES + 1)
    mels = _frequence_vers_mel(np.arange(nb_frequences) * FREQUENCE_WHISPER / TAILLE_FFT)
    gauche = mel_bas + np.arange(NB_BANDES)[:, None] * pas
    montee = (mels[None, :] - gauche) / pas
    descente = (gauche + 2 * pas - mels[None, :]) / pas
    bandes = np.maximum(0.0, np.minimum(montee, descente))
    return np.pad(bandes, ((0, 0), (0, 1)))  # la fréquence de Nyquist n'est dans aucune bande


_BANDES = _bandes_mel()
_FENETRE_HANNING = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(LONGUEUR_FENETRE) / (LONGUEUR_FENETRE - 1))


def spectrogramme(son: np.ndarray) -> np.ndarray:
    """Spectrogramme mel logarithmique « façon Kaldi » d'une tranche, normalisé pour AST : (1024, 128)."""
    nb = max(0, 1 + (len(son) - LONGUEUR_FENETRE) // PAS_FENETRE)
    if nb == 0:
        trames = np.zeros((0, LONGUEUR_FENETRE), np.float32)
    else:
        indices = np.arange(LONGUEUR_FENETRE)[None, :] + PAS_FENETRE * np.arange(nb)[:, None]
        trames = son[indices].astype(np.float64)
        trames -= trames.mean(axis=1, keepdims=True)  # retrait de la composante continue
        trames[:, 1:] -= 0.97 * trames[:, :-1]  # préaccentuation
        trames[:, 0] -= 0.97 * trames[:, 0]
        trames *= _FENETRE_HANNING
    puissance = np.abs(np.fft.rfft(trames, n=TAILLE_FFT)) ** 2
    log_mel = np.log(np.maximum(puissance @ _BANDES.T, np.finfo(np.float32).eps))
    resultat = np.zeros((NB_COLONNES, NB_BANDES))  # complété par des zéros jusqu'à 10,24 s
    resultat[:min(nb, NB_COLONNES)] = log_mel[:NB_COLONNES]
    return ((resultat - MOYENNE_AST) / (ECART_TYPE_AST * 2)).astype(np.float32)


def _modele():
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    import onnxruntime
    from huggingface_hub import hf_hub_download

    chemin = hf_hub_download(DEPOT_MODELE, FICHIER_MODELE)
    etiquettes = json.loads(Path(hf_hub_download(DEPOT_MODELE, "config.json")).read_text(encoding="utf-8"))["id2label"]
    session = onnxruntime.InferenceSession(chemin, providers=["CPUExecutionProvider"])
    index = {nom: int(i) for i, nom in etiquettes.items()}
    familles = {f: [index[n] for n in noms if n in index] for f, noms in FAMILLES.items()}
    return session, familles


def reconnaitre_sons(film: Path, suivi: Suivi) -> dict:
    """Probabilité de chaque famille de sons, seconde par seconde : {famille: [0..1, ...]}."""
    en_cache = cache.lire(film, "sons")
    if en_cache:
        return en_cache

    suivi("Chargement du modèle de reconnaissance des sons (téléchargé au premier lancement)...", None)
    session, familles = _modele()
    son = extraire_audio(film)
    taille = DUREE_TRANCHE * FREQUENCE_WHISPER
    nb_tranches = math.ceil(len(son) / taille)
    duree = math.ceil(len(son) / FREQUENCE_WHISPER)
    resultat = {f: [0.0] * duree for f in familles}

    for premier in range(0, nb_tranches, TRANCHES_PAR_LOT):
        lot = range(premier, min(premier + TRANCHES_PAR_LOT, nb_tranches))
        entree = np.stack([spectrogramme(son[i * taille:(i + 1) * taille + 4 * PAS_FENETRE]) for i in lot])
        logits = session.run(None, {session.get_inputs()[0].name: entree})[0]
        probabilites = 1 / (1 + np.exp(-logits))
        for i, p in zip(lot, probabilites):
            for famille, indices in familles.items():
                valeur = round(float(p[indices].max()), 3)
                for s in range(i * DUREE_TRANCHE, min((i + 1) * DUREE_TRANCHE, duree)):
                    resultat[famille][s] = valeur
        suivi("Reconnaissance des sons (rires, musique, cris, explosions)", min(99.9, lot[-1] / nb_tranches * 100))
    suivi("Reconnaissance des sons (rires, musique, cris, explosions)", 100)

    cache.ecrire(film, "sons", resultat)
    return resultat

# Clippeur de film

Application locale qui analyse un film, recherche en ligne ses citations et scènes cultes, puis en extrait les meilleurs moments sous forme de clips de 1 à 2 minutes.

Statut : étape 1 (transcription horodatée). Voir [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md).

## Installation

Prérequis : Python 3.12 et FFmpeg.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Utilisation

### Interface

Double-cliquer sur `lancer.bat`, ou :

```powershell
.\.venv\Scripts\python.exe -m clippeur interface
```

La page s'ouvre dans le navigateur (http://127.0.0.1:5000). Le bouton « Choisir un film » ouvre la fenêtre Windows de choix de fichier : le film est lu là où il est, sans être copié.

### Ligne de commande

Transcrire les dialogues d'un film avec leurs horaires :

```powershell
.\.venv\Scripts\python.exe -m clippeur transcrire "C:\chemin\vers\le\film.mkv"
```

La transcription utilise, dans cet ordre :
1. un fichier de sous-titres placé à côté du film (`film.srt`, `film.fr.srt`...) ;
2. la piste de sous-titres français intégrée au fichier ;
3. sinon, la reconnaissance vocale Whisper, en local sur le processeur. Le modèle (environ 500 Mo) est téléchargé au premier lancement.

Le résultat est enregistré dans `cache/<film>/transcription.json`. Une relance lit ce cache ; `--forcer` refait la transcription.

Options :
- `--modele tiny|base|small|medium` : modèle Whisper. `small` par défaut ; `medium` est plus précis mais environ 3 fois plus lent.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

# Clippeur de film

Application locale et gratuite qui analyse un film, recherche ses citations cultes sur Wikiquote, puis en extrait les meilleurs moments sous forme de clips de 1 à 2 minutes.

Voir le [cahier des charges](CAHIER_DES_CHARGES.md).

## Installation

Prérequis : Python 3.12 et FFmpeg.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Clé TMDb (gratuite, facultative)

L'application est entièrement gratuite. Une clé [TMDb](https://www.themoviedb.org/settings/api) (gratuite) permet d'avoir la fiche complète du film en français : synopsis, acteurs, affiche. Elle se colle directement dans la page, qui la vérifie puis l'enregistre dans le fichier `.env` (exclu de Git). On peut aussi copier `.env.exemple` en `.env` et l'y écrire.

Sans clé, le film est identifié d'après le nom du fichier, et tout le reste fonctionne.

## Utilisation

### Interface

Double-cliquer sur `lancer.bat`, ou :

```powershell
.\.venv\Scripts\python.exe -m clippeur interface
```

La page s'ouvre dans le navigateur (http://127.0.0.1:5000).

1. **Film** : « Choisir un film » ouvre la fenêtre Windows de choix de fichier ; le film est lu là où il est, sans être copié. Il est identifié automatiquement (titre, année, saison et épisode pour une série), et on peut corriger si ce n'est pas le bon.
2. **Transcription** des dialogues avec leurs horaires.
3. **Citations cultes** : les citations célèbres de l'œuvre sont cherchées sur Wikiquote, puis retrouvées dans les dialogues du film. On coche celles qui doivent compter pour le choix des extraits, et on peut choisir une autre page Wikiquote si la première n'est pas la bonne.
4. **Extraits** : chaque extrait proposé s'affiche avec une miniature, la raison de son choix et ses sources ; ▶ prépare un aperçu en quelques secondes. On décoche ceux qu'on ne veut pas, puis on exporte. Les extraits sont enregistrés dans `output/<film>/`, avec un récapitulatif `extraits.json`, le son remis au niveau des réseaux sociaux.

Le choix des extraits combine les citations cultes cochées et des indices locaux (densité des dialogues, volume sonore, répliques exclamatives). Les bornes sont calées sur des changements de plan, sans couper de réplique.

### Ligne de commande

```powershell
# Transcrire les dialogues d'un film avec leurs horaires
.\.venv\Scripts\python.exe -m clippeur transcrire "C:\chemin\vers\le\film.mkv"

# Identifier le film et rechercher ses citations cultes sur Wikiquote (--page pour choisir la page)
.\.venv\Scripts\python.exe -m clippeur rechercher "C:\chemin\vers\le\film.mkv"

# Proposer des extraits, et les exporter en MP4
.\.venv\Scripts\python.exe -m clippeur extraits "C:\chemin\vers\le\film.mkv" --nombre 10 --exporter
```

La transcription utilise, dans cet ordre :
1. un fichier de sous-titres placé à côté du film (`film.srt`, `film.fr.srt`...) ;
2. la piste de sous-titres intégrée au fichier, dans la langue choisie ;
3. sinon, la reconnaissance vocale Whisper, en local sur le processeur. Le modèle (environ 500 Mo) est téléchargé au premier lancement.

Les résultats intermédiaires sont mis en cache dans `cache/<film>/` ; une relance les relit au lieu de tout refaire.

Options :
- `--langue fr|en` : langue des dialogues (`fr` par défaut). Sert à choisir les sous-titres, la langue de Whisper et celle des citations recherchées.
- `--modele tiny|base|small|medium` : modèle Whisper. `small` par défaut ; `medium` est plus précis mais environ 3 fois plus lent.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

# Clippeur de film

Application locale et gratuite qui analyse un film ou un épisode de série, recherche ses citations cultes sur Wikiquote, puis en extrait les meilleurs moments sous forme de clips de 1 à 2 minutes, au format d'origine ou en vertical 9:16 pour les réseaux sociaux.

**[Présentation du projet](https://bastianpoirier.github.io/clippeur-de-film/)** · **[Démo en ligne](https://bastianpoirier.github.io/clippeur-de-film/demo/)** · [Cahier des charges](CAHIER_DES_CHARGES.md)

La démo en ligne est la vraie interface, alimentée par des résultats calculés à l'avance sur trois épisodes (sans images ni vidéos, pour respecter les droits d'auteur). Elle se reconstruit avec `outils/construire_demo.py`.

## Installation

Prérequis : Python 3.12 et FFmpeg.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Aucune clé nécessaire

L'application est entièrement gratuite et ne demande aucun compte. La fiche du film (résumé, réalisation, acteurs, image) vient de Wikipédia et Wikidata, les citations de Wikiquote.

Facultatif : avec une clé [TMDb](https://www.themoviedb.org/settings/api) (gratuite, mais il faut créer un compte), la fiche vient de TMDb à la place, avec l'affiche et plus de personnages. La clé se colle dans la page (« Utiliser TMDb à la place »), qui la vérifie puis l'enregistre dans `.env` (exclu de Git).

## Utilisation

### Interface

Double-cliquer sur `lancer.bat`, ou :

```powershell
.\.venv\Scripts\python.exe -m clippeur interface
```

La page s'ouvre dans le navigateur (http://127.0.0.1:5000).

1. **Film** : « Choisir un film » ouvre la fenêtre Windows de choix de fichier ; le film est lu là où il est, sans être copié. Il est identifié automatiquement (titre, année, saison et épisode pour une série, fiche Wikipédia), et on peut corriger si ce n'est pas le bon. Ensuite tout s'enchaîne : la langue des dialogues est détectée d'après la piste audio, puis viennent la transcription, les citations et la proposition des extraits.
2. **Transcription** des dialogues avec leurs horaires.
3. **Citations cultes** : les citations célèbres de l'œuvre sont cherchées sur Wikiquote, puis retrouvées dans les dialogues du film. On coche celles qui doivent compter pour le choix des extraits, et on peut choisir une autre page Wikiquote si la première n'est pas la bonne.
4. **Extraits** : chaque extrait proposé s'affiche avec une miniature, la raison de son choix et ses sources ; ▶ prépare un aperçu en quelques secondes. On peut ajuster le début et la fin de chaque extrait, et décocher ceux qu'on ne veut pas, puis on exporte. Les extraits sont enregistrés dans `output/<film>/`, avec un récapitulatif `extraits.json`, le son remis au niveau des réseaux sociaux (-14 LUFS).
5. **Répliques** : toute la transcription, avec un champ de recherche.

Le choix des extraits combine les citations cultes cochées et des indices locaux (densité des dialogues, volume sonore, répliques exclamatives). Les bornes sont calées sur des changements de plan, sans couper de réplique.

#### Reconnaissance des sons

Avec la case « Reconnaître les rires, cris, explosions et musique » (cochée par défaut), la bande son est analysée par tranches de 10 secondes avec le modèle AST, entraîné sur les catégories de sons d'AudioSet. Il tourne en local sur le processeur ; sa version compressée (environ 90 Mo) est téléchargée au premier lancement. Les rires, cris, explosions ou coups de feu et la musique comptent alors dans la note des moments, et apparaissent dans la raison du choix.

#### Montage

Dans « Montage des extraits », avant les aperçus et l'export :
- **Format** : format et résolution d'origine (par défaut), ou vertical 9:16 en 1080×1920 (TikTok, Instagram Reels, YouTube Shorts), soit recadré au centre, soit avec le film entier posé sur un fond flou. Les fichiers verticaux se terminent par `_vertical.mp4`.
- **Musique** de fond, avec son volume (20 % par défaut) et un fondu au début et à la fin. Les morceaux se déposent dans le dossier `musiques/` (MP3, WAV, M4A, AAC, OGG, FLAC, OPUS) et apparaissent dans la liste sans redémarrer. Ils ne sont pas envoyés sur GitHub. Attention aux droits d'auteur : préférez des musiques libres de droits.

#### Traitement automatique

La carte « Traitement automatique » traite les vidéos toutes seules, l'une après l'autre, du début (identification) jusqu'à l'export des extraits :
- en cochant « Surveiller le dossier « à traiter » », toute vidéo déposée dans le dossier `a_traiter/` du projet est prise en charge (l'application attend que la copie soit finie) ;
- « Traiter une saison entière… » ajoute d'un coup toutes les vidéos d'un dossier et de ses sous-dossiers, dans l'ordre des noms. À la fin, `output/saisons/<saison>.json` rassemble les 10 meilleurs extraits de tous les épisodes.

Les réglages de cette carte (extraits par épisode, format, musique, reconnaissance des sons) sont enregistrés et servent à tous les traitements automatiques.

#### Séries du moment

« Afficher les séries du moment » montre les séries les plus consultées sur Wikipédia en français ces 7 derniers jours (statistiques publiques de Wikimedia), ou les tendances de la semaine de TMDb si une clé est enregistrée. La liste est calculée une fois par jour.

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
- `--forcer` (transcrire) : refait la transcription même si elle est en cache.
- `--page` (rechercher) : page Wikiquote à utiliser, si celle trouvée automatiquement n'est pas la bonne.
- `--port` et `--sans-navigateur` (interface) : port de la page (5000 par défaut), et lancement sans ouvrir le navigateur.

Dans la page, la langue peut aussi rester sur « automatique » : elle est alors détectée d'après la piste audio du fichier.

## Dossiers

| Dossier | Contenu |
|---|---|
| `a_traiter/` | Vidéos à traiter automatiquement (si la surveillance est activée) |
| `cache/` | Résultats intermédiaires de chaque film, réglages du traitement automatique |
| `output/` | Extraits exportés, un dossier par film ; récapitulatifs des saisons dans `output/saisons/` |
| `musiques/` | Banque de musiques de fond |

Ces dossiers restent sur le PC : ils sont exclus de Git.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

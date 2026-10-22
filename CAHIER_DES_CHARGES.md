# Cahier des charges — Clippeur de film

> Version 1.0 — V1 réalisée
> Application **entièrement gratuite** : pas d'IA payante.

---

## 1. Présentation du projet

### 1.1 Objectif
**Clippeur de film** est une application locale (exécutée sur le PC de l'utilisateur) qui, à partir d'un fichier vidéo de film ou d'épisode de série :

1. identifie le film ou la série (saison et épisode) ;
2. recherche en ligne ses citations célèbres (Wikiquote) ;
3. retrouve ces citations dans le fichier vidéo ;
4. complète avec sa propre analyse locale (dialogues, sons, changements de plan) ;
5. découpe les meilleurs moments en **extraits d'une durée choisie (1 min par défaut)**, au format d'origine ou en vertical 9:16, prêts à être publiés sur les réseaux sociaux.

### 1.2 Périmètre de la V1
- Application **locale et personnelle** : elle tourne sur le PC, avec une **page web ouverte dans le navigateur**.
- Interface **la plus simple possible** : on importe le film et on récupère les clips.
- Clips au **format d'origine** du film, ou en **vertical 9:16** (recadré au centre ou sur fond flou).
- Dialogues **en français ou en anglais**, langue détectée d'après la piste audio.
- Films et séries fournis par l'utilisateur, traités **un par un** : à la main, ou automatiquement par une file d'attente (dossier surveillé, saison entière).
- **Connexion Internet obligatoire** pendant l'utilisation.
- Un seul utilisateur.
- **Gratuit** : aucun service payant. Les services en ligne utilisés (Wikipédia, Wikidata, Wikiquote, TMDb en option) sont gratuits.

### 1.3 Hors périmètre de la V1
- Services payants, dont l'analyse par une IA en ligne.
- Publication automatique sur les réseaux sociaux.
- Dialogues dans d'autres langues que le français et l'anglais.
- Fonctionnement hors connexion.
- Sous-titres incrustés dans les clips.
- Montage avancé : transitions, effets (seule une musique de fond est proposée).
- Mise en ligne de l'application ou accès multi-utilisateur.

---

## 2. Parcours utilisateur

```
[1] Import du film  →  [2] Identification  →  [3] Recherche en ligne
        →  [4] Analyse du film  →  [5] Sélection des moments
        →  [6] Validation  →  [7] Export des clips
```

| Étape | Description |
|---|---|
| 1. Import | Sur la page web locale, l'utilisateur sélectionne le fichier du film. |
| 2. Identification | L'application déduit le titre et l'année (et pour une série, la saison et l'épisode) à partir du nom du fichier. L'utilisateur confirme ou corrige. |
| 3. Recherche en ligne | L'application collecte les citations célèbres sur Wikiquote ; l'utilisateur choisit celles qui comptent. |
| 4. Analyse du film | Transcription des dialogues avec horodatage, détection des changements de plan, du volume sonore et des sons marquants. |
| 5. Sélection | Mise en correspondance des résultats de la recherche avec la transcription, puis calcul d'un score pour chaque moment candidat. |
| 6. Validation | L'utilisateur voit la liste des clips proposés, les prévisualise, ajuste leurs bornes et peut en retirer avant l'export. |
| 7. Export | Découpe des clips, mise en forme (format, musique, volume) et export dans un dossier de sortie. |

En **traitement automatique**, les étapes 2 à 7 s'enchaînent sans intervention, avec les réglages enregistrés (voir 3.8).

---

## 3. Exigences fonctionnelles

Toutes les exigences ci-dessous sont réalisées, sauf mention contraire.

### 3.1 Import du film
- **F1** — Formats acceptés : MP4, MKV, AVI, MOV.
- **F2** — Les sous-titres sont utilisés s'ils existent : fichier `.srt` placé à côté, ou piste intégrée au fichier. C'est beaucoup plus rapide qu'une transcription.
- **F3** — Le film est lu directement depuis le disque, sans être copié, car un film pèse plusieurs Go.

### 3.2 Identification du film
- **F4** — Proposition automatique du titre et de l'année à partir du nom du fichier, ainsi que de la saison et de l'épisode pour une série.
- **F5** — Récupération des métadonnées en français : résumé, réalisation, acteurs et personnages, via Wikipédia et Wikidata (gratuit, sans clé ni compte). Facultatif : TMDb à la place, si l'utilisateur saisit une clé TMDb dans l'application.
- **F6** — Possibilité pour l'utilisateur de corriger l'identification.

### 3.3 Recherche en ligne
- **F7** — Recherche des **citations célèbres** du film sur Wikiquote, dans la langue des dialogues. L'utilisateur peut choisir une autre page Wikiquote si la première n'est pas la bonne, et cocher les citations qui doivent compter.
- ~~**F8** — Recherche des scènes cultes ou populaires sur le web.~~ → **Retiré** : nécessitait une IA payante.
- **F9** — Pour chaque résultat, conservation de la source et du texte de la citation.
- **F10** — Seules les **informations** sont récupérées (texte, titres, descriptions). Aucune vidéo n'est téléchargée : les clips sont toujours découpés dans le fichier local de l'utilisateur.

### 3.4 Analyse du film
- **F11** — Transcription des dialogues avec horodatage : sous-titres existants en priorité, sinon reconnaissance vocale locale (Whisper). La langue est choisie par l'utilisateur ou détectée d'après la piste audio.
- **F12** — Détection des changements de plan, pour couper sur des transitions naturelles.
- **F13** — Détection des pics audio, et reconnaissance locale des sons marquants : rires, cris, explosions ou coups de feu, musique (modèle AST entraîné sur AudioSet, sur le processeur). Cette reconnaissance peut être désactivée.
- ~~**F14** — Analyse de la transcription par une IA en ligne.~~ → **Retiré** : service payant. Les moments non cités sur Wikiquote sont repérés par les indices locaux (densité des dialogues, volume sonore, répliques exclamatives, sons marquants).

### 3.5 Sélection des moments
- **F15** — Mise en correspondance de chaque citation trouvée en ligne avec la transcription, de façon tolérante aux petites variantes de formulation.
- **F16** — Score de chaque moment candidat, combinant : citations cultes cochées par l'utilisateur et indices locaux (dialogues, intensité sonore, répliques exclamatives, sons marquants).
- **F17** — Calcul des bornes du clip : **durée choisie par l'utilisateur** (30 s, 45 s, 1 min, 1 min 30 ou 2 min ; 1 min par défaut), à ±15 % près (au moins ±8 s), coupe sur un changement de plan, sans couper au milieu d'une phrase.
- **F18** — Pas de chevauchement entre deux clips.
- **F19** — **10 clips** proposés par défaut, nombre réglable (jusqu'à 30).

### 3.6 Validation
- **F20** — Liste des clips proposés avec : miniature, horodatage, durée, raison du choix (ex. « citation culte trouvée sur Wikiquote ») et sources.
- **F21** — L'utilisateur peut retirer un clip avant l'export.
- **F22** — Aperçu vidéo, préparé en quelques secondes avec le même montage que l'export, et ajustement manuel du début et de la fin.

### 3.7 Export et montage
- **F23** — Export en MP4 (H.264 + AAC), **au format et à la résolution d'origine du film** par défaut.
- **F24** — Format vertical 9:16 (1080×1920) pour TikTok, Instagram Reels et YouTube Shorts, au choix : recadrage au centre, ou film entier au milieu sur fond flou.
- **F25** — Nommage des fichiers : `<film>_<numéro>_<titre-du-moment>.mp4`, suivi de `_vertical` en format vertical.
- **F26** — Export d'un fichier récapitulatif `extraits.json` listant les clips et leurs métadonnées.
- **F27** — Son remis au niveau des réseaux sociaux (-14 LUFS, crête à -1,5 dB).
- **F28** — Musique de fond facultative, choisie dans une banque locale (dossier `musiques/`), avec volume réglable et fondu au début et à la fin.

### 3.8 Traitement automatique
- **F29** — File d'attente : les vidéos sont traitées une par une, dans l'ordre d'arrivée, de l'identification à l'export, avec l'avancement visible dans la page.
- **F30** — Surveillance facultative du dossier `a_traiter/` : toute vidéo déposée est ajoutée à la file une fois sa copie terminée.
- **F31** — Ajout d'une saison entière (un dossier et ses sous-dossiers). À la fin, un récapitulatif `output/saisons/<saison>.json` rassemble les 10 meilleurs extraits de tous les épisodes.
- **F32** — Réglages du traitement automatique (extraits par épisode, durée des extraits, format, musique, reconnaissance des sons) enregistrés d'une session à l'autre.

---

## 4. Exigences non fonctionnelles

| Code | Exigence | État |
|---|---|---|
| NF1 | **Local** : le fichier vidéo ne quitte jamais le PC. Seuls des textes (titre du film, extraits de transcription) sont envoyés aux services en ligne. | Réalisé |
| NF2 | **Matériel** : l'application doit fonctionner sur un PC portable **sans carte graphique dédiée**. | Réalisé (Whisper et AST sur le processeur) |
| NF3 | **Performance** : un film de 2 h avec sous-titres est traité en moins de 15 min. Sans sous-titres, la transcription allonge le traitement (voir section 8). | Non mesuré |
| NF4 | **Suivi** : barre de progression et étape en cours visibles sur la page. | Réalisé |
| NF5 | **Reprise** : les résultats intermédiaires (transcription, recherche, sons) sont mis en cache pour ne pas tout refaire. | Réalisé |
| NF6 | **Coût** : l'application est gratuite ; elle n'utilise aucun service payant. | Réalisé |
| NF7 | **Configuration** : la clé TMDb est stockée dans un fichier `.env` exclu de Git. | Réalisé |
| NF8 | **Qualité du code** : code structuré en modules, tests automatisés sur la logique de sélection, documentation dans le README. | Réalisé (41 tests) |

---

## 5. Cadre légal

- L'application est destinée à un **usage personnel**, sur des films que l'utilisateur possède légalement.
- La publication des clips sur les réseaux sociaux relève de la responsabilité de l'utilisateur. Les extraits de films restent protégés par le droit d'auteur, et les plateformes peuvent bloquer ou démonétiser ces contenus. Il en va de même pour les musiques de fond : les morceaux libres de droits sont à privilégier.
- La recherche en ligne respecte les conditions d'utilisation des sites consultés : API officielles en priorité, requêtes espacées, pas de téléchargement de vidéos.

---

## 6. Architecture technique

| Brique | Choix | Rôle |
|---|---|---|
| Langage | Python 3.12 | Écosystème vidéo, audio et IA très riche |
| Interface | Page web locale avec Flask | Import du film, suivi, liste des clips, export, file d'attente |
| Découpe vidéo | FFmpeg | Lecture, découpe, mise en forme et export |
| Transcription | Sous-titres `.srt` ou intégrés en priorité, sinon `faster-whisper` sur le processeur | Dialogues horodatés |
| Changements de plan | FFmpeg (filtre de détection de scène) | Détection des transitions |
| Reconnaissance des sons | Modèle AST (AudioSet) au format ONNX, avec `onnxruntime` | Rires, cris, explosions, musique |
| Identification | `guessit` (nom du fichier), Wikipédia et Wikidata (sans clé) ; TMDb en option | Titre, année, saison, épisode, résumé, casting |
| Recherche en ligne | API de Wikiquote (gratuite) | Citations cultes |
| Correspondance | RapidFuzz | Retrouver les citations dans les dialogues malgré les variantes |
| Stockage | Fichiers JSON | Cache, réglages et résultats |

---

## 7. Prérequis sur le poste

- [x] Git
- [x] GitHub CLI (`gh`)
- [x] VS Code avec les extensions Python et GitHub
- [x] Python 3.12 (3.12.10)
- [x] FFmpeg (9.0.2)
- [x] Compte GitHub connecté à `gh`
- [ ] Clé API TMDb (facultative)

Les modèles Whisper (environ 500 Mo) et AST (environ 90 Mo) sont téléchargés automatiquement au premier usage.

---

## 8. Questions tranchées

1. **Transcription sans sous-titres** → transcription locale avec Whisper (`faster-whisper`, sur le processeur). Gratuite mais lente : de 30 min à plus d'une heure pour un film de 2 h.
2. **Budget d'IA** → aucun. L'application reste entièrement gratuite.
3. **Format vertical** → les deux méthodes sont proposées : recadrage au centre, ou film entier sur fond flou.

---

## 9. Découpage en étapes

| Étape | Livrable | État |
|---|---|---|
| 0 | Cahier des charges validé, environnement installé, dépôt GitHub créé | Fait |
| 1 | Import du film et transcription horodatée | Fait |
| 2 | Identification du film et recherche des citations sur Wikiquote | Fait |
| 3 | Correspondance entre citations et transcription, puis scoring | Fait |
| 4 | Découpe et export des clips (FFmpeg) | Fait |
| ~~5~~ | ~~Analyse IA des moments forts~~ (retiré : payant) | — |
| 6 | Page web locale : import, suivi, liste des clips | Fait |
| 7 | Finitions : cache, tests, documentation | Fait |
| 8 | Extensions : reconnaissance des sons, format vertical, musique, file d'attente et saisons | Fait |

### Pistes pour la suite
- Mesurer le temps de traitement d'un film de 2 h (NF3).
- Sous-titres incrustés dans les clips.
- Publication sur les réseaux sociaux.

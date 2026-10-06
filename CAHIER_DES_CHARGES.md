# Cahier des charges — Clippeur de film

> Version 0.3 — brouillon à valider
> Dernière mise à jour : 2026-10-07

---

## 1. Présentation du projet

### 1.1 Objectif
**Clippeur de film** est une application locale (exécutée sur le PC de l'utilisateur) qui, à partir d'un fichier vidéo de film :

1. identifie le film ;
2. recherche en ligne ses moments les plus marquants : citations célèbres, scènes cultes, extraits déjà publiés ;
3. retrouve ces moments dans le fichier vidéo ;
4. complète si besoin avec sa propre analyse du film ;
5. découpe les meilleurs moments en **extraits de 1 à 2 minutes**, au format d'origine du film. Ils seront publiés plus tard sur les réseaux sociaux.

### 1.2 Périmètre de la V1
- Application **locale et personnelle** : elle tourne sur le PC, avec une **page web ouverte dans le navigateur**.
- Interface **la plus simple possible** : on importe le film et on récupère les clips.
- **Priorité au découpage** : les clips gardent le format du film (horizontal), sans retouche de l'image.
- **Films en français uniquement**, fournis par l'utilisateur.
- **Connexion Internet obligatoire** pendant l'utilisation.
- Un film traité à la fois, un seul utilisateur.

### 1.3 Hors périmètre de la V1
- Publication automatique sur les réseaux sociaux.
- Films dans d'autres langues que le français.
- Fonctionnement hors connexion.
- Passage au format vertical 9:16 (prévu pour une version suivante).
- Sous-titres incrustés dans les clips.
- Montage avancé : musique, transitions.
- Traitement par lots de plusieurs films.
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
| 2. Identification | L'application déduit le titre et l'année du film à partir du nom du fichier. L'utilisateur confirme ou corrige. |
| 3. Recherche en ligne | Le bot collecte les citations célèbres, les scènes cultes et les extraits populaires déjà publiés. |
| 4. Analyse du film | Transcription des dialogues avec horodatage, détection des changements de plan et des pics d'intensité sonore. |
| 5. Sélection | Mise en correspondance des résultats de la recherche avec la transcription, puis calcul d'un score pour chaque moment candidat. |
| 6. Validation | L'utilisateur voit la liste des clips proposés et peut en retirer avant l'export. |
| 7. Export | Découpe des clips et export dans un dossier de sortie. |

---

## 3. Exigences fonctionnelles

### 3.1 Import du film
- **F1** — Formats acceptés : MP4, MKV, AVI, MOV au minimum.
- **F2** — Les sous-titres français sont utilisés s'ils existent : piste intégrée au fichier ou fichier `.srt` placé à côté. C'est beaucoup plus rapide qu'une transcription.
- **F3** — Le film est lu directement depuis le disque, sans être copié, car un film pèse plusieurs Go.

### 3.2 Identification du film
- **F4** — Proposition automatique du titre et de l'année à partir du nom du fichier.
- **F5** — Récupération des métadonnées en français : synopsis, personnages, acteurs (via une base de films comme TMDb).
- **F6** — Possibilité pour l'utilisateur de corriger l'identification.

### 3.3 Recherche en ligne
- **F7** — Recherche des **citations célèbres** du film en français (ex. Wikiquote FR, sites de répliques cultes).
- **F8** — Recherche des **scènes cultes ou populaires** : articles, classements, titres des extraits YouTube les plus vus.
- **F9** — Pour chaque résultat, conservation de la source, du texte de la citation ou de la description de la scène, et d'un indicateur de popularité si disponible.
- **F10** — Seules les **informations** sont récupérées (texte, titres, descriptions). Aucune vidéo n'est téléchargée : les clips sont toujours découpés dans le fichier local de l'utilisateur.

### 3.4 Analyse du film
- **F11** — Transcription des dialogues en français avec horodatage : sous-titres existants en priorité, sinon reconnaissance vocale.
- **F12** — Détection des changements de plan, pour couper sur des transitions naturelles.
- **F13** — Détection des pics audio : musique, cris, explosions, rires.
- **F14** — Analyse par l'IA de la transcription pour repérer les moments forts non trouvés en ligne : répliques marquantes, rebondissements, scènes émotionnelles.

### 3.5 Sélection des moments
- **F15** — Mise en correspondance de chaque citation trouvée en ligne avec la transcription, de façon tolérante aux petites variantes de formulation.
- **F16** — Score de chaque moment candidat, combinant : popularité en ligne, analyse IA et intensité audio et visuelle.
- **F17** — Calcul des bornes du clip : **durée entre 60 et 120 secondes**, coupe sur un changement de plan, sans couper au milieu d'une phrase.
- **F18** — Pas de chevauchement entre deux clips.
- **F19** — **10 clips** proposés par défaut, nombre réglable.

### 3.6 Validation
- **F20** — Liste des clips proposés avec : miniature, horodatage, durée et raison du choix (ex. « citation culte trouvée sur Wikiquote »).
- **F21** — L'utilisateur peut retirer un clip avant l'export.
- **F22** — *(V2)* Aperçu vidéo et ajustement manuel du début et de la fin.

### 3.7 Export
- **F23** — Export en MP4 (H.264 + AAC), **au format et à la résolution d'origine du film**.
- **F24** — *(version suivante)* Passage au format vertical 9:16 (1080×1920) pour TikTok, Instagram Reels et YouTube Shorts. Méthode à choisir : recadrage au centre, ou film au milieu sur fond flou.
- **F25** — Nommage des fichiers : `<film>_<numéro>_<titre-du-moment>.mp4`.
- **F26** — Export d'un fichier récapitulatif (JSON ou CSV) listant les clips et leurs métadonnées.

---

## 4. Exigences non fonctionnelles

| Code | Exigence |
|---|---|
| NF1 | **Local** : le fichier vidéo ne quitte jamais le PC. Seuls des textes (titre du film, extraits de transcription) sont envoyés aux services en ligne. |
| NF2 | **Matériel** : l'application doit fonctionner sur un PC portable **sans carte graphique dédiée**. |
| NF3 | **Performance** : un film de 2 h avec sous-titres est traité en moins de 15 min. Sans sous-titres, la transcription allonge le traitement (voir section 8). |
| NF4 | **Suivi** : barre de progression et étape en cours visibles sur la page. |
| NF5 | **Reprise** : les résultats intermédiaires (transcription, recherche) sont mis en cache pour ne pas tout refaire. |
| NF6 | **Coût** : les appels à l'IA sont limités et leur coût est affiché après chaque film. |
| NF7 | **Configuration** : les clés d'API sont stockées dans un fichier `.env` exclu de Git. |
| NF8 | **Qualité du code** : code structuré en modules, tests automatisés sur la logique de sélection, documentation dans le README. |

---

## 5. Cadre légal

- L'application est destinée à un **usage personnel**, sur des films que l'utilisateur possède légalement.
- La publication des clips sur les réseaux sociaux relève de la responsabilité de l'utilisateur. Les extraits de films restent protégés par le droit d'auteur, et les plateformes peuvent bloquer ou démonétiser ces contenus.
- La recherche en ligne respecte les conditions d'utilisation des sites consultés : API officielles en priorité, pas de téléchargement de vidéos.

---

## 6. Proposition d'architecture technique (à valider)

| Brique | Proposition | Rôle |
|---|---|---|
| Langage | Python 3.12+ | Écosystème vidéo, audio et IA très riche |
| Interface | Page web locale minimale en Python (Flask ou Gradio) | Import du film, suivi, liste des clips, export |
| Découpe vidéo | FFmpeg | Lecture, découpe et export |
| Transcription | Sous-titres `.srt` en priorité, sinon reconnaissance vocale (voir section 8) | Dialogues horodatés |
| Changements de plan | PySceneDetect | Détection des transitions |
| Métadonnées du film | API TMDb | Titre, année, synopsis, casting |
| Recherche web | API de recherche + Wikiquote FR | Citations et scènes cultes |
| IA (agents) | API Claude (Anthropic) | Recherche, analyse de la transcription, choix et justification des moments |
| Stockage | Fichiers JSON | Cache et résultats |

### Agents IA envisagés
1. **Agent chercheur** : interroge le web et collecte les citations et scènes cultes avec leurs sources.
2. **Agent analyste** : lit la transcription et repère les moments forts.
3. **Agent monteur** : fusionne les résultats, calcule les scores et propose les bornes des clips.

---

## 7. Prérequis sur le poste

- [x] Git
- [x] GitHub CLI (`gh`), installé le 2026-10-07
- [x] VS Code avec les extensions Python et GitHub
- [x] Python 3.12 (3.12.10)
- [x] FFmpeg (9.0.2)
- [ ] Compte GitHub connecté à `gh`
- [ ] Clé API Anthropic (payante, à l'usage)
- [ ] Clé API TMDb (gratuite)

---

## 8. Questions ouvertes

1. **Transcription sans sous-titres** : sans carte graphique, transcrire un film de 2 h sur le PC peut prendre de 30 min à plus d'une heure. Deux options :
   - **A. Transcription locale** : gratuite, mais lente.
   - **B. Service de transcription en ligne** : rapide (quelques minutes), avec un petit coût par film. La connexion est de toute façon obligatoire.
2. **Budget d'IA** : quel coût maximum par film accepter ? Ce coût est estimé à moins de 1 € par film et sera mesuré lors des premiers tests.

---

## 9. Découpage en étapes (proposition)

| Étape | Livrable |
|---|---|
| 0 | Cahier des charges validé, environnement installé, dépôt GitHub créé |
| 1 | Import du film et transcription horodatée |
| 2 | Identification du film et recherche en ligne (agent chercheur) |
| 3 | Correspondance entre citations et transcription, puis scoring |
| 4 | Découpe et export des clips (FFmpeg) |
| 5 | Analyse IA des moments forts (agent analyste) |
| 6 | Page web locale : import, suivi, liste des clips |
| 7 | Finitions : cache, tests, documentation |

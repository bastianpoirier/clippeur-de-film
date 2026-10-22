"""Construit la démo en ligne (dossier « demo ») à partir de la vraie page et de vrais résultats.

La démo est la page de l'application, sans serveur : un script (demo/simulation.js) répond à la place
du serveur Python, avec des résultats calculés ici par le vrai parcours de l'application.

Les films utilisés sont ceux de la Blender Foundation, sous licence Creative Commons BY : la démo peut donc
montrer leurs vraies images (miniatures copiées dans demo/images) et lire les extraits depuis les copies
publiques des films. Les noms de fichiers sont nettoyés (pas de chemin du PC).

    .venv\\Scripts\\python.exe outils\\construire_demo.py "C:\\films\\Tears of Steel (2012).mov" ...
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from clippeur import cache  # noqa: E402
from clippeur.export import FORMATS, VOLUME_MUSIQUE_DEFAUT  # noqa: E402
from clippeur.file_attente import REGLAGES_PAR_DEFAUT  # noqa: E402
from clippeur.selection import nom_de_fichier  # noqa: E402
from clippeur.traitement import analyser_film  # noqa: E402
from clippeur.transcription import MODELE_PAR_DEFAUT  # noqa: E402

DOSSIER_DEMO = RACINE / "demo"
DOSSIER_IMAGES = DOSSIER_DEMO / "images"
GABARIT = RACINE / "clippeur" / "templates" / "index.html"
DOSSIER_FICTIF = "C:\\Films"  # affiché à la place du vrai chemin du PC
NB_EXTRAITS = 10
MUSIQUES_EXEMPLE = ["piano-calme (exemple).mp3", "electro-rythmee (exemple).mp3"]

# Copies des films lues par la démo pour les aperçus, et mention de la licence (CC BY). Tears of Steel,
# chargé à l'ouverture de la démo, a sa propre copie légère (demo/films, encodée en 480p avec FFmpeg).
SOURCES = {
    "Tears of Steel": {
        "video": "films/tears-of-steel-480p.mp4",  # copie 480p hébergée avec la démo (CC BY le permet)
        "credit": "Tears of Steel, © Blender Foundation, mango.blender.org, CC BY 3.0",
    },
    "Sintel": {
        "video": "https://archive.org/download/Sintel/sintel-2048-stereo_512kb.mp4",
        "credit": "Sintel, © Blender Foundation, durian.blender.org, CC BY 3.0",
    },
    "Cosmos Laundromat": {
        "video": "https://archive.org/download/CosmosLaundromatFirstCycle/Cosmos%20Laundromat%20-%20First%20Cycle%20%281080p%29.mp4",
        "credit": "Cosmos Laundromat, © Blender Foundation, gooseberry.blender.org, CC BY 4.0",
    },
}

POLICES = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
           '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
           '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;'
           '0,6..72,500;1,6..72,400&family=IBM+Plex+Mono:wght@400;500&display=swap">\n')

# Même en-tête que la page de présentation, puis quelques lignes pour dire ce qu'est cette page.
ENTETE = """
<header class="haut-demo">
  <div class="haut-dedans">
    <a href="../">Clippeur de film</a>
    <nav><a href="../">Présentation</a><a href="https://github.com/bastianpoirier/clippeur-de-film">Code</a></nav>
  </div>
</header>
"""

INTRO = """
  <div class="intro-demo">
    <h1 class="titre-demo">Démo</h1>
    <p>C'est l'interface de l'application, telle qu'elle tourne sur un PC. Les résultats affichés ont été calculés
      par l'application sur trois courts métrages libres de la Blender Foundation (<i>Tears of Steel</i>,
      <i>Sintel</i> et <i>Cosmos Laundromat</i>) ; la page les rejoue sans rien analyser.</p>
    <p class="consigne"><i>Tears of Steel</i> est déjà chargé : ses <a href="#carte-extraits">extraits</a> sont
      prêts, cliquez sur une image pour voir le passage. Pour voir l'analyse se dérouler, choisissez un autre film
      à l'étape <a href="#etape-film">1. Film</a>.</p>
  </div>
  <p class="intertitre-demo">Les autres outils de l'application</p>
"""

CREDITS = """
<footer class="credits-demo">
  <p>Films de la Blender Foundation, sous licence Creative Commons BY :
    <i>Tears of Steel</i> (2012, mango.blender.org), <i>Sintel</i> (2010, durian.blender.org) et
    <i>Cosmos Laundromat</i> (2015, gooseberry.blender.org). Les aperçus de <i>Tears of Steel</i> viennent d'une copie en 480p hébergée avec cette page, ceux des deux autres
    films de leurs copies sur archive.org.</p>
</footer>
"""

# Remplacements dans la page : ce qui demande le serveur (fichiers vidéo, images) est pris en charge
# par la simulation. Chaque texte doit exister une seule fois, sinon la page a changé et le script s'arrête.
REMPLACEMENTS = [
    ('$("modele").value = "{{ modele_par_defaut }}";', f'$("modele").value = "{MODELE_PAR_DEFAUT}";'),
    ("<title>Clippeur de film</title>", "<title>Clippeur de film — démo</title>"),
    ("</style>", "</style>\n" + POLICES + '<link rel="stylesheet" href="../assets/tokens.css">\n'
                 '<link rel="stylesheet" href="demo.css">'),
    ("<body>\n<main>\n", "<body>\n" + ENTETE + "<main>\n" + INTRO),
    ("</main>\n", "</main>\n" + CREDITS),
    ('<section class="carte">\n    <h2>1. Film</h2>', '<section class="carte" id="etape-film">\n    <h2>1. Film</h2>'),
    ('<section class="carte">\n    <h2>2. Transcription</h2>',
     '<section class="carte" id="carte-transcription">\n    <h2>2. Transcription</h2>'),
    ('<section class="carte">\n    <h2>Séries du moment</h2>',
     '<section class="carte" id="carte-tendances">\n    <h2>Séries du moment</h2>'),
    ('<section class="carte">\n    <h2>Traitement automatique</h2>',
     '<section class="carte" id="carte-auto">\n    <h2>Traitement automatique</h2>'),
    ("<script>\n  const $", "<script src=\"donnees.js\"></script>\n<script src=\"simulation.js\"></script>\n<script>\n  const $"),
    ("const miniature = `/media/miniature/${e.numero}?v=${encodeURIComponent(proposeIci.debut)}`;",
     "const miniature = DEMO.miniature(e);"),
    ("      if (fichier) {\n        const video", "      if (fichier && !window.DEMO) {\n        const video"),
    ("      video.src = `/media/apercu/${e.numero}?${parametres}`;", "      DEMO.apercu(video, attente, e, m);"),
    ('"/media/sortie/" + x.lien.split("/").map(encodeURIComponent).join("/")', "null"),
]


def analyser(film: Path, langue: str) -> dict:
    """Le vrai parcours de l'application, avec ses messages d'avancement et ses résultats, dans l'ordre."""
    deroule = []

    def suivi(message: str, pourcentage: float | None) -> None:
        deroule.append({"message": message, "pourcentage": pourcentage})

    def etape(nom: str, resultat: dict) -> None:
        deroule.append({"etape": nom})

    resultats = analyser_film(film, suivi, langue=langue, nombre=NB_EXTRAITS, avec_sons=True, etape=etape)
    # Les messages de pourcentage sont nombreux : on garde ceux du journal et quelques étapes de progression.
    deroule = [d for i, d in enumerate(deroule) if d.get("pourcentage") is None or i % 10 == 0]
    return {"deroule": deroule} | resultats


def frise(film: Path, resultat: dict, nb_cases: int = 160) -> dict:
    """Résumé de l'analyse d'un film, pour la figure de la page de présentation : des valeurs entre 0 et 1
    par tranche de temps, et la place des citations et des extraits."""
    duree = resultat["proposition"]["duree"]
    pas = duree / nb_cases

    def par_case(valeurs_par_seconde, agreger=max):
        cases = []
        for i in range(nb_cases):
            tranche = valeurs_par_seconde[int(i * pas):max(int((i + 1) * pas), int(i * pas) + 1)]
            cases.append(agreger(tranche) if tranche else 0.0)
        return cases

    parole = [0.0] * (int(duree) + 1)
    for s in resultat["transcription"]["segments"]:
        for t in range(int(s["debut"]), min(int(s["fin"]) + 1, len(parole))):
            parole[t] = 1.0
    volume = [min(max((v + 55) / 40, 0.0), 1.0) for v in cache.lire(film, "volume")["volume"]]
    sons = cache.lire(film, "sons") or {}
    plans = [0.0] * (int(duree) + 1)
    for t in cache.lire(film, "plans")["plans"]:
        plans[min(int(t), len(plans) - 1)] = 1.0
    moyenne = lambda tranche: sum(tranche) / len(tranche)
    arrondir = lambda valeurs: [round(v, 2) for v in valeurs]
    return {
        "duree": round(duree, 1),
        "pistes": {
            "parole": arrondir(par_case(parole, moyenne)),
            "volume": arrondir(par_case(volume, moyenne)),
            **{f: arrondir(par_case(sons[f])) for f in ("rires", "cris", "explosions", "musique") if f in sons},
            "plans": arrondir(par_case(plans, sum)),
        },
        "citations": [[round(r["position"]["debut"]), round(r["position"]["fin"])]
                      for r in (resultat["recherche"] or {}).get("resultats", []) if r.get("position")],
        "extraits": [{"debut": round(e["debut"]), "fin": round(e["fin"]), "score": e["score"], "titre": e["titre"].strip(),
                      "raison": e["raison"], "image": e.get("image")}
                     for e in resultat["proposition"]["extraits"]],
    }


def illustrer(film: Path, resultat: dict, titre: str) -> None:
    """Extrait du film une vraie image par extrait (640 px, au même instant que la miniature de l'application),
    et ajoute à chaque extrait l'adresse de son aperçu."""
    DOSSIER_IMAGES.mkdir(parents=True, exist_ok=True)
    source = SOURCES.get(titre, {})
    for extrait in resultat["proposition"]["extraits"]:
        extrait.pop("miniature", None)
        nom = f"{nom_de_fichier(titre)}-{extrait['numero']:02d}.jpg"
        instant = extrait["debut"] + min((extrait["fin"] - extrait["debut"]) / 2, 10)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{instant:.2f}", "-i", str(film), "-frames:v", "1",
                        "-vf", "scale=640:-2:flags=lanczos", "-q:v", "4", str(DOSSIER_IMAGES / nom)], check=True)
        extrait["image"] = f"images/{nom}"
        if source.get("video"):
            extrait["video"] = f"{source['video']}#t={extrait['debut']:.1f},{extrait['fin']:.1f}"


def anonymiser(donnees: dict, film: Path) -> dict:
    texte = json.dumps(donnees, ensure_ascii=False)
    for avant, apres in [(str(film.parent), DOSSIER_FICTIF), (str(cache.DOSSIER_CACHE), "cache")]:
        texte = texte.replace(json.dumps(avant, ensure_ascii=False)[1:-1], json.dumps(apres, ensure_ascii=False)[1:-1])
    return json.loads(texte)


def construire_page() -> None:
    page = GABARIT.read_text(encoding="utf-8")
    for avant, apres in REMPLACEMENTS:
        if page.count(avant) != 1:
            sys.exit(f"Texte introuvable (ou en double) dans la page : {avant!r}")
        page = page.replace(avant, apres)
    (DOSSIER_DEMO / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("films", type=Path, nargs="+", help="fichiers des films ; le premier sert à la figure de la présentation")
    parser.add_argument("--langue", default="en", choices=["fr", "en"], help="langue des dialogues (en par défaut)")
    args = parser.parse_args()

    if DOSSIER_IMAGES.exists():
        shutil.rmtree(DOSSIER_IMAGES)
    films = []
    for film in args.films:
        titre = film.stem.split(" (")[0]
        print(f"Analyse de {film.name}...")
        resultat = analyser(film, args.langue)
        illustrer(film, resultat, titre)
        if not films:  # la figure de la présentation montre le premier film
            (RACINE / "assets").mkdir(exist_ok=True)
            (RACINE / "assets" / "frise.js").write_text(
                "// Généré par outils/construire_demo.py : ne pas modifier à la main.\n"
                f"window.FRISE = {json.dumps(frise(film, resultat) | {'nom': titre}, ensure_ascii=False)};\n",
                encoding="utf-8")
        films.append(anonymiser(resultat, film) | {"nom": film.name, "chemin": f"{DOSSIER_FICTIF}\\{film.name}",
                                                    "credit": SOURCES.get(titre, {}).get("credit")})

    tendances = next(iter(sorted(cache.DOSSIER_CACHE.glob("tendances_*.json"), reverse=True)), None)
    donnees = {
        "episodes": films,
        "dossier_saison": f"{DOSSIER_FICTIF}\\Blender Open Movies",
        "tendances": json.loads(tendances.read_text(encoding="utf-8")) if tendances else None,
        "montage": {"formats": FORMATS, "musiques": MUSIQUES_EXEMPLE, "volume_musique": VOLUME_MUSIQUE_DEFAUT},
        "reglages_auto": REGLAGES_PAR_DEFAUT,
    }
    DOSSIER_DEMO.mkdir(exist_ok=True)
    (DOSSIER_DEMO / "donnees.js").write_text(
        "// Généré par outils/construire_demo.py : ne pas modifier à la main.\n"
        f"window.DONNEES_DEMO = {json.dumps(donnees, ensure_ascii=False, indent=1)};\n", encoding="utf-8")
    construire_page()
    print(f"Démo construite dans {DOSSIER_DEMO} ({len(films)} films).")


if __name__ == "__main__":
    main()

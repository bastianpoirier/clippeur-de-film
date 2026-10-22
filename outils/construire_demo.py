"""Construit la démo en ligne (dossier « demo ») à partir de la vraie page et de vrais résultats.

La démo est la page de l'application, sans serveur : un script (demo/simulation.js) répond à la place
du serveur Python, avec des résultats calculés ici par le vrai parcours, sur des épisodes déjà analysés.

Pour respecter les droits d'auteur, la démo ne contient aucune image ni vidéo des épisodes, et seulement
quelques répliques de chacun. Les noms de fichiers sont nettoyés (pas de chemin du PC).

    .venv\\Scripts\\python.exe outils\\construire_demo.py "C:\\dossier\\de\\la\\saison" --episodes 1 3 4
"""

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from clippeur import cache  # noqa: E402
from clippeur.export import FORMATS, VOLUME_MUSIQUE_DEFAUT  # noqa: E402
from clippeur.file_attente import REGLAGES_PAR_DEFAUT  # noqa: E402
from clippeur.traitement import analyser_film  # noqa: E402
from clippeur.transcription import MODELE_PAR_DEFAUT  # noqa: E402

DOSSIER_DEMO = RACINE / "demo"
GABARIT = RACINE / "clippeur" / "templates" / "index.html"
DOSSIER_FICTIF = "C:\\Films\\Breaking Bad\\Saison 1"  # affiché à la place du vrai chemin du PC

REPLIQUES_TRANSCRIPTION = 60  # répliques de la transcription montrées dans la démo
REPLIQUES_PAR_EXTRAIT = 4
NB_EXTRAITS = 10
MUSIQUES_EXEMPLE = ["piano-calme (exemple).mp3", "electro-rythmee (exemple).mp3"]

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
    <p>C'est l'interface de l'application, telle qu'elle tourne sur un PC. Ici, aucun film n'est analysé : la page
      rejoue des résultats que l'application a calculés à l'avance sur trois épisodes de <i>Breaking Bad</i>, en
      accéléré. Les images et les vidéos sont masquées, et seules quelques répliques sont affichées.</p>
    <p class="consigne">Pour commencer, choisissez un épisode à l'étape <a href="#etape-film">1. Film</a>.</p>
  </div>
  <p class="intertitre-demo">Les autres outils de l'application</p>
"""

# Remplacements dans la page : ce qui demande le serveur (fichiers vidéo, images) est pris en charge
# par la simulation. Chaque texte doit exister une seule fois, sinon la page a changé et le script s'arrête.
REMPLACEMENTS = [
    ('$("modele").value = "{{ modele_par_defaut }}";', f'$("modele").value = "{MODELE_PAR_DEFAUT}";'),
    ("<title>Clippeur de film</title>", "<title>Clippeur de film — démo</title>"),
    ("</style>", "</style>\n" + POLICES + '<link rel="stylesheet" href="../assets/tokens.css">\n'
                 '<link rel="stylesheet" href="demo.css">'),
    ("<body>\n<main>\n", "<body>\n" + ENTETE + "<main>\n" + INTRO),
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


def nom_propre(film: Path) -> str:
    """« Breaking.Bad.S01E01.Pilot.720p.10bit.BluRay....mkv » → « Breaking Bad S01E01 Pilot.mkv »."""
    from guessit import guessit

    g = guessit(film.name)
    nom = f"{g['title']} S{g['season']:02d}E{g['episode']:02d}"
    if g.get("episode_title"):
        nom += f" {g['episode_title']}"
    return nom + film.suffix


def analyser(film: Path) -> dict:
    """Le vrai parcours de l'application, avec ses messages d'avancement et ses résultats, dans l'ordre."""
    deroule = []

    def suivi(message: str, pourcentage: float | None) -> None:
        deroule.append({"message": message, "pourcentage": pourcentage})

    def etape(nom: str, resultat: dict) -> None:
        deroule.append({"etape": nom})

    resultats = analyser_film(film, suivi, langue=None, nombre=NB_EXTRAITS, avec_sons=True, etape=etape)
    # Les messages de pourcentage sont nombreux : on garde ceux du journal et quelques étapes de progression.
    deroule = [d for i, d in enumerate(deroule) if d.get("pourcentage") is None or i % 10 == 0]
    return {"deroule": deroule} | resultats


def frise(film: Path, episode: dict, nb_cases: int = 160) -> dict:
    """Résumé de l'analyse d'un épisode, pour la frise de la page de présentation : des valeurs
    entre 0 et 1 par tranche de temps (aucun texte des dialogues), et la place des citations et des extraits."""
    duree = episode["proposition"]["duree"]
    pas = duree / nb_cases

    def par_case(valeurs_par_seconde, agreger=max):
        cases = []
        for i in range(nb_cases):
            tranche = valeurs_par_seconde[int(i * pas):max(int((i + 1) * pas), int(i * pas) + 1)]
            cases.append(agreger(tranche) if tranche else 0.0)
        return cases

    parole = [0.0] * (int(duree) + 1)
    for s in episode["transcription"]["segments"]:
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
                      for r in episode["recherche"]["resultats"] if r.get("position")],
        "extraits": [{"debut": round(e["debut"]), "fin": round(e["fin"]), "score": e["score"], "titre": e["titre"].strip()}
                     for e in episode["proposition"]["extraits"]],
    }


def alleger(episode: dict) -> dict:
    """Ne garde que quelques répliques, et rien qui pointe vers des fichiers du PC."""
    transcription = episode["transcription"]
    transcription["segments"] = transcription["segments"][:REPLIQUES_TRANSCRIPTION]
    transcription["film"] += f" (démo : {REPLIQUES_TRANSCRIPTION} premières répliques)"
    for extrait in episode["proposition"]["extraits"]:
        extrait.pop("miniature", None)
        if len(extrait["repliques"]) > REPLIQUES_PAR_EXTRAIT:
            extrait["repliques"] = extrait["repliques"][:REPLIQUES_PAR_EXTRAIT] + ["…"]
    return episode


def anonymiser(donnees: dict, film: Path, propre: str) -> dict:
    texte = json.dumps(donnees, ensure_ascii=False)
    for avant, apres in [(str(film), f"{DOSSIER_FICTIF}\\{propre}"), (str(film.parent), DOSSIER_FICTIF),
                         (film.name, propre), (film.stem, Path(propre).stem),
                         (str(cache.DOSSIER_CACHE), "cache")]:
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
    parser.add_argument("dossier", type=Path, help="dossier de la saison (épisodes déjà analysés)")
    parser.add_argument("--episodes", type=int, nargs="+", default=[1, 3, 4])
    args = parser.parse_args()

    videos = sorted(f for f in args.dossier.iterdir() if f.suffix.lower() in {".mkv", ".mp4", ".avi", ".mov"})
    episodes = []
    for film in videos:
        propre = nom_propre(film)
        if not any(f"E{n:02d}" in propre for n in args.episodes):
            continue
        print(f"Analyse de {propre}...")
        episode = analyser(film)
        if not episodes:  # la frise de la présentation montre le premier épisode
            (RACINE / "assets").mkdir(exist_ok=True)
            (RACINE / "assets" / "frise.js").write_text(
                "// Généré par outils/construire_demo.py : ne pas modifier à la main.\n"
                f"window.FRISE = {json.dumps(frise(film, episode) | {'nom': propre}, ensure_ascii=False)};\n",
                encoding="utf-8")
        episode = alleger(episode)
        episodes.append(anonymiser(episode, film, propre) | {"nom": propre, "chemin": f"{DOSSIER_FICTIF}\\{propre}"})

    tendances = next(iter(sorted(cache.DOSSIER_CACHE.glob("tendances_*.json"), reverse=True)), None)
    donnees = {
        "episodes": episodes,
        "dossier_saison": DOSSIER_FICTIF,
        "tendances": json.loads(tendances.read_text(encoding="utf-8")) if tendances else None,
        "montage": {"formats": FORMATS, "musiques": MUSIQUES_EXEMPLE, "volume_musique": VOLUME_MUSIQUE_DEFAUT},
        "reglages_auto": REGLAGES_PAR_DEFAUT,
    }
    DOSSIER_DEMO.mkdir(exist_ok=True)
    (DOSSIER_DEMO / "donnees.js").write_text(
        "// Généré par outils/construire_demo.py : ne pas modifier à la main.\n"
        f"window.DONNEES_DEMO = {json.dumps(donnees, ensure_ascii=False, indent=1)};\n", encoding="utf-8")
    construire_page()
    print(f"Démo construite dans {DOSSIER_DEMO} ({len(episodes)} épisodes).")


if __name__ == "__main__":
    main()

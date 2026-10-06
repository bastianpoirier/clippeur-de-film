"""Page web locale : choix du film, suivi de la transcription, affichage des répliques.

Le serveur n'écoute que sur 127.0.0.1 : il n'est pas accessible depuis un autre appareil.
"""

import subprocess
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from clippeur.transcription import MODELE_PAR_DEFAUT, transcrire

FORMATS_VIDEO = [("Vidéos", "*.mp4 *.mkv *.avi *.mov"), ("Tous les fichiers", "*.*")]

app = Flask(__name__)

# Une seule transcription à la fois : l'état est partagé entre le travail en arrière-plan et la page.
_verrou = threading.Lock()
_etat: dict = {"en_cours": False}


def _mettre_a_jour(**changements) -> None:
    with _verrou:
        _etat.update(changements)


def _travail(film: Path, modele: str, forcer: bool) -> None:
    def suivi(message: str, pourcentage: float | None) -> None:
        with _verrou:
            _etat["message"] = message
            _etat["pourcentage"] = pourcentage
            if pourcentage is None:
                _etat["journal"].append(message)

    try:
        resultat = transcrire(film, modele=modele, forcer=forcer, suivi=suivi)
        _mettre_a_jour(resultat=resultat)
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or b"").decode("utf-8", errors="replace").strip()
        _mettre_a_jour(erreur=f"FFmpeg n'a pas pu lire le fichier. {detail}")
    except Exception as e:  # on affiche l'erreur sur la page plutôt que de la perdre
        _mettre_a_jour(erreur=f"{type(e).__name__} : {e}")
    finally:
        _mettre_a_jour(en_cours=False)


@app.get("/")
def accueil():
    return render_template("index.html", modele_par_defaut=MODELE_PAR_DEFAUT)


@app.post("/api/choisir")
def choisir_film():
    """Ouvre la fenêtre Windows de choix de fichier.

    Le film est lu là où il est, sans être copié : un envoi par le navigateur
    obligerait à recopier plusieurs Go.
    """
    import tkinter
    from tkinter import filedialog

    racine = tkinter.Tk()
    racine.withdraw()
    racine.attributes("-topmost", True)  # sinon la fenêtre s'ouvre derrière le navigateur
    chemin = filedialog.askopenfilename(title="Choisir un film", filetypes=FORMATS_VIDEO, parent=racine)
    racine.destroy()
    return jsonify(chemin=chemin or None)


@app.post("/api/transcrire")
def lancer_transcription():
    donnees = request.get_json()
    film = Path(donnees.get("chemin") or "")
    if not film.is_file():
        return jsonify(erreur=f"Fichier introuvable : {film}"), 400

    with _verrou:
        if _etat["en_cours"]:
            return jsonify(erreur="Une transcription est déjà en cours."), 409
        _etat.clear()
        _etat.update(en_cours=True, film=film.name, message="Démarrage...", pourcentage=None,
                     journal=[], resultat=None, erreur=None)

    threading.Thread(
        target=_travail,
        args=(film, donnees.get("modele") or MODELE_PAR_DEFAUT, bool(donnees.get("forcer"))),
        daemon=True,
    ).start()
    return jsonify(ok=True)


@app.get("/api/etat")
def etat():
    with _verrou:
        return jsonify(_etat)


def lancer(port: int = 5000, ouvrir_navigateur: bool = True) -> None:
    adresse = f"http://127.0.0.1:{port}"
    print(f"Interface disponible sur {adresse} (Ctrl+C pour arrêter)")
    if ouvrir_navigateur:
        threading.Timer(1.0, webbrowser.open, args=[adresse]).start()
    app.run(host="127.0.0.1", port=port, threaded=True)

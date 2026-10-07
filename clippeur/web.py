"""Page web locale : choix du film, transcription, proposition et export des extraits.

Le serveur n'écoute que sur 127.0.0.1 : il n'est pas accessible depuis un autre appareil.
"""

import os
import subprocess
import threading
import webbrowser
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, render_template, request, send_file, send_from_directory

from clippeur import cache, config
from clippeur.export import creer_apercu, dossier_de_sortie, exporter
from clippeur.extraits import proposer
from clippeur.identification import identifier, verifier_cle_tmdb
from clippeur.recherche import choisir_citations, recherche_en_cache, rechercher
from clippeur.transcription import LANGUE_PAR_DEFAUT, MODELE_PAR_DEFAUT, FilmIllisible, transcrire

FORMATS_VIDEO = [("Vidéos", "*.mp4 *.mkv *.avi *.mov"), ("Tous les fichiers", "*.*")]

app = Flask(__name__)

# Une seule tâche à la fois : l'état est partagé entre le travail en arrière-plan et la page.
_verrou = threading.Lock()
_etat: dict = {
    "en_cours": False, "tache": None, "film": None, "chemin": None,
    "message": None, "pourcentage": None, "journal": [], "erreur": None,
    "identification": None, "transcription": None, "recherche": None, "proposition": None, "exports": None,
}
# Résultats à effacer quand une tâche démarre, car ils dépendent de cette tâche.
_RESULTATS_INVALIDES = {
    "identification": ["identification", "recherche", "proposition", "exports"],
    "transcription": ["transcription", "recherche", "proposition", "exports"],
    "recherche": ["recherche", "proposition", "exports"],
    "proposition": ["proposition", "exports"],
    "exports": ["exports"],
}


def _mettre_a_jour(**changements) -> None:
    with _verrou:
        _etat.update(changements)


def _suivi(message: str, pourcentage: float | None) -> None:
    with _verrou:
        _etat["message"] = message
        _etat["pourcentage"] = pourcentage
        if pourcentage is None:
            _etat["journal"].append(message)


def _lancer_tache(tache: str, film: Path, travail) -> tuple:
    """Démarre `travail()` en arrière-plan ; son résultat est rangé dans _etat[tache]."""
    with _verrou:
        if _etat["en_cours"]:
            return jsonify(erreur="Une tâche est déjà en cours."), 409
        # Un autre film : tous les résultats précédents deviennent caducs.
        a_effacer = _RESULTATS_INVALIDES["identification"] + ["transcription"] if _etat["chemin"] != str(film) \
            else _RESULTATS_INVALIDES[tache]
        for cle in a_effacer:
            _etat[cle] = None
        _etat.update(en_cours=True, tache=tache, film=film.name, chemin=str(film),
                     message="Démarrage...", pourcentage=None, journal=[], erreur=None)

    def executer() -> None:
        try:
            _mettre_a_jour(**{tache: travail()})
        except FilmIllisible as e:
            _mettre_a_jour(erreur=str(e))
        except subprocess.CalledProcessError as e:
            detail = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
            _mettre_a_jour(erreur=f"FFmpeg n'a pas pu traiter le fichier. {detail.strip()}")
        except Exception as e:  # on affiche l'erreur sur la page plutôt que de la perdre
            _mettre_a_jour(erreur=f"{type(e).__name__} : {e}")
        finally:
            _mettre_a_jour(en_cours=False)

    threading.Thread(target=executer, daemon=True).start()
    return jsonify(ok=True), 200


def _film_demande() -> tuple[Path | None, dict]:
    donnees = request.get_json() or {}
    film = Path(donnees.get("chemin") or "")
    return (film if film.is_file() else None), donnees


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
    film, donnees = _film_demande()
    if film is None:
        return jsonify(erreur=f"Fichier introuvable : {donnees.get('chemin')}"), 400
    langue = donnees.get("langue") or LANGUE_PAR_DEFAUT

    def travail() -> dict:
        resultat = transcrire(film, modele=donnees.get("modele") or MODELE_PAR_DEFAUT, langue=langue,
                              forcer=bool(donnees.get("forcer")), suivi=_suivi)
        # Une recherche en ligne déjà faite pour ce film est réaffichée sans être refaite (et repayée).
        if not donnees.get("forcer"):
            _mettre_a_jour(recherche=recherche_en_cache(film, langue))
        return resultat

    return _lancer_tache("transcription", film, travail)


@app.get("/api/cles")
def cles():
    return jsonify(config.etat_des_cles())


@app.post("/api/cles")
def enregistrer_cle():
    """Vérifie la clé TMDb auprès de TMDb, puis l'enregistre dans .env (exclu de Git)."""
    cle = ((request.get_json() or {}).get("tmdb") or "").strip()
    if not cle:
        return jsonify(erreur="Collez votre clé TMDb."), 400
    try:
        valide = verifier_cle_tmdb(cle)
    except requests.RequestException:
        return jsonify(erreur="TMDb injoignable : vérifiez la connexion Internet."), 502
    if not valide:
        return jsonify(erreur="TMDb refuse cette clé. Copiez bien la « clé d'API » ou le « jeton d'accès en lecture »."), 400
    config.enregistrer_cle_tmdb(cle)
    return jsonify(config.etat_des_cles())


@app.post("/api/identifier")
def lancer_identification():
    """Devine le film depuis son nom (F4), récupère sa fiche TMDb (F5) ; `correction` vient de l'utilisateur (F6)."""
    film, donnees = _film_demande()
    if film is None:
        return jsonify(erreur=f"Fichier introuvable : {donnees.get('chemin')}"), 400
    correction = donnees.get("correction")
    return _lancer_tache("identification", film, lambda: identifier(
        film, correction=correction, forcer=bool(donnees.get("forcer"))))


@app.post("/api/rechercher")
def lancer_recherche():
    """Recherche des citations cultes sur Wikiquote (F7, F9, F10) ; `page` : page choisie par l'utilisateur."""
    film, donnees = _film_demande()
    if film is None:
        return jsonify(erreur=f"Fichier introuvable : {donnees.get('chemin')}"), 400
    with _verrou:
        identification, transcription, chemin = _etat["identification"], _etat["transcription"], _etat["chemin"]
    if not transcription or chemin != str(film):
        return jsonify(erreur="Lancez d'abord la transcription du film."), 400

    def travail() -> dict:
        nonlocal identification
        if not identification:
            _suivi("Identification du film...", None)
            identification = identifier(film)
            _mettre_a_jour(identification=identification)
        return rechercher(film, identification["fiche"], transcription, _suivi, page=donnees.get("page") or None)

    return _lancer_tache("recherche", film, travail)


@app.post("/api/recherche/choix")
def choisir():
    """Enregistre les citations cochées par l'utilisateur ; les extraits déjà proposés sont à refaire."""
    retenues = [int(i) for i in (request.get_json() or {}).get("retenues", [])]
    with _verrou:
        if _etat["en_cours"]:
            return jsonify(erreur="Une tâche est déjà en cours."), 409
        chemin, transcription = _etat["chemin"], _etat["transcription"]
    if not chemin or not transcription:
        return jsonify(erreur="Aucune recherche pour ce film."), 400
    try:
        recherche = choisir_citations(Path(chemin), transcription.get("langue", LANGUE_PAR_DEFAUT), retenues)
    except ValueError as e:
        return jsonify(erreur=str(e)), 400
    _mettre_a_jour(recherche=recherche)
    return jsonify(ok=True)


@app.post("/api/extraits/proposer")
def lancer_proposition():
    film, donnees = _film_demande()
    if film is None:
        return jsonify(erreur=f"Fichier introuvable : {donnees.get('chemin')}"), 400
    nombre = max(1, min(int(donnees.get("nombre") or 10), 30))
    return _lancer_tache("proposition", film, lambda: proposer(
        film,
        langue=donnees.get("langue") or LANGUE_PAR_DEFAUT,
        nombre=nombre,
        suivi=_suivi,
        modele=donnees.get("modele") or MODELE_PAR_DEFAUT,
    ))


@app.post("/api/extraits/exporter")
def lancer_export():
    numeros = set((request.get_json() or {}).get("numeros") or [])
    with _verrou:
        proposition = _etat["proposition"]
    if not proposition:
        return jsonify(erreur="Aucun extrait proposé."), 400
    choisis = [e for e in proposition["extraits"] if e["numero"] in numeros]
    if not choisis:
        return jsonify(erreur="Aucun extrait gardé."), 400
    film = Path(proposition["chemin"])
    return _lancer_tache("exports", film, lambda: exporter(film, choisis, _suivi))


@app.get("/media/miniature/<int:numero>")
def miniature(numero: int):
    with _verrou:
        proposition = _etat["proposition"]
    for e in (proposition or {}).get("extraits", []):
        if e["numero"] == numero:
            return send_file(e["miniature"], max_age=0)
    abort(404)


_verrous_apercus: dict[str, threading.Lock] = {}


@app.get("/media/apercu/<int:numero>")
def apercu(numero: int):
    """Prépare (au premier clic) puis envoie l'aperçu d'un extrait proposé."""
    with _verrou:
        proposition = _etat["proposition"]
    extrait = next((e for e in (proposition or {}).get("extraits", []) if e["numero"] == numero), None)
    if extrait is None:
        abort(404)
    film = Path(proposition["chemin"])
    # Le nom contient les bornes : si la proposition change, l'aperçu est refait.
    chemin = cache.dossier_du_film(film) / "apercus" / f"{extrait['debut']:.2f}-{extrait['fin']:.2f}.mp4"
    with _verrou:
        verrou_fichier = _verrous_apercus.setdefault(str(chemin), threading.Lock())
    with verrou_fichier:  # deux clics rapides ne lancent pas deux fois FFmpeg
        if not chemin.is_file():
            creer_apercu(film, extrait, chemin)
    return send_file(chemin, max_age=0)


@app.get("/media/extrait/<path:nom>")
def extrait(nom: str):
    with _verrou:
        chemin = _etat["chemin"]
    if not chemin:
        abort(404)
    # send_from_directory refuse les chemins qui sortent du dossier (« ../ »).
    return send_from_directory(dossier_de_sortie(Path(chemin)), nom, max_age=0)


@app.post("/api/ouvrir_dossier")
def ouvrir_dossier():
    with _verrou:
        chemin = _etat["chemin"]
    if not chemin or not dossier_de_sortie(Path(chemin)).is_dir():
        return jsonify(erreur="Aucun dossier d'extraits."), 400
    os.startfile(dossier_de_sortie(Path(chemin)))
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

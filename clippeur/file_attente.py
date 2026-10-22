"""Traitement automatique en arrière-plan : file d'attente, dossier « à traiter » surveillé, saisons entières.

- Tout fichier vidéo déposé dans le dossier « a_traiter » du projet est traité tout seul, du début
  (identification) à la fin (extraits exportés), avec les réglages choisis dans la page.
- Un dossier entier (une saison) peut être ajouté d'un coup ; à la fin, un récapitulatif rassemble
  les meilleurs extraits de tous ses épisodes.
Les films sont traités un par un, dans l'ordre d'arrivée.
"""

import json
import subprocess
import threading
import time
import uuid
from pathlib import Path

from clippeur import cache
from clippeur.export import DOSSIER_SORTIE, MONTAGE_PAR_DEFAUT, dossier_de_sortie, montage_valide
from clippeur.selection import DUREE_PAR_DEFAUT, duree_valide, nom_de_fichier
from clippeur.traitement import traiter_film
from clippeur.transcription import FilmIllisible

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_A_TRAITER = RACINE / "a_traiter"
DOSSIER_SAISONS = DOSSIER_SORTIE / "saisons"
EXTENSIONS_VIDEO = {".mp4", ".mkv", ".avi", ".mov"}
INTERVALLE_SURVEILLANCE = 15  # secondes entre deux coups d'œil au dossier « à traiter »
MEILLEURS_PAR_SAISON = 10

REGLAGES_PAR_DEFAUT = {
    "surveillance": False,  # désactivée tant que l'utilisateur ne l'a pas activée
    "nombre": 5,  # extraits exportés par épisode
    "duree_extraits": DUREE_PAR_DEFAUT,  # longueur visée pour chaque extrait, en secondes
    "avec_sons": True,
    "langue": "auto",
    "montage": MONTAGE_PAR_DEFAUT,
}


def videos_du_dossier(dossier: Path) -> list[Path]:
    """Les vidéos d'un dossier et de ses sous-dossiers, dans l'ordre des noms (S01E01, S01E02...)."""
    return sorted((f for f in dossier.rglob("*") if f.is_file() and f.suffix.lower() in EXTENSIONS_VIDEO),
                  key=lambda f: str(f).lower())


def _cle_fichier(f: Path) -> str:
    info = f.stat()
    return f"{f.resolve()}|{info.st_size}|{info.st_mtime_ns}"


class FileAttente:
    def __init__(self) -> None:
        self._verrou = threading.Lock()
        self._reveil = threading.Event()
        self.elements: list[dict] = []
        self.lots: dict[str, dict] = {}
        self._tailles_vues: dict[str, int] = {}  # pour attendre qu'un fichier ait fini d'être copié
        etat = cache.lire_global("file_attente") or {}
        self.reglages = REGLAGES_PAR_DEFAUT | etat.get("reglages", {})
        self._deja_vus: set[str] = set(etat.get("deja_vus", []))
        self._demarre = False

    # --- Réglages et état, partagés avec la page ---

    def _sauver(self) -> None:
        cache.ecrire_global("file_attente", {"reglages": self.reglages, "deja_vus": sorted(self._deja_vus)})

    def changer_reglages(self, nouveaux: dict) -> dict:
        reglages = self.reglages | {k: v for k, v in nouveaux.items() if k in REGLAGES_PAR_DEFAUT}
        reglages["montage"] = montage_valide(reglages.get("montage"))
        reglages["nombre"] = max(1, min(int(reglages["nombre"]), 30))
        reglages["duree_extraits"] = duree_valide(reglages["duree_extraits"])
        reglages["surveillance"] = bool(reglages["surveillance"])
        with self._verrou:
            self.reglages = reglages
            self._sauver()
        self._reveil.set()
        return reglages

    def etat(self) -> dict:
        with self._verrou:
            return {
                "reglages": self.reglages,
                "dossier_a_traiter": str(DOSSIER_A_TRAITER),
                "elements": [dict(e) for e in self.elements],
                "lots": [dict(l) for l in self.lots.values()],
            }

    # --- Ajout de films ---

    def ajouter(self, film: Path, lot: str | None = None) -> dict | None:
        """Ajoute un film à la file, sauf s'il y attend déjà ou est en cours de traitement."""
        film = film.resolve()
        with self._verrou:
            if any(e["chemin"] == str(film) and e["statut"] in ("en attente", "en cours") for e in self.elements):
                return None
            element = {
                "id": uuid.uuid4().hex[:8], "chemin": str(film), "fichier": film.name, "lot": lot,
                "statut": "en attente", "message": "", "pourcentage": None, "erreur": None,
                "extraits": [], "dossier_sortie": str(dossier_de_sortie(film)), "ajoute_le": time.time(),
            }
            self.elements.append(element)
        self._reveil.set()
        return element

    def ajouter_dossier(self, dossier: Path) -> dict:
        """Ajoute toutes les vidéos d'un dossier (une saison) ; leur récapitulatif sera fait à la fin."""
        videos = videos_du_dossier(dossier)
        if not videos:
            raise ValueError(f"Aucune vidéo dans « {dossier} ».")
        lot = {"id": uuid.uuid4().hex[:8], "nom": dossier.name, "dossier": str(dossier),
               "nb": len(videos), "termine": False, "meilleurs": [], "recapitulatif": None}
        with self._verrou:
            self.lots[lot["id"]] = lot
        for video in videos:
            self.ajouter(video, lot=lot["id"])
        return lot

    def retirer(self, identifiant: str) -> bool:
        """Retire un film qui attend encore (un film en cours de traitement va jusqu'au bout)."""
        with self._verrou:
            avant = len(self.elements)
            self.elements = [e for e in self.elements if not (e["id"] == identifiant and e["statut"] == "en attente")]
            return len(self.elements) < avant

    # --- Travail en arrière-plan ---

    def demarrer(self) -> None:
        if self._demarre:
            return
        self._demarre = True
        DOSSIER_A_TRAITER.mkdir(exist_ok=True)
        threading.Thread(target=self._boucle_traitement, daemon=True, name="file-attente").start()
        threading.Thread(target=self._boucle_surveillance, daemon=True, name="surveillance").start()

    def _boucle_surveillance(self) -> None:
        while True:
            if self.reglages["surveillance"]:
                try:
                    self.surveiller_une_fois()
                except OSError:
                    pass  # dossier momentanément inaccessible : on réessaiera au prochain tour
            time.sleep(INTERVALLE_SURVEILLANCE)

    def surveiller_une_fois(self) -> list[Path]:
        """Ajoute les vidéos nouvelles du dossier « à traiter » dont la copie est terminée."""
        ajoutees = []
        for video in videos_du_dossier(DOSSIER_A_TRAITER):
            taille = video.stat().st_size
            # Un fichier en cours de copie grossit encore : on attend que sa taille soit stable.
            if self._tailles_vues.get(str(video)) != taille:
                self._tailles_vues[str(video)] = taille
                continue
            cle = _cle_fichier(video)
            if cle in self._deja_vus:
                continue
            with self._verrou:
                self._deja_vus.add(cle)
                self._sauver()
            if self.ajouter(video):
                ajoutees.append(video)
        return ajoutees

    def _prochain(self) -> dict | None:
        with self._verrou:
            return next((e for e in self.elements if e["statut"] == "en attente"), None)

    def _boucle_traitement(self) -> None:
        while True:
            element = self._prochain()
            if element is None:
                self._reveil.wait(timeout=5)
                self._reveil.clear()
                continue
            self.traiter(element)

    def traiter(self, element: dict) -> None:
        def suivi(message: str, pourcentage: float | None) -> None:
            with self._verrou:
                element["message"], element["pourcentage"] = message, pourcentage

        with self._verrou:
            element["statut"] = "en cours"
            reglages = dict(self.reglages)
        try:
            resultat = traiter_film(Path(element["chemin"]), reglages, suivi)
            fiche = resultat["identification"]["fiche"]
            dossier = Path(element["dossier_sortie"]).relative_to(DOSSIER_SORTIE).as_posix()
            with self._verrou:
                element["statut"] = "terminé"
                element["titre"] = fiche.get("titre")
                # « lien » : chemin dans output/, pour regarder l'extrait depuis la page.
                element["extraits"] = [{"numero": e["numero"], "titre": e["titre"], "score": e["score"],
                                        "duree": round(e["fin"] - e["debut"], 1), "fichier": e["fichier"],
                                        "lien": f"{dossier}/{e['fichier']}"}
                                       for e in resultat["exports"]]
                element["message"] = f"{len(resultat['exports'])} extraits exportés."
        except FilmIllisible as e:
            self._echec(element, str(e))
        except subprocess.CalledProcessError as e:
            detail = e.stderr if isinstance(e.stderr, str) else (e.stderr or b"").decode("utf-8", "replace")
            self._echec(element, f"FFmpeg n'a pas pu traiter le fichier. {detail.strip()[-300:]}")
        except Exception as e:  # un film en échec ne doit pas arrêter toute la file
            self._echec(element, f"{type(e).__name__} : {e}")
        if element["lot"]:
            self._finir_lot_si_complet(element["lot"])

    def _echec(self, element: dict, erreur: str) -> None:
        with self._verrou:
            element["statut"], element["erreur"], element["message"] = "erreur", erreur, ""

    def _finir_lot_si_complet(self, lot_id: str) -> None:
        """Quand tous les épisodes d'une saison sont traités, rassemble ses meilleurs extraits."""
        with self._verrou:
            lot = self.lots.get(lot_id)
            episodes = [e for e in self.elements if e["lot"] == lot_id]
            if lot is None or lot["termine"] or any(e["statut"] in ("en attente", "en cours") for e in episodes):
                return
            tous = [x | {"episode": e["fichier"], "chemin_sortie": str(Path(e["dossier_sortie"]) / x["fichier"])}
                    for e in episodes for x in e["extraits"]]
            meilleurs = sorted(tous, key=lambda x: -x["score"])[:MEILLEURS_PAR_SAISON]
            lot["termine"], lot["meilleurs"] = True, meilleurs
            lot["erreurs"] = sum(1 for e in episodes if e["statut"] == "erreur")

        DOSSIER_SAISONS.mkdir(parents=True, exist_ok=True)
        recapitulatif = DOSSIER_SAISONS / f"{nom_de_fichier(lot['nom'], longueur_max=60)}.json"
        recapitulatif.write_text(json.dumps({
            "saison": lot["nom"], "dossier": lot["dossier"], "episodes": lot["nb"],
            "episodes_en_erreur": lot["erreurs"], "meilleurs_extraits": meilleurs,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        with self._verrou:
            lot["recapitulatif"] = str(recapitulatif)


file_attente = FileAttente()

import json
from pathlib import Path

import pytest

from clippeur import file_attente as module
from clippeur.transcription import FilmIllisible


@pytest.fixture
def file(monkeypatch, tmp_path):
    """Une file d'attente isolée : dossiers temporaires et faux traitement des films."""
    a_traiter, sortie = tmp_path / "a_traiter", tmp_path / "output"
    a_traiter.mkdir()
    monkeypatch.setattr(module, "DOSSIER_A_TRAITER", a_traiter)
    monkeypatch.setattr(module, "DOSSIER_SORTIE", sortie)
    monkeypatch.setattr(module, "DOSSIER_SAISONS", sortie / "saisons")
    monkeypatch.setattr(module.cache, "DOSSIER_CACHE", tmp_path / "cache")
    monkeypatch.setattr(module, "dossier_de_sortie", lambda film: sortie / film.stem)

    def faux_traitement(film: Path, reglages: dict, suivi) -> dict:
        if "abime" in film.name:
            raise FilmIllisible("fichier abîmé")
        score = float(film.stem[-1])  # E1 → 1, E2 → 2...
        return {"identification": {"fiche": {"titre": "Ma série"}},
                "exports": [{"numero": 1, "titre": f"Moment {film.stem}", "score": score,
                             "debut": 0.0, "fin": 60.0, "fichier": f"{film.stem}_01.mp4"}]}
    monkeypatch.setattr(module, "traiter_film", faux_traitement)
    return module.FileAttente()


def video(dossier: Path, nom: str, taille: int = 10) -> Path:
    f = dossier / nom
    f.write_bytes(b"x" * taille)
    return f


def test_le_dossier_surveille_attend_la_fin_de_la_copie(file):
    f = video(module.DOSSIER_A_TRAITER, "Serie.S01E1.mkv")
    video(module.DOSSIER_A_TRAITER, "notes.txt")
    assert file.surveiller_une_fois() == []  # premier coup d'œil : la copie est peut-être en cours
    f.write_bytes(b"x" * 20)  # le fichier grossit encore
    assert file.surveiller_une_fois() == []
    assert file.surveiller_une_fois() == [f]  # taille stable : on le prend
    assert file.surveiller_une_fois() == []  # jamais deux fois le même fichier


def test_un_fichier_deja_traite_n_est_pas_repris_apres_redemarrage(file):
    video(module.DOSSIER_A_TRAITER, "Serie.S01E1.mkv")
    file.surveiller_une_fois()
    file.surveiller_une_fois()
    nouvelle = module.FileAttente()  # comme après un redémarrage de l'application
    nouvelle.surveiller_une_fois()
    assert nouvelle.surveiller_une_fois() == []


def test_pas_de_doublon_dans_la_file(file, tmp_path):
    f = video(tmp_path, "Film.mkv")
    assert file.ajouter(f) is not None
    assert file.ajouter(f) is None


def test_une_saison_entiere_et_son_recapitulatif(file, tmp_path):
    saison = tmp_path / "Saison 1"
    saison.mkdir()
    for nom in ("Serie.S01E2.mkv", "Serie.S01E1.mkv", "Serie.S01E3.abime.mkv", "Serie.S01E4.mkv"):
        video(saison, nom)
    lot = file.ajouter_dossier(saison)
    assert lot["nb"] == 4
    assert [e["fichier"] for e in file.elements][0] == "Serie.S01E1.mkv"  # dans l'ordre des épisodes

    while (element := file._prochain()) is not None:
        file.traiter(element)

    statuts = {e["fichier"]: e["statut"] for e in file.elements}
    assert statuts["Serie.S01E3.abime.mkv"] == "erreur"  # un épisode en échec n'arrête pas la saison
    lot = file.lots[lot["id"]]
    assert lot["termine"] and lot["erreurs"] == 1
    assert [m["score"] for m in lot["meilleurs"]] == [4.0, 2.0, 1.0]  # du meilleur au moins bon
    recapitulatif = json.loads(Path(lot["recapitulatif"]).read_text(encoding="utf-8"))
    assert recapitulatif["episodes"] == 4 and len(recapitulatif["meilleurs_extraits"]) == 3


def test_reglages_valides_et_enregistres(file):
    reglages = file.changer_reglages({"nombre": 99, "surveillance": 1, "inconnu": "ignoré",
                                      "montage": {"format": "flou"}})
    assert reglages["nombre"] == 30 and reglages["surveillance"] is True and "inconnu" not in reglages
    assert module.FileAttente().reglages["montage"]["format"] == "flou"
    with pytest.raises(ValueError):
        file.changer_reglages({"montage": {"format": "carre"}})

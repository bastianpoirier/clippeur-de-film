from pathlib import Path

import numpy as np
import pytest

from clippeur import export, sons
from clippeur.segments import Segment
from clippeur.selection import proposer_extraits
from clippeur.web import _avec_bornes

FILM = Path("film.mkv")


# --- Format vertical (F24) et musique ---

@pytest.fixture
def banque(monkeypatch, tmp_path):
    (tmp_path / "ambiance.mp3").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("pas une musique")
    monkeypatch.setattr(export, "DOSSIER_MUSIQUES", tmp_path)
    return tmp_path


def test_banque_de_musiques(banque):
    assert export.lister_musiques() == ["ambiance.mp3"]


def test_montage_refuse_une_musique_hors_banque(banque):
    with pytest.raises(ValueError):
        export.montage_valide({"musique": "..\\..\\.env"})
    with pytest.raises(ValueError):
        export.montage_valide({"format": "carre"})
    assert export.montage_valide({"volume_musique": 250})["volume_musique"] == 100


def test_la_duree_s_applique_au_film_et_pas_a_la_musique(banque):
    """Régression : « -t » placé après « -i film » visait la musique, et l'extrait durait tout le film."""
    montage = export.montage_valide({"musique": "ambiance.mp3"})
    commande = export._commande(FILM, 100.0, 160.0, montage, Path("sortie.mp4"), apercu=False)
    i_film = commande.index(str(FILM))
    assert commande[i_film - 3:i_film + 1] == ["-t", "60.0", "-i", str(FILM)]
    filtres = commande[commande.index("-filter_complex") + 1]
    assert "volume=0.2" in filtres and "amix" in filtres and "loudnorm" in filtres


def test_formats_verticaux():
    assert "crop=1080:1920" in export._filtre_video("recadre", False)
    flou = export._filtre_video("flou", False)
    assert "boxblur" in flou and "overlay" in flou and "scale=1080:1920" in flou
    assert export._filtre_video("original", False) == "null"
    # Aperçu : même cadrage, assez grand pour juger la netteté.
    assert "crop=720:1280" in export._filtre_video("recadre", True)
    assert "lanczos" in export._filtre_video("recadre", False)


# --- Ajustement des bornes (F22) ---

def test_bornes_ajustees_restent_dans_le_film():
    extrait = {"numero": 1, "debut": 100.0, "fin": 160.0}
    assert _avec_bornes(extrait, None, None, 3000.0) == extrait
    assert _avec_bornes(extrait, 95, 170, 3000.0)["debut"] == 95
    ajuste = _avec_bornes(extrait, -10, 4000, 3000.0)
    assert ajuste["debut"] == 0 and ajuste["fin"] == 300  # 5 minutes au plus
    trop_court = _avec_bornes(extrait, 200, 201, 3000.0)
    assert trop_court["fin"] - trop_court["debut"] == 5


# --- Reconnaissance des sons (F13) ---

def test_spectrogramme_au_format_attendu_par_le_modele():
    seconde = np.sin(2 * np.pi * 440 * np.arange(16000) / 16000).astype(np.float32)
    spectre = sons.spectrogramme(np.tile(seconde, 10))
    assert spectre.shape == (1024, 128) and spectre.dtype == np.float32
    # La bande qui contient 440 Hz est bien plus forte que la plus haute.
    assert spectre[100].argmax() < 40
    assert np.isfinite(sons.spectrogramme(np.zeros(100, np.float32))).all()  # tranche trop courte


def test_les_rires_font_monter_un_extrait():
    segments = [Segment(d, d + 4, "Une réplique ordinaire.") for d in range(0, 1190, 10)]
    rires = [0.0] * 1200
    for t in range(700, 760):
        rires[t] = 0.25  # probabilité modeste, typique du modèle
    sons_reconnus = {"rires": rires, "cris": [0.0] * 1200, "explosions": [0.0] * 1200, "musique": [0.1] * 1200}
    extraits = proposer_extraits(segments, [], [-40.0] * 1200, 1200.0, nombre=2, sons=sons_reconnus)
    assert extraits[0].debut < 760 and extraits[0].fin > 700
    assert "rires" in extraits[0].raison.lower()

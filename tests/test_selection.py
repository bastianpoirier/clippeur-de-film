from clippeur.segments import Segment
from clippeur.selection import DUREE_MAX, DUREE_MIN, nom_de_fichier, proposer_extraits


def film_de_test(duree=1200):
    """Un film de 20 min : une réplique calme toutes les 10 s, et une scène agitée de 300 à 400 s."""
    segments = []
    for debut in range(0, duree - 10, 10):
        if 300 <= debut < 400:
            segments += [Segment(debut, debut + 4, "Non ! Pourquoi tu as fait ça ? Réponds-moi !"),
                         Segment(debut + 5, debut + 9, "Je n'avais pas le choix, tu comprends ?")]
        else:
            segments.append(Segment(debut, debut + 3, "Bonjour."))
    volume = [-40.0] * duree
    for t in range(300, 400):
        volume[t] = -15.0
    plans = [float(t) for t in range(0, duree, 7)]
    return segments, plans, volume, float(duree)


def test_trouve_la_scene_agitee_en_premier():
    extraits = proposer_extraits(*film_de_test(), nombre=3)
    meilleur = extraits[0]
    assert meilleur.debut < 400 and meilleur.fin > 300
    assert "!" in meilleur.titre


def test_duree_et_chevauchement():
    extraits = proposer_extraits(*film_de_test(), nombre=8)
    assert len(extraits) >= 3
    for e in extraits:
        assert DUREE_MIN - 1 <= e.duree <= DUREE_MAX
    bornes = sorted((e.debut, e.fin) for e in extraits)
    for (_, fin), (debut_suivant, _) in zip(bornes, bornes[1:]):
        assert fin <= debut_suivant


def test_ne_coupe_pas_une_replique():
    segments, plans, volume, duree = film_de_test()
    for e in proposer_extraits(segments, plans, volume, duree, nombre=5):
        for s in segments:
            assert not (s.debut < e.debut < s.fin), "le début coupe une réplique"
            assert not (s.debut < e.fin < s.fin), "la fin coupe une réplique"


def test_film_sans_dialogue():
    assert proposer_extraits([], [], [-40.0] * 100, 100.0) == []


def test_nom_de_fichier():
    assert nom_de_fichier("Oh, mon Dieu ! Ça alors…") == "oh-mon-dieu-ca-alors"
    assert nom_de_fichier("?!") == "extrait"

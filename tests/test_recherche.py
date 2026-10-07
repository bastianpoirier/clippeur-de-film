from pathlib import Path

from clippeur import config, identification, recherche, wikiquote
from clippeur.correspondance import placer_dans_le_film
from clippeur.segments import Segment
from clippeur.selection import proposer_extraits
from clippeur.wikiquote import extraire_citations

# --- Wikiquote (F7) ---

WIKI_FR = """== Répliques ==
{{citation|{{Personnage|François Pignon}} : La tour Eiffel… entièrement faite avec des allumettes, {{formatnum:346422}} exactement !}}
{{Réf Film|titre=Le Dîner de cons}}
{{citation|citation=<poem>
{{Personnage|François Pignon}} : Il s'appelle Juste Leblanc.
{{Personnage|Pierre Brochant}} : Ah bon, il a pas de prénom ?
</poem>}}
{{citation|Oui.}}
"""

WIKI_EN = """=== ''[[w:Pilot (Breaking Bad)|Pilot]]'' [1.01] ===
:'''[[w:Walter White (Breaking Bad)|Walter]]''': My name is Walter Hartwell White.
----
:''[Jesse records Walter cooking]''
:'''Jesse''': Wow, this is a really great look for you.
:'''Walter''': Shut up and help me.
=== ''Cat's in the Bag...'' [1.02] ===
:'''Jesse''': Yo, this is another episode entirely.
"""


def test_wikiquote_francais():
    citations = extraire_citations(WIKI_FR, {"type": "film"})
    assert citations[0] == ["La tour Eiffel… entièrement faite avec des allumettes, 346422 exactement !"]
    assert citations[1] == ["Il s'appelle Juste Leblanc.", "Ah bon, il a pas de prénom ?"]
    assert len(citations) == 2  # « Oui. » est trop court pour retrouver une scène


def test_wikiquote_anglais_garde_seulement_l_episode():
    citations = extraire_citations(WIKI_EN, {"type": "serie", "saison": 1, "episode": 1})
    assert citations == [
        ["My name is Walter Hartwell White."],
        ["Wow, this is a really great look for you.", "Shut up and help me."],
    ]


def test_pages_possibles_met_la_page_de_la_saison_en_premier(monkeypatch):
    def fausse_api(langue, **parametres):
        return {"query": {"search": [{"title": t} for t in
                                     ("Bryan Cranston", "Breaking Bad", "Breaking Bad (season 1)")]}}
    monkeypatch.setattr(wikiquote, "_api", fausse_api)
    fiche = {"titre": "Breaking Bad", "type": "serie", "saison": 1}
    pages = wikiquote.pages_possibles("en", fiche)
    assert pages[:2] == ["Breaking Bad (season 1)", "Breaking Bad"]
    assert wikiquote.page_probable(fiche, pages) == "Breaking Bad (season 1)"
    # « Bryan Cranston » reste proposé à l'utilisateur, mais n'est jamais choisi d'office.
    assert wikiquote.page_probable(fiche, ["Bryan Cranston"]) is None


# --- Correspondance avec la transcription (F15) ---

def segments_de_test():
    lignes = ["Yo.", "No.", "Hey, Mr. White!", "My name is Walter Hartwell White.",
              "I live at 308 Negra Arroyo Lane,", "Albuquerque, New Mexico.", "Goodbye."]
    return [{"debut": 10.0 * i, "fin": 10.0 * i + 4, "texte": t} for i, t in enumerate(lignes)]


def test_retrouve_une_citation_coupee_en_plusieurs_sous_titres():
    resultats = placer_dans_le_film([{"repliques": [
        "My name is Walter Hartwell White. I live at 308 Negra Arroyo Lane, Albuquerque, New Mexico, 87104."]}],
        segments_de_test())
    assert resultats[0]["position"]["debut"] == 30.0


def test_tolere_les_petites_differences():
    resultats = placer_dans_le_film([{"repliques": ["My name's Walter H. White."]}], segments_de_test())
    assert resultats[0]["position"] is not None


def test_une_replique_tres_courte_ne_fait_pas_un_faux_positif():
    """« Yo » est contenu dans « Yo, why are you here? » : ce n'est pas pour autant la bonne scène."""
    resultats = placer_dans_le_film([{"repliques": ["Yo, why are you here? I was curious, honestly."]}],
                                    segments_de_test())
    assert resultats[0]["position"] is None


# --- Sélection avec les citations (F16) ---

def film_avec_une_citation():
    segments, volume = [], [-40.0] * 1200
    for debut in range(0, 1190, 10):
        texte = "Non ! Pourquoi tu as fait ça ? Réponds !" if 300 <= debut < 400 else "Bonjour, comment ça va ?"
        segments.append(Segment(debut, debut + 4, texte))
    for t in range(300, 400):
        volume[t] = -15.0
    culte = {"type": "citation", "titre": "Bonjour, comment ça va ?", "source": "Wikiquote (fr)",
             "source_url": "https://fr.wikiquote.org/wiki/X", "popularite": 4, "retenue": True,
             "position": {"debut": 900.0, "fin": 904.0, "score": 100, "replique_trouvee": "Bonjour"}}
    return segments, volume, culte


def test_la_citation_culte_passe_devant_la_scene_agitee():
    segments, volume, culte = film_avec_une_citation()
    extraits = proposer_extraits(segments, [], volume, 1200.0, nombre=3, references=[culte])
    assert extraits[0].debut <= 900 <= extraits[0].fin
    assert "Citation culte" in extraits[0].raison
    assert extraits[0].sources[0]["url"].startswith("https://fr.wikiquote.org")


def test_une_citation_decochee_ne_compte_plus():
    segments, volume, culte = film_avec_une_citation()
    extraits = proposer_extraits(segments, [], volume, 1200.0, nombre=3, references=[culte | {"retenue": False}])
    assert not (extraits[0].debut <= 900 <= extraits[0].fin)
    assert all("Citation culte" not in e.raison for e in extraits)


def test_choix_des_citations_enregistre(monkeypatch, tmp_path):
    film = tmp_path / "film.mkv"
    film.write_bytes(b"")
    monkeypatch.setattr(recherche.cache, "DOSSIER_CACHE", tmp_path / "cache")
    position = {"debut": 1.0, "fin": 2.0, "score": 100, "replique_trouvee": "x"}
    recherche.cache.ecrire(film, "recherche_fr", {
        "page": "P", "url": "u", "pages_possibles": ["P"], "avertissements": [],
        "resultats": [{"position": position, "retenue": True},
                      {"position": position, "retenue": True},
                      {"position": None, "retenue": False}],
    })
    donnees = recherche.choisir_citations(film, "fr", [1, 2])
    # La 3e est absente du film : elle ne peut pas être retenue, même cochée.
    assert [r["retenue"] for r in donnees["resultats"]] == [False, True, False]
    assert recherche.recherche_en_cache(film, "fr") == donnees


# --- Identification (F4 à F6) ---

def test_devine_un_episode_de_serie():
    devine = identification.deviner(Path("Breaking.Bad.S01E01.Pilot.720p.10bit.BluRay.x265.mkv"))
    assert devine == {"titre": "Breaking Bad", "annee": None, "type": "serie", "saison": 1, "episode": 1}


def test_devine_un_film():
    devine = identification.deviner(Path("Le.Diner.de.Cons.1998.FRENCH.1080p.BluRay.x264.mkv"))
    assert devine["type"] == "film" and devine["annee"] == 1998


def test_sans_cle_tmdb_l_identification_reste_utilisable(monkeypatch, tmp_path):
    film = tmp_path / "Le.Diner.de.Cons.1998.mkv"
    film.write_bytes(b"")
    monkeypatch.setattr(identification.config, "cle_tmdb", lambda: None)
    monkeypatch.setattr(identification.cache, "DOSSIER_CACHE", tmp_path / "cache")
    resultat = identification.identifier(film)
    assert resultat["fiche"]["titre"] == "Le Diner de Cons"
    assert "TMDb" in resultat["avertissement"]


def test_fiche_tmdb_d_un_film(monkeypatch):
    reponses = {
        "/search/movie": {"results": [{"id": 9, "title": "Le Dîner de cons", "original_title": "Le Dîner de cons",
                                       "release_date": "1998-04-15", "poster_path": "/a.jpg"}]},
        "/movie/9": {"title": "Le Dîner de cons", "original_title": "Le Dîner de cons", "release_date": "1998-04-15",
                     "overview": "Chaque mercredi…", "poster_path": "/a.jpg",
                     "credits": {"cast": [{"name": "Jacques Villeret", "character": "François Pignon"}],
                                 "crew": [{"name": "Francis Veber", "job": "Director"}]}},
    }
    monkeypatch.setattr(identification, "_appel_tmdb", lambda chemin, **p: reponses[chemin])
    candidats = identification.chercher_candidats("Le Diner de Cons", 1998, "film")
    fiche = identification.fiche_tmdb(candidats[0]["tmdb_id"], "film")
    assert fiche["realisation"] == "Francis Veber"
    assert fiche["acteurs"][0]["personnage"] == "François Pignon"
    assert fiche["affiche"].endswith("/a.jpg")


def test_enregistrer_la_cle_tmdb_garde_les_autres_lignes(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("# commentaire\nTMDB_API_KEY=ancienne\nAUTRE=1\n", encoding="utf-8")
    monkeypatch.setattr(config, "FICHIER_ENV", env)
    config.enregistrer_cle_tmdb("nouvelle")
    assert env.read_text(encoding="utf-8") == "# commentaire\nAUTRE=1\nTMDB_API_KEY=nouvelle\n"
    assert config.cle_tmdb() == "nouvelle"

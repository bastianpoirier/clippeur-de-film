from clippeur.web import app


def test_la_page_s_affiche():
    reponse = app.test_client().get("/")
    assert reponse.status_code == 200
    assert "Clippeur de film" in reponse.get_data(as_text=True)


def test_film_introuvable():
    reponse = app.test_client().post("/api/analyser", json={"chemin": "C:/nulle/part.mkv"})
    assert reponse.status_code == 400
    assert "introuvable" in reponse.get_json()["erreur"]

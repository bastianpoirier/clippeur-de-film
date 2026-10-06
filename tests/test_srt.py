from clippeur.segments import format_horodatage
from clippeur.sous_titres import choisir_piste
from clippeur.srt import lire_srt

EXEMPLE = """﻿1
00:00:01,500 --> 00:00:03,000
<i>Bonjour,</i>
tout le monde.

2
00:01:02,250 --> 00:01:04,000
{\\an8}Je reviens.

3
00:01:05,000 --> 00:01:06,000

"""


def test_lit_horaires_et_texte():
    segments = lire_srt(EXEMPLE)
    assert len(segments) == 2
    assert segments[0].debut == 1.5
    assert segments[0].fin == 3.0
    assert segments[0].texte == "Bonjour, tout le monde."
    assert segments[1].debut == 62.25
    assert segments[1].texte == "Je reviens."


def test_fins_de_ligne_windows():
    segments = lire_srt(EXEMPLE.replace("\n", "\r\n"))
    assert [s.texte for s in segments] == ["Bonjour, tout le monde.", "Je reviens."]


def test_format_horodatage():
    assert format_horodatage(3725.9) == "01:02:05"


def test_choisit_la_piste_francaise_complete():
    pistes = [
        {"index": 2, "codec_name": "subrip", "tags": {"language": "eng"}},
        {"index": 3, "codec_name": "subrip", "tags": {"language": "fre"}, "disposition": {"forced": 1}},
        {"index": 4, "codec_name": "hdmv_pgs_subtitle", "tags": {"language": "fre"}},
        {"index": 5, "codec_name": "subrip", "tags": {"language": "fre"}, "disposition": {"forced": 0}},
    ]
    assert choisir_piste(pistes)["index"] == 5


def test_ignore_les_pistes_dans_une_autre_langue():
    assert choisir_piste([{"index": 2, "codec_name": "subrip", "tags": {"language": "eng"}}]) is None


def test_choisit_la_piste_anglaise_si_demandee():
    pistes = [
        {"index": 2, "codec_name": "subrip", "tags": {"language": "fre"}},
        {"index": 3, "codec_name": "subrip", "tags": {"language": "eng"}},
    ]
    assert choisir_piste(pistes, "en")["index"] == 3

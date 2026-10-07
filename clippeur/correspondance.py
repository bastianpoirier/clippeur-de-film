"""Retrouve dans la transcription les citations trouvées en ligne (F15).

La comparaison tolère les petites différences de formulation entre une citation
recopiée sur un site et les sous-titres (ponctuation, mots ajoutés ou manquants).
"""

import re
import unicodedata

from rapidfuzz import fuzz, process

SEUIL = 82  # sur 100 : en dessous, la ressemblance est trop faible pour être fiable
MOTS_MIN = 4  # les répliques plus courtes (« Oh mon Dieu ») se retrouvent partout
REPLIQUES_PAR_FENETRE = 4  # une citation peut s'étaler sur plusieurs sous-titres


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", sans_accents.lower()))


def _fenetres(segments: list[dict]) -> list[tuple[str, float, float]]:
    """Textes formés de 1 à 3 répliques consécutives, avec leurs horaires."""
    fenetres = []
    for i in range(len(segments)):
        for n in range(1, REPLIQUES_PAR_FENETRE + 1):
            if i + n > len(segments):
                break
            groupe = segments[i:i + n]
            fenetres.append((normaliser(" ".join(s["texte"] for s in groupe)), groupe[0]["debut"], groupe[-1]["fin"]))
    return fenetres


def localiser(repliques: list[str], fenetres: list[tuple[str, float, float]]) -> dict | None:
    """Cherche chaque réplique d'une citation ; renvoie la meilleure position trouvée."""
    trouvees = []
    for replique in repliques:
        cible = normaliser(replique)
        if len(cible.split()) < MOTS_MIN:
            continue
        # Les citations longues sont coupées en plusieurs sous-titres : on compare le début
        # de la citation (une douzaine de mots), qui tient dans quelques répliques consécutives.
        cible = " ".join(cible.split()[:12])
        # partial_ratio cherche le plus court des deux textes dans le plus long : sans ce filtre,
        # une réplique de deux lettres (« yo ») se retrouverait « à 100 % » dans n'importe quelle citation.
        candidats = [(i, f[0]) for i, f in enumerate(fenetres) if len(f[0]) >= 0.8 * len(cible)]
        if not candidats:
            continue
        meilleurs = process.extract(cible, [c[1] for c in candidats], scorer=fuzz.partial_ratio,
                                    score_cutoff=SEUIL, limit=10)
        if not meilleurs:
            continue
        # Plusieurs passages contiennent souvent la citation (avec une réplique de plus avant ou après) :
        # parmi les meilleurs scores, le plus court est le plus précis.
        score = max(m[1] for m in meilleurs)
        _, _, rang = min((m for m in meilleurs if m[1] >= score - 1), key=lambda m: len(m[0]))
        index = candidats[rang][0]
        trouvees.append({"replique": replique, "score": round(score), "debut": fenetres[index][1],
                         "fin": fenetres[index][2]})
    if not trouvees:
        return None
    trouvees.sort(key=lambda t: t["debut"])
    return {
        "debut": trouvees[0]["debut"],
        "fin": trouvees[-1]["fin"],
        "score": max(t["score"] for t in trouvees),
        "replique_trouvee": max(trouvees, key=lambda t: t["score"])["replique"],
    }


def placer_dans_le_film(resultats: list[dict], segments: list[dict]) -> list[dict]:
    """Ajoute à chaque résultat de recherche sa position dans le film (ou None s'il n'y est pas)."""
    fenetres = _fenetres(sorted(segments, key=lambda s: s["debut"]))
    return [r | {"position": localiser(r["repliques"], fenetres)} for r in resultats]

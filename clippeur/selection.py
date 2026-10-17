"""Choix des meilleurs moments du film (F16).

Chaque fenêtre de 1 à 2 minutes reçoit une note qui combine :
- la popularité en ligne : citations de Wikiquote retrouvées dans les dialogues et gardées par l'utilisateur ;
- des indices calculés en local, seconde par seconde : densité des dialogues, volume sonore
  comparé au volume habituel du film, répliques exclamatives ou interrogatives.
Sans recherche en ligne (pas de connexion, pas de page Wikiquote), seuls les indices locaux comptent.
On garde les meilleures fenêtres sans chevauchement, et on cale leurs bornes sur des changements de plan.
"""

import re
import statistics
import unicodedata
from dataclasses import asdict, dataclass, field

from clippeur.segments import Segment

DUREE_MIN = 60.0
DUREE_MAX = 120.0
# Le calage sur les changements de plan peut rallonger un extrait de quelques secondes :
# on garde de la marge pour ne jamais dépasser DUREE_MAX.
MARGE_CALAGE = 4.0

POIDS_PAROLE = 0.45
POIDS_VOLUME = 0.35
POIDS_EMOTION = 0.20
# Avec la reconnaissance des sons (F13), une part de la note locale va aux rires, cris, explosions et musique.
POIDS_AVEC_SONS = {"parole": 0.35, "volume": 0.25, "emotion": 0.15, "sons": 0.25}
POIDS_MUSIQUE = 0.5  # la musique seule signale moins souvent un moment fort que des rires ou des cris
SEUIL_SON = 0.15  # probabilité au-dessus de laquelle un son est mentionné dans la raison du choix
# Le modèle donne souvent des probabilités modestes (0,2 ou 0,3 pour des rires nets) : chaque famille
# est ramenée à l'échelle du film, sans descendre sous ce plancher pour ne pas grossir du bruit.
PLANCHER_ECHELLE_SON = 0.2

# Quand des citations cultes ont été retrouvées, elles pèsent plus que les indices locaux.
POIDS_CULTE = 0.60
POIDS_LOCAL = 0.40


@dataclass
class Extrait:
    numero: int
    debut: float
    fin: float
    score: float
    titre: str
    raison: str
    repliques: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)

    @property
    def duree(self) -> float:
        return self.fin - self.debut

    def vers_dict(self) -> dict:
        return asdict(self) | {"duree": round(self.duree, 1)}


def _notes_par_seconde(segments: list[Segment], volume: list[float], duree: int,
                       sons: dict | None = None) -> dict[str, list[float]]:
    """Calcule, pour chaque seconde, les indices locaux ramenés entre 0 et 1."""
    mots = [0.0] * duree
    emotion = [0.0] * duree
    for s in segments:
        debut, fin = int(s.debut), max(int(s.debut) + 1, int(s.fin))
        nb_mots = len(s.texte.split())
        for t in range(debut, min(fin, duree)):
            mots[t] += nb_mots / (fin - debut)
        if debut < duree:
            emotion[debut] += min(s.texte.count("!") + s.texte.count("?"), 2) / 2

    # On parle en moyenne 2 à 3 mots par seconde : 3 mots/s = dialogue très dense.
    parole = [min(m / 3, 1.0) for m in mots]

    vol = (volume + [volume[-1] if volume else -90.0] * duree)[:duree]
    mediane = statistics.median(vol) if vol else -90.0
    fort = sorted(vol)[int(len(vol) * 0.95)] if vol else mediane
    ecart = max(fort - mediane, 1.0)
    volume_relatif = [min(max((v - mediane) / ecart, 0.0), 1.0) for v in vol]

    notes = {"parole": parole, "volume": volume_relatif, "emotion": [min(e, 1.0) for e in emotion]}
    if sons:
        familles = {f: (valeurs + [0.0] * duree)[:duree] for f, valeurs in sons.items()}
        for f, valeurs in familles.items():
            notes[f"son:{f}"] = valeurs
        echelle = {f: max(max(v, default=0.0), PLANCHER_ECHELLE_SON) for f, v in familles.items()}
        relatives = {f: [min(x / echelle[f], 1.0) * (POIDS_MUSIQUE if f == "musique" else 1.0) for x in v]
                     for f, v in familles.items()}
        notes["sons"] = [max(relatives[f][t] for f in relatives) for t in range(duree)]
    return notes


def _sommes_cumulees(valeurs: list[float]) -> list[float]:
    cumul = [0.0]
    for v in valeurs:
        cumul.append(cumul[-1] + v)
    return cumul


def _moyenne(cumul: list[float], debut: float, fin: float) -> float:
    a, b = int(debut), max(int(debut) + 1, int(fin))
    b = min(b, len(cumul) - 1)
    return (cumul[b] - cumul[a]) / max(b - a, 1)


def _coupe_une_replique(instant: float, segments: list[Segment]) -> bool:
    return any(s.debut < instant < s.fin for s in segments)


def _caler_debut(debut: float, plans: list[float], segments: list[Segment]) -> float:
    """Recule le début jusqu'au changement de plan le plus proche, sans couper de réplique."""
    possibles = [p for p in plans if debut - MARGE_CALAGE <= p <= debut and not _coupe_une_replique(p, segments)]
    return max(possibles) if possibles else max(0.0, debut - 0.3)


def _caler_fin(fin: float, plans: list[float], segments: list[Segment], duree_film: float) -> float:
    """Avance la fin jusqu'au changement de plan le plus proche, sans couper de réplique."""
    possibles = [p for p in plans if fin <= p <= fin + MARGE_CALAGE and not _coupe_une_replique(p, segments)]
    return min(possibles) if possibles else min(duree_film, fin + 0.5)


def _titre(repliques: list[Segment]) -> str:
    """La réplique la plus marquante de l'extrait : exclamative de préférence, puis la plus longue."""
    meilleure = max(repliques, key=lambda s: ("!" in s.texte, min(len(s.texte.split()), 12)))
    return meilleure.texte


def _raison(notes: dict, cumul: dict, debut: float, fin: float, nb_emotion: int) -> str:
    raisons = []
    if _moyenne(cumul["parole"], debut, fin) > 1.2 * statistics.mean(notes["parole"]):
        raisons.append("dialogues denses")
    if _moyenne(cumul["volume"], debut, fin) > 1.5 * statistics.mean(notes["volume"]):
        raisons.append("passages sonores intenses")
    if nb_emotion >= 3:
        raisons.append(f"{nb_emotion} répliques exclamatives ou interrogatives")
    # Sons reconnus (F13) : nettement plus présents dans l'extrait que dans le reste du film.
    for cle in [c for c in notes if c.startswith("son:")]:
        presence = max(notes[cle][int(debut):max(int(fin), int(debut) + 1)], default=0.0)
        if presence >= SEUIL_SON and _moyenne(cumul[cle], debut, fin) > 2 * statistics.mean(notes[cle]):
            raisons.append(NOMS_SONS.get(cle[4:], cle[4:]))
    return ", ".join(raisons).capitalize() if raisons else "Scène dialoguée"


NOMS_SONS = {"rires": "rires", "cris": "cris", "explosions": "explosions ou coups de feu", "musique": "musique"}


def _court(texte: str, longueur: int = 90) -> str:
    return texte if len(texte) <= longueur else texte[:longueur].rsplit(" ", 1)[0] + "…"


def _references_dans(debut: float, fin: float, references: list[dict]) -> list[dict]:
    """Citations cultes dont la position trouvée tombe dans la fenêtre."""
    return [r for r in references if debut <= (r["position"]["debut"] + r["position"]["fin"]) / 2 <= fin]


def proposer_extraits(
    segments: list[Segment],
    plans: list[float],
    volume: list[float],
    duree_film: float,
    nombre: int = 10,
    references: list[dict] | None = None,
    sons: dict | None = None,
) -> list[Extrait]:
    """Renvoie les `nombre` meilleurs extraits, triés du meilleur au moins bon.

    `references` : citations trouvées en ligne et placées dans le film (avec « position »).
    Celles que l'utilisateur a écartées (« retenue » à faux) ne comptent pas.
    `sons` : probabilités seconde par seconde des familles de sons (rires, cris, explosions, musique).
    """
    segments = sorted(segments, key=lambda s: s.debut)
    if not segments:
        return []
    references = [r for r in (references or []) if r.get("position") and r.get("retenue", True)]
    avec_recherche = bool(references)
    duree = int(duree_film) + 1
    notes = _notes_par_seconde(segments, volume, duree, sons)
    cumul = {nom: _sommes_cumulees(valeurs) for nom, valeurs in notes.items()}
    poids = POIDS_AVEC_SONS if "sons" in notes else {
        "parole": POIDS_PAROLE, "volume": POIDS_VOLUME, "emotion": POIDS_EMOTION}

    def note(debut: float, fin: float) -> float:
        locale = sum(p * _moyenne(cumul[indice], debut, fin) for indice, p in poids.items())
        if not avec_recherche:
            return locale
        culte = min(1.0, sum(r["popularite"] / 5 for r in _references_dans(debut, fin, references)))
        return POIDS_CULTE * culte + POIDS_LOCAL * locale

    # Candidats : commencer au début d'une réplique et finir à la fin d'une réplique,
    # pour ne jamais couper une phrase. On garde la meilleure fin pour chaque début.
    candidats = []
    for i, premier in enumerate(segments):
        meilleur = None
        for dernier in segments[i:]:
            longueur = dernier.fin - premier.debut
            if longueur > DUREE_MAX - 2 * MARGE_CALAGE:
                break
            if longueur >= DUREE_MIN:
                n = note(premier.debut, dernier.fin)
                if meilleur is None or n > meilleur[0]:
                    meilleur = (n, premier.debut, dernier.fin)
        if meilleur:
            candidats.append(meilleur)

    # On prend les meilleurs candidats qui ne se chevauchent pas, avec un écart suffisant
    # pour que le calage sur les plans ne les fasse pas se chevaucher ensuite.
    ecart = 2 * MARGE_CALAGE
    retenus: list[tuple[float, float, float]] = []
    for n, debut, fin in sorted(candidats, reverse=True):
        if all(fin + ecart <= d or debut >= f + ecart for _, d, f in retenus):
            retenus.append((n, debut, fin))
        if len(retenus) == nombre:
            break

    extraits = []
    for numero, (n, debut, fin) in enumerate(retenus, start=1):
        dedans = [s for s in segments if s.debut >= debut and s.fin <= fin]
        nb_emotion = sum(1 for s in dedans if "!" in s.texte or "?" in s.texte)
        titre, raisons, sources = _titre(dedans), [], []

        cultes = sorted(_references_dans(debut, fin, references), key=lambda r: -r["popularite"])
        for r in cultes:
            raisons.append(f"Citation culte ({r['source']}) : « {_court(r['titre'])} »")
            source = {"nom": r["source"], "url": r.get("source_url") or ""}
            if source not in sources:
                sources.append(source)
        raisons.append(_raison(notes, cumul, debut, fin, nb_emotion))
        if cultes:
            titre = _court(cultes[0]["titre"])

        extraits.append(Extrait(
            numero=numero,
            debut=round(_caler_debut(debut, plans, segments), 2),
            fin=round(_caler_fin(fin, plans, segments, duree_film), 2),
            score=round(n * 100, 1),
            titre=titre,
            raison=" · ".join(raisons),
            repliques=[s.texte for s in dedans],
            sources=sources,
        ))
    return extraits


def nom_de_fichier(texte: str, longueur_max: int = 40) -> str:
    """« Oh, mon Dieu ! » → « oh-mon-dieu »."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    mots = re.findall(r"[a-z0-9]+", sans_accents.lower())
    nom = "-".join(mots)[:longueur_max].rstrip("-")
    return nom or "extrait"

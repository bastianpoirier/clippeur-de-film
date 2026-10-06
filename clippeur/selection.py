"""Choix des meilleurs moments du film, à partir d'indices calculés en local.

Version provisoire, en attendant la recherche en ligne et l'analyse par l'IA (étapes 2 et 5).
Chaque seconde du film reçoit une note qui combine :
- la densité des dialogues (mots par seconde) ;
- le volume sonore, comparé au volume habituel du film ;
- les répliques exclamatives ou interrogatives, signe d'une scène tendue ou émotive.
On cherche ensuite les fenêtres de 1 à 2 minutes qui ont la meilleure note moyenne,
sans chevauchement, et on cale leurs bornes sur des changements de plan.
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


@dataclass
class Extrait:
    numero: int
    debut: float
    fin: float
    score: float
    titre: str
    raison: str
    repliques: list[str] = field(default_factory=list)

    @property
    def duree(self) -> float:
        return self.fin - self.debut

    def vers_dict(self) -> dict:
        return asdict(self) | {"duree": round(self.duree, 1)}


def _notes_par_seconde(segments: list[Segment], volume: list[float], duree: int) -> dict[str, list[float]]:
    """Calcule, pour chaque seconde, les trois indices ramenés entre 0 et 1."""
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

    return {"parole": parole, "volume": volume_relatif, "emotion": [min(e, 1.0) for e in emotion]}


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
    return ", ".join(raisons).capitalize() if raisons else "Scène dialoguée"


def proposer_extraits(
    segments: list[Segment],
    plans: list[float],
    volume: list[float],
    duree_film: float,
    nombre: int = 10,
) -> list[Extrait]:
    """Renvoie les `nombre` meilleurs extraits, triés du meilleur au moins bon."""
    segments = sorted(segments, key=lambda s: s.debut)
    if not segments:
        return []
    duree = int(duree_film) + 1
    notes = _notes_par_seconde(segments, volume, duree)
    cumul = {nom: _sommes_cumulees(valeurs) for nom, valeurs in notes.items()}

    def note(debut: float, fin: float) -> float:
        return (
            POIDS_PAROLE * _moyenne(cumul["parole"], debut, fin)
            + POIDS_VOLUME * _moyenne(cumul["volume"], debut, fin)
            + POIDS_EMOTION * _moyenne(cumul["emotion"], debut, fin)
        )

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
        extraits.append(Extrait(
            numero=numero,
            debut=round(_caler_debut(debut, plans, segments), 2),
            fin=round(_caler_fin(fin, plans, segments, duree_film), 2),
            score=round(n * 100, 1),
            titre=_titre(dedans),
            raison=_raison(notes, cumul, debut, fin, nb_emotion),
            repliques=[s.texte for s in dedans],
        ))
    return extraits


def nom_de_fichier(texte: str, longueur_max: int = 40) -> str:
    """« Oh, mon Dieu ! » → « oh-mon-dieu »."""
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    mots = re.findall(r"[a-z0-9]+", sans_accents.lower())
    nom = "-".join(mots)[:longueur_max].rstrip("-")
    return nom or "extrait"

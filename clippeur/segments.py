"""Un segment = une réplique du film avec son horodatage."""

from dataclasses import asdict, dataclass


@dataclass
class Segment:
    debut: float  # en secondes depuis le début du film
    fin: float
    texte: str

    def vers_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def depuis_dict(cls, d: dict) -> "Segment":
        return cls(debut=d["debut"], fin=d["fin"], texte=d["texte"])


def format_horodatage(secondes: float) -> str:
    """Affiche 3725.5 sous la forme 01:02:05."""
    s = int(secondes)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"

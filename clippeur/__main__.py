"""Point d'entrée en ligne de commande : python -m clippeur transcrire <film>"""

import argparse
import sys
from pathlib import Path

from clippeur import cache
from clippeur.segments import format_horodatage
from clippeur.transcription import MODELE_PAR_DEFAUT, transcrire


def commande_transcrire(args: argparse.Namespace) -> int:
    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        print(f"Fichier introuvable : {film}", file=sys.stderr)
        return 1

    resultat = transcrire(film, modele=args.modele, forcer=args.forcer)
    segments = resultat["segments"]
    print(f"\n{len(segments)} réplique{'s' if len(segments) > 1 else ''} ({resultat['source']}).")
    for s in segments[:5]:
        print(f"  [{format_horodatage(s['debut'])}] {s['texte']}")
    if len(segments) > 5:
        print("  ...")
    print(f"\nRésultat complet : {cache.dossier_du_film(film) / 'transcription.json'}")
    return 0


def commande_interface(args: argparse.Namespace) -> int:
    from clippeur.web import lancer  # Flask n'est chargé que pour l'interface

    lancer(port=args.port, ouvrir_navigateur=not args.sans_navigateur)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="clippeur", description="Clippeur de film")
    sous = parser.add_subparsers(dest="commande", required=True)

    p = sous.add_parser("transcrire", help="transcrit les dialogues du film avec leurs horaires")
    p.add_argument("film", help="chemin du fichier vidéo")
    p.add_argument("--modele", default=MODELE_PAR_DEFAUT,
                   help="modèle Whisper : tiny, base, small, medium (plus gros = plus précis mais plus lent)")
    p.add_argument("--forcer", action="store_true", help="refait la transcription même si elle est en cache")
    p.set_defaults(fonction=commande_transcrire)

    p = sous.add_parser("interface", help="ouvre la page web locale")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--sans-navigateur", action="store_true", help="n'ouvre pas le navigateur automatiquement")
    p.set_defaults(fonction=commande_interface)

    args = parser.parse_args()
    return args.fonction(args)


if __name__ == "__main__":
    sys.exit(main())

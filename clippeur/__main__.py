"""Point d'entrée en ligne de commande : python -m clippeur transcrire <film>"""

import argparse
import sys
from pathlib import Path

from clippeur import cache
from clippeur.segments import format_horodatage
from clippeur.transcription import LANGUE_PAR_DEFAUT, MODELE_PAR_DEFAUT, FilmIllisible, transcrire


def commande_transcrire(args: argparse.Namespace) -> int:
    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        print(f"Fichier introuvable : {film}", file=sys.stderr)
        return 1

    try:
        resultat = transcrire(film, modele=args.modele, langue=args.langue, forcer=args.forcer)
    except FilmIllisible as e:
        print(e, file=sys.stderr)
        return 1
    segments = resultat["segments"]
    print(f"\n{len(segments)} réplique{'s' if len(segments) > 1 else ''} ({resultat['source']}).")
    for s in segments[:5]:
        print(f"  [{format_horodatage(s['debut'])}] {s['texte']}")
    if len(segments) > 5:
        print("  ...")
    print(f"\nRésultat complet : {cache.dossier_du_film(film) / f'transcription_{args.langue}.json'}")
    return 0


def commande_extraits(args: argparse.Namespace) -> int:
    from clippeur.export import dossier_de_sortie, exporter
    from clippeur.extraits import proposer
    from clippeur.transcription import afficher_dans_terminal

    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        print(f"Fichier introuvable : {film}", file=sys.stderr)
        return 1
    try:
        proposition = proposer(film, args.langue, args.nombre, afficher_dans_terminal)
    except FilmIllisible as e:
        print(e, file=sys.stderr)
        return 1

    print()
    for e in proposition["extraits"]:
        print(f"{e['numero']:2d}. [{format_horodatage(e['debut'])} → {format_horodatage(e['fin'])}, {e['duree']:.0f} s]"
              f" note {e['score']:.0f} · {e['raison']}")
        print(f"    « {e['titre']} »")
    if args.exporter:
        exporter(film, proposition["extraits"], afficher_dans_terminal)
        print(f"Extraits dans : {dossier_de_sortie(film)}")
    return 0


def commande_rechercher(args: argparse.Namespace) -> int:
    from clippeur.identification import identifier, nom_complet
    from clippeur.recherche import rechercher
    from clippeur.transcription import afficher_dans_terminal

    film = Path(args.film).expanduser().resolve()
    if not film.is_file():
        print(f"Fichier introuvable : {film}", file=sys.stderr)
        return 1
    identification = identifier(film, forcer=True)
    print(f"Identifié : {nom_complet(identification['fiche'])} (d'après : {identification['fiche']['source']})")
    if identification["avertissement"]:
        print(f"  ⚠ {identification['avertissement']}")
    try:
        transcription = transcrire(film, langue=args.langue)
    except FilmIllisible as e:
        print(e, file=sys.stderr)
        return 1
    resultat = rechercher(film, identification["fiche"], transcription, afficher_dans_terminal, page=args.page)

    print(f"\nPage Wikiquote : {resultat['page'] or 'aucune'}")
    autres = [p for p in resultat["pages_possibles"] if p != resultat["page"]]
    if autres:
        print(f"  Autres pages possibles (option --page) : {', '.join(autres)}")
    for a in resultat["avertissements"]:
        print(f"⚠ {a}")
    for r in sorted(resultat["resultats"], key=lambda r: r["position"] is None):
        position = f"à {format_horodatage(r['position']['debut'])}" if r["position"] else "non retrouvée"
        print(f"[{position}] {r['titre']}")
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
    p.add_argument("--langue", choices=["fr", "en"], default=LANGUE_PAR_DEFAUT, help="langue des dialogues (fr par défaut)")
    p.add_argument("--forcer", action="store_true", help="refait la transcription même si elle est en cache")
    p.set_defaults(fonction=commande_transcrire)

    p = sous.add_parser("extraits", help="propose les meilleurs extraits du film, et les exporte si demandé")
    p.add_argument("film", help="chemin du fichier vidéo")
    p.add_argument("--langue", choices=["fr", "en"], default=LANGUE_PAR_DEFAUT, help="langue des dialogues (fr par défaut)")
    p.add_argument("--nombre", type=int, default=10, help="nombre d'extraits (10 par défaut)")
    p.add_argument("--exporter", action="store_true", help="découpe et enregistre les extraits en MP4")
    p.set_defaults(fonction=commande_extraits)

    p = sous.add_parser("rechercher", help="identifie le film et recherche ses citations cultes sur Wikiquote")
    p.add_argument("film", help="chemin du fichier vidéo")
    p.add_argument("--langue", choices=["fr", "en"], default=LANGUE_PAR_DEFAUT, help="langue des dialogues (fr par défaut)")
    p.add_argument("--page", help="page Wikiquote à utiliser, si celle trouvée automatiquement n'est pas la bonne")
    p.set_defaults(fonction=commande_rechercher)

    p = sous.add_parser("interface", help="ouvre la page web locale")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--sans-navigateur", action="store_true", help="n'ouvre pas le navigateur automatiquement")
    p.set_defaults(fonction=commande_interface)

    args = parser.parse_args()
    return args.fonction(args)


if __name__ == "__main__":
    sys.exit(main())

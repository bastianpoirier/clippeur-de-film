"""Citations célèbres depuis Wikiquote (F7), via l'API officielle de MediaWiki.

Wikiquote existe dans plusieurs langues : on interroge celle des dialogues du film,
pour que les citations soient formulées comme dans les sous-titres.
"""

import re

import requests

ENTETES = {"User-Agent": "clippeur-de-film/0.1 (application personnelle ; https://github.com/bastianpoirier/clippeur-de-film)"}
MOTS_MIN = 3  # en dessous, une réplique (« Oui. ») est trop banale pour retrouver une scène


def _api(langue: str, **parametres) -> dict:
    reponse = requests.get(f"https://{langue}.wikiquote.org/w/api.php",
                           params={"format": "json", "formatversion": 2, **parametres},
                           headers=ENTETES, timeout=20)
    reponse.raise_for_status()
    return reponse.json()


def pages_possibles(langue: str, fiche: dict) -> list[str]:
    """Pages Wikiquote qui peuvent correspondre à l'œuvre, la plus probable en premier.

    Pour une série, la page de la saison passe avant celle de la série. La liste est proposée
    à l'utilisateur pour qu'il puisse choisir une autre page si la première n'est pas la bonne.
    """
    titres = [t for t in dict.fromkeys((fiche.get("titre_original"), fiche.get("titre"))) if t]
    exacts = []
    if fiche.get("type") == "serie" and fiche.get("saison"):
        exacts += [f"{t} (season {fiche['saison']})" if langue == "en" else f"{t} (saison {fiche['saison']})"
                   for t in titres]
    exacts += titres

    trouvees: list[str] = []
    for recherche in exacts:
        for r in _api(langue, action="query", list="search", srsearch=recherche, srlimit=6)["query"]["search"]:
            if r["title"] not in trouvees:
                trouvees.append(r["title"])

    def rang(page: str) -> tuple:
        bas = page.lower()
        exact = next((i for i, e in enumerate(exacts) if e.lower() == bas), len(exacts))
        contient = any(t.lower() in bas for t in titres)
        return exact, not contient

    return sorted(trouvees, key=rang)[:8]


def page_probable(fiche: dict, possibles: list[str]) -> str | None:
    """La page la plus probable, si elle porte au moins le titre de l'œuvre."""
    titres = [t.lower() for t in (fiche.get("titre_original"), fiche.get("titre")) if t]
    return next((p for p in possibles if any(t in p.lower() for t in titres)), None)


def _blocs_entre_accolades(texte: str, debut: str) -> list[str]:
    """Contenu de chaque modèle {{debut|...}}, en respectant les accolades imbriquées."""
    blocs = []
    for m in re.finditer(r"\{\{\s*" + debut + r"\s*\|", texte, re.IGNORECASE):
        profondeur, i = 2, m.end()
        while i < len(texte) and profondeur:
            if texte.startswith("{{", i):
                profondeur, i = profondeur + 2, i + 2
            elif texte.startswith("}}", i):
                profondeur, i = profondeur - 2, i + 2
            else:
                i += 1
        blocs.append(texte[m.end(): i - 2])
    return blocs


def nettoyer(wikitexte: str) -> str:
    """Retire la syntaxe wiki pour ne garder que le texte lisible."""
    t = re.sub(r"\{\{\s*(?:Personnage|w|lang\|\w+)\s*\|([^{}|]*)(?:\|[^{}]*)?\}\}", r"\1", wikitexte, flags=re.I)
    t = re.sub(r"\{\{formatnum:([^}]*)\}\}", r"\1", t)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"\[[^\[\]]*\]", "", t)  # indications de mise en scène : « [Jesse filme Walter] »
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"'{2,}", "", t)  # gras et italique wiki : '' ''' '''''
    # Une ligne sans aucune lettre (reste de mise en forme) ne contient pas de réplique.
    return t.strip() if re.search(r"\w", t) else ""


def _sans_personnage(ligne: str) -> str:
    """« Walter : Je suis le danger. » → « Je suis le danger. »"""
    m = re.match(r"^\s*[^:]{1,40}?\s?:\s+(.+)$", ligne)
    return m.group(1).strip() if m else ligne.strip()


def _section_episode(wikitexte: str, saison: int, episode: int) -> str | None:
    """Sur Wikiquote anglais, chaque épisode a sa section, notée « [1.01] »."""
    marque = f"[{saison}.{episode:02d}]"
    sections = re.split(r"(?m)^(==+[^=\n].*?==+)\s*$", wikitexte)
    for i in range(1, len(sections) - 1, 2):
        if marque in sections[i]:
            return sections[i + 1]
    return None


def extraire_citations(wikitexte: str, fiche: dict) -> list[list[str]]:
    """Renvoie une liste de citations ; chaque citation est une liste de répliques."""
    if fiche.get("type") == "serie" and fiche.get("saison") and fiche.get("episode"):
        section = _section_episode(wikitexte, int(fiche["saison"]), int(fiche["episode"]))
        if section is not None:
            wikitexte = section

    citations = []
    # Wikiquote français : modèles {{citation|...}} ou {{citation|citation=...}}.
    for bloc in _blocs_entre_accolades(wikitexte, "citation"):
        bloc = re.sub(r"^\s*citation\s*=", "", bloc)
        lignes = [_sans_personnage(nettoyer(l)) for l in re.split(r"\n|<br\s*/?>", bloc)]
        citations.append([l for l in lignes if l])

    # Wikiquote anglais : lignes commençant par « : » ou « * », regroupées par paragraphe.
    if not citations:
        courant: list[str] = []
        for ligne in wikitexte.split("\n"):
            if re.match(r"^[:*]+(?!\s*\[\[(?:File|Image|Fichier):)", ligne) and not ligne.startswith(":'''Season"):
                texte = _sans_personnage(nettoyer(ligne.lstrip(":* ")))
                if texte:
                    courant.append(texte)
            elif courant:
                citations.append(courant)
                courant = []
        if courant:
            citations.append(courant)

    return [c for c in citations if any(len(l.split()) >= MOTS_MIN for l in c)]


def citations_wikiquote(fiche: dict, langue: str, page: str | None = None) -> dict:
    """Renvoie {page, url, pages_possibles, citations: [{repliques, source, source_url}]} (F7, F9).

    `page` : page choisie par l'utilisateur ; sinon, la plus probable.
    """
    possibles = pages_possibles(langue, fiche)
    if page is None:
        page = page_probable(fiche, possibles)
    elif page not in possibles:
        possibles.insert(0, page)
    if page is None:
        return {"page": None, "url": None, "pages_possibles": possibles, "citations": []}
    wikitexte = _api(langue, action="parse", page=page, prop="wikitext")["parse"]["wikitext"]
    url = f"https://{langue}.wikiquote.org/wiki/{page.replace(' ', '_')}"
    return {
        "page": page,
        "url": url,
        "pages_possibles": possibles,
        "citations": [{"repliques": c, "source": f"Wikiquote ({langue})", "source_url": url}
                      for c in extraire_citations(wikitexte, fiche)],
    }

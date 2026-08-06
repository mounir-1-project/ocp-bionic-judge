"""
La documentation decrit-elle le systeme qui existe ?

POURQUOI CE FICHIER EXISTE
----------------------------------------------------------------------------
La documentation est la seule partie du depot qu'aucun outil ne verifiait. Le
code a des tests, le referentiel a un controle d'integrite en integration
continue, le poste a trois bancs — les 2 400 lignes de Markdown, elles,
pouvaient affirmer n'importe quoi sans que rien ne bronche. Et elles l'ont
fait :

  - le rapport technique presentait un modele economique de 29 parametres et un
    solde annuel de 1,07 M MAD, alors que la couche economique avait ete
    RETIREE du systeme et que deux tests interdisent son retour ;
  - il citait `test_le_gain_ne_vient_pas_dune_baisse_de_frequence` comme verrou
    de son principe le plus important : ce test n'a jamais existe ;
  - le runbook d'exploitation demandait au technicien de consulter chaque jour
    `/api/business/assumptions`, un endpoint supprime ;
  - le README listait « energie thermique evacuee en exces » parmi les
    indicateurs produits, quelques paragraphes avant d'expliquer que cette
    formulation avait ete retiree.

Une documentation fausse est pire qu'une documentation absente : elle est lue,
et elle est crue. Ces controles la rattachent au code.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

# `docs/audits/` EST ECARTE, ET LA RAISON EST UN CONTRAT, PAS UNE COMMODITE.
#
# Ce fichier verifie que la documentation decrit LE SYSTEME QUI EXISTE. Un
# journal d'audit decrit son HISTOIRE : il cite par construction des endpoints
# supprimes (`/api/business/assumptions`), des tests qui n'existaient pas, des
# montants retires — c'est precisement son objet, et c'est ce qui rend une
# correction retracable.
#
# Les inclure obligerait a echapper chaque citation, donc a rendre le journal
# illisible pour satisfaire un controle qui ne le vise pas. Le meme raisonnement
# que `ABSENCES_ASSUMEES` ci-dessous, applique a un dossier entier plutot qu'a
# une liste de noms.
#
# Contrepartie assumee : si de la documentation d'usage etait un jour ecrite
# sous `docs/audits/`, elle echapperait a ces quatre controles. Elle n'y a pas
# sa place.
AUDITS = RACINE / "docs" / "audits"
DOCUMENTS = [
    *sorted(p for p in (RACINE / "docs").rglob("*.md") if AUDITS not in p.parents),
    RACINE / "README.md",
]

# Noms de tests cites par la documentation POUR DIRE QU'ILS N'EXISTENT PAS.
# Toute autre citation d'un test absent est une erreur.
ABSENCES_ASSUMEES = {"test_le_gain_ne_vient_pas_dune_baisse_de_frequence"}


def _texte() -> str:
    """Concatenation de toute la documentation Markdown."""
    return "\n".join(d.read_text(encoding="utf-8") for d in DOCUMENTS)


def _routes_declarees() -> set[str]:
    """Chemins effectivement exposes par l'API.

    Returns:
        Ensemble des motifs de route, parametres compris.
    """
    module = ast.parse((RACINE / "api" / "main.py").read_text(encoding="utf-8"))
    routes = set()
    for noeud in ast.walk(module):
        if (
            isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and isinstance(noeud.func.value, ast.Name)
            and noeud.func.value.id == "app"
            and noeud.func.attr in {"get", "post", "patch", "put", "delete"}
            and noeud.args
            and isinstance(noeud.args[0], ast.Constant)
        ):
            routes.add(noeud.args[0].value)
    return routes


def test_aucun_endpoint_documente_n_a_disparu_de_l_api():
    """LE RUNBOOK ENVOYAIT L'EXPLOITANT SUR UNE URL MORTE.

    Son tableau de controles quotidiens listait `/api/business/assumptions`,
    supprime avec la couche economique. Une procedure d'exploitation qui
    demande d'ouvrir une adresse inexistante n'est pas un defaut de redaction :
    c'est une consigne infaisable, decouverte au poste.
    """
    routes = _routes_declarees()
    assert routes, "aucune route trouvee dans api/main.py"

    def existe(chemin: str) -> bool:
        if chemin in routes:
            return True
        return any(
            re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", route), chemin)
            for route in routes
        )

    fantomes = sorted({
        f"{document.relative_to(RACINE)} : {endpoint}"
        for document in DOCUMENTS
        for endpoint in set(
            re.findall(r"`(/api/[\w/{}.-]+)`", document.read_text(encoding="utf-8"))
        )
        if not existe(endpoint.rstrip("/"))
    })
    assert not fantomes, f"endpoints documentes et inexistants : {fantomes}"


def test_aucun_test_cite_par_la_documentation_n_est_absent():
    """LE RAPPORT CITAIT UN TEST INEXISTANT COMME PREUVE.

    « Un test automatise (`test_le_gain_ne_vient_pas_dune_baisse_de_frequence`)
    verrouille ce principe dans le code. » Le principe en question etait le plus
    important du chapitre — que le gain ne vienne jamais d'une baisse de
    frequence des defaillances. Le verrou annonce n'existait pas.
    """
    suite = "\n".join(
        p.read_text(encoding="utf-8") for p in (RACINE / "tests").glob("*.py")
    )
    definis = set(re.findall(r"def (test_\w+)", suite))
    fichiers = {p.stem for p in (RACINE / "tests").glob("test_*.py")}

    cites = set(re.findall(r"`(test_\w+)`", _texte()))
    absents = sorted(cites - definis - fichiers - ABSENCES_ASSUMEES)
    assert not absents, f"tests cites par la documentation et inexistants : {absents}"


def test_aucun_script_ni_cible_make_documente_n_est_absent():
    """Une commande copiee depuis la documentation doit s'executer."""
    scripts = {p.name for p in (RACINE / "scripts").glob("*")}
    cibles = set(re.findall(
        r"^([a-z][\w-]*):", (RACINE / "Makefile").read_text(encoding="utf-8"), re.M
    ))
    texte = _texte()

    manquants = [
        f"scripts/{s}" for s in set(re.findall(r"scripts/([\w.]+)", texte))
        if s not in scripts
    ] + [
        f"make {m}" for m in set(re.findall(r"make ([a-z][\w-]+)", texte))
        if m not in cibles
    ]
    assert not manquants, f"commandes documentees et inexistantes : {sorted(manquants)}"


def test_aucun_chemin_cite_par_la_documentation_n_est_absent():
    """UN DOSSIER FANTOME ETAIT AFFIRME PAR QUATRE DOCUMENTS.

    `architecture.md`, `rapport_technique.md`, le runbook et le README
    decrivaient tous un repertoire `legacy/` « conservant la version 1 ». Il
    n'a jamais existe dans ce depot. Le README lui donnait meme une ligne dans
    son tableau des modules, entre `api/` et le reste.

    Les trois controles precedents couvraient les endpoints, les noms de tests
    et les commandes. Un chemin de fichier ou de dossier n'entre dans aucune de
    ces classes : c'est le trou par lequel `legacy/` est passe.
    """
    EXTENSIONS = "py|md|yaml|yml|json|toml|js|mjs|css|html|lock|txt|ipynb|xlsx|xls|pdf"
    # Un chemin cite porte un separateur OU une extension connue.
    motif = re.compile(rf"^(?:[\w.-]+/)+[\w.-]*$|^[\w-]+\.(?:{EXTENSIONS})$")
    # UN NOM DE FICHIER SUFFIT, LE DOSSIER N'EST PAS TOUJOURS ECRIT.
    # `amdec.yaml` est cite tel quel dans quatre documents et vit dans
    # `src/domain/`. Exiger le chemin complet transformerait ce controle en
    # generateur de faux positifs, et un controle bruyant finit desactive.
    #
    # Le balayage est BORNE aux dossiers du projet. Un `rglob("*")` depuis la
    # racine traverse `.venv` et `node_modules` — des dizaines de milliers de
    # fichiers — et rendait ce controle plus lent que toute la suite. Un test
    # lent finit par ne plus etre lance, ce qui revient a ne pas l'ecrire.
    SOURCES = ("src", "api", "tests", "scripts", "docs", "notebooks",
               "data", "models", "reports", ".github")
    presents = {p.name for racine in SOURCES for p in (RACINE / racine).rglob("*")
                if "__pycache__" not in p.parts}
    presents |= {p.name for p in RACINE.iterdir()}

    def existe(chemin: str) -> bool:
        chemin = chemin.strip().rstrip("/")
        if (RACINE / chemin).exists():
            return True
        # `amdec.yaml/plan_maintenance`, `tags.yaml/equipment` : ce ne sont pas
        # des chemins de fichier mais des chemins DANS un fichier de donnees.
        # La question posee est alors l'existence du fichier porteur.
        tete = chemin.split("/", 1)[0]
        if re.search(rf"\.(?:{EXTENSIONS})$", tete):
            return tete in presents
        return "/" not in chemin and chemin in presents

    fantomes = sorted({
        f"{document.relative_to(RACINE)} : {chemin}"
        for document in DOCUMENTS
        for chemin in set(re.findall(r"`([^`\n]+)`", document.read_text(encoding="utf-8")))
        if motif.match(chemin.strip()) and not existe(chemin)
    })
    assert not fantomes, f"chemins documentes et inexistants : {fantomes}"


def test_aucun_lien_markdown_relatif_ne_pointe_dans_le_vide():
    """UN LIEN MORT VERS UN ADR QUI N'A JAMAIS EXISTE.

    `architecture.md` renvoyait a
    `decisions/ADR-008-architecture-v2-locale-deterministe.md`. Le fichier reel
    est `ADR-008-interface-isa-101.md`, et aucun ADR du depot ne porte le titre
    cite. Un lecteur qui suit la reference pour verifier une affirmation tombe
    sur rien — et conclut, a raison, que l'affirmation n'a pas ete verifiee.
    """
    morts = sorted({
        f"{document.relative_to(RACINE)} : {cible}"
        for document in DOCUMENTS
        for cible in re.findall(
            r"\]\(([^)#:]+\.md)(?:#[^)]*)?\)", document.read_text(encoding="utf-8")
        )
        if not (document.parent / cible).resolve().exists()
    })
    assert not morts, f"liens Markdown pointant dans le vide : {morts}"


def test_aucun_montant_n_est_presente_comme_un_resultat():
    """LA COUCHE ECONOMIQUE A ETE RETIREE — LE RAPPORT LA CHIFFRAIT ENCORE.

    Un tableau annoncait 543 000, 326 000 et 244 000 MAD/an de gains et un solde
    de 1,07 M MAD/an, produits par un modele qui n'existe plus. Dix-neuf de ses
    vingt-neuf parametres etaient marques « a valider par OCP » : la precision
    affichee contredisait l'incertitude declaree deux lignes plus bas.

    Le controle interdit les MONTANTS, pas le mot : les sections qui expliquent
    le retrait doivent pouvoir le nommer.
    """
    montants = []
    for document in DOCUMENTS:
        for numero, ligne in enumerate(
            document.read_text(encoding="utf-8").splitlines(), start=1
        ):
            # Un chiffre suivi de MAD dans un tableau ou une phrase affirmative.
            for trouve in re.finditer(r"[\d  .,]{3,}\s*(?:M\s*)?MAD", ligne):
                extrait = trouve.group(0)
                # Les rappels historiques sont ecrits en toutes lettres autour
                # d'une explication de retrait; on ne les confond pas avec un
                # tableau de resultats, reconnaissable a ses barres verticales.
                if ligne.lstrip().startswith("|"):
                    montants.append(
                        f"{document.relative_to(RACINE)}:{numero} — {extrait}"
                    )
    assert not montants, (
        "montants presentes dans un tableau de resultats alors qu'aucun "
        f"calcul economique n'existe : {montants}"
    )

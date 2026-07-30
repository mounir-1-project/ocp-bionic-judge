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
DOCUMENTS = [*sorted((RACINE / "docs").rglob("*.md")), RACINE / "README.md"]

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

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
import json
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


def _load_domain():
    """Domaine charge a la demande : ce fichier ne doit pas payer l'import."""
    from src.domain.knowledge import load_domain

    return load_domain()


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


def test_aucun_chiffre_cle_ne_contredit_les_artefacts():
    """LE CONTROLE QUI MANQUAIT, ET QUI VALAIT HUIT CONSTATS.

    `test_le_rapport_technique_cite_les_artefacts` verifiait `valeur not in
    rapport` — une INCLUSION DE SOUS-CHAINE. Il exigeait que la bonne valeur
    soit presente quelque part; il n'interdisait pas qu'une valeur fausse le
    soit ailleurs. La valeur attendue pour les features est la chaine « 11 », et
    « 11 » est satisfait par `1118-9754`, la taille Chemetics de l'appareil : le
    controle serait reste vert si le rapport avait ecrit « dix features »
    partout, ce qu'il faisait dans son annexe B.

    Ce test-ci pose la question inverse et decisive : le terme etant nomme, une
    AUTRE valeur le qualifie-t-elle quelque part ? Il a attrape, a son
    ecriture :

      - « 10 features » (annexe B du rapport, ADR-003)
      - « 511 heures atypiques » a trois lignes de « 530 »
      - « 22 % » et « ~80 % » de generalisation, quand l'artefact mesure 10 %
      - « 48,8 % » de couverture, quand le code en calcule 30,2 %
      - « 267 cas de test », « 84 verifications », « 62 episodes »

    Un chiffre publie a la main, jamais confronte a l'artefact qui le produit,
    finit par en differer. C'est le motif dominant de ce depot.
    """
    metrics = json.loads(
        (RACINE / "reports/project_metrics.json").read_text(encoding="utf-8")
    )
    judge = json.loads(
        (RACINE / "reports/judge_eval_summary.json").read_text(encoding="utf-8")
    )
    coverage = _load_domain().risk_coverage()

    # terme -> (valeur exacte attendue, motif qui capture la valeur ecrite)
    attendus: dict[str, tuple[str, str]] = {
        "features du modèle": (
            str(metrics["model"]["n_features"]),
            r"(\d+)\s+features?\b",
        ),
        # LE MOTIF VISE LE TOTAL, PAS LA CHARGE MENSUELLE.
        # `(\d+)\s+épisodes` attrapait « 5 épisodes/mois » — une autre
        # grandeur — et jusqu'au « 1 » de « § 9.1 Épisodes les plus marqués ».
        # Un controle bruyant finit desactive : on exige donc le qualificatif
        # qui designe le decompte sur les quatorze mois.
        #
        # CE COMMENTAIRE QUALIFIAIT CE « 5 » DE « JUSTE ». Il ne l'etait pas :
        # `kpi.alert_load` calcule `58 x 30 / 424` = **4,1**. Ecarter une valeur
        # d'un motif n'est pas la verifier, et la declarer juste au passage lui
        # a donne vingt lots de survie. Le terme « charge d'alertes » ci-dessous
        # la confronte desormais a l'artefact.
        "épisodes agrégés": (
            str(metrics["model"]["episodes"]),
            r"(\d+)\s+épisodes\s+(?:candidats|agrégés)",
        ),
        "heures atypiques": (
            str(metrics["model"]["alert_hours_historical"]),
            r"([\d   ]+)\s+heures atypiques\b",
        ),
        # LE JUMEAU AVAIT SURVECU EN CHANGEANT DE MOT.
        #
        # La docstring ci-dessus recense « 511 heures atypiques a trois lignes
        # de 530 » parmi les huit constats de ce controle. La premiere
        # occurrence a bien ete corrigee — mais la SECONDE, trois lignes plus
        # bas, ecrivait « un operateur ne traite pas 511 points d'alarme ». Le
        # motif ne la voyait pas : elle designe la meme grandeur sous un autre
        # nom, et elle est restee fausse pendant tout ce temps.
        #
        # Le motif dominant du depot, applique au controle cense l'empecher.
        "points d'alarme": (
            str(metrics["model"]["alert_hours_historical"]),
            r"([\d   ]+)\s+points d'alarme\b",
        ),
        # LA CHARGE D'ALERTES ETAIT SUR-ESTIMEE DE 22 %, ET L'ADR AVAIT RAISON.
        #
        # `kpi.alert_load` calcule `len(episodes) * 30 / span_days`, soit
        # 58 x 30 / 424 = 4,1 episodes/mois. Le README et le rapport publiaient
        # « environ 5 », ADR-003 publiait « environ 4,1 ».
        #
        # C'est la SECONDE exception a l'ordre de fraicheur etabli par cet audit
        # sur dix-huit occurrences — code/artefacts -> README -> ADR -> rapport.
        # Ici l'ADR portait la valeur juste et les deux documents les plus lus
        # portaient l'ancienne.
        "charge d'alertes": (
            f"{metrics['model']['episodes'] * 30.0 / 424:.1f}".replace(".", ","),
            r"([\d,]+)\s*(?:\*\*)?\s*épisodes?[ /](?:par )?mois",
        ),
        # Le § 12.2 publie le nombre de routes `/api/`. Il est juste
        # aujourd'hui — verifie, 45 — et rien ne le maintenait : une route
        # ajoutee ou retiree le rendait faux en silence.
        "routes de l'API": (
            str(metrics["api"]["route_count"]),
            r"expose\s+\*\*(\d+)\s+routes",
        ),
        # LA PRECISION PUBLIEE DOIT ETRE CELLE DE L'ARTEFACT.
        #
        # L'attendu etait arrondi a l'entier (`:.0f`) et le motif ne capturait
        # que des chiffres. Le banc mesure 0,086 : le document doit ecrire
        # « 8,6 % », que ce controle lisait « 8 » et comparait a « 9 ».
        # Arrondir un taux de gouvernance a l'entier fait perdre un demi-point
        # sur un chiffre qui vaut moins de dix.
        "généralisation du contrôleur": (
            f"{judge['blind_mutations']['flagged_rate'] * 100:.1f}".replace(".", ","),
            r"\*\*([\d,]+)\s*%\*\*\s*\(n\s*=\s*\d+\)",
        ),
        # LE MEME CHIFFRE EST PUBLIE TROIS FOIS DANS LE README, ET LE MOTIF
        # CI-DESSUS N'EN VOYAIT QU'UNE — celle qui porte « (n = ...) ».
        # C'est le motif de « 511 » (S26-3) : la valeur survit la ou le
        # controle ne regarde pas. Celui-ci attrape la mise en avant.
        "généralisation mise en avant": (
            f"{judge['blind_mutations']['flagged_rate'] * 100:.1f}".replace(".", ","),
            r"\*\*([\d,]+)\s*%, et c'est le chiffre à retenir",
        ),
        "part du risque couverte": (
            f"{coverage['part_couverte_pct']:.1f}".replace(".", ","),
            r"part du risque réellement couverte\s*:\s*([\d,]+)\s*%",
        ),
    }

    ecarts: list[str] = []
    for document in DOCUMENTS:
        texte = document.read_text(encoding="utf-8")
        for terme, (attendu, motif) in attendus.items():
            for trouve in re.finditer(motif, texte, re.I):
                ecrit = trouve.group(1).strip()
                normalise = re.sub(r"[   ]", "", ecrit)
                if normalise != re.sub(r"[   ]", "", attendu):
                    ligne = texte[: trouve.start()].count("\n") + 1
                    ecarts.append(
                        f"{document.relative_to(RACINE)}:{ligne} — {terme} : "
                        f"« {ecrit} » écrit, « {attendu} » mesuré"
                    )
    assert not ecarts, (
        "chiffres publiés qui contredisent les artefacts :\n  " + "\n  ".join(ecarts)
    )


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

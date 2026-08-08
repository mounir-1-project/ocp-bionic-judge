"""
Invariants de la couche service, verifies sans demarrer le service.

POURQUOI CE FICHIER EXISTE
----------------------------------------------------------------------------
Les defauts corriges dans la couche HTTP ne se voient pas a l'execution d'une
requete isolee : ils se voient dans la FORME du code. Un handler declare
`async def` sans jamais `await` fonctionne parfaitement en test unitaire et
gele la boucle d'evenements en exploitation. Une reponse d'erreur renvoyee
avant le bloc d'en-tetes repond correctement et part sans politique de
securite. Un client sortant construit sans delai maximal repond vite tant que
le reseau va bien.

Ces proprietes se verifient donc statiquement, par lecture de l'arbre
syntaxique. Aucun de ces tests ne charge la chaine de traitement : ils
s'executent en quelques millisecondes et echouent des la reintroduction du
defaut, pas au premier incident d'exploitation.

Author: Mounir Sanbouli — Stage OCP, Programme Bionic
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
API_MAIN = RACINE / "api" / "main.py"
AGENT = RACINE / "src" / "agents" / "detection_agent.py"
ALARMES = RACINE / "src" / "operations" / "alarms.py"
REJEU = RACINE / "src" / "realtime" / "replay.py"
DETECTEUR = RACINE / "src" / "models" / "detector.py"
INGESTION = RACINE / "src" / "ingest" / "dcs_loader.py"

METHODES_HTTP = {"get", "post", "patch", "put", "delete"}

# Handlers dont le corps CALCULE : chaine d'analyse, pandas, derivation PBKDF2,
# lecture disque, appel sortant. Ils doivent etre declares `def` pour que
# FastAPI les execute dans son pool de threads.
HANDLERS_CALCULANTS = frozenset({
    "analyze", "notable", "timeseries", "operational_kpi", "episodes",
    "sensor_detail", "governance", "coverage", "equipment", "topology",
    "sensor_health", "auth_login", "dashboard", "replay_start", "replay_stop",
    "workflow_templates", "judge_audit", "notification_governance",
})


def _handlers(module: ast.Module) -> list[ast.AsyncFunctionDef | ast.FunctionDef]:
    """Fonctions portant un decorateur de route FastAPI.

    Args:
        module: Arbre syntaxique du module.

    Returns:
        Les handlers de route, dans l'ordre du fichier.
    """
    trouves = []
    for noeud in module.body:
        if not isinstance(noeud, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for decorateur in noeud.decorator_list:
            if (
                isinstance(decorateur, ast.Call)
                and isinstance(decorateur.func, ast.Attribute)
                and isinstance(decorateur.func.value, ast.Name)
                and decorateur.func.value.id == "app"
                and decorateur.func.attr in METHODES_HTTP
            ):
                trouves.append(noeud)
                break
    return trouves


def test_aucun_handler_calculant_ne_reste_sur_la_boucle_d_evenements():
    """TRENTE-DEUX HANDLERS SUR QUARANTE-SEPT BLOQUAIENT LA BOUCLE.

    Ils etaient declares `async def` sans le moindre `await` : leur corps
    entier s'executait sur la boucle d'evenements, qui est unique. Parmi eux,
    `auth_login`, dont la derivation PBKDF2 est volontairement couteuse
    (600 000 iterations), et `analyze`, qui appelle le modele de langage.

    Un handler declare `def` est execute par FastAPI dans son pool de threads.
    La regle : `async def` seulement si le corps `await`, ou s'il se limite a
    des lectures en memoire.
    """
    module = ast.parse(API_MAIN.read_text(encoding="utf-8"))
    fautifs = [
        noeud.name
        for noeud in _handlers(module)
        if isinstance(noeud, ast.AsyncFunctionDef)
        and noeud.name in HANDLERS_CALCULANTS
        and not any(isinstance(x, ast.Await) for x in ast.walk(noeud))
    ]
    assert not fautifs, (
        "handlers qui calculent sur la boucle d'evenements et gelent tout le "
        f"service pendant leur execution : {fautifs}"
    )


def test_tout_handler_asynchrone_attend_reellement():
    """Un `async def` qui n'attend rien n'a aucune raison d'etre asynchrone."""
    module = ast.parse(API_MAIN.read_text(encoding="utf-8"))
    sans_await = [
        noeud.name
        for noeud in _handlers(module)
        if isinstance(noeud, ast.AsyncFunctionDef)
        and not any(isinstance(x, ast.Await) for x in ast.walk(noeud))
    ]
    # Les sondes et les lectures de dictionnaires restent asynchrones : elles
    # doivent repondre meme si le pool de threads est sature.
    tolerees = {
        "auth_status", "auth_refresh", "auth_logout", "auth_audit",
        "health", "liveness", "readiness", "model_availability",
        "version_health", "effective_config", "replay_speed", "replay_state",
        "replay_stream", "replay_alerts", "replay_disagreements",
        "notification_status", "notification_test",
    }
    assert set(sans_await) <= tolerees, (
        "nouveaux handlers asynchrones sans `await` : "
        f"{sorted(set(sans_await) - tolerees)}"
    )


def test_les_en_tetes_de_securite_sont_poses_en_un_seul_endroit():
    """LES REFUS 401, 403 ET 500 PARTAIENT SANS AUCUN EN-TETE DE DEFENSE.

    Le middleware retournait directement la reponse d'erreur, sautant le bloc
    d'en-tetes place apres `call_next`; le gestionnaire d'exception, lui,
    s'execute en dehors des middlewares applicatifs. Ce sont precisement les
    reponses qu'un attaquant provoque le plus facilement.

    Toutes passent desormais par `_durcir`, qui est le seul endroit du fichier
    ou un en-tete de securite est pose.
    """
    module = ast.parse(API_MAIN.read_text(encoding="utf-8"))
    durcir = next(
        n for n in module.body
        if isinstance(n, ast.FunctionDef) and n.name == "_durcir"
    )
    interieur = set(range(durcir.lineno, (durcir.end_lineno or durcir.lineno) + 1))

    en_tetes = {
        "Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options",
        "Referrer-Policy", "Permissions-Policy", "Strict-Transport-Security",
    }
    hors = [
        (noeud.lineno, noeud.slice.value)
        for noeud in ast.walk(module)
        if isinstance(noeud, ast.Subscript)
        and isinstance(noeud.slice, ast.Constant)
        and noeud.slice.value in en_tetes
        and noeud.lineno not in interieur
    ]
    assert not hors, f"en-tetes de securite poses hors de `_durcir` : {hors}"

    # CE CONTROLE NOMMAIT TROIS CODES ET N'EN VERIFIAIT QUE DEUX — et par
    # comparaison de CHAINES avec l'indentation exacte. Deux defauts :
    #   1. le 500, cite dans la docstring, n'etait pas couvert ;
    #   2. un simple reformatage (`ruff format`) faisait echouer le test avec le
    #      message « un refus ne passe plus par `_durcir` », qui aurait ete FAUX.
    #      Un controle dont le message ment quand il echoue est pire qu'absent.
    #
    # La propriete generale remplace les trois exemples : toute `JSONResponse`
    # portant un code d'erreur LITTERAL doit etre enveloppee par `_durcir`.
    # Elle subsume 401, 403 et 500, et couvrira tout refus ajoute demain.
    durcies = {
        id(argument)
        for noeud in ast.walk(module)
        if isinstance(noeud, ast.Call)
        and isinstance(noeud.func, ast.Name)
        and noeud.func.id == "_durcir"
        for argument in noeud.args
    }
    nus = []
    for noeud in ast.walk(module):
        if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name)):
            continue
        if noeud.func.id != "JSONResponse" or id(noeud) in durcies:
            continue
        for mot in noeud.keywords:
            if (
                mot.arg == "status_code"
                and isinstance(mot.value, ast.Constant)
                and isinstance(mot.value.value, int)
                and mot.value.value >= 400
            ):
                nus.append((noeud.lineno, mot.value.value))
    assert not nus, (
        f"reponses d'erreur qui ne passent pas par `_durcir` : {nus}. "
        f"Elles partent sans en-tete de defense — ce sont precisement celles "
        f"qu'un attaquant provoque le plus facilement."
    )

    # Et les trois codes que la docstring nomme sont bien couverts aujourd'hui.
    codes_durcis = {
        mot.value.value
        for noeud in ast.walk(module)
        if isinstance(noeud, ast.Call)
        and isinstance(noeud.func, ast.Name)
        and noeud.func.id == "_durcir"
        for argument in noeud.args
        if isinstance(argument, ast.Call)
        and isinstance(argument.func, ast.Name)
        and argument.func.id == "JSONResponse"
        for mot in argument.keywords
        if mot.arg == "status_code"
        and isinstance(mot.value, ast.Constant)
        and isinstance(mot.value.value, int)
    }
    assert {401, 403, 500} <= codes_durcis, (
        f"refus cites par cette docstring et non durcis : "
        f"{sorted({401, 403, 500} - codes_durcis)}"
    )


def test_la_configuration_est_validee_avant_tout_effet_de_bord():
    """Elle ne l'etait qu'au demarrage du `lifespan`.

    C'est-a-dire APRES la construction de la gestion de session, APRES la
    lecture du registre des techniciens et APRES le montage du middleware
    CORS — tous trois pilotes par cette meme configuration. Un lancement par
    `uvicorn api.main:app`, forme documentee dans l'en-tete du fichier,
    contournait donc le refus propre de `api/__main__.py`.
    """
    source = API_MAIN.read_text(encoding="utf-8")
    validation = source.index("config.validate()")
    for effet in ("AUTH_MANAGER = _build_auth_manager()", "app.add_middleware("):
        assert validation < source.index(effet), (
            f"`{effet}` s'execute avant la validation de la configuration"
        )


def test_le_client_du_modele_de_langage_a_un_delai_maximal():
    """SANS DELAI, UN APPEL SORTANT QUI PEND FIGE LA SUPERVISION.

    Le client etait construit avec `max_retries=0` mais aucun `timeout`. La
    couche de redaction est facultative par construction : expirer et retomber
    sur la formulation deterministe est toujours preferable a bloquer.
    """
    module = ast.parse(AGENT.read_text(encoding="utf-8"))
    appels = [
        noeud for noeud in ast.walk(module)
        if isinstance(noeud, ast.Call)
        and isinstance(noeud.func, ast.Name)
        and noeud.func.id == "ChatGoogleGenerativeAI"
    ]
    assert appels, "client Gemini introuvable"
    for appel in appels:
        noms = {mot.arg for mot in appel.keywords}
        assert "timeout" in noms, (
            "le client du modele de langage est construit sans delai maximal"
        )


def test_le_pas_d_allegement_n_entre_pas_dans_la_vitesse_de_rejeu():
    """LE SEUL REGLAGE QUE L'EXPLOITANT MANIPULE ETAIT FAUX D'UN FACTEUR TROIS.

    Le delai valait `analyze_every / speed` et s'appliquait a CHAQUE entree
    d'index, c'est-a-dire a chaque heure de process : la vitesse effective
    valait donc `speed / analyze_every`. Avec les valeurs par defaut du depot
    — REPLAY_SPEED=120, REPLAY_STEP=3 — le rejeu defilait a 40 h/s pendant que
    l'API publiait `speed_hours_per_second: 120`.
    """
    module = ast.parse(REJEU.read_text(encoding="utf-8"))
    boucle = next(
        n for n in ast.walk(module)
        if isinstance(n, ast.FunctionDef) and n.name == "_loop"
    )
    affectations = [
        n for n in ast.walk(boucle)
        if isinstance(n, ast.Assign)
        and any(isinstance(c, ast.Name) and c.id == "delay" for c in n.targets)
    ]
    assert affectations, "temporisation du rejeu introuvable"
    for affectation in affectations:
        noms = {
            n.attr for n in ast.walk(affectation.value) if isinstance(n, ast.Attribute)
        }
        assert "_analyze_every" not in noms, (
            "le pas d'allegement entre dans la temporisation : la vitesse "
            "annoncee n'est pas la vitesse reelle"
        )


def test_le_mode_synchrone_respecte_les_instants_incontournables():
    """LA GARANTIE N'ETAIT TENUE QUE PAR UN DES DEUX CHEMINS D'EXECUTION.

    `_instants_incontournables` etablit qu'aucun franchissement de seuil ne
    peut etre saute par une regle de performance. La boucle threadee
    l'honorait; `run_sync`, emprunte par les tests et les scripts hors ligne,
    decimait par simple decoupage et ignorait l'ensemble.
    """
    module = ast.parse(REJEU.read_text(encoding="utf-8"))
    synchrone = next(
        n for n in ast.walk(module)
        if isinstance(n, ast.FunctionDef) and n.name == "run_sync"
    )
    references = {
        n.attr for n in ast.walk(synchrone) if isinstance(n, ast.Attribute)
    }
    assert "_obligatoires" in references, (
        "`run_sync` ne consulte pas les instants incontournables"
    )


def test_le_reentrainement_invalide_le_cache_de_scores():
    """LE CACHE DE SCORES SURVIVAIT A L'AJUSTEMENT DU MODELE.

    `score_series` memorise ses resultats sous une cle qui ne decrit que les
    DONNEES — longueur et bornes de l'index — jamais le modele. Deux
    ajustements successifs du meme detecteur sur les memes features produisent
    la meme cle : les scores de l'ancien modele etaient renvoyes tels quels.

    `invalidate_cache()` existait, sa docstring disait « a appeler apres tout
    re-entrainement », et rien ne l'appelait : la methode etait l'aveu du
    defaut, laissee debranchee.
    """
    module = ast.parse(DETECTEUR.read_text(encoding="utf-8"))
    classe = next(
        n for n in module.body
        if isinstance(n, ast.ClassDef) and n.name == "CoolerAnomalyDetector"
    )
    ajuste = next(
        n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == "fit"
    )
    appels = {
        n.func.attr for n in ast.walk(ajuste)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "invalidate_cache" in appels, (
        "`fit` n'invalide pas le cache : un re-entrainement reste sans effet "
        "observable sur les scores"
    )


def test_la_mise_en_forme_des_durees_est_centralisee():
    """L'ADR-011 AFFIRMAIT UNE CENTRALISATION QUI N'EXISTAIT PAS.

    Il cite `duree_pas` parmi les fonctions par lesquelles « la mise en forme
    est centralisee ». Or l'ingestion publiait `str(step_nominal)`, soit
    « 0 days 01:00:00 », et c'est le navigateur qui rattrapait la sortie avec sa
    propre fonction `duree()`. Deux implementations d'une meme regle dans deux
    langages, dont la seule vivante etait celle que l'ADR dit ne pas exister.
    """
    source = INGESTION.read_text(encoding="utf-8")
    assert "duree_pas(step_nominal)" in source, (
        "le pas d'echantillonnage n'est pas mis en forme cote serveur"
    )
    # Les COMMENTAIRES sont ecartes : ils citent l'ancienne expression pour
    # expliquer le defaut, et une recherche naive dans le fichier entier
    # retomberait dessus — le meme faux positif qu'un motif attrapant une
    # docstring au lieu du code.
    code = "\n".join(
        ligne for ligne in source.splitlines()
        if not ligne.lstrip().startswith("#")
    )
    assert "str(step_nominal)" not in code, (
        "la representation interne du Timedelta est encore publiee"
    )


def test_aucun_outil_de_qualite_declare_n_est_inerte():
    """UNE CONFIGURATION QUI MENT SUR CE QU'ELLE CONTROLE EST PIRE QU'ABSENTE.

    `pyproject.toml` configurait mypy — version cible, exclusions, options —
    sans que l'outil soit installe nulle part : absent des dependances, absent
    du Makefile, absent de l'integration continue. Le seul endroit du depot
    qui le mentionnait etait `make clean`, pour effacer un cache que rien ne
    produisait.
    """
    pyproject = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
    if "[tool.mypy]" not in pyproject:
        return
    # On cherche une LIGNE DE DEPENDANCE, pas une mention. Les commentaires du
    # fichier expliquent justement pourquoi mypy y figure : un simple `in`
    # aurait passe meme apres suppression de la dependance — le controle se
    # serait auto-satisfait sur sa propre explication.
    requirements = (RACINE / "requirements.txt").read_text(encoding="utf-8")
    declare = any(
        ligne.strip().startswith("mypy")
        for ligne in requirements.splitlines()
        if not ligne.lstrip().startswith("#")
    )
    makefile = (RACINE / "Makefile").read_text(encoding="utf-8")
    assert declare, "mypy est configure mais n'est pas une dependance declaree"
    assert "\tmypy " in makefile, "mypy est configure mais aucune cible ne l'execute"

    # CE TEST NE VERIFIAIT QUE DEUX TIERS DE SON PROPRE ENONCE.
    #
    # Sa docstring nomme trois manques — « absent des dependances, absent du
    # Makefile, ABSENT DE L'INTEGRATION CONTINUE » — et il n'en controlait que
    # deux. Le troisieme, celui qui compte le plus, survivait donc sous le test
    # ecrit pour l'empecher : `mypy` avait une cible que personne n'appelait.
    #
    # La chaine l'execute desormais en mode informatif, comme `make types` le
    # declare. Ce controle exige qu'il y figure, pas qu'il bloque.
    ci = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s*run:\s*mypy ", ci, re.M), (
        "mypy est configure et dote d'une cible, mais l'integration continue "
        "ne l'execute pas : le seul endroit ou son absence se verrait"
    )


def test_les_bancs_du_poste_sont_executes_par_l_integration_continue():
    """QUATRE-VINGT-QUATRE VERIFICATIONS NE BLOQUAIENT RIEN.

    `package.json` declare `npm test`, le Makefile declare `test-front`, et le
    workflow n'appelait ni l'un ni l'autre. Le poste est la seule surface que
    l'exploitant voit, et celle qui casse le plus silencieusement : une erreur
    de cablage ne leve aucune exception cote Python.
    """
    ci = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for banc in ("frontend_smoke.mjs", "twin_smoke.mjs", "boot_smoke.mjs"):
        assert banc in ci, f"{banc} n'est pas execute par l'integration continue"
    assert "needs: [qualite, tests, frontend]" in ci, (
        "la construction de l'image ne depend pas des bancs du poste"
    )


def test_chaque_action_operateur_porte_un_libelle_de_journal():
    """LA COLONNE `transition` RECEVAIT L'ETAT D'ARRIVEE, PAS L'ACTION.

    Le journal enregistrait « ACTIVE » aussi bien pour une desinhibition que
    pour une reapparition : l'auditeur ne pouvait plus dire pourquoi l'etat
    avait change. Les transitions systeme, elles, inscrivaient bien
    APPEARED / REPEATED / REACTIVATED.
    """
    module = ast.parse(ALARMES.read_text(encoding="utf-8"))
    tables: dict[str, set[str]] = {}
    for noeud in module.body:
        if not isinstance(noeud, ast.AnnAssign) or not isinstance(noeud.target, ast.Name):
            continue
        if noeud.target.id in {"OPERATOR_TRANSITIONS", "OPERATOR_TRANSITION_LABELS"}:
            assert isinstance(noeud.value, ast.Dict)
            tables[noeud.target.id] = {
                cle.value for cle in noeud.value.keys if isinstance(cle, ast.Constant)
            }
    assert tables.keys() == {"OPERATOR_TRANSITIONS", "OPERATOR_TRANSITION_LABELS"}
    assert tables["OPERATOR_TRANSITIONS"] == tables["OPERATOR_TRANSITION_LABELS"], (
        "une action operateur n'a pas de libelle de journal, ou l'inverse"
    )

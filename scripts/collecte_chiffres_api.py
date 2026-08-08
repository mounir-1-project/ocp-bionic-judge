"""Collecte des chiffres de la partie B, section 18 — le contrat d'API.

Même procédé que `collecte_chiffres_front.py` : rien n'est repris d'un
commentaire, tout est recompté. L'analyse passe par l'AST de `api/main.py`,
jamais par `grep` — un décorateur est un appel, et une chaîne citée dans un
docstring ressemble à une route.

Sortie : `reports/chiffres_api.txt`.

Blocs :
  1. les routes, par famille et par verbe
  2. la règle de déclaration des handlers (`async def` seulement s'il `await`)
  3. le contrôle d'accès : routes publiques, rôles exigés
  4. les paramètres de requête et leurs bornes
  5. les champs servis, et ceux que l'écran ne lit jamais
  6. les six sondes de santé
  7. les modèles de requête Pydantic
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
MAIN = RACINE / "api" / "main.py"
APP = RACINE / "api" / "static" / "app.js"
SORTIE = RACINE / "reports" / "chiffres_api.txt"

VERBES = {"get", "post", "put", "patch", "delete", "head"}


def _litteral_du_test(nom: str) -> frozenset[str]:
    """Lit un ensemble nomme dans le fichier de test qui fait autorite.

    On lit par AST plutot que d'importer le module : ce script ne doit exiger
    ni pytest ni les dependances de la suite. `frozenset({...})` etant un
    APPEL et non un litteral, on descend jusqu'a son argument.
    """
    source = (RACINE / "tests" / "test_service_invariants.py").read_text(encoding="utf-8")
    for noeud in ast.walk(ast.parse(source)):
        cibles = getattr(noeud, "targets", [])
        if not (isinstance(noeud, ast.Assign)
                and any(getattr(c, "id", "") == nom for c in cibles)):
            continue
        valeur = noeud.value
        if (isinstance(valeur, ast.Call)
                and getattr(valeur.func, "id", "") in {"frozenset", "set"}
                and valeur.args):
            valeur = valeur.args[0]
        return frozenset(ast.literal_eval(valeur))
    return frozenset()


HANDLERS_CALCULANTS = _litteral_du_test("HANDLERS_CALCULANTS")

# Handlers asynchrones sans `await` que le depot tolere : sondes et lectures
# de dictionnaires, qui doivent repondre meme si le pool de threads sature.
TOLEREES = _litteral_du_test("tolerees")

_lignes: list[str] = []


def dire(texte: str = "") -> None:
    _lignes.append(texte)
    print(texte)


def bloc(titre: str) -> None:
    dire()
    dire("=" * 74)
    dire(titre)
    dire("=" * 74)


# ── Extraction ───────────────────────────────────────────────────────────────

class Route:
    """Une route servie, telle que l'AST la décrit."""

    def __init__(self, verbe, chemin, noeud, tag, kwargs):
        self.verbe = verbe
        self.chemin = chemin
        self.noeud = noeud
        self.tag = tag
        self.kwargs = kwargs

    @property
    def nom(self) -> str:
        return self.noeud.name

    @property
    def asynchrone(self) -> bool:
        return isinstance(self.noeud, ast.AsyncFunctionDef)

    @property
    def attend(self) -> bool:
        """Le corps contient-il un `await` ou un `async with` / `async for` ?"""
        for n in ast.walk(self.noeud):
            if isinstance(n, (ast.Await, ast.AsyncWith, ast.AsyncFor)):
                return True
        return False

    @property
    def calcule(self) -> bool:
        """Ce handler compte-t-il parmi ceux qui CALCULENT ?

        LE PREDICAT EST IMPORTE, PAS REECRIT.

        Premiere version de ce script : une heuristique maison declarait
        « calculant » tout handler citant `_replay()` ou `_notifier()`. Elle
        designait neuf routes fautives — dont `replay_state`, qui ne fait que
        lire un dictionnaire en memoire, et que le depot tolere explicitement.
        Un controle dont le message ment quand il echoue est pire qu'absent.

        `tests/test_service_invariants.py` porte la liste qui fait autorite,
        etablie a la main lors de la correction du defaut. C'est elle qu'on
        lit. Convention de test n° 1 du depot : ne reimplemente pas pour
        mesurer, importe le predicat reel.
        """
        return self.nom in HANDLERS_CALCULANTS

    @property
    def roles(self) -> list[str]:
        roles: list[str] = []
        for n in ast.walk(self.noeud):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "_require_roles"):
                roles += [a.value for a in n.args if isinstance(a, ast.Constant)]
        return roles

    @property
    def parametres(self) -> list[tuple[str, str]]:
        """Paramètres de requête, avec leurs bornes quand `Query` les pose."""
        sortie: list[tuple[str, str]] = []
        a = self.noeud.args
        defauts = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
        for arg, defaut in zip(a.args, defauts):
            if arg.arg in {"request", "self"}:
                continue
            borne = ""
            if isinstance(defaut, ast.Call) and getattr(defaut.func, "id", "") == "Query":
                morceaux = []
                for kw in defaut.keywords:
                    if kw.arg in {"ge", "le", "gt", "lt"} and isinstance(kw.value, ast.Constant):
                        morceaux.append(f"{kw.arg}={kw.value.value}")
                if defaut.args and isinstance(defaut.args[0], ast.Constant):
                    morceaux.insert(0, f"défaut {defaut.args[0].value}")
                elif defaut.args:
                    morceaux.insert(0, "OBLIGATOIRE")
                borne = ", ".join(morceaux)
            elif isinstance(defaut, ast.Constant):
                borne = f"défaut {defaut.value}"
            sortie.append((arg.arg, borne))
        return sortie

    @property
    def champs(self) -> set[str]:
        """Clés de premier niveau des dictionnaires littéraux retournés."""
        cles: set[str] = set()
        for n in ast.walk(self.noeud):
            if not isinstance(n, ast.Return) or n.value is None:
                continue
            cible = n.value
            # `return JSONResponse({...})` et `return {...}`
            if isinstance(cible, ast.Call) and cible.args:
                cible = cible.args[0]
            if isinstance(cible, ast.Dict):
                cles |= {k.value for k in cible.keys
                         if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        return cles


def routes() -> list[Route]:
    arbre = ast.parse(MAIN.read_text(encoding="utf-8"))
    trouvees: list[Route] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                continue
            if deco.func.attr not in VERBES:
                continue
            if not deco.args or not isinstance(deco.args[0], ast.Constant):
                continue
            tag = ""
            kwargs = {}
            for kw in deco.keywords:
                if kw.arg == "tags" and isinstance(kw.value, ast.List) and kw.value.elts:
                    prem = kw.value.elts[0]
                    if isinstance(prem, ast.Constant):
                        tag = prem.value
                elif isinstance(kw.value, ast.Constant):
                    kwargs[kw.arg] = kw.value.value
            trouvees.append(
                Route(deco.func.attr.upper(), deco.args[0].value, noeud, tag, kwargs)
            )
    return sorted(trouvees, key=lambda r: (r.tag, r.chemin, r.verbe))


# ── Blocs ────────────────────────────────────────────────────────────────────

def inventaire(rs: list[Route]) -> None:
    bloc("1. LES ROUTES, PAR FAMILLE")
    dire(f"  fichier   : api/main.py, {len(MAIN.read_text(encoding='utf-8').splitlines())} lignes")
    dire(f"  routes    : {len(rs)} couples verbe+chemin")
    dire(f"  chemins   : {len({r.chemin for r in rs})} distincts")
    dire()
    familles: dict[str, list[Route]] = {}
    for r in rs:
        familles.setdefault(r.tag or "(sans étiquette)", []).append(r)
    for tag in sorted(familles):
        dire(f"  {tag} — {len(familles[tag])} route(s)")
        for r in familles[tag]:
            dire(f"      {r.verbe:<6} {r.chemin:<44} {r.nom}")
        dire()


def handlers(rs: list[Route]) -> None:
    bloc("2. RÈGLE DE DÉCLARATION DES HANDLERS")
    dire("  Un handler est `async def` UNIQUEMENT s'il `await`, ou si son corps")
    dire("  se limite à des lectures en mémoire. Tout ce qui calcule est `def` :")
    dire("  FastAPI l'exécute alors dans son pool de threads.")
    dire()
    a_sans_await = [r for r in rs if r.asynchrone and not r.attend]
    fautifs = [r for r in a_sans_await if r.calcule]
    dire(f"  handlers `async def`            : {sum(1 for r in rs if r.asynchrone)}")
    dire(f"  handlers `def`                  : {sum(1 for r in rs if not r.asynchrone)}")
    dire(f"  `async def` sans aucun `await`  : {len(a_sans_await)}")
    dire(f"  dont declares CALCULANTS        : {len(fautifs)}")
    hors_liste = [r for r in a_sans_await if r.nom not in TOLEREES]
    dire(f"  dont hors de la liste toleree   : {len(hors_liste)}")
    if hors_liste:
        for r in hors_liste:
            dire(f"      NOUVEAU  {r.verbe:<6} {r.chemin:<38} {r.nom}")
    dire(f"  handlers declares calculants    : {len(HANDLERS_CALCULANTS)}")
    dire(f"  handlers asynchrones toleres    : {len(TOLEREES)}")
    if fautifs:
        for r in fautifs:
            dire(f"      A VERIFIER  {r.verbe:<6} {r.chemin:<40} {r.nom}")
    else:
        dire("      aucun — la regle tient")
    dire()
    dire("  Le commentaire d'api/main.py annonce « 32 des 47 handlers » comme")
    dire("  etat D'ORIGINE, avant correction. Le decompte ci-dessus est l'etat")
    dire("  COURANT : les deux se lisent ensemble, jamais l'un pour l'autre.")


def acces(rs: list[Route]) -> None:
    bloc("3. CONTRÔLE D'ACCÈS")
    src = MAIN.read_text(encoding="utf-8")
    dire("  Chemins publics — traversent le middleware sans session :")
    for motif in ('request.url.path == "/"', 'startswith("/assets/")',
                  '== "/api/health"', 'startswith("/api/health/")',
                  'startswith("/api/auth/")'):
        dire(f"      {motif}")
    dire()
    proteges = [r for r in rs if r.roles]
    dire(f"  routes exigeant un rôle : {len(proteges)} sur {len(rs)}")
    par_role: dict[str, list[str]] = {}
    for r in proteges:
        cle = ", ".join(sorted(r.roles))
        par_role.setdefault(cle, []).append(f"{r.verbe} {r.chemin}")
    for cle in sorted(par_role, key=lambda c: -len(par_role[c])):
        dire(f"    [{cle}]")
        for c in sorted(par_role[cle]):
            dire(f"        {c}")
    dire()
    mutations = [r for r in rs if r.verbe in {"POST", "PUT", "PATCH", "DELETE"}]
    sans_role = [r for r in mutations if not r.roles]
    dire(f"  routes de mutation : {len(mutations)}")
    dire(f"  dont sans exigence de rôle explicite : {len(sans_role)}")
    for r in sans_role:
        dire(f"      {r.verbe:<6} {r.chemin}")
    dire()
    n_csrf = src.count("X-CSRF-Token")
    dire(f"  CSRF : jeton exigé sur POST/PUT/PATCH/DELETE, sauf login et logout")
    dire(f"         ({n_csrf} occurrences de l'en-tête dans le service)")
    n_entetes = len(re.findall(r'response\.headers\["([^"]+)"\]', src))
    dire(f"  en-têtes de défense posés par `_durcir` : {n_entetes}")


def parametres(rs: list[Route]) -> None:
    bloc("4. PARAMÈTRES DE REQUÊTE ET LEURS BORNES")
    n = 0
    for r in rs:
        ps = [p for p in r.parametres if p[1]]
        if not ps:
            continue
        n += len(ps)
        dire(f"  {r.verbe} {r.chemin}")
        for nom, borne in ps:
            dire(f"      {nom:<16} {borne}")
    dire()
    dire(f"  {n} paramètres bornés au total. Une borne absente est une "
         f"dénégation de service offerte.")


def champs_orphelins(rs: list[Route]) -> None:
    bloc("5. CHAMPS SERVIS, ET CEUX QUE L'ÉCRAN NE LIT JAMAIS")
    src = APP.read_text(encoding="utf-8")
    # Commentaires blanchis : un champ cité dans un commentaire n'est pas lu.
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", " ", src, flags=re.M)

    total = 0
    orphelins: list[tuple[str, str]] = []
    for r in rs:
        cs = r.champs
        if not cs:
            continue
        total += len(cs)
        for champ in sorted(cs):
            # Le front lit un champ par `.champ`, `["champ"]` ou destructuration.
            lu = (re.search(rf"\.{re.escape(champ)}\b", src)
                  or re.search(rf'\["{re.escape(champ)}"\]', src)
                  or re.search(rf"\b{re.escape(champ)}\s*[,}}]", src))
            if not lu:
                orphelins.append((f"{r.verbe} {r.chemin}", champ))

    dire(f"  champs de premier niveau servis (dict littéraux) : {total}")
    dire(f"  jamais lus par api/static/app.js                 : {len(orphelins)}")
    dire()
    dire("  ATTENTION A LA PORTEE DE CE CONSTAT. Un champ non lu par le poste")
    dire("  n'est pas mort : il peut servir a un orchestrateur, a un test, ou")
    dire("  a un lecteur de la documentation OpenAPI. Le controle dit ce qu'il")
    dire("  mesure — ce que L'ECRAN ignore — et rien de plus.")
    dire()
    courant = None
    for route, champ in orphelins:
        if route != courant:
            dire(f"    {route}")
            courant = route
        dire(f"        {champ}")


def sondes(rs: list[Route]) -> None:
    bloc("6. LES SONDES DE SANTÉ")
    sondes_r = [r for r in rs if r.chemin.startswith("/api/health")]
    dire(f"  {len(sondes_r)} sondes servies :")
    correspondance = {
        "/api/health": "synthèse humaine — lue par le poste au démarrage",
        "/api/health/live": "liveness Kubernetes / Docker HEALTHCHECK",
        "/api/health/ready": "readiness — 503 tant que la chaîne n'est pas construite",
        "/api/health/model": "état de promotion du modèle, distinct de sa disponibilité",
        "/api/health/database": "lecture réelle des deux registres SQLite, 503 + motifs",
        "/api/health/version": "versions applicative et signature du détecteur",
    }
    for r in sondes_r:
        dire(f"      {r.verbe:<5} {r.chemin:<26} {correspondance.get(r.chemin, '—')}")
    dire()
    src = MAIN.read_text(encoding="utf-8")
    n_503 = len(re.findall(r"status_code=503", src))
    dire(f"  réponses 503 explicites dans le service : {n_503}")


def modeles() -> None:
    bloc("7. MODÈLES DE REQUÊTE")
    arbre = ast.parse(MAIN.read_text(encoding="utf-8"))
    for n in ast.walk(arbre):
        if not isinstance(n, ast.ClassDef):
            continue
        if not any(getattr(b, "id", "") == "BaseModel" for b in n.bases):
            continue
        champs = []
        for corps in n.body:
            if isinstance(corps, ast.AnnAssign) and isinstance(corps.target, ast.Name):
                contrainte = ""
                if isinstance(corps.value, ast.Call):
                    bits = []
                    for kw in corps.value.keywords:
                        if isinstance(kw.value, ast.Constant):
                            bits.append(f"{kw.arg}={kw.value.value!r}")
                    contrainte = ", ".join(bits)
                champs.append((corps.target.id, contrainte))
        dire(f"  {n.name} — {len(champs)} champ(s)")
        for nom, contrainte in champs:
            dire(f"      {nom:<18} {contrainte}")
        dire()


def main() -> None:
    horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dire(f"COLLECTE DES CHIFFRES DE L'API — {horodatage}")
    dire(f"dépôt : {RACINE}")
    rs = routes()
    inventaire(rs)
    handlers(rs)
    acces(rs)
    parametres(rs)
    champs_orphelins(rs)
    sondes(rs)
    modeles()
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text("\n".join(_lignes) + "\n", encoding="utf-8")
    print(f"\n→ {SORTIE}")


if __name__ == "__main__":
    main()

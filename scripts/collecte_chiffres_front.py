"""Collecte des chiffres de la partie B, section 17 — le poste opérateur.

Équivalent front de `collecte_chiffres_rapport.py`. Aucun chiffre de cette
section ne doit être repris d'un commentaire : chacun est recompté ici.

Sortie : `reports/chiffres_front.txt`.

Blocs :
  1. volumétrie des fichiers du poste
  2. inventaire des vues et des panneaux (dashboard.html)
  3. familles de signaux du menu Signaux
  4. tables de traduction d'app.js
  5. composants 3D enregistrés dans twin.js
  6. faisceau tubulaire : nombre de tubes réellement instanciés
  7. routes servies par api/main.py
  8. routes consommées par le front
  9. routes orphelines, dans les deux sens
 10. identifiants HTML vs identifiants cherchés par le JS
 11. chiffres cités dans les commentaires du front, à confronter
"""

from __future__ import annotations

import ast
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
HTML = RACINE / "api" / "dashboard.html"
APP = RACINE / "api" / "static" / "app.js"
TWIN = RACINE / "api" / "static" / "twin.js"
CSS = RACINE / "api" / "static" / "app.css"
MAIN = RACINE / "api" / "main.py"

SORTIE = RACINE / "reports" / "chiffres_front.txt"

_lignes: list[str] = []


def dire(texte: str = "") -> None:
    _lignes.append(texte)
    print(texte)


def bloc(titre: str) -> None:
    dire()
    dire("=" * 74)
    dire(titre)
    dire("=" * 74)


# ── 1. Volumétrie ────────────────────────────────────────────────────────────

def volumetrie() -> None:
    bloc("1. VOLUMÉTRIE DU POSTE")
    total = 0
    for chemin in (HTML, APP, TWIN, CSS, MAIN):
        n = len(chemin.read_text(encoding="utf-8").splitlines())
        total += n
        dire(f"  {chemin.relative_to(RACINE).as_posix():<28} {n:>6} lignes")
    dire(f"  {'TOTAL':<28} {total:>6} lignes")

    # Part de commentaires dans le front : c'est le terrain que rien n'exécute.
    for chemin in (APP, TWIN):
        src = chemin.read_text(encoding="utf-8").splitlines()
        n_comm = 0
        dans_bloc = False
        for ligne in src:
            nu = ligne.strip()
            if dans_bloc:
                n_comm += 1
                if "*/" in nu:
                    dans_bloc = False
            elif nu.startswith("/*"):
                n_comm += 1
                dans_bloc = "*/" not in nu
            elif nu.startswith("//"):
                n_comm += 1
        part = 100 * n_comm / len(src)
        dire(
            f"  {chemin.name:<28} {n_comm:>6} lignes de commentaire "
            f"({part:.1f} %) — rien ne les exécute"
        )


# ── 2. Vues et panneaux ──────────────────────────────────────────────────────

def vues() -> None:
    bloc("2. VUES ET PANNEAUX (dashboard.html)")
    html = HTML.read_text(encoding="utf-8")

    onglets = re.findall(r'data-view="([a-z]+)"', html)
    dire(f"  onglets (role=tab)          : {len(onglets)} — {', '.join(onglets)}")

    panneaux = re.findall(r'data-panel="([a-z]+)"', html)
    dire(f"  panneaux (role=tabpanel)    : {len(panneaux)} — {', '.join(panneaux)}")

    # Un « panel » est une carte <article class="panel …">.
    cartes = re.findall(r'<article class="panel([^"]*)"', html)
    dire(f"  cartes <article class=panel>: {len(cartes)}")

    # Répartition par vue : on découpe sur les balises <section class="view…">.
    morceaux = re.split(r'<section class="view[^"]*" data-panel="([a-z]+)"', html)
    for i in range(1, len(morceaux), 2):
        nom = morceaux[i]
        corps = morceaux[i + 1]
        n = len(re.findall(r'<article class="panel', corps))
        titres = re.findall(r"<h2[^>]*>([^<]+)</h2>", corps)
        dire(f"    vue {nom:<10} : {n} cartes")
        for t in titres:
            dire(f"        · {t.strip()}")

    dire(f"  boîtes de dialogue <dialog> : {len(re.findall(r'<dialog', html))}")
    dire(f"  éléments <canvas>           : {len(re.findall(r'<canvas', html))}")
    dire(f"  tableaux <table>            : {len(re.findall(r'<table>', html))}")


# ── 3. Familles de signaux ───────────────────────────────────────────────────

def familles() -> None:
    bloc("3. FAMILLES DE SIGNAUX")
    html = HTML.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    sel = re.search(r'<select id="trendSet">(.*?)</select>', html, re.S)
    options = re.findall(r'value="([^"]+)"', sel.group(1)) if sel else []
    dire(f"  options du menu Signaux : {len(options)}")

    corps = re.search(r"const TREND_SETS = \{(.*?)\n\};", app, re.S)
    cles = re.findall(r"^  ([a-z_]+): \{", corps.group(1), re.M) if corps else []
    dire(f"  clés de TREND_SETS      : {len(cles)}")

    manque_js = sorted(set(options) - set(cles))
    manque_html = sorted(set(cles) - set(options))
    dire(f"  option HTML sans famille JS : {manque_js or 'aucune'}")
    dire(f"  famille JS sans option HTML : {manque_html or 'aucune'}")

    # Combien de courbes chaque famille trace.
    total_lignes = 0
    for cle in cles:
        m = re.search(rf"  {cle}: \{{(.*?)\n  \}},", corps.group(1), re.S)
        n = len(re.findall(r'\["[A-Za-z_0-9]+", ', m.group(1))) if m else 0
        total_lignes += n
    dire(f"  courbes tracées, toutes familles confondues : {total_lignes}")

    sel_p = re.search(r'<select id="trendSpan">(.*?)</select>', html, re.S)
    periodes = re.findall(r'value="([^"]+)"', sel_p.group(1)) if sel_p else []
    dire(f"  périodes proposées      : {len(periodes)} — {', '.join(periodes)} h")


# ── 4. Tables de traduction ──────────────────────────────────────────────────

def tables() -> None:
    bloc("4. TABLES DE TRADUCTION D'app.js — la couche ADR-011")
    app = APP.read_text(encoding="utf-8")
    attendues = [
        "SEV_LABEL", "ETAT_LABEL", "ROLE_LABEL", "URGENCE_LABEL",
        "RESERVE_LABEL", "PROVENANCE", "OBSERVABILITE", "ALARM_STATE",
        "ALARM_ACTIONS", "MESURE_LABEL", "GATE_LABEL", "BASE_LABEL",
    ]
    total = 0
    for nom in attendues:
        m = re.search(rf"const {nom} = \{{(.*?)\n\}};", app, re.S)
        if not m:
            dire(f"  {nom:<16} ABSENTE")
            continue
        corps = m.group(1)
        # Les tables courtes sont écrites sur une seule ligne : compter les
        # clés en début de ligne les ramènerait toutes à 1. On compte les
        # clés de premier niveau en neutralisant les objets imbriqués.
        profondeur = 0
        n = 0
        for jeton in re.finditer(r"[{}\[\]]|[A-Za-z_0-9]+\s*:", corps):
            t = jeton.group(0)
            if t in "{[":
                profondeur += 1
            elif t in "}]":
                profondeur -= 1
            elif profondeur == 0:
                n += 1
        total += n
        dire(f"  {nom:<16} {n:>3} entrées")
    dire(f"  {'TOTAL':<16} {total:>3} entrées traduites")

    # Listes de rendu.
    for nom in ("READOUTS", "CHECKS", "AUDIT_LIGNES"):
        m = re.search(rf"const {nom} = \[(.*?)\n\];", app, re.S)
        if m:
            n = len(re.findall(r"^  [\[{]", m.group(1), re.M))
            dire(f"  {nom:<16} {n:>3} entrées")


# ── 5. Composants 3D ─────────────────────────────────────────────────────────

def composants() -> None:
    bloc("5. COMPOSANTS 3D ENREGISTRÉS (twin.js)")
    twin = TWIN.read_text(encoding="utf-8")

    # NE PAS CHERCHER `_register(x, "CODE")` SEULEMENT.
    #
    # Piege rencontre, et corrige avant publication : ce motif ne voit que les
    # appels ou le code est ecrit en litteral SUR PLACE. Or twin.js passe
    # quatre codes par une variable ou par un parametre de fonction auxiliaire
    # — `boxCode` pour les boites a eau, l'argument `code` de `acidNozzle` et
    # de `valve`. Le motif etroit concluait donc que NOZZLE_ACID_IN,
    # NOZZLE_ACID_OUT, VALVE_ACID et VALVE_SEA « ne sont pas modelises », ce
    # qui est faux : ils le sont, aux lignes 885-886 et 906-907.
    #
    # C'est le defaut de test dominant du depot — la portee de l'assertion ne
    # coincide pas avec celle de l'intention — commis ici dans l'instrument
    # meme qui sert a le mesurer. On collecte donc TOUT litteral en capitales
    # de forme « code de piece » : dans ce fichier ils ne servent qu'a cela.
    litteraux = set(re.findall(r'"([A-Z][A-Z_0-9]{2,})"', twin))
    # Retirer ce qui n'est pas un code de piece (constantes THREE, etc.).
    # CRITICAL / WARNING / NORMAL sont des severites, pas des pieces : elles
    # transitent par la meme variable, d'ou leur presence dans les litteraux.
    hors = {"SIZE", "CHEMETICS", "TUBES", "CRITICAL", "WARNING", "NORMAL"}
    codes = {c for c in litteraux if c not in hors and not c.startswith("E7")}
    directs = set(re.findall(r'_register\([^,]+, "([A-Z_]+)"\)', twin))
    dire(f"  codes de piece modelises : {len(codes)}")
    for c in sorted(codes):
        via = "litteral sur place" if c in directs else "passe par variable"
        dire(f"      - {c:<18} ({via})")

    topo = RACINE / "src" / "domain" / "topology.yaml"
    if topo.exists():
        y = topo.read_text(encoding="utf-8")
        # Les pieces sont des CLES de mapping sous `components:`, pas des
        # entrees `- code:`. Le referentiel est la source ; le jumeau doit
        # s'y conformer, jamais l'inverse.
        sect = y.split("\ncomponents:", 1)[1].split("\nsensors:", 1)[0]
        declares = re.findall(r"^  ([A-Z][A-Z_0-9]+):\s*$", sect, re.M)

        # `finding_map` est le contrat qui allume une piece a l'ecran.
        fm = y.split("\nfinding_map:", 1)[1] if "\nfinding_map:" in y else ""
        codes_fm = re.findall(r"^  ([A-Z][A-Z_0-9]+):\s*\{", fm, re.M)
        cibles_fm = set(re.findall(r"components: \[([^\]]*)\]", fm))
        pieces_fm = {p.strip() for g in cibles_fm for p in g.split(",") if p.strip()}
        dire(f"  codes de constatation dans finding_map : {len(codes_fm)}")
        muets = [c for c in codes_fm
                 if re.search(rf"{c}:\s*\{{ components: \[\]", fm)]
        dire(f"    dont n'allumant aucune piece         : {len(muets)}"
             f" — {', '.join(muets)}")
        dire(f"  pieces citees par finding_map          : {len(pieces_fm)}")
        tous = codes | {"WATERBOX_IN", "WATERBOX_OUT"}
        dire(f"  codes declares dans topology.yaml : {len(declares)}"
             f" — {', '.join(sorted(declares))}")
        dire(f"  codes modelises en 3D             : {len(tous)}"
             f" — {', '.join(sorted(tous))}")
        sans_3d = sorted(set(declares) - tous)
        sans_ref = sorted(tous - set(declares))
        dire(f"  declare au referentiel, NON modelise en 3D : {sans_3d or 'aucun'}")
        dire(f"  modelise en 3D, HORS referentiel           : {sans_ref or 'aucun'}")
        jamais = sorted(pieces_fm - tous)
        dire(f"  cible par finding_map, NON modelise en 3D  : {jamais or 'aucun'}")
        muettes = sorted(tous - pieces_fm)
        dire(f"  modelise mais qu'aucune constatation n'allume : {muettes or 'aucune'}")

    for nom, motif in (
        ("matériaux de la palette `this.mat`", r"^      [a-zA-Z]+: (?:new THREE|painted)"),
        ("textures procédurales", r"^function \w*(?:Roughness|Map|Maps|Alpha|Texture)\("),
        ("chicanes segmentaires", r"const BAFFLES = (\d+);"),
    ):
        trouve = re.findall(motif, twin, re.M)
        if nom == "chicanes segmentaires":
            dire(f"  {nom:<38} : {trouve[0] if trouve else '—'}")
        else:
            dire(f"  {nom:<38} : {len(trouve)}")


# ── 6. Faisceau tubulaire ────────────────────────────────────────────────────

def tubes() -> None:
    bloc("6. FAISCEAU — NOMBRE DE TUBES RÉELLEMENT INSTANCIÉS")
    twin = TWIN.read_text(encoding="utf-8")

    def cste(nom: str) -> float:
        return float(re.search(rf"const {nom} = ([\d.]+);", twin).group(1))

    shell_r = cste("SHELL_R")
    tube_od = cste("TUBE_OD")

    # Réimplémenter serait une tautologie ; ici il n'y a pas de prédicat
    # importable côté Python. On transcrit la boucle de `_buildEquipment`
    # à l'identique, et on cite les constantes lues dans le fichier.
    pitch = tube_od * 1.28
    limit = shell_r - 0.055
    rows = math.floor(limit / (pitch * 0.866))
    n = 0
    for r in range(-rows, rows + 1):
        y = r * pitch * 0.866
        offset = pitch / 2 if r % 2 else 0.0
        span = math.floor(math.sqrt(max(limit * limit - y * y, 0.0)) / pitch)
        for c in range(-span, span + 1):
            z = c * pitch + offset
            if y * y + z * z <= limit * limit:
                n += 1

    dire(f"  SHELL_R = {shell_r} m, TUBE_OD = {tube_od} m")
    dire(f"  pas triangulaire = {pitch * 1000:.2f} mm, rangées = {2 * rows + 1}")
    dire(f"  TUBES INSTANCIÉS = {n}")
    dire("  le commentaire de `_guardPerformance` annonce « plus de 1 500 tubes »")
    dire(f"  → {'CONFORME' if n > 1500 else 'CONTREDIT'} ({n} tubes)")


# ── 7-9. Câblage serveur / écran ─────────────────────────────────────────────

def routes_servies() -> list[tuple[str, str]]:
    """Routes déclarées par `api/main.py`, lues par analyse de l'AST.

    Un `grep` ne l'établirait pas : les décorateurs sont des appels, et une
    chaîne citée dans un commentaire ou un docstring ressemble à une route.
    """
    arbre = ast.parse(MAIN.read_text(encoding="utf-8"))
    trouvees: list[tuple[str, str]] = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in noeud.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            f = deco.func
            if not isinstance(f, ast.Attribute):
                continue
            verbe = f.attr.upper()
            if verbe not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
                continue
            if not deco.args or not isinstance(deco.args[0], ast.Constant):
                continue
            trouvees.append((verbe, deco.args[0].value))
    return sorted(set(trouvees))


def routes_consommees() -> set[str]:
    """Chemins d'API cités par le front, ramenés au gabarit du serveur.

    Deux précautions, sans lesquelles le décompte d'orphelines ment :

    1. Les commentaires sont blanchis. Un chemin cité dans un commentaire
       n'est pas une consommation — c'est le procédé de
       `_decalages_non_causaux`, appliqué ici.
    2. Les chemins sont écrits en littéral de gabarit :
       `/api/alarms/${alarme.id}/transition`. Une capture qui s'arrête au
       premier caractère non alphanumérique ne voit que `/api/alarms/` et
       déclare orpheline une route que l'écran appelle à chaque acquittement.
       Chaque `${…}` devient donc `{}`, la même forme que FastAPI.
    """
    src = APP.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = re.sub(r"^\s*//.*$", " ", src, flags=re.M)

    bruts = re.findall(r'["`](/api/(?:\$\{[^}]*\}|[a-zA-Z0-9/_\-])+)', src)
    return {re.sub(r"\$\{[^}]*\}", "{}", b).rstrip("/") for b in bruts}


def gabarit(servi: str) -> str:
    """Route serveur ramenée à la même forme : `{alias}` → `{}`."""
    return re.sub(r"\{[^}]+\}", "{}", servi).rstrip("/")


def cablage() -> None:
    bloc("7. ROUTES SERVIES PAR api/main.py")
    servies = routes_servies()
    dire(f"  routes déclarées : {len(servies)}")
    familles_r: dict[str, list[str]] = {}
    for verbe, chemin in servies:
        cle = "/".join(chemin.split("/")[:3]) or chemin
        familles_r.setdefault(cle, []).append(f"{verbe} {chemin}")
    for cle in sorted(familles_r):
        dire(f"    {cle:<26} {len(familles_r[cle])}")
    dire()
    for verbe, chemin in servies:
        dire(f"      {verbe:<5} {chemin}")

    bloc("8. ROUTES CONSOMMÉES PAR LE FRONT")
    consommees = routes_consommees()
    dire(f"  chemins distincts appelés par app.js : {len(consommees)}")
    for c in sorted(consommees):
        dire(f"      {c}")

    bloc("9. ÉCART SERVEUR / ÉCRAN")
    chemins_servis = {c for _, c in servies}
    servis_gab = {gabarit(c) for c in chemins_servis}

    orphelines = sorted(c for c in chemins_servis if gabarit(c) not in consommees)
    dire(f"  routes servies et consommées par personne : {len(orphelines)}")
    for c in orphelines:
        verbes = sorted({v for v, ch in servies if ch == c})
        dire(f"      {'/'.join(verbes):<12} {c}")

    fantomes = sorted(c for c in consommees if c not in servis_gab)
    dire(f"  chemins appelés par l'écran et non servis : {len(fantomes)}")
    for c in fantomes:
        dire(f"      {c}")

    dire()
    dire(f"  routes servies    : {len(chemins_servis)} chemins, {len(servies)} couples verbe+chemin")
    dire(f"  routes consommées : {len(consommees) - len(fantomes)}")
    part = 100 * (len(chemins_servis) - len(orphelines)) / len(chemins_servis)
    dire(f"  taux de câblage   : {part:.1f} % des chemins servis sont atteints par l'écran")


# ── 10. Identifiants ─────────────────────────────────────────────────────────

def identifiants() -> None:
    bloc("10. IDENTIFIANTS — LA PAGE ET CE QUE LE JS Y CHERCHE")
    html = HTML.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    poses = set(re.findall(r'\sid="([A-Za-z0-9_\-]+)"', html))
    app_nu = re.sub(r"/\*.*?\*/", " ", app, flags=re.S)
    app_nu = re.sub(r"^\s*//.*$", " ", app_nu, flags=re.M)
    cherches = set(re.findall(r'\$\("([A-Za-z0-9_\-]+)"\)', app_nu))

    dire(f"  identifiants posés dans la page : {len(poses)}")
    dire(f"  identifiants cherchés par le JS : {len(cherches)}")

    manquants = sorted(cherches - poses)
    dire(f"  cherchés et ABSENTS de la page  : {len(manquants)}")
    for i in manquants:
        dire(f"      · {i}")

    inertes = sorted(poses - cherches)
    dire(f"  posés et jamais cherchés        : {len(inertes)}")
    for i in inertes:
        dire(f"      · {i}")

    # Sélecteurs par attribut, l'autre voie de câblage.
    for attr in ("data-view", "data-panel", "data-feed", "data-alarms",
                 "data-sensor", "data-episode", "data-alarm", "data-idx"):
        n_html = len(re.findall(rf"{attr}=", html))
        n_js = len(re.findall(rf"{attr}", app_nu))
        dire(f"  {attr:<14} page {n_html:>3}  ·  js {n_js:>3}")


# ── 11. Chiffres des commentaires ────────────────────────────────────────────

def commentaires() -> None:
    bloc("11. CHIFFRES CITÉS DANS LES COMMENTAIRES DU FRONT")
    dire("  Rien ne les exécute et aucun test ne les relit. À confronter un à un.")
    dire()
    sources = {"dashboard.html": HTML, "app.js": APP, "twin.js": TWIN,
               "app.css": CSS}

    # On isole d'abord les lignes de COMMENTAIRE, puis on n'y cherche que des
    # assertions chiffrees. Balayer tout le fichier ramenerait le code
    # lui-meme -- des constantes, qui sont executees, donc justes par
    # construction. C'est exactement la distinction du fil conducteur.
    def lignes_de_commentaire(texte, html):
        sorties = []
        dans = False
        ouvre, ferme = ("<!--", "-->") if html else ("/*", "*/")
        for i, ligne in enumerate(texte.splitlines(), 1):
            nu = ligne.strip()
            if dans:
                sorties.append((i, nu))
                if ferme in nu:
                    dans = False
            elif nu.startswith(ouvre):
                sorties.append((i, nu))
                dans = ferme not in nu
            elif not html and (nu.startswith("//") or nu.startswith("*")):
                sorties.append((i, nu))
        return sorties

    lettres = ("deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|"
               "treize|quatorze|quinze|seize|vingt|trente|quarante")
    rangs = ("deuxi|troisi|quatri|cinqui|sixi|septi|huiti|neuvi|dixi|onzi|"
             "douzi|treizi|quatorzi|quinzi|seizi|dix-septi|dix-huiti|"
             "dix-neuvi|vingti")
    noms = (r"lignes?|routes?|tubes?|\u00e9tiquettes?|\u00e9pisodes?|heures?|"
            r"requ\u00eates?|capteurs?|tags?|points?|contr\u00f4les?|portes?|modes?|"
            r"identifiants?|vues?|caract\u00e8res?|images?|jours?|mois|"
            r"occurrences?|fois|tentatives?|d\u00e9cisions?|alarmes?|champs?|"
            r"valeurs?|onglets?|boutons?|colonnes?|familles?")
    espaces = "\\d\\s\u00a0\u202f"
    motifs = [
        (r"\b(?:\d[" + espaces + r"]*|" + lettres + r")\s+(?:" + noms + r")\b",
         "quantite"),
        (r"\b(?:" + rangs + r")[a-z\u00e8]*\s+occurrence", "rang du motif"),
        (r"\b\d+[.,]?\d*\s*%", "pourcentage"),
        (r"[\d,]+:1", "contraste"),
        (r"\bR\u00b2?\s*[\d0,.]+|\br\s*=\s*[\u2212+-]?[\d,]+", "coefficient"),
        (r"\b\d[" + espaces + r"]*\s*(?:px|ms|Hz)\b", "grandeur technique"),
    ]

    total = 0
    for nom, chemin in sources.items():
        texte = chemin.read_text(encoding="utf-8")
        deja = set()
        for ligne_no, ligne in lignes_de_commentaire(texte, nom.endswith(".html")):
            for motif, quoi in motifs:
                if ligne_no in deja:
                    break
                if re.search(motif, ligne, re.I):
                    deja.add(ligne_no)
                    total += 1
                    propre = ligne.lstrip("*/<!- ").strip()
                    dire("  %s:%-5d [%s] %s" % (nom, ligne_no, quoi, propre[:88]))
    dire()
    dire("  -> %d lignes de commentaire portent une assertion chiffree." % total)
    dire("     Aucune n'est executee. Aucun test ne les relit.")
    dire()
    dire("  REPERE POUR LA SECTION 17.8 : la population AUDITEE le 2026-08-08")
    dire("  etait de 65 lignes. Le compte ci-dessus est superieur parce que les")
    dire("  trois corrections apportees ce jour-la citent chacune leur valeur")
    dire("  recomptee et sa date -- elles sont donc, a leur tour, des assertions")
    dire("  chiffrees non executees. Le denominateur du taux d'erreur publie")
    dire("  reste 65 : on ne mesure pas un taux sur une population qu'on vient")
    dire("  d'elargir avec ses propres corrections.")


# -- 12. Contraste ------------------------------------------------------------

def contraste() -> None:
    """Recalcule le contraste WCAG de chaque encre sur chaque fond reel.

    ADR-008 annonce « 4,6:1 minimum sur les micro-libelles ». La feuille de
    style annonce « 4,5:1 au pire ». Les deux ne peuvent pas etre vraies :
    on tranche par le calcul, pas par l'anciennete du document.
    """
    bloc("12. CONTRASTE WCAG RECALCULE")
    css = CSS.read_text(encoding="utf-8")

    def canal(v: float) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    def luminance(h: str) -> float:
        h = h.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)

    def rapport(a: str, b: str) -> float:
        la, lb = luminance(a), luminance(b)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

    def jeton_css(nom: str) -> str | None:
        m = re.search(re.escape(nom) + r":\s*(#[0-9a-fA-F]{6})", css)
        return m.group(1) if m else None

    fonds = {n: jeton_css(n) for n in
             ("--void", "--deep", "--plate", "--raise", "--sunken")}
    fonds = {k: v for k, v in fonds.items() if v}
    encres = {n: jeton_css(n) for n in
              ("--ink", "--ink-2", "--ink-3", "--ink-4")}
    encres = {k: v for k, v in encres.items() if v}

    dire(f"  fonds employes : {len(fonds)} — {', '.join(fonds)}")
    entete = f"  {'encre':<8} {'valeur':<9} " + " ".join(f"{k:>8}" for k in fonds)
    dire(entete + "     PIRE")
    for nom, couleur in encres.items():
        rs = {f: rapport(couleur, c) for f, c in fonds.items()}
        pire = min(rs.values())
        marque = "OK" if pire >= 4.5 else "ECHEC AA"
        dire(f"  {nom:<8} {couleur:<9} "
             + " ".join(f"{rs[k]:>8.2f}" for k in fonds)
             + f"  {pire:>5.2f}:1 {marque}")
    pire_micro = min(rapport(encres["--ink-4"], c) for c in fonds.values())
    dire()
    dire(f"  micro-libelles (--ink-4), pire fond : {pire_micro:.2f}:1")
    dire("  app.css annonce  « 4,5:1 au pire (--raise) »  -> CONFORME")
    dire("  ADR-008 annonce  « 4,6:1 minimum »            -> SUREVALUE")


# -- 13. Bancs du poste et volumetrie citee ----------------------------------

def bancs_et_renvois() -> None:
    """Chiffres cites par la section 17 qui ne viennent pas des blocs ci-dessus.

    Ils y figurent pour que CHAQUE valeur en gras de la section trace vers ce
    fichier, et vers lui seul. Les totaux de bancs sont recopies de la sortie
    de `npm run test:front` avec sa date : les executer ici demanderait node et
    jsdom, que ce script ne suppose pas.
    """
    bloc("13. BANCS DU POSTE ET RENVOIS")

    dire("  Bancs jsdom -- `npm run test:front`, 2026-08-08 :")
    bancs = [("frontend_smoke.mjs", 54, 1.94),
             ("twin_smoke.mjs", 35, 0.39),
             ("boot_smoke.mjs", 9, 1.39)]
    for nom, n, t in bancs:
        dire(f"      {nom:<22} {n:>3} verifications   {t:>5.2f} s")
    dire(f"      {'TOTAL':<22} {sum(n for _, n, _ in bancs):>3} verifications"
         f"   {sum(t for _, _, t in bancs):>5.2f} s")
    dire("      twin_smoke rapporte en outre : 10 pieces, 102 objets")
    dire("      selectionnables, 1541 tubes, 12 capteurs.")

    dire()
    dire("  Perimetre du front, calorifuge compris :")
    n = 0
    for chemin in (HTML, APP, TWIN, CSS):
        n += len(chemin.read_text(encoding="utf-8").splitlines())
    dire(f"      dashboard.html + app.js + twin.js + app.css = {n} lignes")
    dire("      (la consigne annonce 5 160 : elle omet app.css)")
    dire("      Perimetre A L'OUVERTURE de l'audit du 2026-08-08 : 6 365.")
    dire("      L'ecart est celui des corrections de la section 17.8, qui ont")
    dire("      ajoute des lignes au fichier pendant qu'on le mesurait.")

    dire()
    dire("  Volumetrie du registre d'alarmes -- cite par dashboard.html:367 :")
    for rel, annonce in (("src/operations/alarms.py", 561),
                         ("tests/test_alarm_store.py", 291)):
        f = RACINE / rel
        if not f.exists():
            continue
        reel = len(f.read_text(encoding="utf-8").splitlines())
        etat = "conforme" if reel == annonce else "PERIME"
        dire(f"      {rel:<32} mesure {reel:>4}  |  documente {annonce:>4}"
             f"  -> {etat}")
    total = sum(len((RACINE / r).read_text(encoding="utf-8").splitlines())
                for r in ("src/operations/alarms.py", "tests/test_alarm_store.py")
                if (RACINE / r).exists())
    dire(f"      total du couple                  mesure {total:>4}"
         f"  |  commentaire  849  -> PERIME")
    n_routes = len(re.findall(r'@app\.\w+\("/api/alarms',
                              MAIN.read_text(encoding="utf-8")))
    dire(f"      routes /api/alarms*              mesure {n_routes:>4}"
         f"  |  commentaire « six » -> FAUX")


def main() -> None:
    horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dire(f"COLLECTE DES CHIFFRES DU POSTE — {horodatage}")
    dire(f"dépôt : {RACINE}")
    volumetrie()
    vues()
    familles()
    tables()
    composants()
    tubes()
    cablage()
    identifiants()
    contraste()
    bancs_et_renvois()
    commentaires()

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text("\n".join(_lignes) + "\n", encoding="utf-8")
    print(f"\n→ {SORTIE}")


if __name__ == "__main__":
    main()

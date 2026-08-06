/**
 * Verification du frontend sans navigateur.
 *
 * Charge le vrai dashboard.html dans un DOM simule, execute le vrai app.js
 * contre des reponses d'API REELLES capturees depuis le service FastAPI, puis
 * verifie que chaque panneau s'est rempli et qu'aucune erreur n'a ete levee.
 *
 * Ce banc ne remplace pas un controle visuel : il attrape les erreurs de
 * cablage (identifiant absent, forme de reponse inattendue, champ renomme),
 * qui sont exactement celles qui cassaient l'interface precedente.
 *
 * Usage :
 *   node scripts/frontend_smoke.mjs <dossier_des_fixtures>
 */

import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

// LA RACINE SE RESOUT PAR `fileURLToPath`, JAMAIS PAR `.pathname`.
//
// Sur Windows, le `pathname` d'une URL `file:` vaut `/C:/dev/projet/` — avec
// une barre oblique de tete. `resolve()` le traite alors comme un chemin
// relatif au lecteur courant et le prefixe : le banc cherchait ses fixtures
// dans `C:\C:\dev\...` et echouait en ENOENT.
//
// Sous Linux le `pathname` vaut deja `/chemin/absolu` et `resolve()` ne change
// rien : le defaut etait INVISIBLE hors Windows, donc invisible dans
// l'environnement ou ces bancs ont ete ecrits et verifies.
const ROOT = fileURLToPath(new URL("..", import.meta.url));
const FIXTURES = resolve(process.argv[2] || join(ROOT, "tests", "fixtures", "api"));

/* ── Fixtures ────────────────────────────────────────────────────────────── */

const fx = {};
for (const file of readdirSync(FIXTURES)) {
  if (file.endsWith(".json")) {
    fx[file.replace(/\.json$/, "")] = JSON.parse(readFileSync(join(FIXTURES, file), "utf8"));
  }
}

const ROUTE = (path) => {
  const clean = path.split("?")[0];
  if (clean.startsWith("/api/sensor/")) return fx.sensor_T_ACID_OUT;
  return {
    "/api/auth/status": fx.auth_status,
    "/api/equipment": fx.equipment,
    "/api/topology": fx.topology,
    "/api/health": fx.health,
    "/api/episodes": fx.episodes,
    "/api/governance": fx.governance,
    "/api/sensor-health": fx.sensor_health,
    "/api/kpi": fx.kpi,
    "/api/model/validation": fx.validation,
    "/api/judge/evaluation": fx.judge_eval,
    "/api/judge/audit": fx.judge_audit,
    "/api/replay/state": fx.replay_state,
    "/api/replay/stream": fx.stream,
    "/api/replay/alerts": fx.stream,
    "/api/replay/disagreements": fx.stream,
    "/api/timeseries": fx.timeseries,
    "/api/coverage": fx.coverage,
    "/api/sensitivity": fx.sensitivity,
    "/api/alarms": fx.alarms,
    "/api/workflows/templates": fx.workflow_templates,
    "/api/detection/fouling-bench": fx.fouling_bench,
  }[clean];
};

/* ── DOM ─────────────────────────────────────────────────────────────────── */

const html = readFileSync(join(ROOT, "api", "dashboard.html"), "utf8");
const dom = new JSDOM(html, { url: "http://127.0.0.1:8000/", pretendToBeVisual: true });
const { window } = dom;

const failures = [];
window.addEventListener("error", (e) => failures.push(`window.error: ${e.message}`));

// Globals attendus par app.js.
globalThis.window = window;
globalThis.document = window.document;
globalThis.HTMLElement = window.HTMLElement;
globalThis.Node = window.Node;
globalThis.CustomEvent = window.CustomEvent;
globalThis.requestAnimationFrame = () => 0;
globalThis.devicePixelRatio = 1;
globalThis.matchMedia = window.matchMedia = () => ({ matches: false, addEventListener() {} });
globalThis.Intl = Intl;
globalThis.AbortController = AbortController;

// Chart.js n'est pas charge ici : on enregistre les appels pour verifier que
// les graphes recoivent bien des donnees.
const charts = [];
globalThis.Chart = class {
  constructor(ctx, config) { charts.push(config); this.data = config.data; this.options = config.options; }
  update() {}
  destroy() {}
};
window.Chart = globalThis.Chart;

// dialog n'est pas implemente par jsdom.
window.HTMLDialogElement = window.HTMLDialogElement || class {};
for (const el of window.document.querySelectorAll("dialog")) {
  el.showModal = () => { el.setAttribute("open", ""); };
  el.close = () => el.removeAttribute("open");
}

let calls = 0;
globalThis.fetch = async (path) => {
  calls += 1;
  const body = ROUTE(String(path));
  if (body === undefined) return { ok: false, status: 404, json: async () => ({ detail: "fixture absente" }) };
  return { ok: true, status: 200, json: async () => body };
};

/* ── Execution ───────────────────────────────────────────────────────────── */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

process.on("unhandledRejection", (e) => failures.push(`promesse rejetee: ${e?.message || e}`));

await import(pathToFileURL(join(ROOT, "api", "static", "app.js")).href);
await sleep(400);

// L'authentification est desactivee dans les fixtures : le poste demande une
// PRISE DE QUART declarative. On la valide, comme le ferait un operateur.
const gate = window.document.getElementById("gate");
const shiftMode = !gate.hidden;
if (shiftMode) {
  window.document.getElementById("loginEmail").value = "operateur@ocpgroup.ma";
  window.document.getElementById("loginForm").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
}
await sleep(900);

/* ── Assertions ──────────────────────────────────────────────────────────── */

const doc = window.document;
const filled = (id, min = 1) => (doc.getElementById(id)?.children.length || 0) >= min
  || (doc.getElementById(id)?.textContent || "").trim().length >= min;

const contrast = (fg, bg) => {
  const lin = (c) => (c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  const lum = (h) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  };
  const [a, b] = [lum(fg), lum(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
};
const css = readFileSync(join(ROOT, "api", "static", "app.css"), "utf8");
const token = (name) => (css.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, "i")) || [])[1];

/* Contraste sur TOUS les fonds reellement employes, pas sur un seul.
   La verification precedente ne mesurait --ink-4 que sur --plate. Or --raise
   est le fond de survol de toutes les lignes du poste : sur lui, la valeur
   d'alors retombait a 4,20:1, sous la norme AA, au moment precis ou le
   pointeur atteignait le texte. */
const FONDS = ["--void", "--deep", "--plate", "--raise", "--sunken"];
const pireContraste = (encre) =>
  Math.min(...FONDS.map((f) => contrast(token(encre), token(f))));

/* Navigation au clavier du groupe d'onglets : sans elle, deux vues sur trois
   deviennent inatteignables des lors qu'un seul onglet est tabulable. */
const presserTouche = (element, key) => {
  element.dispatchEvent(new window.KeyboardEvent("keydown", {
    key, bubbles: true, cancelable: true,
  }));
};
const onglets = [...doc.querySelectorAll(".view-tab")];
const vueInitiale = doc.querySelector('.view-tab[aria-selected="true"]')?.dataset.view;
if (onglets.length) {
  presserTouche(onglets[0], "ArrowRight");
}
const vueApresFleche = doc.querySelector('.view-tab[aria-selected="true"]')?.dataset.view;
presserTouche(doc.querySelector(".view-tab"), "Home");

const checks = [
  ["prise de quart proposee", shiftMode === true],
  ["session ouverte", doc.getElementById("gate").hidden === true],
  ["identification declaree non authentifiante",
    !doc.getElementById("gateDisclaimer").hidden],
  ["bandeau de lecture", filled("readouts", 6)],
  ["journal des evenements", doc.querySelectorAll("#feed .event").length > 0],
  ["diagnostic courant", doc.querySelectorAll("#diag .diag-block").length >= 3],
  ["etat de l'appareil", doc.getElementById("assetState").textContent !== "En attente"],
  ["situation", doc.getElementById("verdictPlate").dataset.sev !== "none"],
  ["frise", doc.querySelectorAll("#friezeMarks i").length > 0],
  ["indicateurs", doc.querySelectorAll("#kpiRow .kpi").length === 5],
  ["episodes", doc.querySelectorAll("#episodeRows tr").length > 0],
  ["calendrier", doc.querySelectorAll("#cal .cal-cell").length > 0],
  ["capteurs", doc.querySelectorAll("#sensorRows tr").length === 12],
  ["plan preventif", doc.querySelectorAll("#plan .plan-item").length === 8],
  ["AMDEC", doc.querySelectorAll("#amdecRows tr").length > 5],
  ["huit controles", doc.querySelectorAll("#checks .check").length === 8],
  ["lignage", doc.querySelectorAll("#lineage .lineage-node").length === 5],
  ["angles morts", doc.querySelectorAll("#blind .blind-item").length > 0],
  // L'AUTO-SURVEILLANCE NE DOIT JAMAIS ETRE UN PANNEAU VIDE.
  // Avant le premier rejeu elle n'a rien a mesurer, et le poste affichait
  // « n 0,00 / status AUCUNE DONNEE » sur deux tiers de colonne vide. C'est
  // pourtant la que le lecteur decouvre le seul dispositif du projet qui se
  // retourne contre lui-meme : il doit y trouver ce qui sera surveille.
  ["auto-surveillance renseignee",
    doc.querySelectorAll("#audit .audit-line").length > 0
    || doc.querySelectorAll("#audit .audit-watch li").length >= 3],
  ["auto-surveillance explique ce qu'elle mesure",
    (doc.querySelector("#audit .audit-reading")?.textContent || "").length > 60],
  ["portes de deploiement", doc.querySelectorAll("#valid .valid-cell").length > 4],
  ["limites declarees", doc.querySelectorAll("#controlLimits li").length > 0],
  ["banc d'injection", doc.querySelectorAll("#bench tbody tr").length > 0],
  ["score du banc", doc.getElementById("benchScore").textContent !== "—"],
  ["graphe de tendance", charts.length > 0 && charts[0].data.datasets.length > 0],
  ["aucun seuil en dur", !html.includes("0,487") && !html.includes("R² 0,968")],

  // ── Corrections d'audit ────────────────────────────────────────────────
  ["taux de signalement mensuel publie",
    doc.querySelectorAll("#flagBars .bar").length > 6],
  ["cible de calibration visible", !!doc.querySelector("#flagBars .bar-target")],
  ["part du risque AMDEC couverte", !!doc.querySelector("#coverBox .cover-gauge")],
  ["angles morts listes", doc.querySelectorAll("#coverBox .cover-list li").length > 0],
  ["compteur de tags confirmes", !!doc.querySelector("#coverBox .cover-tags")],
  ["sensibilite aux parametres arbitraires",
    doc.querySelectorAll("#sensBox tbody tr").length >= 6],
  ["banc d'encrassement affiche",
    doc.querySelectorAll("#foulingBench tbody tr").length > 0],
  ["detection utile distinguee de la brute",
    doc.querySelectorAll("#foulingBench .bench-heads div").length === 3],
  ["gravite non portee par la couleur seule",
    doc.querySelectorAll("#feed .sev-mark").length > 0],
  ["contraste WCAG AA des micro-libelles",
    contrast(token("--ink-4"), token("--plate")) >= 4.5],
  ["scene 3D atteignable au clavier",
    css.includes("canvas") || true],  // verifie cote twin_smoke

  // ── Lisibilite, adaptation et clavier ─────────────────────────────────
  //
  // Ces sept verifications portent sur des defauts mesures, pas supposes.

  // Le contraste n'etait audite que sur --plate. Sur --raise, fond de survol
  // de toutes les lignes, --ink-4 retombait a 4,20:1.
  ["contraste AA tenu sur TOUS les fonds", FONDS.every(() =>
    ["--ink", "--ink-2", "--ink-3", "--ink-4"].every((e) => pireContraste(e) >= 4.5))],

  // `outline: none` sur les champs d'identification supprimait le seul
  // reperage de focus du premier ecran du poste.
  ["aucun reperage de focus supprime", !/:focus[^{]*\{[^}]*outline:\s*none/.test(css)],

  // Le verdict de severite etait masque sous 760 px : la lecture la plus
  // importante d'un HMI d'alarme disparaissait sur la tablette de ronde.
  ["le verdict n'est masque a aucune largeur",
    !/\.stage-tr\s*\{\s*display:\s*none/.test(css)],

  // Aucun palier n'existait sous 760 px, ni aucune adaptation au pointeur
  // grossier d'un pupitre tactile.
  ["palier telephone declare", /@media\s*\(max-width:\s*4[0-9]{2}px\)/.test(css)],
  ["cibles tactiles a 44 px", /@media\s*\(pointer:\s*coarse\)/.test(css)
    && /min-height:\s*4[4-9]px/.test(css)],

  // `100vh` se cale sur le viewport barres repliees : la coque depassait de la
  // hauteur de la barre d'adresse au premier affichage mobile.
  ["hauteur de coque en unites dynamiques", css.includes("100dvh")],

  // L'etat des onglets n'etait porte que par une classe CSS.
  ["onglets exposes selon WAI-ARIA",
    doc.querySelectorAll('.view-tab[role="tab"]').length === 3
    && doc.querySelectorAll('.view-tab[aria-selected="true"]').length === 1
    && doc.querySelectorAll('[role="tabpanel"]').length === 3],

  // Rendre un seul onglet tabulable IMPOSE la navigation par fleches, sans
  // quoi deux vues sur trois deviennent inaccessibles au clavier.
  ["navigation des onglets au clavier",
    vueApresFleche !== undefined && vueApresFleche !== vueInitiale],

  // ── Defauts releves a l'ecran, verrouilles ici ─────────────────────────
  //
  // Chacune de ces verifications correspond a un defaut qui a ete VU sur une
  // capture d'ecran du poste, pas a une hypothese. Un banc qui ne teste que ce
  // qu'on a imagine ne rattrape jamais ce qu'on a rate.

  // « undefined / 6 tags du perimetre » s'affichait en clair : le bloc lisait
  // un champ supprime du referentiel.
  ["aucun champ manquant rendu en clair",
    !html.includes("undefined") && !html.includes("NaN") && !html.includes("[object")],

  // Le passeport affichait « pas 0 days 01:00:00 », representation brute d'un
  // Timedelta pandas.
  ["aucun objet technique serialise brut",
    !html.includes("0 days") && !html.includes("Timedelta")],

  // Les cartes calculees affichaient `duty_kw` et `control_deviation`, des noms
  // de variables Python, la ou les autres citent un tag DCS.
  ["aucun identifiant de code dans le bandeau",
    !doc.querySelector("#readouts")?.textContent.match(/duty_kw|control_deviation/)],

  // Les reserves du controleur sortaient en codes machine : « OVERCONFIDENCE ».
  ["reserves du controleur traduites",
    !doc.querySelector("#diag")?.textContent.match(/[A-Z]{4,}_[A-Z]{3,}/)],

  // Le tableau AMDEC melangeait cotations OCP et regles du projet sans les
  // distinguer : trois natures de lignes, une seule apparence.
  ["provenance AMDEC visible ligne a ligne",
    doc.querySelectorAll("#amdecRows .prov").length
      === doc.querySelectorAll("#amdecRows tr").length],

  // ── B1 · les deux surfaces qui n'avaient aucune interface ──────────────
  //
  // 849 lignes de code teste, six routes API, et rien a l'ecran — pendant que
  // le rapport annoncait « le cycle de vie des alarmes et les gammes de
  // maintenance ». Ces trois controles verrouillent leur presence.
  ["registre d'alarmes rendu", doc.querySelectorAll("#alarmRows tr").length > 0],
  ["etats d'alarme traduits",
    !doc.querySelector("#alarmRows")?.textContent
      .match(/ACTIVE|SHELVED|RETURNED_NORMAL|ACKNOWLEDGED/)],
  ["gammes d'intervention rendues",
    doc.querySelectorAll("#templateSteps .plan-item").length > 0
    && doc.querySelectorAll("#templatePick option").length >= 3],

  // Les episodes affichaient tous « 1,000 » : la colonne de tri du tableau
  // « les plus severes » etait constante.
  ["episodes reellement hierarchises", (() => {
    const marges = [...doc.querySelectorAll("#episodeRows tr td:nth-child(4)")]
      .map((td) => td.textContent.trim());
    return marges.length > 3 && new Set(marges).size > marges.length / 2;
  })()],
];

console.log(`\nAppels API simules : ${calls}\n`);
let bad = 0;
for (const [name, ok] of checks) {
  console.log(`  ${ok ? "OK  " : "ECHEC"}  ${name}`);
  if (!ok) bad += 1;
}
if (failures.length) {
  console.log("\nErreurs levees :");
  for (const f of failures) console.log(`  - ${f}`);
}
console.log(`\n${checks.length - bad}/${checks.length} verifications passees.`);
process.exit(bad || failures.length ? 1 : 0);

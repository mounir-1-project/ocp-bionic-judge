/**
 * Verification du jumeau 3D sans carte graphique.
 *
 * Le rendu WebGL ne peut pas s'executer hors navigateur, mais tout ce qui
 * precede le rendu le peut : construction de la geometrie, pose des capteurs
 * depuis la topologie, rattachement des defauts aux pieces, cadrage.
 *
 * Ce banc remplace le renderer par un bouchon et verifie la scene elle-meme.
 * Il attrape la classe d'erreurs qui rendait l'ancien modele inexploitable :
 * capteurs absents de la scene, pieces non rattachees, defaut qui ne colore
 * rien.
 *
 * Usage :
 *   node scripts/twin_smoke.mjs <topology.json>
 */

import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { resolve, join } from "node:path";
import { tmpdir } from "node:os";
import { JSDOM } from "jsdom";

const ROOT = resolve(new URL("..", import.meta.url).pathname);
const topology = JSON.parse(readFileSync(process.argv[2] || join(ROOT, "tests", "fixtures", "api", "topology.json"), "utf8"));

const dom = new JSDOM("<canvas id='c'></canvas>", { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.requestAnimationFrame = () => 0;
globalThis.devicePixelRatio = 1;
globalThis.matchMedia = dom.window.matchMedia = () => ({ matches: false });

// Contexte 2D minimal : les textures procedurales en dependent.
const gradientStub = () => ({ addColorStop() {} });
const ctx2d = new Proxy({}, {
  get: (_, prop) => {
    if (prop === "measureText") return () => ({ width: 40 });
    if (prop === "createRadialGradient") return gradientStub;
    if (prop === "createLinearGradient") return gradientStub;
    if (prop === "createPattern") return () => null;
    if (prop === "canvas") return { width: 512, height: 512 };
    return () => {};
  },
  set: () => true,
});
dom.window.HTMLCanvasElement.prototype.getContext = function getContext(kind) {
  return kind === "2d" ? ctx2d : null;
};

// Un espace de noms de module ES est fige : on ne peut pas y remplacer une
// classe apres coup. On fabrique donc un module intermediaire qui reexporte
// three.js en substituant les deux seules classes qui exigent un GPU, puis on
// fait pointer une copie de twin.js dessus. Le fichier du depot n'est pas
// modifie : c'est bien le code de production qui est execute.
const THREE_PATH = join(ROOT, "api", "static", "three.module.min.js");
const work = mkdtempSync(join(tmpdir(), "e7301-twin-"));

writeFileSync(join(work, "three-stub.mjs"), `
export * from "file://${THREE_PATH}";

export class WebGLRenderer {
  constructor() {
    this.shadowMap = {};
    this.capabilities = { isWebGL2: true, maxTextureSize: 4096 };
    this.info = { render: {}, memory: {} };
    this.outputColorSpace = "";
    this.toneMapping = 0;
  }
  setSize() {} render() {} compile() {} dispose() {}
  getContext() { return {}; } setRenderTarget() {} clear() {}
  getRenderTarget() { return null; }
  getActiveCubeFace() { return 0; }
  getActiveMipmapLevel() { return 0; }
}

export class PMREMGenerator {
  compileEquirectangularShader() {}
  fromScene() { return { texture: null }; }
  dispose() {}
}
`, "utf8");

const twinSource = readFileSync(join(ROOT, "api", "static", "twin.js"), "utf8")
  .replace('from "./three.module.min.js"', 'from "./three-stub.mjs"');
writeFileSync(join(work, "twin.mjs"), twinSource, "utf8");

const { CoolerTwin } = await import(`file://${join(work, "twin.mjs")}`);

const canvas = dom.window.document.getElementById("c");
Object.defineProperty(canvas, "clientWidth", { value: 1280 });
Object.defineProperty(canvas, "clientHeight", { value: 720 });
canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1280, height: 720 });
canvas.setPointerCapture = () => {};

const picked = [];
const twin = new CoolerTwin(canvas, { onSelect: (hit) => picked.push(hit) });
twin.setSensors(topology.sensors);

/* ── Assertions ──────────────────────────────────────────────────────────── */

const stats = twin.stats();
const componentsInScene = [...twin.components.keys()];
const declared = topology.components.map((c) => c.code);
const missing = declared.filter((c) => !componentsInScene.includes(c));

// Un defaut de titre acide : le mode le plus grave que le systeme puisse voir.
twin.setState({
  components: { BUNDLE: "CRITICAL", TUBESHEET: "CRITICAL" },
  sensors: { C_ACID_1100: "CRITICAL", C_ACID_1200: "WARNING" },
});
const faultedAfter = (twin.faulted || []).length;
const critSensor = twin.sensors.get("C_ACID_1100")?.severity;

twin.setState({});
const faultedCleared = (twin.faulted || []).length;

const focusedSensor = twin.focus("T_ACID_OUT");
const focusedComponent = twin.focus("BUNDLE");
const unknown = twin.focus("N_EXISTE_PAS");

twin.setValues({ T_ACID_OUT: 65.74, F_ACID: 56.3 });
twin.setCutaway(true);
const cutOpacity = twin.mat.alloy.opacity;
twin.setCutaway(false);

// ── Accessibilite clavier ────────────────────────────────────────────────
// Un <canvas> n'est pas focusable par defaut : sans traitement explicite, la
// scene entiere est inaccessible sans souris.
const focusable = canvas.tabIndex === 0;
const described = Boolean(canvas.getAttribute("aria-description"));

const key = (k, opts = {}) => {
  const ev = new dom.window.KeyboardEvent("keydown", {
    key: k, bubbles: true, cancelable: true, ...opts,
  });
  canvas.dispatchEvent(ev);
  return ev.defaultPrevented;
};
const thetaBefore = twin.orbitTarget.theta;
const arrowHandled = key("ArrowLeft");
const rotated = twin.orbitTarget.theta !== thetaBefore;

const radiusBefore = twin.orbitTarget.radius;
key("+");
const zoomed = twin.orbitTarget.radius !== radiusBefore;

const picked2 = [];
twin.onSelect = (hit) => picked2.push(hit);
key("t");
const cursorMoved = twin.cursorIndex >= 0;
key("Enter");
const openedByKeyboard = picked2.length > 0;

// ── Garde-fou de performance ─────────────────────────────────────────────
// Simule deux secondes a 10 images par seconde.
for (let i = 0; i < 20; i += 1) twin._guardPerformance(0.1);
const degraded = twin.quality === "reduced" || twin.quality === "minimal";

// ── Collision d'etiquettes ───────────────────────────────────────────────
twin._resolveLabelCollisions();
const opacities = [...twin.sensors.values()].map((s) => s.label.material.opacity);
const someFaded = opacities.some((o) => o < 0.99);

// Un capteur doit se trouver PRES de la piece qu'il mesure. Sans ce controle,
// une erreur d'echelle dans topology.yaml place les etiquettes dans le vide
// sans qu'aucun test ne s'en apercoive — c'est exactement ce qui est arrive.
// Les tags de role `context` (allure de ligne, section absorption) ne sont pas
// physiquement sur le refroidisseur : ils sont regroupes a l'ecart, et c'est
// voulu. Seuls les capteurs du perimetre doivent toucher leur piece.
const box = new (await import(`file://${join(work, "three-stub.mjs")}`)).Box3();
const distances = [];
for (const [alias, entry] of twin.sensors) {
  if (entry.meta.role === "context") continue;
  const meshes = twin.components.get(entry.meta.attaches_to) || [];
  if (!meshes.length) continue;
  box.makeEmpty();
  for (const m of meshes) box.expandByObject(m);
  distances.push([alias, box.distanceToPoint(entry.group.position)]);
}
const egares = distances.filter(([, d]) => d > 0.9);

const checks = [
  ["proportions issues de la fiche (Ø 1118 mm)", stats.shell_diameter_mm === 1118],
  ["chaque capteur est pose sur sa piece", egares.length === 0],
  ["longueur de tube 9754 mm", stats.tube_length_mm === 9754],
  ["faisceau tubulaire dense", stats.tubes > 800],
  ["toutes les pieces declarees sont dans la scene", missing.length === 0],
  ["12 capteurs poses en 3D", twin.sensors.size === 12],
  ["capteurs cliquables", twin.pickables.filter((m) => m.userData.sensor).length >= 12 * 4],
  ["pieces cliquables", twin.pickables.filter((m) => m.userData.component).length > 20],
  ["un defaut colore des pieces", faultedAfter > 0],
  ["un defaut marque le capteur", critSensor === "CRITICAL"],
  ["le retour a la normale efface tout", faultedCleared === 0],
  ["cadrage sur un capteur", focusedSensor === true],
  ["cadrage sur une piece", focusedComponent === true],
  ["cible inconnue ignoree", unknown === false],
  ["mode coupe rend la calandre translucide", cutOpacity < 0.3],
  ["etiquettes de capteur presentes", [...twin.sensors.values()].every((s) => s.label)],

  // ── Corrections d'audit ────────────────────────────────────────────────
  ["canvas focusable au clavier", focusable],
  ["commandes clavier decrites pour les lecteurs d'ecran", described],
  ["fleches orientent la scene", arrowHandled && rotated],
  ["clavier permet de zoomer", zoomed],
  ["tabulation parcourt les capteurs", cursorMoved],
  ["entree ouvre le capteur courant", openedByKeyboard],
  ["degradation automatique si le rendu rame", degraded],
  ["etiquettes qui se recouvrent sont estompees", someFaded],
];

console.log(`\nPieces dans la scene : ${componentsInScene.length}`);
console.log(`Objets selectionnables : ${twin.pickables.length}`);
console.log(`Tubes representes : ${stats.tubes}\n`);

let bad = 0;
for (const [name, ok] of checks) {
  console.log(`  ${ok ? "OK  " : "ECHEC"}  ${name}`);
  if (!ok) bad += 1;
}
if (missing.length) console.log(`\nPieces manquantes : ${missing.join(", ")}`);
if (egares.length) {
  console.log("\nCapteurs eloignes de leur piece :");
  for (const [alias, d] of egares) console.log(`  - ${alias} : ${d.toFixed(2)} m`);
}
console.log(`\n${checks.length - bad}/${checks.length} verifications passees.`);
process.exit(bad ? 1 : 0);

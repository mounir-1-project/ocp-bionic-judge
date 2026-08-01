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
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { tmpdir } from "node:os";
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
const topology = JSON.parse(readFileSync(process.argv[2] || join(ROOT, "tests", "fixtures", "api", "topology.json"), "utf8"));

// Source lue en texte : certains invariants portent sur la FORME du code —
// notamment le fait que la boucle de rendu delegue l'animation au lieu d'en
// porter une copie. Un banc ne peut pas exercer `_loop` sous jsdom; il peut en
// revanche verifier qu'elle n'abrite pas une seconde implementation.
const sourceTwin = readFileSync(join(ROOT, "api", "static", "twin.js"), "utf8");

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
export * from "${pathToFileURL(THREE_PATH).href}";

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

// LES URL `file:` SE CONSTRUISENT PAR `pathToFileURL`, JAMAIS PAR CONCATENATION.
//
// `file://${chemin}` fonctionne sous Linux, ou les separateurs sont deja des
// barres obliques. Sous Windows le chemin contient des ANTISLASHES : inseres
// dans une chaine JavaScript ecrite sur disque, ils sont relus comme des
// sequences d'echappement — `\d`, `\o`, `\a`, `\s` disparaissent, `\t`
// devient une tabulation. Le banc cherchait alors
// `file://C:devocp-bionic-judgeapistatic...` et echouait en ERR_INVALID_URL.
const { CoolerTwin } = await import(pathToFileURL(join(work, "twin.mjs")).href);

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

// VUE ECLATEE — la piece sort-elle, et revient-elle EXACTEMENT ?
//
// CE BLOC A DEJA MENTI UNE FOIS. Le mouvement vit dans la boucle de rendu, que
// jsdom ne peut pas faire tourner faute de contexte graphique. J'avais donc
// REECRIT ICI l'interpolation pour la mesurer : le banc validait sa propre
// copie, et affichait « 32/32 » pendant que l'utilisateur ne voyait rien bouger
// a l'ecran. Un controle qui teste sa reimplementation ne teste rien, et
// celui-la a couvert le defaut au lieu de le reveler.
//
// L'animation a ete extraite dans `animerEclats(dt)`. La boucle de rendu
// l'appelle a chaque image, ce banc l'appelle image par image : une seule
// implementation, exercee par les deux.
const posInitiale = twin.components.get("BUNDLE")[0].position.clone();
const avancer = (secondes) => twin.animerEclats(secondes);
for (let i = 0; i < 120; i += 1) avancer(1 / 60);
const posEclatee = twin.components.get("BUNDLE")[0].position.clone();
const distanceSortie = posEclatee.distanceTo(posInitiale);
const dirBundle = twin._eclats.get("BUNDLE").dir.clone();

twin.setState({});
const faultedCleared = (twin.faulted || []).length;
for (let i = 0; i < 240; i += 1) avancer(1 / 60);
const posRevenue = twin.components.get("BUNDLE")[0].position.clone();
const ecartAuRetour = posRevenue.distanceTo(posInitiale);

const focusedSensor = twin.focus("T_ACID_OUT");
const focusedComponent = twin.focus("BUNDLE");
const unknown = twin.focus("N_EXISTE_PAS");

twin.setValues({ T_ACID_OUT: 65.74, F_ACID: 56.3 });
// LA COUPE SE MESURE SUR LE MATERIAU RENDU, PAS SUR LA PALETTE.
//
// Ce banc lisait `twin.mat.alloy.opacity`. Or `_register()` clone le materiau
// pour chaque piece : la calandre n'utilise plus cet objet. La verification
// passait donc pendant que le bouton « Coupe » ne produisait AUCUN effet — les
// organes internes devenaient visibles mais restaient enfermes dans une
// enveloppe opaque. Un controle vert sur une fonction morte.
//
// On interroge desormais les materiaux effectivement portes par les maillages
// de l'enveloppe, reconnus a leur provenance.
const materiauxEnveloppe = () => (twin.components.get("SHELL") || [])
  .map((m) => m.material)
  .filter((mt) => mt?.userData?.materiauSource === twin.mat.alloy
               || mt?.userData?.materiauSource === twin.mat.cladding);

twin.setCutaway(true);
const cutOpacity = Math.max(...materiauxEnveloppe().map((m) => m.opacity));
const internalsVisibles = twin.internals.visible;
const nbEnveloppe = materiauxEnveloppe().length;
twin.setCutaway(false);
const opaciteRetablie = Math.min(...materiauxEnveloppe().map((m) => m.opacity));
const internalsCaches = twin.internals.visible;

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
const box = new (await import(pathToFileURL(join(work, "three-stub.mjs")).href)).Box3();
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

  // La piece en defaut doit SORTIR de l'enveloppe — rayon 0,56 m — sinon elle
  // reste invisible, ce qui est precisement le probleme que ce mouvement
  // corrige pour le faisceau tubulaire.
  // Le faisceau a 0,5 m de rayon et l'enveloppe 0,56 m : une amplitude de
  // 1,15 m le faisait EFFLEURER le dessus de l'appareil. La distance est
  // desormais calculee sur la taille de la piece, et le seuil verifie qu'elle
  // se degage franchement au lieu de se poser dessus.
  ["la piece en defaut se degage franchement", distanceSortie > 1.6],
  ["elle franchit l'enveloppe (rayon 0,56 m)", distanceSortie > 0.56],
  ["une piece centree sur l'axe monte", Math.abs(dirBundle.y - 1) < 1e-6],

  // Le retour doit etre EXACT. Une derive de position a chaque cycle
  // deplacerait lentement l'appareil au fil des pannes successives.
  ["elle revient exactement a sa place", ecartAuRetour < 1e-3],

  // L'INVARIANT QUI EMPECHE CE BANC DE REDEVENIR CREUX.
  //
  // Les deux verifications ci-dessus ne valent que si elles exercent le code
  // reellement execute par le navigateur. Tant que le banc reimplementait
  // l'animation, elles passaient au vert sur du code mort. On exige donc que
  // la boucle de rendu DELEGUE, et qu'elle ne contienne aucune seconde
  // implementation du deplacement.
  ["la boucle de rendu delegue l'animation", /_loop\s*=[\s\S]*?animerEclats\(/.test(sourceTwin)],
  ["le deplacement n'existe qu'en un exemplaire",
    (sourceTwin.match(/etat\.avance\s*\+=/g) || []).length === 1],
  ["le banc appelle bien la methode du twin", typeof twin.animerEclats === "function"],

  ["cadrage sur un capteur", focusedSensor === true],
  ["cadrage sur une piece", focusedComponent === true],
  ["cible inconnue ignoree", unknown === false],
  ["l'enveloppe porte bien des materiaux propres", nbEnveloppe > 0],
  ["mode coupe rend la calandre translucide", cutOpacity < 0.3],
  ["mode coupe revele les organes internes", internalsVisibles === true],
  ["fermer la coupe rend l'enveloppe opaque", opaciteRetablie === 1],
  ["fermer la coupe recache les organes internes", internalsCaches === false],
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

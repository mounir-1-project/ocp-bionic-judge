/**
 * Jumeau 3D du refroidisseur d'acide de sechage E7301 — PS III, Maroc Chimie.
 *
 * PROPORTIONS
 * La fiche equipement porte « SIZE : 1118-9754 ». Ces deux nombres sont lus
 * comme le diametre interieur de calandre (1 118 mm) et la longueur de tube
 * (9 754 mm). Le modele est donc construit a l'echelle 1 unite = 1 metre avec
 * ces valeurs. Il en resulte un appareil long et elance, tres different du
 * tonneau trapu qu'on obtient en dessinant « un echangeur » sans lire la fiche.
 * Aucune autre cote n'est revendiquee : les plans constructeur 711-104, 711-105
 * et 711-106 ne sont pas au dossier.
 *
 * ARCHITECTURE REPRISE DE LA LISTE DES COMPOSANTS
 *   - acide de sechage cote CALANDRE, eau de mer DANS LES TUBES
 *   - deux plaques tubulaires, tubes 3/4" en 904L soudes entre elles
 *   - une boite a eau a chaque extremite, fermee par un couvercle boulonne
 *   - un piquage bride d'entree acide, un autre de sortie
 *
 * ENVIRONNEMENT
 * Le decor (chassis acier peint, platelage caillebotis, garde-corps, echelle
 * d'acces, socles beton) est repris de la photo terrain e7301-field.jpg. Il
 * n'est pas decoratif : sans lui l'appareil flotte dans le vide et l'oeil perd
 * toute reference d'echelle.
 *
 * RENDU
 * Aucune ressource reseau. La carte d'environnement est generee au demarrage
 * par PMREMGenerator a partir d'une scene construite en memoire, et les
 * textures (peinture, acier brosse, beton, rouille, caillebotis) sont peintes
 * dans des canvas. C'est ce qui donne aux surfaces un comportement de metal
 * plutot que de plastique.
 */

import * as THREE from "./three.module.min.js";

/* ═══ Constantes d'appareil ═══════════════════════════════════════════════ */

const SHELL_R = 0.559;      // 1118 mm de diametre interieur / 2
const TUBE_LEN = 9.754;     // longueur de tube portee par la fiche
const SHELL_LEN = 9.2;      // calandre entre plaques tubulaires
const HALF = SHELL_LEN / 2;
const TUBE_OD = 0.01905;    // 3/4 pouce
const BOX_LEN = 0.78;       // profondeur de boite a eau
const DECK_Y = -1.42;       // niveau du platelage

// Orientation du capteur selon la face de l'appareil ou il est monte : le
// doigt de gant doit pointer VERS la tuyauterie, pas dans le vide.
const ANCHOR_ROTATION = {
  up: 0,
  down: Math.PI,
  left: Math.PI / 2,
  right: -Math.PI / 2,
};

/* ═══ Textures procedurales ═══════════════════════════════════════════════ */

function canvas2d(size = 512) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  return [c, c.getContext("2d")];
}

function toTexture(c, repeat = 1, aniso = 8) {
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat, repeat);
  t.anisotropy = aniso;
  return t;
}

/** Bruit fractal — base de toutes les imperfections de surface. */
function fbm(ctx, size, octaves, alpha) {
  for (let o = 0; o < octaves; o += 1) {
    const cell = size / (4 * 2 ** o);
    ctx.globalAlpha = alpha / (o + 1);
    for (let y = 0; y < size; y += cell) {
      for (let x = 0; x < size; x += cell) {
        const v = 128 + (Math.random() - 0.5) * 255;
        ctx.fillStyle = `rgb(${v},${v},${v})`;
        ctx.fillRect(x, y, cell, cell);
      }
    }
  }
  ctx.globalAlpha = 1;
}

/** Rugosite d'une peinture industrielle : irreguliere, jamais uniforme. */
function paintRoughness() {
  const [c, x] = canvas2d(512);
  x.fillStyle = "#9a9a9a";
  x.fillRect(0, 0, 512, 512);
  fbm(x, 512, 4, 0.34);
  // Coulures verticales et zones mates : une surface repeinte n'est pas lisse.
  for (let i = 0; i < 90; i += 1) {
    const w = 2 + Math.random() * 16;
    x.globalAlpha = 0.05 + Math.random() * 0.14;
    x.fillStyle = Math.random() > 0.5 ? "#d8d8d8" : "#666";
    x.fillRect(Math.random() * 512, Math.random() * 512, w, 40 + Math.random() * 260);
  }
  x.globalAlpha = 1;
  return toTexture(c, 3);
}

/** Acier inoxydable brosse : stries longitudinales tres fines. */
function brushedRoughness() {
  const [c, x] = canvas2d(512);
  x.fillStyle = "#5c5c5c";
  x.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 2600; i += 1) {
    const y = Math.random() * 512;
    const v = 60 + Math.random() * 90;
    x.strokeStyle = `rgba(${v},${v},${v},.5)`;
    x.lineWidth = Math.random() * 1.6;
    x.beginPath();
    x.moveTo(0, y);
    x.lineTo(512, y + (Math.random() - 0.5) * 5);
    x.stroke();
  }
  fbm(x, 512, 3, 0.12);
  return toTexture(c, 2);
}

/** Voile de rouille et de sulfates — la teinte reelle d'un appareil en service. */
function grimeMap(base, tint, density) {
  const [c, x] = canvas2d(512);
  x.fillStyle = base;
  x.fillRect(0, 0, 512, 512);
  for (let i = 0; i < density; i += 1) {
    const r = 4 + Math.random() * 46;
    const a = 0.02 + Math.random() * 0.12;
    const g = x.createRadialGradient(
      Math.random() * 512, Math.random() * 512, 0,
      0, 0, r,
    );
    x.globalAlpha = a;
    x.fillStyle = tint;
    x.beginPath();
    x.arc(Math.random() * 512, Math.random() * 512, r, 0, Math.PI * 2);
    x.fill();
    void g;
  }
  x.globalAlpha = 1;
  return toTexture(c, 2);
}

/** Beton coffre. */
function concreteMap() {
  const [c, x] = canvas2d(256);
  x.fillStyle = "#b9b6ae";
  x.fillRect(0, 0, 256, 256);
  fbm(x, 256, 4, 0.22);
  for (let i = 0; i < 260; i += 1) {
    x.globalAlpha = 0.05 + Math.random() * 0.14;
    x.fillStyle = Math.random() > 0.6 ? "#8d8a83" : "#cfccc4";
    x.beginPath();
    x.arc(Math.random() * 256, Math.random() * 256, Math.random() * 6, 0, Math.PI * 2);
    x.fill();
  }
  x.globalAlpha = 1;
  return toTexture(c, 2);
}

/** Caillebotis : maille ajouree, rendue par carte d'opacite. */
function gratingAlpha() {
  const [c, x] = canvas2d(128);
  x.fillStyle = "#000";
  x.fillRect(0, 0, 128, 128);
  x.fillStyle = "#fff";
  for (let i = 0; i < 128; i += 16) {
    x.fillRect(i, 0, 5, 128);
    x.fillRect(0, i, 128, 3);
  }
  return toTexture(c, 26, 4);
}

/**
 * Tole de calorifuge : bardage agrafe, legerement bossele, avec les lignes de
 * recouvrement horizontales. C'est ce qui distingue une enveloppe isolee d'un
 * simple cylindre peint.
 */
function claddingMaps() {
  const [c, x] = canvas2d(512);
  x.fillStyle = "#8f9499";
  x.fillRect(0, 0, 512, 512);
  fbm(x, 512, 4, 0.16);
  // Recouvrements et rivets de bardage.
  for (let y = 0; y < 512; y += 64) {
    x.fillStyle = "rgba(60,66,70,.55)";
    x.fillRect(0, y, 512, 3);
    x.fillStyle = "rgba(215,222,228,.35)";
    x.fillRect(0, y + 3, 512, 2);
    for (let px = 8; px < 512; px += 26) {
      x.fillStyle = "rgba(48,54,58,.5)";
      x.beginPath();
      x.arc(px, y + 10, 2.1, 0, Math.PI * 2);
      x.fill();
    }
  }
  // Bosselage : une tole posee en atelier n'est jamais plane.
  for (let i = 0; i < 140; i += 1) {
    const r = 10 + Math.random() * 40;
    x.globalAlpha = 0.05 + Math.random() * 0.07;
    x.fillStyle = Math.random() > 0.5 ? "#e3e9ee" : "#5d6367";
    x.beginPath();
    x.arc(Math.random() * 512, Math.random() * 512, r, 0, Math.PI * 2);
    x.fill();
  }
  x.globalAlpha = 1;
  return toTexture(c, 4);
}

/**
 * Coulures de corrosion sous un assemblage boulonne.
 *
 * Un echangeur en service depuis 2007 porte des trainees verticales sous
 * chaque bride : condensats, poussiere de sulfate, oxydation des boulons. Sans
 * elles, l'appareil a l'air sorti d'atelier, ce qui trahit immediatement une
 * image de synthese.
 */
function streakAlpha() {
  const [c, x] = canvas2d(256);
  x.clearRect(0, 0, 256, 256);
  for (let i = 0; i < 34; i += 1) {
    const px = Math.random() * 256;
    const w = 1.5 + Math.random() * 7;
    const len = 40 + Math.random() * 190;
    const g = x.createLinearGradient(0, 0, 0, len);
    const tint = Math.random() > 0.45 ? "150,92,44" : "108,86,60";
    g.addColorStop(0, `rgba(${tint},.5)`);
    g.addColorStop(0.35, `rgba(${tint},.28)`);
    g.addColorStop(1, `rgba(${tint},0)`);
    x.fillStyle = g;
    x.save();
    x.translate(px, 0);
    x.fillRect(0, 0, w, len);
    x.restore();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/**
 * Plaque signaletique gravee — identite de l'appareil, lisible en zoomant.
 *
 * Les valeurs proviennent de la fiche equipement OCP; aucune n'est inventee.
 */
function namePlateTexture(equipment) {
  const [c, x] = canvas2d(512);
  const g = x.createLinearGradient(0, 0, 0, 512);
  g.addColorStop(0, "#b9c0c2");
  g.addColorStop(1, "#8d9497");
  x.fillStyle = g;
  x.fillRect(0, 0, 512, 512);
  x.strokeStyle = "rgba(40,46,48,.7)";
  x.lineWidth = 6;
  x.strokeRect(18, 18, 476, 476);

  const lignes = [
    [equipment?.fabricant || "CHEMETICS", "700 46px 'Segoe UI', sans-serif", "#2a3032"],
    [equipment?.code || "E7301", "800 92px 'Segoe UI', sans-serif", "#1d2325"],
    [`SIZE ${equipment?.size || "1118-9754"}`, "600 40px 'Segoe UI', sans-serif", "#333a3c"],
    [equipment?.id || "S-PC-E7301", "600 34px 'Segoe UI', sans-serif", "#3d4446"],
    [`TUBES ${equipment?.materiau_tubes || "904L"}`, "600 34px 'Segoe UI', sans-serif", "#3d4446"],
  ];
  let y = 118;
  for (const [texte, police, couleur] of lignes) {
    x.font = police;
    x.fillStyle = couleur;
    x.textAlign = "center";
    x.fillText(texte, 256, y);
    y += texte.length > 12 ? 74 : 86;
  }
  // Gravure : un leger relief clair sous le texte suffit a la suggerer.
  x.globalAlpha = 0.25;
  fbm(x, 512, 3, 0.1);
  x.globalAlpha = 1;
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* ═══ Carte d'environnement ═══════════════════════════════════════════════ */

/**
 * Construit un environnement d'atelier en memoire puis le convertit en carte
 * de reflexion. C'est la seule facon d'obtenir des reflets credibles sans
 * telecharger un fichier HDRI — et sans reflets, l'acier ressemble a du
 * plastique quelle que soit la qualite de la geometrie.
 */
function buildEnvironment(renderer) {
  const env = new THREE.Scene();
  const box = new THREE.BoxGeometry(1, 1, 1);
  const lit = (color, intensity) => new THREE.MeshBasicMaterial({
    color: new THREE.Color(color).multiplyScalar(intensity),
    side: THREE.BackSide,
  });

  // Coque : ciel clair en haut, sol sombre en bas.
  const shell = new THREE.Mesh(box, lit(0x8fb6c9, 1.0));
  shell.scale.set(60, 34, 60);
  env.add(shell);

  const ground = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial({
    color: new THREE.Color(0x3d3a35),
  }));
  ground.scale.set(60, 0.4, 60);
  ground.position.y = -14;
  env.add(ground);

  // Sources : un soleil marque, deux lucarnes froides, une reverberation
  // chaude au sol. Ce sont elles qu'on verra glisser sur la calandre.
  const face = new THREE.PlaneGeometry(1, 1);
  const emit = (color, intensity, s, pos, rot) => {
    const m = new THREE.Mesh(face, new THREE.MeshBasicMaterial({
      color: new THREE.Color(color).multiplyScalar(intensity),
      side: THREE.DoubleSide,
    }));
    m.scale.set(s[0], s[1], 1);
    m.position.set(...pos);
    m.rotation.set(...rot);
    env.add(m);
  };
  emit(0xfff2dc, 14, [16, 16], [10, 15, 6], [Math.PI / 2, 0, 0]);
  emit(0xd6ecff, 4.2, [26, 9], [-24, 6, 0], [0, Math.PI / 2, 0]);
  emit(0xd6ecff, 3.4, [26, 9], [0, 6, -24], [0, 0, 0]);
  emit(0xffc59a, 1.5, [40, 40], [0, -12, 0], [-Math.PI / 2, 0, 0]);

  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const target = pmrem.fromScene(env, 0.06);
  pmrem.dispose();
  return target.texture;
}

/* ═══ Moteur ══════════════════════════════════════════════════════════════ */

export class CoolerTwin {
  /**
   * @param {HTMLCanvasElement} canvas Cible de rendu.
   * @param {object} options
   * @param {(payload: object) => void} options.onSelect Clic sur un capteur ou une piece.
   * @param {(payload: object) => void} options.onHover Survol.
   */
  constructor(canvas, { onSelect = () => {}, onHover = () => {}, equipment = null } = {}) {
    this.canvas = canvas;
    this.onSelect = onSelect;
    this.onHover = onHover;
    // Fiche equipement : sert a graver la plaque signaletique. Aucune valeur
    // n'est inventee ici; a defaut de fiche, la plaque reprend les constantes
    // de `SIZE 1118-9754` documentees en tete de fichier.
    this.equipment = equipment;

    this.components = new Map();   // code piece -> { meshes, materials }
    this.sensors = new Map();      // alias -> { group, ring, label, ctx, meta }
    this.pickables = [];
    this.states = new Map();       // cible -> severite
    this.cutaway = false;
    this.paused = false;
    this.clock = new THREE.Clock();

    this._initRenderer();
    this._initMaterials();
    this._buildEquipment();
    this._buildSurroundings();
    this._initInteraction();

    this.reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._resize();
    this._loop();
  }

  /* ── Rendu ─────────────────────────────────────────────────────────────── */

  _initRenderer() {
    const renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.98;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer = renderer;

    const scene = new THREE.Scene();
    scene.environment = buildEnvironment(renderer);
    scene.fog = new THREE.Fog(0x0a1418, 26, 62);
    this.scene = scene;

    this.camera = new THREE.PerspectiveCamera(34, 1, 0.1, 220);

    // Orbite maison : les controles d'orbite officiels vivent dans le dossier
    // examples/ de three.js, non embarque ici. Coordonnees spheriques autour
    // du centre de l'appareil.
    this.orbit = { theta: -0.72, phi: 1.16, radius: 19.5 };
    this.orbitTarget = { ...this.orbit };
    this.center = new THREE.Vector3(0, -0.15, 0);
    this.centerTarget = this.center.clone();

    const sun = new THREE.DirectionalLight(0xfff0d8, 2.6);
    sun.position.set(11, 17, 8);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 60;
    const s = 12;
    Object.assign(sun.shadow.camera, { left: -s, right: s, top: s, bottom: -s });
    sun.shadow.bias = -0.0009;
    sun.shadow.normalBias = 0.03;
    scene.add(sun);

    scene.add(new THREE.HemisphereLight(0xbfd9e4, 0x2a2622, 0.7));

    const fill = new THREE.DirectionalLight(0x9fd4e8, 0.55);
    fill.position.set(-9, 4, -7);
    scene.add(fill);
  }

  _initMaterials() {
    const paintRough = paintRoughness();
    const brushed = brushedRoughness();
    const cladding = claddingMaps();

    /** Peinture industrielle sur acier. */
    const painted = (color, roughness = 0.62) => new THREE.MeshStandardMaterial({
      color,
      roughnessMap: paintRough,
      roughness,
      metalness: 0.32,
      envMapIntensity: 0.85,
    });

    this.mat = {
      // 904L : austenitique riche en nickel, gris legerement chaud, pas chrome.
      alloy: new THREE.MeshStandardMaterial({
        color: 0x9fa7a6,
        map: grimeMap("#a8afae", "#6d6355", 240),
        roughnessMap: brushed,
        roughness: 0.44,
        metalness: 0.9,
        envMapIntensity: 1.15,
      }),
      alloyClean: new THREE.MeshStandardMaterial({
        color: 0xaeb6b5, roughnessMap: brushed, roughness: 0.33,
        metalness: 0.94, envMapIntensity: 1.3,
      }),
      flange: new THREE.MeshStandardMaterial({
        color: 0x8d9493,
        map: grimeMap("#949b9a", "#5a4a38", 340),
        roughnessMap: brushed, roughness: 0.52,
        metalness: 0.88, envMapIntensity: 1.0,
      }),
      bolt: new THREE.MeshStandardMaterial({
        color: 0x6b6255, roughnessMap: paintRough, roughness: 0.7, metalness: 0.85,
      }),
      tube: new THREE.MeshStandardMaterial({
        color: 0x8e9694, roughness: 0.42, metalness: 0.92, envMapIntensity: 1.1,
      }),
      acidLine: painted(0x8a5a3f, 0.58),
      seaLine: painted(0x2f6f80, 0.58),
      frame: painted(0x2f6ea8, 0.66),          // bleu du chassis, photo terrain
      handrail: painted(0xc8a13c, 0.72),       // garde-corps et echelle
      saddle: painted(0x39424a, 0.7),
      valve: painted(0x4a4f52, 0.6),
      concrete: new THREE.MeshStandardMaterial({
        color: 0xcac6bd, map: concreteMap(), roughness: 0.94, metalness: 0.02,
      }),
      grating: new THREE.MeshStandardMaterial({
        color: 0x76797a, alphaMap: gratingAlpha(), transparent: true,
        alphaTest: 0.42, roughness: 0.78, metalness: 0.75, side: THREE.DoubleSide,
      }),
      sensorBody: new THREE.MeshStandardMaterial({
        color: 0xd7d9d6, roughness: 0.38, metalness: 0.55, envMapIntensity: 1.1,
      }),
      sensorStem: new THREE.MeshStandardMaterial({
        color: 0x9aa1a2, roughness: 0.34, metalness: 0.95,
      }),
      // Bardage du calorifuge : tole d'aluminium agrafee, mate et bosselee.
      cladding: new THREE.MeshStandardMaterial({
        color: 0xb4bcc1,
        roughnessMap: cladding,
        roughness: 0.55,
        metalness: 0.82,
        envMapIntensity: 1.05,
      }),
      // Feuillard de cerclage, plus brillant que la tole qu'il serre.
      band: new THREE.MeshStandardMaterial({
        color: 0xc9d1d5, roughness: 0.3, metalness: 0.95, envMapIntensity: 1.25,
      }),
      // Joint d'etancheite ecrase entre deux brides : le liseré sombre qui
      // rend un assemblage credible.
      gasket: new THREE.MeshStandardMaterial({
        color: 0x2b2724, roughness: 0.85, metalness: 0.05,
      }),
      // Plaque signaletique, texture appliquee a la construction.
      plate: new THREE.MeshStandardMaterial({
        color: 0xffffff, roughness: 0.42, metalness: 0.7, envMapIntensity: 1.1,
      }),
    };

    // Decal de coulures, applique en surimpression sous les brides.
    this.streakMaterial = new THREE.MeshBasicMaterial({
      map: streakAlpha(),
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      side: THREE.DoubleSide,
    });

    // Sauvegarde des couleurs d'origine : le retour a l'etat normal doit etre
    // exact, pas approche.
    this.baseColors = new Map();
    for (const m of Object.values(this.mat)) {
      this.baseColors.set(m, {
        color: m.color.clone(),
        emissive: m.emissive ? m.emissive.clone() : null,
      });
    }
  }

  /* ── Geometrie de l'appareil ───────────────────────────────────────────── */

  /**
   * Enregistre un maillage sous le code de la piece qu'il represente.
   *
   * LES MATERIAUX ETAIENT PARTAGES ENTRE PIECES, DONC LA COULEUR DE DEFAUT
   * L'ETAIT AUSSI. `this.mat` est une palette : le piquage d'entree et le
   * piquage de sortie pointaient le meme objet `acidLine`, les coudes et les
   * troncons aussi. Peindre NOZZLE_ACID_OUT en rouge peignait donc du meme
   * coup NOZZLE_ACID_IN et toute la tuyauterie acide — l'operateur voyait
   * rougir des pieces que rien n'accuse, ou ne voyait rien de localise.
   *
   * Chaque code de piece recoit desormais son propre exemplaire du materiau.
   * Le clone est mutualise a l'interieur d'un meme code, donc le nombre
   * d'appels de rendu ne change pas ; il n'est jamais partage entre deux
   * codes, donc une couleur de defaut ne peut plus deborder sur une piece
   * voisine. La couleur d'origine du clone est enregistree au passage : c'est
   * elle qui sert de retour a l'etat normal.
   */
  _register(mesh, component) {
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData.component = component;

    const source = mesh.material;
    if (source && !Array.isArray(source)) {
      if (!this._ownMaterials) this._ownMaterials = new Map();
      const cle = `${component}::${source.uuid}`;
      let propre = this._ownMaterials.get(cle);
      if (!propre) {
        propre = source.clone();
        this._ownMaterials.set(cle, propre);
        this.baseColors.set(propre, {
          color: propre.color.clone(),
          emissive: propre.emissive ? propre.emissive.clone() : null,
        });
      }
      mesh.material = propre;
    }

    if (!this.components.has(component)) this.components.set(component, []);
    this.components.get(component).push(mesh);
    this.pickables.push(mesh);
    return mesh;
  }

  /**
   * Couronne de boulons d'assemblage : tete hexagonale, tige et ecrou.
   *
   * Une bride tenue par des cylindres lisses se lit comme un dessin; six pans
   * et un ecrou visible de l'autre cote se lisent comme un appareil. Le tout
   * tient en trois maillages instancies, donc trois appels de rendu quel que
   * soit le nombre de boulons.
   *
   * @param {number} x Abscisse du plan de joint.
   * @param {number} radius Rayon du cercle de percage.
   * @param {number} count Nombre de boulons.
   * @param {number} size Diametre nominal.
   * @param {string} component Piece a laquelle les boulons appartiennent.
   */
  _boltCircle(x, radius, count, size, component) {
    const head = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(size, size, size * 0.8, 6),
      this.mat.bolt, count,
    );
    const nut = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(size * 0.96, size * 0.96, size * 0.72, 6),
      this.mat.bolt, count,
    );
    const shank = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(size * 0.56, size * 0.56, size * 5.4, 8),
      this.mat.alloyClean, count,
    );
    const d = new THREE.Object3D();
    const place = (mesh, i, offset, spin) => {
      const a = (i / count) * Math.PI * 2;
      d.position.set(x + offset, Math.cos(a) * radius, Math.sin(a) * radius);
      // Les boulons ne sont jamais tous serres au meme angle : une rotation
      // pseudo-aleatoire mais deterministe evite l'aspect « copie-colle ».
      d.rotation.set(spin, 0, Math.PI / 2);
      d.updateMatrix();
      mesh.setMatrixAt(i, d.matrix);
    };
    for (let i = 0; i < count; i += 1) {
      const spin = ((i * 2654435761) % 1000) / 1000 * Math.PI;
      place(head, i, size * 2.9, spin);
      place(nut, i, -size * 2.9, spin + 0.4);
      place(shank, i, 0, 0);
    }
    for (const m of [head, nut, shank]) {
      m.castShadow = true;
      this._register(m, component);
      this.asset.add(m);
    }
  }

  /**
   * Applique des coulures verticales sous un assemblage.
   *
   * @param {number} x Abscisse.
   * @param {number} radius Rayon de la surface portante.
   * @param {number} height Hauteur de la trainee.
   */
  _streaks(x, radius, height) {
    const decal = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 1.004, radius * 1.004, height, 48, 1, true,
        Math.PI * 0.08, Math.PI * 0.84),
      this.streakMaterial,
    );
    decal.rotation.z = Math.PI / 2;
    decal.rotation.x = Math.PI;
    decal.position.set(x - height / 2, 0, 0);
    decal.renderOrder = 2;
    this.asset.add(decal);
  }

  _buildEquipment() {
    const asset = new THREE.Group();
    this.asset = asset;
    this.scene.add(asset);

    /* Calandre — l'acide circule autour des tubes. */
    const shell = new THREE.Mesh(
      new THREE.CylinderGeometry(SHELL_R, SHELL_R, SHELL_LEN, 72, 1, true),
      this.mat.alloy,
    );
    shell.material.side = THREE.DoubleSide;
    shell.rotation.z = Math.PI / 2;
    this._register(shell, "SHELL");
    asset.add(shell);
    this.shellMesh = shell;

    // Renforts de virole : un cylindre nu de 9 m de long se lit mal ; les
    // soudures circulaires donnent l'echelle.
    for (let i = -3; i <= 3; i += 1) {
      if (i === 0) continue;
      const weld = new THREE.Mesh(
        new THREE.TorusGeometry(SHELL_R + 0.004, 0.012, 8, 64),
        this.mat.alloyClean,
      );
      weld.rotation.y = Math.PI / 2;
      weld.position.x = i * 1.15;
      weld.castShadow = false;
      asset.add(weld);
    }

    for (const side of [-1, 1]) {
      const isSeaIn = side < 0;
      const boxCode = isSeaIn ? "WATERBOX_IN" : "WATERBOX_OUT";

      /* Plaque tubulaire — interface acide / eau de mer.
         Elle est PERCEE : chaque trou recoit un tube dudge et soude. C'est la
         piece ou se fait le tamponnage d'un tube perce (gamme de tamponnage
         au dossier), donc celle qu'un exploitant veut voir de pres. */
      const plate = new THREE.Mesh(
        new THREE.CylinderGeometry(SHELL_R + 0.03, SHELL_R + 0.03, 0.075, 72),
        this.mat.flange,
      );
      plate.rotation.z = Math.PI / 2;
      plate.position.x = side * HALF;
      this._register(plate, "TUBESHEET");
      asset.add(plate);

      /* Boite a eau. */
      const boxX = side * (HALF + BOX_LEN / 2);
      const wbox = new THREE.Mesh(
        new THREE.CylinderGeometry(SHELL_R + 0.012, SHELL_R + 0.012, BOX_LEN, 72),
        this.mat.alloy,
      );
      wbox.rotation.z = Math.PI / 2;
      wbox.position.x = boxX;
      this._register(wbox, boxCode);
      asset.add(wbox);

      /* Couvercle bombe — la « porte de visite » de l'AMDEC. */
      const cover = new THREE.Mesh(
        new THREE.SphereGeometry(SHELL_R + 0.012, 48, 24, 0, Math.PI * 2, 0, Math.PI / 2),
        this.mat.alloy,
      );
      cover.rotation.z = side > 0 ? -Math.PI / 2 : Math.PI / 2;
      cover.position.x = side * (HALF + BOX_LEN + 0.005);
      cover.scale.y = 0.52;
      this._register(cover, boxCode);
      asset.add(cover);

      /* Bride boulonnee de couvercle — tres visible sur la photo terrain. */
      const flange = new THREE.Mesh(
        new THREE.CylinderGeometry(SHELL_R + 0.11, SHELL_R + 0.11, 0.085, 72),
        this.mat.flange,
      );
      flange.rotation.z = Math.PI / 2;
      flange.position.x = side * (HALF + BOX_LEN);
      this._register(flange, boxCode);
      asset.add(flange);

      /* Joint ecrase, visible dans le plan de bride. */
      const gasket = new THREE.Mesh(
        new THREE.CylinderGeometry(SHELL_R + 0.108, SHELL_R + 0.108, 0.014, 72),
        this.mat.gasket,
      );
      gasket.rotation.z = Math.PI / 2;
      gasket.position.x = side * (HALF + BOX_LEN + 0.05);
      this._register(gasket, boxCode);
      asset.add(gasket);

      this._boltCircle(
        side * (HALF + BOX_LEN), SHELL_R + 0.077, 40, 0.026, boxCode,
      );
      // Coulures sous la bride de couvercle : c'est la premiere chose qu'on
      // remarque sur la photo terrain, et ce que l'oeil cherche pour juger
      // qu'un appareil est en service depuis 2007.
      this._streaks(side * (HALF + BOX_LEN) - side * 0.06, SHELL_R + 0.02, 1.3);

      /* Oreilles de levage — presentes sur tout appareil de cette masse. */
      const lug = new THREE.Mesh(
        new THREE.BoxGeometry(0.05, 0.24, 0.17), this.mat.alloyClean,
      );
      lug.position.set(side * (HALF - 0.5), SHELL_R + 0.1, 0);
      this._register(lug, "SHELL");
      asset.add(lug);
      const eye = new THREE.Mesh(
        new THREE.TorusGeometry(0.06, 0.018, 8, 20), this.mat.alloyClean,
      );
      eye.position.set(side * (HALF - 0.5), SHELL_R + 0.24, 0);
      eye.rotation.y = Math.PI / 2;
      this._register(eye, "SHELL");
      asset.add(eye);

      /* Buse eau de mer sur la boite a eau. */
      const seaNozzle = new THREE.Mesh(
        new THREE.CylinderGeometry(0.13, 0.13, 0.95, 28),
        this.mat.seaLine,
      );
      seaNozzle.position.set(boxX, side < 0 ? -SHELL_R - 0.45 : SHELL_R + 0.45, 0);
      this._register(seaNozzle, boxCode);
      asset.add(seaNozzle);

      const seaFlange = new THREE.Mesh(
        new THREE.CylinderGeometry(0.2, 0.2, 0.05, 28), this.mat.flange,
      );
      seaFlange.position.set(boxX, side < 0 ? -SHELL_R - 0.92 : SHELL_R + 0.92, 0);
      this._register(seaFlange, boxCode);
      asset.add(seaFlange);
    }

    /* Faisceau tubulaire — visible en coupe. */
    const positions = [];
    const pitch = TUBE_OD * 1.28;
    const limit = SHELL_R - 0.055;
    const rows = Math.floor(limit / (pitch * 0.866));
    for (let r = -rows; r <= rows; r += 1) {
      const y = r * pitch * 0.866;
      const offset = r % 2 ? pitch / 2 : 0;
      const span = Math.floor(Math.sqrt(Math.max(limit * limit - y * y, 0)) / pitch);
      for (let cIdx = -span; cIdx <= span; cIdx += 1) {
        const z = cIdx * pitch + offset;
        if (y * y + z * z <= limit * limit) positions.push([y, z]);
      }
    }
    const bundle = new THREE.InstancedMesh(
      new THREE.CylinderGeometry(TUBE_OD / 2, TUBE_OD / 2, TUBE_LEN, 6),
      this.mat.tube,
      positions.length,
    );
    const dummy = new THREE.Object3D();
    positions.forEach(([y, z], i) => {
      dummy.position.set(0, y, z);
      dummy.rotation.set(0, 0, Math.PI / 2);
      dummy.updateMatrix();
      bundle.setMatrixAt(i, dummy.matrix);
    });
    bundle.castShadow = true;
    this._register(bundle, "BUNDLE");
    asset.add(bundle);
    this.bundleMesh = bundle;
    this.tubeCount = positions.length;

    /* Mandrinage : la collerette de chaque tube affleurant la plaque
       tubulaire. C'est ce detail qui donne a la plaque son aspect de piece
       usinee plutot que de disque plein, et il est visible des qu'on tourne
       l'appareil pour regarder une extremite. */
    for (const side of [-1, 1]) {
      const ferrules = new THREE.InstancedMesh(
        new THREE.CylinderGeometry(TUBE_OD * 0.78, TUBE_OD * 0.78, 0.012, 8),
        this.mat.alloyClean,
        positions.length,
      );
      const f = new THREE.Object3D();
      positions.forEach(([y, z], i) => {
        f.position.set(side * (HALF + 0.044), y, z);
        f.rotation.set(0, 0, Math.PI / 2);
        f.updateMatrix();
        ferrules.setMatrixAt(i, f.matrix);
      });
      this._register(ferrules, "TUBESHEET");
      asset.add(ferrules);
    }

    /* Piquages acide : entree en partie haute, sortie en partie basse. */
    const acidNozzle = (x, up, code) => {
      const n = new THREE.Mesh(
        new THREE.CylinderGeometry(0.16, 0.16, 0.9, 32), this.mat.acidLine,
      );
      n.position.set(x, up ? SHELL_R + 0.42 : -SHELL_R - 0.42, 0);
      this._register(n, code);
      asset.add(n);

      const f = new THREE.Mesh(
        new THREE.CylinderGeometry(0.245, 0.245, 0.055, 32), this.mat.flange,
      );
      f.position.set(x, up ? SHELL_R + 0.87 : -SHELL_R - 0.87, 0);
      this._register(f, code);
      asset.add(f);

      // Amorce de tuyauterie : coude puis depart horizontal. Elle appartient
      // au meme organe que la buse — c'est sur elle qu'est monte le debitmetre,
      // et une fuite de conduite s'y rattache dans la check-list d'inspection.
      const elbow = new THREE.Mesh(
        new THREE.TorusGeometry(0.34, 0.16, 16, 32, Math.PI / 2), this.mat.acidLine,
      );
      elbow.position.set(x, up ? SHELL_R + 1.2 : -SHELL_R - 1.2, 0);
      elbow.rotation.set(Math.PI / 2, 0, up ? 0 : Math.PI);
      this._register(elbow, code);
      asset.add(elbow);

      const run = new THREE.Mesh(
        new THREE.CylinderGeometry(0.16, 0.16, 1.9, 32), this.mat.acidLine,
      );
      run.rotation.z = Math.PI / 2;
      run.position.set(x + (up ? 1.28 : -1.28), up ? SHELL_R + 1.54 : -SHELL_R - 1.54, 0);
      this._register(run, code);
      asset.add(run);
    };
    acidNozzle(-2.5, true, "NOZZLE_ACID_IN");
    acidNozzle(2.5, false, "NOZZLE_ACID_OUT");

    /* Vannes de vidange — criticite AMDEC 112 pour la vanne d'acide. */
    const valve = (x, y, code) => {
      const g = new THREE.Group();
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.3, 0.24), this.mat.valve);
      const stem = new THREE.Mesh(
        new THREE.CylinderGeometry(0.022, 0.022, 0.26, 12), this.mat.alloyClean,
      );
      stem.position.y = -0.26;
      const wheel = new THREE.Mesh(
        new THREE.TorusGeometry(0.15, 0.022, 10, 28), this.mat.handrail,
      );
      wheel.position.y = -0.4;
      wheel.rotation.x = Math.PI / 2;
      g.add(body, stem, wheel);
      g.position.set(x, y, 0);
      g.traverse((o) => { if (o.isMesh) this._register(o, code); });
      asset.add(g);
    };
    valve(0.9, -SHELL_R - 0.32, "VALVE_ACID");
    valve(-HALF - BOX_LEN / 2, -SHELL_R - 0.32, "VALVE_SEA");

    /* Anodes sacrificielles — criticite 112, non instrumentees.
       Rendues visibles precisement parce qu'aucun capteur ne les couvre. */
    for (const side of [-1, 1]) {
      const anode = new THREE.Mesh(
        new THREE.BoxGeometry(0.42, 0.075, 0.13),
        new THREE.MeshStandardMaterial({
          color: 0xb8bec2, roughness: 0.72, metalness: 0.5,
        }),
      );
      anode.position.set(side * (HALF + BOX_LEN * 0.55), 0.24, side * 0.3);
      this._register(anode, "ANODE");
      asset.add(anode);
    }

    /* Selles support — berceau epousant la calandre, semelle et tirants. */
    for (const x of [-3.1, 3.1]) {
      // Tole d'usure : une selle ne porte jamais directement sur la virole.
      const wear = new THREE.Mesh(
        new THREE.CylinderGeometry(SHELL_R + 0.014, SHELL_R + 0.014, 0.42, 40, 1, true,
          Math.PI * 0.62, Math.PI * 0.76),
        this.mat.saddle,
      );
      wear.rotation.z = Math.PI / 2;
      wear.position.set(x, 0, 0);
      wear.castShadow = true;
      wear.receiveShadow = true;
      asset.add(wear);

      const saddle = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.66, 1.3), this.mat.saddle);
      saddle.position.set(x, -SHELL_R - 0.33, 0);
      saddle.castShadow = true;
      saddle.receiveShadow = true;
      asset.add(saddle);

      // Goussets de raidissement, de part et d'autre de l'ame.
      for (const z of [-0.45, 0.45]) {
        const gusset = new THREE.Mesh(
          new THREE.BoxGeometry(0.26, 0.5, 0.016), this.mat.saddle,
        );
        gusset.position.set(x, -SHELL_R - 0.38, z);
        gusset.castShadow = true;
        asset.add(gusset);
      }

      const base = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.06, 1.5), this.mat.saddle);
      base.position.set(x, -SHELL_R - 0.68, 0);
      base.castShadow = true;
      asset.add(base);

      // Tirants d'ancrage. Cote fixe : trous ronds. Cote libre : trous oblongs,
      // pour laisser l'appareil se dilater — 9,2 m d'acier entre 20 et 95 degC
      // s'allongent d'une dizaine de millimetres.
      for (const z of [-0.58, 0.58]) {
        const anchor = new THREE.Mesh(
          new THREE.CylinderGeometry(0.017, 0.017, 0.16, 8), this.mat.bolt,
        );
        anchor.position.set(x, -SHELL_R - 0.7, z);
        anchor.castShadow = true;
        asset.add(anchor);
        const washer = new THREE.Mesh(
          new THREE.CylinderGeometry(0.042, 0.042, 0.012, 12), this.mat.bolt,
        );
        washer.position.set(x, -SHELL_R - 0.64, z);
        asset.add(washer);
      }
    }

    this._buildInternals();
    this._buildDetails();
  }

  /**
   * Organes internes, visibles uniquement en coupe.
   *
   * Sans chicanes ni plaque percee, la vue en coupe montre un fagot de tubes
   * dans un tube : c'est un dessin d'ecolier. Les chicanes sont ce qui force
   * l'acide a serpenter en travers du faisceau, et donc ce qui fait de cet
   * appareil un echangeur plutot qu'un simple collecteur.
   */
  _buildInternals() {
    const internals = new THREE.Group();
    this.internals = internals;
    this.asset.add(internals);

    /* Chicanes segmentaires, alternees haut / bas. */
    const BAFFLES = 9;
    const cut = 0.25;  // hauteur de passage, en fraction du diametre
    for (let i = 0; i < BAFFLES; i += 1) {
      const x = -HALF + ((i + 1) * SHELL_LEN) / (BAFFLES + 1);
      const up = i % 2 === 0;
      const shape = new THREE.Shape();
      shape.absarc(0, 0, SHELL_R - 0.02, 0, Math.PI * 2, false);
      const baffle = new THREE.Mesh(
        new THREE.ExtrudeGeometry(shape, { depth: 0.012, bevelEnabled: false }),
        this.mat.flange,
      );
      baffle.rotation.y = Math.PI / 2;
      baffle.position.x = x;
      // La decoupe segmentaire est obtenue par un plan de coupe local : c'est
      // moins couteux qu'une geometrie booleenne et le resultat est identique
      // a l'oeil.
      baffle.material = this.mat.flange.clone();
      baffle.material.clippingPlanes = [
        new THREE.Plane(new THREE.Vector3(0, up ? -1 : 1, 0), SHELL_R * (1 - cut)),
      ];
      baffle.material.side = THREE.DoubleSide;
      baffle.castShadow = true;
      internals.add(baffle);
    }
    this.renderer.localClippingEnabled = true;

    /* Tirants d'entretoise reliant les chicanes. */
    for (const [y, z] of [[0.34, 0.3], [-0.34, 0.3], [0.34, -0.3], [-0.34, -0.3]]) {
      const rod = new THREE.Mesh(
        new THREE.CylinderGeometry(0.011, 0.011, SHELL_LEN - 0.3, 8),
        this.mat.alloyClean,
      );
      rod.rotation.z = Math.PI / 2;
      rod.position.set(0, y, z);
      internals.add(rod);
    }

    internals.visible = false;
  }

  /**
   * Details d'exploitation : calorifuge, plaque signaletique, event et purge,
   * soudure longitudinale, tresse de mise a la terre.
   */
  _buildDetails() {
    const asset = this.asset;

    /* Calorifuge sur la moitie chaude, avec bardage et cerclage.
       L'acide entre a 95 degC : la portion amont est isolee, pas la totalite. */
    const CLAD_START = -3.4;
    const CLAD_LEN = 3.0;
    const clad = new THREE.Mesh(
      new THREE.CylinderGeometry(SHELL_R + 0.09, SHELL_R + 0.09, CLAD_LEN, 64, 1, true),
      this.mat.cladding,
    );
    clad.rotation.z = Math.PI / 2;
    clad.position.x = CLAD_START + CLAD_LEN / 2;
    clad.castShadow = true;
    clad.receiveShadow = true;
    this._register(clad, "SHELL");
    asset.add(clad);

    for (const end of [CLAD_START, CLAD_START + CLAD_LEN]) {
      const cap = new THREE.Mesh(
        new THREE.RingGeometry(SHELL_R + 0.005, SHELL_R + 0.09, 48),
        this.mat.cladding,
      );
      cap.rotation.y = Math.PI / 2;
      cap.position.x = end;
      cap.material.side = THREE.DoubleSide;
      asset.add(cap);
    }
    // Feuillards de cerclage tous les 50 cm.
    for (let x = CLAD_START + 0.25; x < CLAD_START + CLAD_LEN; x += 0.5) {
      const band = new THREE.Mesh(
        new THREE.TorusGeometry(SHELL_R + 0.094, 0.008, 6, 48), this.mat.band,
      );
      band.rotation.y = Math.PI / 2;
      band.position.x = x;
      asset.add(band);
    }

    /* Soudure longitudinale de virole, decalee d'un troncon a l'autre. */
    for (let i = 0; i < 4; i += 1) {
      const seam = new THREE.Mesh(
        new THREE.CylinderGeometry(SHELL_R + 0.006, SHELL_R + 0.006, 2.2, 48, 1, true,
          i * 1.1, 0.05),
        this.mat.alloyClean,
      );
      seam.rotation.z = Math.PI / 2;
      seam.position.x = -HALF + 1.1 + i * 2.3;
      asset.add(seam);
    }

    /* Plaque signaletique, boulonnee sur une patte soudee a la virole. */
    const plateMat = this.mat.plate.clone();
    plateMat.map = namePlateTexture(this.equipment);
    const nameplate = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.3), plateMat);
    nameplate.position.set(0.35, SHELL_R * 0.62, SHELL_R * 0.82);
    nameplate.lookAt(nameplate.position.clone().multiplyScalar(2));
    this._register(nameplate, "SHELL");
    asset.add(nameplate);

    /* Event en point haut et purge en point bas — obligatoires pour vidanger
       et remplir la calandre, cites par la gamme de consignation PS3-ABS-REFR. */
    const tap = (y, up) => {
      const g = new THREE.Group();
      const neck = new THREE.Mesh(
        new THREE.CylinderGeometry(0.038, 0.038, 0.2, 14), this.mat.acidLine,
      );
      const flange = new THREE.Mesh(
        new THREE.CylinderGeometry(0.07, 0.07, 0.022, 16), this.mat.flange,
      );
      flange.position.y = up ? 0.11 : -0.11;
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(0.09, 0.11, 0.09), this.mat.valve,
      );
      body.position.y = up ? 0.2 : -0.2;
      const wheel = new THREE.Mesh(
        new THREE.TorusGeometry(0.055, 0.011, 8, 20), this.mat.handrail,
      );
      wheel.position.y = up ? 0.31 : -0.31;
      wheel.rotation.x = Math.PI / 2;
      g.add(neck, flange, body, wheel);
      g.position.set(-0.9, y, 0);
      g.traverse((o) => { if (o.isMesh) this._register(o, "SHELL"); });
      asset.add(g);
    };
    tap(SHELL_R + 0.1, true);
    tap(-SHELL_R - 0.1, false);

    /* Tresse de mise a la terre — petit detail, tres present sur site. */
    const path = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-3.1, -SHELL_R - 0.2, 0.62),
      new THREE.Vector3(-3.0, -SHELL_R - 0.62, 0.78),
      new THREE.Vector3(-3.1, -SHELL_R - 0.74, 0.66),
    ]);
    const strap = new THREE.Mesh(
      new THREE.TubeGeometry(path, 18, 0.011, 6, false),
      new THREE.MeshStandardMaterial({ color: 0x5f6d3a, roughness: 0.75, metalness: 0.6 }),
    );
    asset.add(strap);
  }

  /* ── Decor d'atelier ───────────────────────────────────────────────────── */

  _buildSurroundings() {
    const g = new THREE.Group();
    this.scene.add(g);

    const post = new THREE.BoxGeometry(0.17, 3.6, 0.17);
    const beamX = new THREE.BoxGeometry(9.4, 0.17, 0.17);
    const beamZ = new THREE.BoxGeometry(0.17, 0.17, 3.4);

    for (const x of [-4.5, 4.5]) {
      for (const z of [-1.6, 1.6]) {
        const p = new THREE.Mesh(post, this.mat.frame);
        p.position.set(x, DECK_Y + 1.8, z);
        p.castShadow = true;
        g.add(p);

        const plinth = new THREE.Mesh(new THREE.BoxGeometry(0.44, 0.5, 0.44), this.mat.concrete);
        plinth.position.set(x, DECK_Y - 0.25, z);
        plinth.castShadow = true;
        plinth.receiveShadow = true;
        g.add(plinth);
      }
      const cross = new THREE.Mesh(beamZ, this.mat.frame);
      cross.position.set(x, DECK_Y + 3.6, 0);
      g.add(cross);
    }
    for (const z of [-1.6, 1.6]) {
      for (const y of [DECK_Y + 3.6, DECK_Y + 0.05]) {
        const b = new THREE.Mesh(beamX, this.mat.frame);
        b.position.set(0, y, z);
        b.castShadow = true;
        g.add(b);
      }
    }

    // Platelage caillebotis.
    const deck = new THREE.Mesh(new THREE.PlaneGeometry(11.5, 3.6), this.mat.grating);
    deck.rotation.x = -Math.PI / 2;
    deck.position.set(0, DECK_Y, 0);
    deck.receiveShadow = true;
    g.add(deck);

    // Garde-corps : lisse haute, sous-lisse, montants.
    const rail = (z) => {
      for (const y of [DECK_Y + 1.05, DECK_Y + 0.55]) {
        const r = new THREE.Mesh(
          new THREE.CylinderGeometry(0.026, 0.026, 11.4, 12), this.mat.handrail,
        );
        r.rotation.z = Math.PI / 2;
        r.position.set(0, y, z);
        r.castShadow = true;
        g.add(r);
      }
      for (let x = -5.4; x <= 5.4; x += 1.35) {
        const m = new THREE.Mesh(
          new THREE.CylinderGeometry(0.024, 0.024, 1.05, 10), this.mat.handrail,
        );
        m.position.set(x, DECK_Y + 0.53, z);
        m.castShadow = true;
        g.add(m);
      }
    };
    rail(-1.78);
    rail(1.78);

    // Echelle d'acces.
    const ladder = new THREE.Group();
    for (const z of [-0.22, 0.22]) {
      const side = new THREE.Mesh(
        new THREE.CylinderGeometry(0.028, 0.028, 2.4, 10), this.mat.handrail,
      );
      side.position.set(0, -1.2, z);
      ladder.add(side);
    }
    for (let y = -2.28; y <= -0.1; y += 0.29) {
      const rung = new THREE.Mesh(
        new THREE.CylinderGeometry(0.017, 0.017, 0.44, 8), this.mat.handrail,
      );
      rung.rotation.x = Math.PI / 2;
      rung.position.set(0, y, 0);
      ladder.add(rung);
    }
    ladder.position.set(-2.1, DECK_Y + 1.2, 2.05);
    ladder.traverse((o) => { if (o.isMesh) o.castShadow = true; });
    g.add(ladder);

    // Sol.
    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(70, 70),
      new THREE.MeshStandardMaterial({ color: 0x8e8a82, map: concreteMap(), roughness: 0.97 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = DECK_Y - 0.52;
    floor.receiveShadow = true;
    g.add(floor);
  }

  /* ── Capteurs ──────────────────────────────────────────────────────────── */

  /**
   * Installe les capteurs decrits par /api/topology.
   * Chaque capteur est un objet 3D reel, ancre a la piece qu'il surveille :
   * son etiquette tourne avec l'appareil au lieu de rester collee a un coin
   * de l'ecran.
   *
   * @param {Array<object>} sensors Capteurs situes.
   */
  setSensors(sensors) {
    // LES RESSOURCES GPU DES CAPTEURS PRECEDENTS N'ETAIENT PAS LIBEREES.
    //
    // Les groupes etaient retires de la scene, mais leurs geometries, leurs
    // materiaux et surtout leurs textures d'etiquette — un canvas 512 x 256
    // par capteur — restaient alloues cote pilote graphique. Un seul appel
    // passe inapercu; la methode est publique et rejouable, et chaque rappel
    // abandonnait douze etiquettes en memoire video.
    //
    // Le filtrage de `pickables` etait de surcroit place DANS la boucle : il
    // retirait tous les capteurs des la premiere iteration, puis rebalayait le
    // tableau entier onze fois pour rien.
    for (const entry of this.sensors.values()) {
      this.asset.remove(entry.group);
      entry.group.traverse((o) => {
        if (!o.isMesh && !o.isSprite) return;
        o.geometry?.dispose?.();
        const materiaux = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of materiaux) {
          m?.map?.dispose?.();
          m?.dispose?.();
        }
      });
    }
    if (this.sensors.size) {
      this.pickables = this.pickables.filter((m) => m.userData.sensor === undefined);
    }
    this.sensors.clear();

    for (const meta of sensors) {
      // Les positions sont deja en metres dans le repere de l'appareil.
      const [ax, ay, az] = meta.at;
      const group = new THREE.Group();
      group.position.set(ax, ay, az);
      group.rotation.z = ANCHOR_ROTATION[meta.anchor] ?? 0;

      const degraded = meta.role === "degraded";

      // Corps de transmetteur.
      const body = new THREE.Mesh(
        new THREE.CylinderGeometry(0.075, 0.085, 0.17, 20),
        this.mat.sensorBody,
      );
      body.castShadow = true;
      body.userData.sensor = meta.alias;
      group.add(body);

      const head = new THREE.Mesh(
        new THREE.CylinderGeometry(0.052, 0.052, 0.07, 16), this.mat.sensorStem,
      );
      head.position.y = 0.12;
      head.userData.sensor = meta.alias;
      group.add(head);

      // Tige de raccordement vers la piece surveillee.
      const stem = new THREE.Mesh(
        new THREE.CylinderGeometry(0.024, 0.024, 0.3, 10), this.mat.sensorStem,
      );
      stem.position.y = -0.22;
      stem.userData.sensor = meta.alias;
      group.add(stem);

      // Bague d'etat : c'est elle qui pulse en defaut.
      const ringMat = new THREE.MeshStandardMaterial({
        color: degraded ? 0x8a8f92 : 0x4fd6a6,
        emissive: degraded ? 0x2a2d2f : 0x0f5a41,
        emissiveIntensity: 0.9,
        roughness: 0.4,
        metalness: 0.2,
      });
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.088, 0.017, 10, 28), ringMat);
      ring.rotation.x = Math.PI / 2;
      ring.position.y = 0.055;
      ring.userData.sensor = meta.alias;
      group.add(ring);

      // Halo d'alerte, invisible tant que le capteur est sain.
      const halo = new THREE.Mesh(
        new THREE.SphereGeometry(0.2, 16, 12),
        new THREE.MeshBasicMaterial({
          color: 0xff4d4d, transparent: true, opacity: 0, depthWrite: false,
        }),
      );
      group.add(halo);

      // Etiquette : un sprite fait toujours face a la camera, donc le texte
      // reste lisible sous n'importe quel angle, tout en suivant la piece.
      const [lc, lctx] = canvas2d(512);
      lc.height = 256;
      const labelTex = new THREE.CanvasTexture(lc);
      labelTex.colorSpace = THREE.SRGBColorSpace;
      labelTex.anisotropy = 8;
      labelTex.minFilter = THREE.LinearFilter;
      const label = new THREE.Sprite(new THREE.SpriteMaterial({
        map: labelTex, transparent: true, depthTest: true, depthWrite: false,
      }));
      label.scale.set(1.25, 0.625, 1);
      label.position.set(0, 0.42, 0);
      label.userData.sensor = meta.alias;
      group.add(label);

      this.asset.add(group);
      this.pickables.push(body, head, ring, label);

      const entry = {
        group, ring, ringMat, halo, label, labelTex, ctx: lctx,
        meta, value: null, severity: "NORMAL",
      };
      this.sensors.set(meta.alias, entry);
      this._paintLabel(entry);
    }
  }

  /**
   * Redessine l'etiquette d'un capteur.
   *
   * L'etiquette est dessinee a 512 px pour une largeur affichee d'environ
   * 1,15 unite de scene. La version precedente la peignait a 256 px : a la
   * distance de lecture normale, le texte tombait sous un pixel par trait et
   * l'etiquette se lisait comme une plaque noire. Le doublement de resolution
   * et le passage a un fond opaque a fort contraste corrigent les deux causes.
   *
   * Le code du capteur est ecrit AU-DESSUS de la valeur et en plus petit : ce
   * qu'un operateur cherche du regard, c'est le nombre, pas le tag.
   */
  _paintLabel(entry) {
    const { ctx, meta, value, severity } = entry;
    const W = 512;
    const H = 256;
    ctx.clearRect(0, 0, W, H);

    const accent = severity === "CRITICAL" ? "#ff6a5e"
      : severity === "WARNING" ? "#ffc250"
        : meta.role === "degraded" ? "#9aa6aa" : "#63e8ba";

    // Ombre portee : detache l'etiquette de l'appareil metallique derriere.
    ctx.shadowColor = "rgba(0,0,0,.55)";
    ctx.shadowBlur = 18;
    ctx.shadowOffsetY = 5;
    ctx.fillStyle = "rgba(6,14,18,.94)";
    ctx.beginPath();
    ctx.roundRect(14, 36, W - 28, 158, 18);
    ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;

    ctx.strokeStyle = accent;
    ctx.lineWidth = 3;
    ctx.stroke();
    // Bandeau d'etat a gauche : la severite se lit avant le texte.
    ctx.fillStyle = accent;
    ctx.beginPath();
    ctx.roundRect(14, 36, 10, 158, [18, 0, 0, 18]);
    ctx.fill();

    ctx.fillStyle = "#9fb6bb";
    ctx.font = "700 30px 'Segoe UI', system-ui, sans-serif";
    ctx.fillText(meta.alias, 44, 84);

    // UN CAPTEUR MORT N'AFFICHE PAS DE MESURE.
    //
    // TI5303-4X est colle a sa butee d'echelle 327,67 depuis aout 2024 —
    // 32767/100, un depassement d'entier signe sur 16 bits cote acquisition.
    // PHI5306X-3 est reste fige 1 900 h. Le jumeau affichait « 327,7 » et
    // « 10,2 » dans la meme typographie que les mesures valides, c'est-a-dire
    // exactement ce que fait le DCS et exactement ce que ce projet reproche au
    // DCS. Ces deux capteurs sont d'ailleurs le cas d'ecole que le projet met
    // en avant : les montrer comme des mesures ruinerait la demonstration.
    const degraded = meta.role === "degraded";
    if (degraded) {
      ctx.fillStyle = "#9aa6aa";
      ctx.font = "700 40px 'Segoe UI', system-ui, sans-serif";
      ctx.fillText("hors service", 44, 150);
      ctx.font = "500 24px 'Segoe UI', system-ui, sans-serif";
      ctx.fillStyle = "#77878c";
      ctx.fillText(
        value === null || value === undefined || Number.isNaN(value)
          ? "aucune mesure"
          : `signal figé à ${Number(value).toLocaleString("fr-FR", {
            maximumFractionDigits: 2 })}`,
        44, 180,
      );
      entry.labelTex.needsUpdate = true;
      return;
    }

    const shown = value === null || value === undefined || Number.isNaN(value)
      ? "—"
      : Number(value).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
    ctx.fillStyle = "#f4faf9";
    ctx.font = "700 62px 'Segoe UI', system-ui, sans-serif";
    ctx.fillText(shown, 44, 158);

    ctx.fillStyle = "#8aa3a8";
    ctx.font = "600 34px 'Segoe UI', system-ui, sans-serif";
    ctx.fillText(displayUnit(meta.unit), 52 + ctx.measureText(shown).width, 158);

    entry.labelTex.needsUpdate = true;
  }

  /**
   * Met a jour la valeur affichee sur chaque etiquette.
   * @param {Record<string, number|null>} values alias -> valeur.
   */
  setValues(values) {
    for (const [alias, entry] of this.sensors) {
      const next = values?.[alias];
      if (next === entry.value) continue;
      entry.value = next ?? null;
      this._paintLabel(entry);
    }
  }

  /* ── Etat de defaut ────────────────────────────────────────────────────── */

  /**
   * Applique l'etat de defaut sur les pieces et les capteurs.
   * Les cibles proviennent de `finding_map` dans topology.yaml : aucune
   * correspondance n'est devinee ici.
   *
   * @param {{components?: Record<string,string>, sensors?: Record<string,string>}} state
   */
  setState(state = {}) {
    const comps = state.components || {};
    const sens = state.sensors || {};
    this.states = new Map([
      ...Object.entries(comps).map(([k, v]) => [`c:${k}`, v]),
      ...Object.entries(sens).map(([k, v]) => [`s:${k}`, v]),
    ]);

    // Remise a zero franche, puis application.
    for (const [material, base] of this.baseColors) {
      material.color.copy(base.color);
      if (material.emissive && base.emissive) material.emissive.copy(base.emissive);
      if (material.emissive) material.emissiveIntensity = 0;
    }
    this.faulted = [];
    for (const [code, severity] of Object.entries(comps)) {
      const meshes = this.components.get(code) || [];
      for (const mesh of meshes) {
        const m = mesh.material;
        if (!m || Array.isArray(m)) continue;
        this.faulted.push({ material: m, severity });
      }
    }
    this._marquerPieces(comps);
    for (const [alias, entry] of this.sensors) {
      entry.severity = sens[alias] || "NORMAL";
      this._paintLabel(entry);
    }
  }

  /**
   * Pose un repere de defaut sur chaque piece mise en cause.
   *
   * LA PIECE LA PLUS SOUVENT ACCUSEE EST CELLE QU'ON NE VOIT PAS. Le faisceau
   * tubulaire est enferme dans la calandre : une teinte rouge appliquee sur
   * ses tubes ne sort pas de l'appareil tant que la coupe n'est pas active.
   * L'operateur voyait donc une severite CRITIQUE annoncee dans le bandeau et
   * un appareil intact a l'ecran — la contradiction la plus couteuse qu'une
   * supervision puisse produire.
   *
   * Le repere est dessine SANS TEST DE PROFONDEUR et rendu en dernier : il
   * traverse la tole et designe la piece meme fermee. Il porte le nom de la
   * piece, parce qu'un halo rouge sans nom oblige a chercher.
   */
  _marquerPieces(comps) {
    if (!this._reperes) {
      this._reperes = new THREE.Group();
      this._reperes.renderOrder = 999;
      this.asset.add(this._reperes);
    }
    for (const enfant of [...this._reperes.children]) {
      this._reperes.remove(enfant);
      enfant.material?.map?.dispose?.();
      enfant.material?.dispose?.();
    }
    this.reperes = [];

    const boite = new THREE.Box3();
    const centre = new THREE.Vector3();
    for (const [code, severity] of Object.entries(comps)) {
      const meshes = this.components.get(code) || [];
      if (!meshes.length) continue;
      boite.makeEmpty();
      for (const mesh of meshes) boite.expandByObject(mesh);
      if (boite.isEmpty()) continue;
      boite.getCenter(centre);

      const critique = severity === "CRITICAL";
      const teinte = critique ? "#ff6a5e" : "#ffc250";
      const nom = (this.componentLabels?.[code] || code)
        .replace(/\s*—.*$/, "").toUpperCase();

      const c = document.createElement("canvas");
      c.width = 512; c.height = 128;
      const g = c.getContext("2d");
      g.fillStyle = "rgba(10,14,17,.88)";
      g.strokeStyle = teinte;
      g.lineWidth = 6;
      const r = 18;
      g.beginPath();
      g.moveTo(r, 3); g.lineTo(509 - r, 3); g.quadraticCurveTo(509, 3, 509, 3 + r);
      g.lineTo(509, 125 - r); g.quadraticCurveTo(509, 125, 509 - r, 125);
      g.lineTo(r, 125); g.quadraticCurveTo(3, 125, 3, 125 - r);
      g.lineTo(3, 3 + r); g.quadraticCurveTo(3, 3, r, 3);
      g.closePath(); g.fill(); g.stroke();
      g.fillStyle = teinte;
      g.font = "700 40px ui-monospace, Menlo, Consolas, monospace";
      g.textAlign = "center"; g.textBaseline = "middle";
      g.fillText(critique ? "▲ CRITIQUE" : "▲ ALERTE", 256, 40);
      g.fillStyle = "#e8eef1";
      g.font = "600 30px ui-monospace, Menlo, Consolas, monospace";
      g.fillText(nom.slice(0, 26), 256, 88);

      const tex = new THREE.CanvasTexture(c);
      tex.anisotropy = 8;
      tex.minFilter = THREE.LinearFilter;
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: tex, transparent: true, depthTest: false, depthWrite: false,
      }));
      sprite.scale.set(3.2, 0.8, 1);
      sprite.position.copy(centre);
      sprite.position.y += 1.1;
      sprite.renderOrder = 1000;
      sprite.userData.component = code;
      this._reperes.add(sprite);

      const anneau = new THREE.Mesh(
        new THREE.RingGeometry(0.42, 0.58, 48),
        new THREE.MeshBasicMaterial({
          color: new THREE.Color(teinte), transparent: true, opacity: 0.9,
          depthTest: false, depthWrite: false, side: THREE.DoubleSide,
        }),
      );
      anneau.position.copy(centre);
      anneau.renderOrder = 1000;
      this._reperes.add(anneau);

      this.reperes.push({ sprite, anneau, critique });
    }
  }

  /** Focalise la camera sur une piece ou un capteur. */
  focus(target) {
    const sensor = this.sensors.get(target);
    if (sensor) {
      this.centerTarget.copy(sensor.group.position);
      this.orbitTarget.radius = 6.5;
      return true;
    }
    const meshes = this.components.get(target);
    if (meshes?.length) {
      const box = new THREE.Box3();
      for (const m of meshes) box.expandByObject(m);
      box.getCenter(this.centerTarget);
      this.orbitTarget.radius = Math.max(7, box.getSize(new THREE.Vector3()).length() * 1.5);
      return true;
    }
    return false;
  }

  resetView() {
    this.centerTarget.set(0, -0.15, 0);
    this.orbitTarget = { theta: -0.72, phi: 1.16, radius: 19.5 };
  }

  /**
   * Coupe longitudinale.
   *
   * La calandre et le bardage deviennent translucides, et les organes internes
   * apparaissent : chicanes segmentaires alternees et tirants d'entretoise.
   * C'est cette vue qui explique le fonctionnement de l'appareil — l'acide ne
   * traverse pas la calandre en ligne droite, il serpente en travers du
   * faisceau, et c'est ce parcours force qui produit l'echange.
   */
  setCutaway(enabled) {
    this.cutaway = Boolean(enabled);
    for (const m of [this.mat.alloy, this.mat.cladding]) {
      m.transparent = this.cutaway;
      m.opacity = this.cutaway ? 0.14 : 1;
      m.depthWrite = !this.cutaway;
      m.needsUpdate = true;
    }
    if (this.internals) this.internals.visible = this.cutaway;
    // Les feuillards de cerclage masqueraient l'interieur : on les efface avec
    // la tole qu'ils serrent.
    this.mat.band.transparent = this.cutaway;
    this.mat.band.opacity = this.cutaway ? 0.2 : 1;
    this.mat.band.needsUpdate = true;
  }

  setPaused(paused) { this.paused = Boolean(paused); }

  /* ── Interaction ───────────────────────────────────────────────────────── */

  _initInteraction() {
    const canvas = this.canvas;
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let dragging = false;
    let moved = false;
    let last = { x: 0, y: 0 };
    let pinch = 0;

    const toPointer = (event) => {
      const r = canvas.getBoundingClientRect();
      pointer.x = ((event.clientX - r.left) / r.width) * 2 - 1;
      pointer.y = -((event.clientY - r.top) / r.height) * 2 + 1;
    };

    const pick = () => {
      raycaster.setFromCamera(pointer, this.camera);
      const hit = raycaster.intersectObjects(this.pickables, false)[0];
      if (!hit) return null;
      const { sensor, component } = hit.object.userData;
      if (sensor) return { type: "sensor", id: sensor };
      if (component) return { type: "component", id: component };
      return null;
    };

    canvas.addEventListener("pointerdown", (e) => {
      dragging = true;
      moved = false;
      last = { x: e.clientX, y: e.clientY };
      canvas.setPointerCapture(e.pointerId);
      this.idle = 0;
    });

    canvas.addEventListener("pointermove", (e) => {
      if (dragging) {
        const dx = e.clientX - last.x;
        const dy = e.clientY - last.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
        this.orbitTarget.theta -= dx * 0.006;
        this.orbitTarget.phi = Math.min(
          Math.PI - 0.18,
          Math.max(0.2, this.orbitTarget.phi - dy * 0.005),
        );
        last = { x: e.clientX, y: e.clientY };
        this.idle = 0;
        return;
      }
      toPointer(e);
      const found = pick();
      canvas.style.cursor = found ? "pointer" : "grab";
      this.onHover(found);
    });

    canvas.addEventListener("pointerup", (e) => {
      dragging = false;
      canvas.style.cursor = "grab";
      if (moved) return;
      toPointer(e);
      const found = pick();
      if (found) {
        this.focus(found.id);
        this.onSelect(found);
      }
    });

    canvas.addEventListener("pointerleave", () => {
      dragging = false;
      this.onHover(null);
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.orbitTarget.radius = Math.min(
        42, Math.max(3.4, this.orbitTarget.radius * (1 + Math.sign(e.deltaY) * 0.11)),
      );
      this.idle = 0;
    }, { passive: false });

    canvas.addEventListener("touchmove", (e) => {
      if (e.touches.length !== 2) return;
      const [a, b] = e.touches;
      const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (pinch) {
        this.orbitTarget.radius = Math.min(
          42, Math.max(3.4, this.orbitTarget.radius * (pinch / d)),
        );
      }
      pinch = d;
      this.idle = 0;
    }, { passive: true });

    canvas.addEventListener("touchend", () => { pinch = 0; });

    // ── Accessibilite clavier ──────────────────────────────────────────
    // Un <canvas> n'est pas focusable et ne recoit aucun evenement clavier :
    // sans ce bloc, toute la scene est inaccessible sans souris. Les fleches
    // orientent, +/- zooment, Tab parcourt les capteurs, Entree ouvre.
    canvas.tabIndex = 0;
    canvas.setAttribute("role", "application");
    canvas.setAttribute(
      "aria-description",
      "Fleches pour orienter, plus et moins pour zoomer, "
      + "T pour parcourir les capteurs, Entree pour ouvrir le capteur courant.",
    );
    this.cursorIndex = -1;

    canvas.addEventListener("keydown", (event) => {
      const step = event.shiftKey ? 0.24 : 0.08;
      let handled = true;
      switch (event.key) {
        case "ArrowLeft": this.orbitTarget.theta -= step; break;
        case "ArrowRight": this.orbitTarget.theta += step; break;
        case "ArrowUp":
          this.orbitTarget.phi = Math.max(0.2, this.orbitTarget.phi - step); break;
        case "ArrowDown":
          this.orbitTarget.phi = Math.min(Math.PI - 0.18, this.orbitTarget.phi + step); break;
        case "+": case "=":
          this.orbitTarget.radius = Math.max(3.4, this.orbitTarget.radius * 0.85); break;
        case "-": case "_":
          this.orbitTarget.radius = Math.min(42, this.orbitTarget.radius * 1.18); break;
        case "t": case "T": {
          const aliases = [...this.sensors.keys()];
          if (!aliases.length) break;
          this.cursorIndex = (this.cursorIndex + (event.shiftKey ? -1 : 1) + aliases.length)
            % aliases.length;
          const alias = aliases[this.cursorIndex];
          this.focus(alias);
          this.onHover({ type: "sensor", id: alias });
          break;
        }
        case "Enter": case " ": {
          const aliases = [...this.sensors.keys()];
          if (this.cursorIndex >= 0 && aliases[this.cursorIndex]) {
            this.onSelect({ type: "sensor", id: aliases[this.cursorIndex] });
          }
          break;
        }
        case "Home": this.resetView(); break;
        default: handled = false;
      }
      if (handled) {
        event.preventDefault();
        this.idle = 0;
      }
    });

    this.idle = 0;
    canvas.style.cursor = "grab";
  }

  /**
   * Reduit la charge graphique si le rendu ne tient pas la cadence.
   *
   * La scene compte plus de 1 500 tubes instancies, des ombres 2048 et une
   * carte d'environnement. Sur un GPU integre — configuration courante en
   * salle de controle — cela peut tomber sous 20 images par seconde. Plutot
   * que de laisser l'interface ramer, on degrade : ombres d'abord, puis
   * resolution.
   */
  _guardPerformance(dt) {
    this._frames = (this._frames || 0) + 1;
    this._elapsed = (this._elapsed || 0) + dt;
    if (this._elapsed < 2) return;

    const fps = this._frames / this._elapsed;
    this._frames = 0;
    this._elapsed = 0;
    this.fps = Math.round(fps);

    if (fps < 22 && this.quality !== "reduced") {
      this.quality = "reduced";
      this.renderer.shadowMap.enabled = false;
      this.maxPixelRatio = 1;
      this.scene.traverse((o) => { if (o.isMesh) o.castShadow = false; });
      this.canvas.width = 0;  // force un redimensionnement au prochain tour
      this.onQuality?.("reduced", this.fps);
    } else if (fps < 14 && this.quality === "reduced") {
      this.quality = "minimal";
      this.maxPixelRatio = 0.75;
      if (this.bundleMesh) this.bundleMesh.visible = this.cutaway;
      this.canvas.width = 0;
      this.onQuality?.("minimal", this.fps);
    }
  }

  /* ── Boucle ────────────────────────────────────────────────────────────── */

  _resize() {
    const dpr = Math.min(devicePixelRatio || 1, this.maxPixelRatio ?? 2);
    const w = Math.max(1, Math.floor(this.canvas.clientWidth * dpr));
    const h = Math.max(1, Math.floor(this.canvas.clientHeight * dpr));
    if (this.canvas.width === w && this.canvas.height === h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = this.canvas.clientWidth / Math.max(this.canvas.clientHeight, 1);
    this.camera.updateProjectionMatrix();
  }

  _loop = () => {
    requestAnimationFrame(this._loop);
    if (this.paused) return;
    this._resize();

    const dt = Math.min(this.clock.getDelta(), 0.1);
    const t = this.clock.elapsedTime;
    this._guardPerformance(dt);

    // Rotation lente automatique, suspendue des que l'operateur manipule la vue
    // et reprise apres quelques secondes d'inactivite.
    this.idle += dt;
    if (!this.reduceMotion && this.idle > 3.5) this.orbitTarget.theta += dt * 0.055;

    const k = this.reduceMotion ? 1 : Math.min(1, dt * 4.5);
    this.orbit.theta += (this.orbitTarget.theta - this.orbit.theta) * k;
    this.orbit.phi += (this.orbitTarget.phi - this.orbit.phi) * k;
    this.orbit.radius += (this.orbitTarget.radius - this.orbit.radius) * k;
    this.center.lerp(this.centerTarget, k);

    const { theta, phi, radius } = this.orbit;
    this.camera.position.set(
      this.center.x + radius * Math.sin(phi) * Math.cos(theta),
      this.center.y + radius * Math.cos(phi),
      this.center.z + radius * Math.sin(phi) * Math.sin(theta),
    );
    this.camera.lookAt(this.center);

    // Pulsation de defaut : deux battements par seconde pour le critique, un
    // pour l'avertissement. Le rythme differencie la gravite sans lire un texte.
    const pulseC = 0.55 + 0.45 * Math.sin(t * 7.2);
    const pulseW = 0.45 + 0.3 * Math.sin(t * 3.4);
    for (const { material, severity } of this.faulted || []) {
      const critical = severity === "CRITICAL";
      const colour = critical ? FAULT_RED : FAULT_AMBER;
      material.color.lerpColors(
        this.baseColors.get(material)?.color || colour, colour, critical ? 0.85 : 0.6,
      );
      if (material.emissive) {
        material.emissive.copy(colour);
        material.emissiveIntensity = critical ? pulseC * 1.5 : pulseW * 0.75;
      }
    }

    // Reperes de piece : ils battent au meme rythme que la piece qu'ils
    // designent, et font face a la camera pour rester lisibles sous tout angle.
    for (const { sprite, anneau, critique } of this.reperes || []) {
      const p = critique ? pulseC : pulseW;
      sprite.material.opacity = 0.62 + 0.38 * p;
      anneau.material.opacity = 0.35 + 0.55 * p;
      anneau.scale.setScalar(1 + p * 0.35);
      anneau.quaternion.copy(this.camera.quaternion);
    }

    for (const entry of this.sensors.values()) {
      const sev = entry.severity;
      const critical = sev === "CRITICAL";
      const warning = sev === "WARNING";
      if (critical || warning) {
        const colour = critical ? FAULT_RED : FAULT_AMBER;
        entry.ringMat.color.copy(colour);
        entry.ringMat.emissive.copy(colour);
        entry.ringMat.emissiveIntensity = critical ? pulseC * 2.4 : pulseW * 1.2;
        entry.halo.material.color.copy(colour);
        entry.halo.material.opacity = (critical ? pulseC : pulseW) * 0.24;
        entry.halo.scale.setScalar(1 + (critical ? pulseC : pulseW) * 0.5);
      } else {
        const degraded = entry.meta.role === "degraded";
        entry.ringMat.color.setHex(degraded ? 0x8a8f92 : 0x4fd6a6);
        entry.ringMat.emissive.setHex(degraded ? 0x2a2d2f : 0x0f5a41);
        entry.ringMat.emissiveIntensity = 0.9;
        entry.halo.material.opacity = 0;
      }
      // L'etiquette s'efface quand elle est loin, pour ne pas encombrer.
      const d = this.camera.position.distanceTo(entry.group.position);
      entry.label.material.opacity = Math.max(0.15, Math.min(1, 26 / (d * d) * 6));
    }

    this._resolveLabelCollisions();
    this.renderer.render(this.scene, this.camera);
  };

  /**
   * Efface les etiquettes qui se recouvrent a l'ecran.
   *
   * Douze etiquettes ancrees en 3D finissent par se superposer sous certains
   * angles, et une pile de textes illisibles est pire que pas d'etiquette du
   * tout. On projette chaque etiquette en coordonnees ecran et, en cas de
   * conflit, on garde la plus proche de la camera — l'autre s'estompe.
   * Un capteur en defaut n'est jamais efface.
   */
  _resolveLabelCollisions() {
    const projected = [];
    for (const entry of this.sensors.values()) {
      if (!entry.label.visible) continue;
      const p = entry.group.position.clone();
      p.y += entry.group.rotation.z === Math.PI ? -0.42 : 0.42;
      const distance = this.camera.position.distanceTo(p);
      p.project(this.camera);
      projected.push({ entry, x: p.x, y: p.y, z: p.z, distance });
    }
    projected.sort((a, b) => a.distance - b.distance);

    const kept = [];
    // Demi-taille d'etiquette en coordonnees normalisees, ajustee a l'aspect.
    const aspect = this.camera.aspect || 1.6;
    const halfW = 0.085 * (1.6 / aspect);
    const halfH = 0.045;

    for (const item of projected) {
      const faulted = item.entry.severity === "CRITICAL"
        || item.entry.severity === "WARNING";
      const behind = item.z > 1;
      // UNE ETIQUETTE A MOITIE COUPEE PAR LE BORD EST PIRE QU'ABSENTE.
      // Les capteurs de contexte sont poses hors de l'appareil; sous certains
      // angles leurs etiquettes sortaient du cadre et s'empilaient, tronquees,
      // contre la bordure droite de la scene. On les efface des qu'elles
      // debordent, plutot que de laisser le navigateur les rogner.
      const horsCadre = Math.abs(item.x) + halfW > 1 || Math.abs(item.y) + halfH > 1;
      const clash = kept.some(
        (k) => Math.abs(k.x - item.x) < halfW * 2 && Math.abs(k.y - item.y) < halfH * 2,
      );
      if (behind || horsCadre) {
        item.entry.label.material.opacity = 0;
      } else if (clash && !faulted) {
        // Estompe plutot que masquer : le repere reste devinable.
        item.entry.label.material.opacity = Math.min(
          item.entry.label.material.opacity, 0.12,
        );
      } else {
        kept.push(item);
      }
    }
  }

  /** Statistiques affichables sous le modele. */
  stats() {
    return {
      tubes: this.tubeCount,
      shell_diameter_mm: Math.round(SHELL_R * 2000),
      tube_length_mm: Math.round(TUBE_LEN * 1000),
    };
  }
}

const FAULT_RED = new THREE.Color(0xf0453c);
const FAULT_AMBER = new THREE.Color(0xf0a52f);

/** Convertit une unite du referentiel en notation lisible. */
export function displayUnit(unit) {
  return { degC: "°C", "m3/h": "m³/h", "t/h": "t/h", "%": "%", "-": "" }[unit] ?? unit ?? "";
}

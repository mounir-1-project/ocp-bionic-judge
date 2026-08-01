/**
 * Poste de surveillance E7301 — logique d'interface.
 *
 * Trois principes tenus dans tout ce fichier :
 *
 *  1. Aucune connaissance metier n'est ecrite ici. Les seuils, les libelles de
 *     tags, la position des capteurs et le rattachement d'une anomalie a une
 *     piece viennent tous de l'API, donc des YAML gouvernes. L'interface ne
 *     devine rien.
 *  2. Aucun chiffre affiche n'est en dur. La version precedente affichait
 *     « seuil 0,487 » et « R2 0,968 » dans le HTML alors que les valeurs
 *     reelles etaient 0,973 et dependaient du jeu de donnees.
 *  3. Le modele 3D est la vue principale, pas une vignette. Il recoit les
 *     valeurs en direct et l'etat de defaut piece par piece.
 */

import { CoolerTwin, displayUnit } from "./twin.js";

const TIMEOUT = 12000;
const TICK = 1600;

const S = {
  view: "salle",
  feed: "stream",
  twin: null,
  charts: {},
  topology: null,
  equipment: null,
  sensors: [],
  episodes: [],
  governance: null,
  series: null,
  latest: null,
  feedEvents: [],
  seriesKey: null,
  // Le tiroir capteur a sa propre fenêtre : la version précédente empruntait
  // celle du sélecteur de tendance, couplage arbitraire et invisible.
  drawerSpan: 504,
  replay: null,
  operator: null,
  csrf: "",
  openSensor: null,
  cursor: null,
  timer: null,
  busy: false,
};

/* ── Utilitaires ─────────────────────────────────────────────────────────── */

const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c]
));

const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : null);

function fmt(v, d = 1) {
  const n = num(v);
  return n === null ? "—" : n.toLocaleString("fr-FR", {
    minimumFractionDigits: d, maximumFractionDigits: d,
  });
}

function stamp(value, withDate = true) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value).replace("T", " ").slice(0, 16);
  return new Intl.DateTimeFormat("fr-FR", {
    day: withDate ? "2-digit" : undefined,
    month: withDate ? "2-digit" : undefined,
    year: withDate ? "2-digit" : undefined,
    hour: "2-digit", minute: "2-digit",
  }).format(d);
}

const SEV_LABEL = {
  NORMAL: "Nominal", INFO: "Information", WARNING: "Avertissement", CRITICAL: "Critique",
};
const SEV_RANK = { NORMAL: 0, INFO: 1, WARNING: 2, CRITICAL: 3 };

/**
 * Les états procédé sont des identifiants du DCS. Les afficher bruts —
 * « RUNNING », « STOPPED » — dans une interface entièrement en français
 * obligeait l'opérateur à traduire, et trahissait une donnée recopiée telle
 * quelle. Le code reste la référence machine ; seul l'affichage est traduit.
 */
const ETAT_LABEL = {
  RUNNING: "En marche", TRANSIENT: "Régime transitoire", STOPPED: "À l'arrêt",
};
const etatLisible = (code) => ETAT_LABEL[code] || code || "—";

/** Délai de QUALIFICATION de la constatation, distinct de l'exécution. */
const URGENCE_LABEL = {
  AUCUNE: "aucun délai",
  SOUS_SURVEILLANCE: "à surveiller",
  SOUS_24H: "à qualifier sous 24 h",
  SOUS_8H: "à qualifier sous 8 h",
  IMMEDIATE: "à qualifier immédiatement",
};
const urgenceLisible = (code) => URGENCE_LABEL[code] || code || "—";

/**
 * Réserves émises par le contrôleur de cohérence.
 *
 * Le poste affichait le code brut — « OVERCONFIDENCE » — dans un encadré
 * destiné à l'exploitant. Un code de programme n'est pas une réserve : il
 * faut dire ce qui a été constaté et ce que cela change pour la lecture du
 * diagnostic. Les codes restent la référence machine, exposés par l'API et
 * utilisés par les tests ; seul l'affichage est traduit.
 */
const RESERVE_LABEL = {
  OVERCONFIDENCE: {
    titre: "Confiance surévaluée",
    sens: "l'agent s'avance plus que ses preuves ne le permettent",
  },
  UNDERCONFIDENCE: {
    titre: "Confiance sous-évaluée",
    sens: "les preuves sont plus solides que la confiance annoncée",
  },
  HALLUCINATED_VALUE: {
    titre: "Valeur non retrouvée",
    sens: "un nombre cité ne correspond à aucune mesure de cet instant",
  },
  UNVERIFIABLE_VALUE: {
    titre: "Valeur invérifiable",
    sens: "un nombre cité ne se rattache à aucune grandeur connue",
  },
  NO_QUANTITATIVE_EVIDENCE: {
    titre: "Diagnostic sans chiffres",
    sens: "aucune valeur mesurée n'appuie la conclusion",
  },
  SEVERITY_OVERESTIMATED: {
    titre: "Sévérité surestimée",
    sens: "les règles déterministes concluent à un niveau plus bas",
  },
  SEVERITY_UNDERESTIMATED: {
    titre: "Sévérité sous-estimée",
    sens: "les règles déterministes concluent à un niveau plus élevé",
  },
  INVENTED_AMDEC_MODE: {
    titre: "Mode AMDEC inexistant",
    sens: "le mode invoqué ne figure pas au référentiel de 2019",
  },
  UNSUPPORTED_AMDEC_MODE: {
    titre: "Mode AMDEC non étayé",
    sens: "aucune constatation ne soutient le rattachement",
  },
  NO_AMDEC_LINK: {
    titre: "Aucun rattachement",
    sens: "le diagnostic ne cite aucun mode de défaillance",
  },
  BLIND_SPOT_CLAIM: {
    titre: "Angle mort revendiqué",
    sens: "le mode invoqué n'est couvert par aucun capteur",
  },
  ACTION_UNDERSIZED: {
    titre: "Délai trop long",
    sens: "le délai de qualification ne correspond pas à la sévérité",
  },
  ACTION_OVERSIZED: {
    titre: "Arrêt injustifié",
    sens: "l'action immobilise la ligne sans que le plan l'exige",
  },
  UNSAFE_ACTION: {
    titre: "Action dangereuse",
    sens: "elle omet l'arrêt et la consignation qu'exige la tâche",
  },
  VAGUE_ACTION: {
    titre: "Action trop vague",
    sens: "un technicien ne peut pas l'exécuter en l'état",
  },
  INVALID_TASK_REF: {
    titre: "Tâche inconnue",
    sens: "la référence citée n'existe pas au plan préventif",
  },
  STATE_MISMATCH: {
    titre: "État de marche erroné",
    sens: "l'état annoncé diffère de l'état réel de la ligne",
  },
  DIAGNOSIS_OUT_OF_STATE: {
    titre: "Diagnostic hors marche",
    sens: "une dégradation est annoncée alors que la ligne est à l'arrêt",
  },
  INCOMPLETE_COVERAGE: {
    titre: "Constatation ignorée",
    sens: "le fait le plus grave n'est pas traité par le diagnostic",
  },
  MISSING_CAVEAT: {
    titre: "Limite non énoncée",
    sens: "la base de mesure est dégradée et le diagnostic ne le dit pas",
  },
};

/**
 * Met en forme une durée sérialisée par pandas.
 *
 * Le pas d'échantillonnage arrivait sous la forme `0 days 01:00:00` et
 * s'affichait tel quel dans le passeport de la donnée. C'est une
 * représentation interne de bibliothèque, pas une information d'exploitation.
 *
 * @param {string} valeur Durée au format pandas.
 * @returns {string} Durée lisible, ou la valeur d'origine si non reconnue.
 */
function duree(valeur) {
  const m = /(?:(\d+)\s*days?\s*)?(\d{2}):(\d{2}):(\d{2})/.exec(String(valeur ?? ""));
  if (!m) return String(valeur ?? "—");
  const [, j, h, mn, s] = m.map((v) => (v === undefined ? 0 : Number(v)));
  const parts = [];
  if (j) parts.push(`${j} j`);
  if (h) parts.push(`${h} h`);
  if (mn) parts.push(`${mn} min`);
  if (s && !j && !h) parts.push(`${s} s`);
  return parts.join(" ") || "0 s";
}

/**
 * Marqueur de gravité : glyphe + mot + couleur.
 * La couleur seule ne suffit pas — environ 8 % des hommes ne distinguent pas
 * le rouge de l'ambre, et une capture en noir et blanc les confond toujours.
 */
function sevMark(severity) {
  const sev = severity || "NORMAL";
  return `<span class="sev-mark" data-sev="${esc(sev)}">${esc(SEV_LABEL[sev] || sev)}</span>`;
}

async function api(path, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT);
  try {
    const res = await fetch(path, {
      ...options,
      signal: ctrl.signal,
      headers: {
        "Content-Type": "application/json",
        ...(S.csrf && (options.method || "GET") !== "GET" ? { "X-CSRF-Token": S.csrf } : {}),
        ...(options.headers || {}),
      },
    });
    if (res.status === 401) { showGate(); throw new Error("session expiree"); }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `${res.status}`);
    }
    return res.status === 204 ? null : res.json();
  } finally {
    clearTimeout(timer);
  }
}

function toast(message, tone = "info") {
  const el = document.createElement("div");
  el.className = "toast";
  el.dataset.tone = tone;
  el.textContent = message;
  $("toasts").append(el);
  setTimeout(() => el.remove(), 5200);
}

/* ── Session ─────────────────────────────────────────────────────────────── */

function showGate() {
  $("gate").hidden = false;
  document.body.dataset.boot = "gate";

  // LA SCRUTATION DOIT MOURIR AVEC LA SESSION.
  //
  // Elle ne s'arretait pas. `pump()` tourne toutes les 1,6 s et emet deux a
  // trois requetes par passage : une fois la session expiree, le poste
  // continuait a marteler l'API a environ 75 requetes non authentifiees par
  // minute, indefiniment, chacune repondue en 401. Mesure sur le poste de
  // l'exploitant : la console n'affichait plus que cela.
  //
  // Trois consequences, par gravite croissante :
  //
  // 1. Le limiteur de debit voit un poste legitime se comporter comme une
  //    attaque. Quand le technicien revient s'identifier, il peut se heurter
  //    a un blocage que son propre poste a provoque.
  // 2. Tout l'affichage — courbes, journal, ET LA SCENE 3D — reste fige sur
  //    le dernier etat recu, sans que rien ne le signale. Une supervision qui
  //    montre un etat perime sans le dire est pire qu'un ecran noir.
  // 3. Le bandeau annoncait « Service injoignable ». C'est FAUX : le service
  //    repond parfaitement, c'est la session qui a expire. Un diagnostic
  //    errone envoie l'exploitant verifier le reseau au lieu de se
  //    reconnecter.
  if (S.timer) { clearInterval(S.timer); S.timer = null; }
  setLink("down", "Session expirée — écran figé");
}

/**
 * Relance la scrutation apres une identification reussie.
 *
 * `start()` ne peut pas servir : il est garde par `S.started` et reconstruit
 * tout le poste. Apres une simple expiration de session, la page est intacte —
 * seule la boucle est a redemarrer, et une seule fois.
 */
async function reprendreScrutation() {
  if (S.timer) return;
  await pump();
  S.timer = setInterval(pump, TICK);
}

function applyOperator(auth) {
  S.operator = auth.operator || null;
  S.csrf = auth.operator?.csrf_token || "";
  const name = auth.operator?.email || auth.operator?.username || "Poste local";
  $("whoName").textContent = name;
  $("whoBadge").textContent = name.slice(0, 2);
  $("logout").hidden = !auth.required;
}

/**
 * Bascule l'écran d'accueil en mode « prise de quart ».
 *
 * L'authentification est désactivée par défaut, et l'activer exige une
 * allowlist et un hachage PBKDF2 configurés hors dépôt — c'est un choix de
 * sécurité correct. Conséquence : l'écran d'identification ne s'affichait
 * jamais. On le conserve, mais en disant ce qu'il est : une prise de poste
 * déclarative, qui trace le quart sans prétendre authentifier qui que ce soit.
 */
function setGateMode(secured) {
  S.secured = secured;
  $("gateKicker").textContent = secured ? "Accès poste" : "Prise de quart";
  $("gateTitle").textContent = secured ? "Identification technicien" : "Prise de poste";
  $("gateNote").textContent = secured
    ? "Identifiez-vous avec votre compte technicien. L'adresse saisie identifie "
      + "la session de quart dans le journal des actions."
    : "Aucun compte n'est enregistré sur ce poste. Renseignez votre adresse pour "
      + "tracer la prise de quart ; aucun mot de passe ne peut être vérifié.";
  $("passwordField").hidden = !secured;
  $("loginPassword").required = secured;
  $("gateSubmit").textContent = secured ? "Ouvrir la session" : "Prendre le poste";
  $("gateDisclaimer").hidden = secured;
}

/**
 * Affiche l'écran d'attente du service et réessaie jusqu'à ce qu'il réponde.
 *
 * L'ÉCRAN ÉTAIT ENTIÈREMENT BLANC. `boot()` posait l'indicateur de lien sur
 * « Service injoignable » puis abandonnait, en laissant `data-boot="pending"` :
 * or la feuille de style met la coque à `opacity: 0` dans cet état, et le
 * panneau d'identification reste `hidden` par défaut. L'utilisateur n'avait
 * donc RIEN — pas un message, pas un logo, pas une erreur.
 *
 * Ce n'est pas un cas rare : le service construit l'historique complet et
 * entraîne le modèle au démarrage. Toute ouverture du poste pendant cette
 * fenêtre tombait sur une page vide.
 *
 * @param {number} essai Numéro de la tentative en cours.
 */
function attendreLeService(essai) {
  document.body.dataset.boot = "waiting";
  setLink("down", "Service injoignable");
  const plaque = $("bootWait");
  if (plaque) {
    plaque.hidden = false;
    $("bootWaitDetail").textContent = essai === 1
      ? "Le service construit la chaîne de traitement au démarrage."
      : `Nouvelle tentative dans quelques secondes (essai ${essai}).`;
  }
  // Attente progressive, plafonnée : inutile de marteler un service qui charge.
  const delai = Math.min(2000 * essai, 10000);
  setTimeout(() => boot(essai + 1), delai);
}

async function boot(essai = 1) {
  let auth;
  try {
    auth = await api("/api/auth/status");
  } catch {
    attendreLeService(essai);
    return;
  }
  const plaque = $("bootWait");
  if (plaque) plaque.hidden = true;
  setLink("idle", "Connecté");

  if (auth.required && !auth.authenticated) {
    setGateMode(true);
    showGate();
    return;
  }

  applyOperator(auth);
  if (!auth.required) {
    // Poste local : on demande quand meme qui prend le quart.
    setGateMode(false);
    showGate();
    return;
  }

  $("gate").hidden = true;
  document.body.dataset.boot = "ready";
  await start();
}

async function login(event) {
  event.preventDefault();
  $("loginError").textContent = "";

  const email = $("loginEmail").value.trim();

  if (!S.secured) {
    // Prise de quart declarative : rien n'est envoye au serveur, et rien ne
    // pretend le contraire.
    S.shiftOperator = email;
    $("whoName").textContent = email;
    $("whoBadge").textContent = email.slice(0, 2).toUpperCase();
    $("gate").hidden = true;
    document.body.dataset.boot = "ready";
    if (!S.started) { S.started = true; await start(); }
    return;
  }

  try {
    const auth = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password: $("loginPassword").value }),
    });
    applyOperator({ required: true, operator: auth.operator || auth });
    $("gate").hidden = true;
    document.body.dataset.boot = "ready";
    // `S.started` reste vrai apres une expiration de session : sans cette
    // branche, se reidentifier rendait la main sur un poste definitivement
    // muet — la boucle arretee par `showGate` n'etait jamais relancee.
    if (!S.started) { S.started = true; await start(); }
    else await reprendreScrutation();
  } catch (err) {
    $("loginError").textContent = err.message || "Identification refusee";
  }
}

/* ── Navigation ──────────────────────────────────────────────────────────── */

function slideTab() {
  const active = document.querySelector(".view-tab.is-on");
  if (!active) return;
  const slider = $("viewSlider");
  slider.style.left = `${active.offsetLeft}px`;
  slider.style.width = `${active.offsetWidth}px`;
}

function switchView(view) {
  S.view = view;
  $$(".view-tab").forEach((b) => {
    const actif = b.dataset.view === view;
    b.classList.toggle("is-on", actif);
    // L'ETAT DES ONGLETS N'ETAIT PORTE QUE PAR UNE CLASSE CSS.
    // Un lecteur d'ecran annoncait trois boutons identiques sans jamais dire
    // lequel etait selectionne, et la tabulation traversait les trois onglets
    // alors que la convention WAI-ARIA n'en expose qu'un : celui qui est actif.
    b.setAttribute("aria-selected", actif ? "true" : "false");
    b.tabIndex = actif ? 0 : -1;
  });
  $$(".view").forEach((v) => { v.hidden = v.dataset.panel !== view; });
  slideTab();
  // Le rendu 3D est suspendu hors de sa vue : inutile de faire tourner un
  // moteur WebGL derriere un onglet cache.
  S.twin?.setPaused(view !== "salle");
}

/* ── Horloge ─────────────────────────────────────────────────────────────── */

function tickClock() {
  const now = new Date();
  $("clock").textContent = new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit", minute: "2-digit",
  }).format(now);
  $("clockDate").textContent = new Intl.DateTimeFormat("fr-FR", {
    weekday: "short", day: "2-digit", month: "short",
  }).format(now);
}

function setLink(state, label) {
  // L'INDICATEUR DE LIAISON NE DOIT JAMAIS FAIRE TOMBER CE QUI L'APPELLE.
  // Il est pose depuis les chemins d'erreur — expiration de session, service
  // injoignable. Si l'element manquait, la mise a jour du bandeau ferait
  // echouer la gestion de l'erreur elle-meme : le poste perdrait a la fois la
  // liaison ET le traitement de sa perte.
  const el = $("linkState");
  if (!el) return;
  el.dataset.link = state;
  const texte = el.querySelector("span");
  if (texte) texte.textContent = label;
}

/* ═══ Jumeau 3D ═══════════════════════════════════════════════════════════ */

/**
 * Construit le jumeau 3D.
 *
 * La fiche équipement lui est transmise : elle sert à graver la plaque
 * signalétique portée par la calandre, avec le constructeur, le code appareil
 * et la taille réels. Sans elle, la plaque retomberait sur les constantes
 * documentées en tête de `twin.js`.
 *
 * @param {object|null} equipment Fiche équipement issue de /api/equipment.
 */
function initTwin(equipment = null) {
  try {
    S.twin = new CoolerTwin($("twin"), {
      equipment,
      onSelect: (hit) => {
        if (hit.type === "sensor") openSensor(hit.id);
        else openComponent(hit.id);
      },
    });
    // POIGNEE DE DIAGNOSTIC. La scene 3D vit dans une portee de module :
    // inatteignable depuis la console. Quand l'affichage contredit l'etat
    // annonce — une piece designee CRITIQUE qui ne bouge pas, un capteur muet —
    // il n'existait aucun moyen de savoir, sur le poste concerne, si le defaut
    // venait des donnees, du code charge, ou du rendu. On diagnostiquait a
    // l'aveugle. Cette reference ne fait qu'exposer un objet deja construit :
    // elle n'ouvre aucun acces que la page n'ait deja.
    window.__twin = S.twin;

    const stats = S.twin.stats();
    $("stageLegal").innerHTML =
      `Géométrie construite sur <b>SIZE 1118-9754</b> de la fiche équipement — `
      + `calandre Ø ${stats.shell_diameter_mm} mm, tubes ${stats.tube_length_mm} mm, `
      + `${stats.tubes} tubes représentés.`;
  } catch (err) {
    $("stage").insertAdjacentHTML("beforeend",
      `<p class="stage-legal">Rendu 3D indisponible sur ce poste (${esc(err.message)}).</p>`);
  }
}

/**
 * Traduit les constatations du detecteur en pieces et capteurs a colorer.
 * La correspondance vient integralement de `finding_map` (topology.yaml) :
 * un code inconnu n'allume rien, plutot que d'accuser la mauvaise piece.
 */
function twinStateFrom(event) {
  const map = S.topology?.finding_map || {};
  const components = {};
  const sensors = {};
  const raise = (bag, key, sev) => {
    if (!key) return;
    if (!bag[key] || SEV_RANK[sev] > SEV_RANK[bag[key]]) bag[key] = sev;
  };

  for (const finding of event?.findings || []) {
    const sev = finding.severity || "INFO";
    if (sev === "INFO" || sev === "NORMAL") continue;
    const target = map[finding.code];
    if (!target) continue;
    (target.components || []).forEach((c) => raise(components, c, sev));
    (target.sensors || []).forEach((s) => raise(sensors, s, sev));
  }
  return { components, sensors };
}

/* ── Panneau capteur ─────────────────────────────────────────────────────── */

async function openSensor(alias) {
  S.openSensor = alias;
  const drawer = $("drawer");
  drawer.hidden = false;
  $("drawerName").textContent = "Chargement…";

  let data;
  try {
    const end = S.cursor ? `&end=${encodeURIComponent(S.cursor)}` : "";
    data = await api(
      `/api/sensor/${encodeURIComponent(alias)}?window_h=${S.drawerSpan}${end}`,
    );
  } catch (err) {
    $("drawerName").textContent = "Indisponible";
    toast(`Capteur ${alias} : ${err.message}`, "fault");
    return;
  }

  const degraded = data.role === "degraded";
  $("drawerRole").textContent = degraded
    ? "Capteur déclaré défaillant"
    : `Capteur ${data.role} · confiance ${data.confidence}`;
  $("drawerName").textContent = data.label;
  $("drawerTag").textContent = `${data.tag} · ${data.placement?.placement || "—"}`;
  $("drawerValue").textContent = fmt(data.stats.last, 2);
  $("drawerUnit").textContent = displayUnit(data.unit);

  const avail = num(data.quality.availability_pct);
  const chip = $("drawerQuality");
  chip.textContent = avail === null ? "—" : `${fmt(avail, 1)} % disponible`;
  chip.dataset.tone = avail === null ? "" : avail > 95 ? "ok" : avail > 70 ? "warn" : "fault";

  const th = data.thresholds || {};
  const facts = [
    ["Dernière mesure", stamp(data.stats.last_at)],
    ["Plage exploitation", data.range_operating
      ? `${fmt(data.range_operating[0], 1)} – ${fmt(data.range_operating[1], 1)}` : "—"],
    ["Consigne", data.setpoint === null || data.setpoint === undefined ? "—" : fmt(data.setpoint, 1)],
    ["Seuil haut", th.alarm_high === null || th.alarm_high === undefined ? "—" : fmt(th.alarm_high, 1)],
    ["Seuil bas", th.alarm_low === null || th.alarm_low === undefined ? "—" : fmt(th.alarm_low, 1)],
    ["P1 – P99", `${fmt(data.stats.p01, 1)} – ${fmt(data.stats.p99, 1)}`],
    ["Min – Max", `${fmt(data.stats.min, 1)} – ${fmt(data.stats.max, 1)}`],
    ["Défauts tracés", `${data.quality.n_events}`],
  ];
  $("drawerFacts").innerHTML = facts
    .map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");

  const issues = Object.entries(data.quality.issues || {})
    .map(([k, v]) => `${k.toLowerCase()} ×${v}`).join(", ");
  $("drawerRationale").textContent =
    (data.rationale || "Aucune justification enregistrée.")
    + (issues ? `\n\nDéfauts relevés : ${issues}.` : "");

  drawSensorChart(data);
}

function drawSensorChart(data) {
  const ctx = $("drawerChart");
  S.charts.sensor?.destroy();
  const th = data.thresholds || {};
  const guide = (value, colour, dash) => (value === null || value === undefined ? null : {
    label: "", data: data.series.timestamps.map(() => value),
    borderColor: colour, borderWidth: 1, borderDash: dash, pointRadius: 0, fill: false,
  });
  const datasets = [
    {
      label: data.alias,
      data: data.series.values,
      borderColor: CHARTE.mer,
      backgroundColor: "rgba(79,188,212,.12)",
      borderWidth: 1.8, pointRadius: 0, fill: true, tension: .18, spanGaps: false,
    },
    guide(data.setpoint, CHARTE.alliage, [4, 4]),
    guide(th.alarm_high, CHARTE.alerte, [2, 3]),
    guide(th.alarm_low, CHARTE.alerte, [2, 3]),
  ].filter(Boolean);

  S.charts.sensor = new Chart(ctx, {
    type: "line",
    data: { labels: data.series.timestamps.map((t) => stamp(t, false)), datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: tooltipStyle() },
      scales: {
        x: { ticks: { color: CHARTE.encre4, font: { size: 9 }, maxTicksLimit: 5 }, grid: { display: false } },
        y: {
          ticks: { color: CHARTE.encre4, font: { size: 9 } },
          grid: { color: CHARTE.trait },
        },
      },
    },
  });
}

function openComponent(code) {
  const comp = (S.topology?.components || []).find((c) => c.code === code);
  if (!comp) return;
  $("drawer").hidden = true;
  $("modalTitle").textContent = comp.label;
  const modes = comp.amdec_modes
    .map((m) => (S.equipment?.amdec || []).find((a) => a.code === m))
    .filter(Boolean);
  $("modalBody").innerHTML = `
    <dl>
      <div><dt>Fluide</dt><dd>${esc(comp.fluide || "—")}</dd></div>
      <div><dt>Criticité AMDEC max</dt><dd>${comp.criticite_max || "—"}</dd></div>
      <div><dt>Instrumenté</dt><dd>${comp.instrumented ? "oui" : "non — angle mort"}</dd></div>
      <div><dt>Couverture préventive</dt><dd>${esc(comp.inspection || "—")}</dd></div>
    </dl>
    <p style="color:var(--ink-3);font-size:13px;line-height:1.65">${esc(comp.description)}</p>
    ${modes.length ? `<h3 style="font:400 15px var(--disp);margin:22px 0 10px">Modes de défaillance rattachés</h3>
    <div class="tbl"><table><thead><tr><th>Mode</th><th>Effet</th><th>C</th><th>Action de référence</th></tr></thead><tbody>
      ${modes.map((m) => `<tr>
        <td>${esc(m.mode)}</td><td>${esc(m.element)}</td>
        <td><span class="crit" data-band="${esc(m.band)}">${m.C}</span></td>
        <td>${esc(m.action)}</td></tr>`).join("")}
    </tbody></table></div>` : ""}
  `;
  $("modal").showModal();
}

/* ═══ Courbe principale ═══════════════════════════════════════════════════ */

/**
 * Jeton de charte résolu depuis la feuille de style.
 *
 * LES GRAPHIQUES FIGEAIENT LEURS COULEURS EN DUR — dont `#5b7276`, quatre
 * fois, pour la couleur des graduations. C'est l'ANCIENNE valeur de
 * `--ink-4`, que `app.css` déclare explicitement rejetée pour échec WCAG AA :
 * 3,56:1 sur le fond des cartes, 3,26:1 au survol. Le jeton CSS a été relevé
 * deux fois ; les graphiques sont restés sur la valeur fautive, hors de
 * portée du banc frontend qui, lui, lit le jeton.
 *
 * Chart.js ne résout pas les variables CSS : on les lit donc une fois au
 * chargement. La charte redevient une source unique.
 *
 * @param {string} nom Nom de la variable CSS, sans `var()`.
 * @param {string} repli Valeur si la variable est absente.
 * @returns {string} Couleur résolue.
 */
function jeton(nom, repli) {
  // La résolution est enveloppée : `getComputedStyle` n'existe pas dans un
  // contexte sans rendu, et une charte ne doit jamais empêcher le poste de
  // démarrer. La valeur de repli est celle du jeton au moment de l'écriture.
  try {
    const v = window.getComputedStyle(document.documentElement)
      .getPropertyValue(nom).trim();
    return v || repli;
  } catch {
    return repli;
  }
}

const CHARTE = {
  encre: jeton("--ink", "#e9f2f1"),
  encre2: jeton("--ink-2", "#b3c6c7"),
  encre3: jeton("--ink-3", "#7c9396"),
  encre4: jeton("--ink-4", "#718a8e"),
  mer: jeton("--sea-live", "#4fbcd4"),
  acide: jeton("--acid-live", "#e07a45"),
  ok: jeton("--ok", "#4fd6a6"),
  alerte: jeton("--warn", "#f0a52f"),
  alliage: jeton("--alloy", "#9fa7a6"),
  trait: jeton("--hair", "rgba(154,190,196,.13)"),
};

const PALETTE = [CHARTE.acide, CHARTE.mer, CHARTE.ok, "#a98fe0", CHARTE.alerte];

function tooltipStyle() {
  return {
    backgroundColor: "rgba(8,16,20,.96)",
    borderColor: "rgba(154,190,196,.26)",
    borderWidth: 1,
    titleColor: CHARTE.encre2,
    bodyColor: CHARTE.encre,
    titleFont: { size: 11 },
    bodyFont: { size: 12 },
    padding: 10,
    displayColors: true,
    boxWidth: 8,
    boxHeight: 8,
  };
}

const TREND_SETS = {
  thermal: {
    title: "Températures du circuit acide", unit: "°C",
    lines: [["T_ACID_IN", "Entrée acide"], ["T_ACID_OUT", "Sortie acide"], ["T_CIRC_1300", "Circuit 1300"]],
    guide: ["Consigne 66 °C", 66],
  },
  titre: {
    title: "Analyseurs de titre acide", unit: "%",
    lines: [["C_ACID_1100", "AI1100 · circuit 1100"], ["C_ACID_1200", "AI1200 · circuit 1200"]],
  },
  debit: {
    title: "Débit acide et allure de marche", unit: "m³/h",
    lines: [["F_ACID", "Débit acide"], ["LOAD_SULFUR", "Charge soufre (t/h)"]],
  },
  duty: {
    title: "Puissance évacuée — observée contre attendue", unit: "kW",
    lines: [["duty_kw", "Observé"], ["duty_expected", "Référence semi-empirique"]],
  },
  absorption: {
    title: "Contexte section absorption", unit: "",
    lines: [["F_3412", "FI3412"], ["A_3301", "AI3301"], ["A_3302", "AI3302"]],
  },
  degrade: {
    title: "Instrumentation dégradée — valeurs DCS brutes", unit: "",
    lines: [["TI_5303", "TI5303-4X · butée 327,67"], ["PHI_5306", "PHI5306X-3 · figé −14,407"]],
  },
};

function drawTrend() {
  const series = S.series;
  if (!series) return;
  const set = TREND_SETS[$("trendSet").value] || TREND_SETS.thermal;
  $("trendTitle").textContent = set.title;

  const labels = series.timestamps.map((t) => stamp(t, false));
  const datasets = set.lines.map(([key, label], i) => ({
    label,
    data: series[key] || [],
    borderColor: PALETTE[i % PALETTE.length],
    backgroundColor: "transparent",
    borderWidth: 1.7, pointRadius: 0, tension: .16, spanGaps: false,
  }));
  if (set.guide) {
    datasets.push({
      label: set.guide[0],
      data: labels.map(() => set.guide[1]),
      borderColor: CHARTE.encre3, borderDash: [5, 5], borderWidth: 1, pointRadius: 0,
    });
  }

  $("trendLegend").innerHTML = `<div class="legend">${
    datasets.map((d) => `<span><i style="background:${d.borderColor}"></i>${esc(d.label)}</span>`).join("")
  }</div>`;

  if (S.charts.trend) {
    S.charts.trend.data.labels = labels;
    S.charts.trend.data.datasets = datasets;
    S.charts.trend.options.scales.y.ticks.callback = (v) => `${String(v).replace(".", ",")} ${set.unit}`;
    S.charts.trend.update("none");
    return;
  }
  S.charts.trend = new Chart($("trendChart"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: tooltipStyle() },
      scales: {
        x: { ticks: { color: CHARTE.encre4, font: { size: 9 }, maxTicksLimit: 8 }, grid: { display: false } },
        y: {
          ticks: {
            color: CHARTE.encre4, font: { size: 9 },
            callback: (v) => `${String(v).replace(".", ",")} ${set.unit}`,
          },
          grid: { color: CHARTE.trait },
        },
      },
    },
  });
}

/* ═══ Bandeau de lecture ══════════════════════════════════════════════════ */

/**
 * Bandeau de lecture.
 *
 * Chaque carte porte SA PROVENANCE en sous-titre. Les quatre premières sont
 * des mesures et citent leur tag DCS ; les deux dernières sont calculées et
 * citent leur formule.
 *
 * La version précédente affichait `duty_kw` et `control_deviation` — des noms
 * de variables Python — là où les autres cartes affichaient un tag
 * d'instrumentation. Un opérateur ne peut rien faire d'un identifiant de code,
 * et un jury y voit la couture entre le calcul et l'affichage.
 */
const READOUTS = [
  { alias: "T_ACID_IN", label: "Entrée acide", digits: 1 },
  { alias: "T_ACID_OUT", label: "Sortie acide", digits: 2 },
  { alias: "F_ACID", label: "Débit acide", digits: 1 },
  { alias: "LOAD_SULFUR", label: "Charge soufre", digits: 1 },
  {
    key: "duty_kw", label: "Puissance évacuée", unit: "kW", digits: 0,
    source: "calculé · ρ·cp·Q·ΔT",
  },
  {
    key: "control_deviation", label: "Écart consigne", unit: "°C", digits: 2,
    source: "calculé · sortie − 66 °C",
  },
];

function lastValue(list) {
  if (!Array.isArray(list)) return null;
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const v = num(list[i]);
    if (v !== null) return v;
  }
  return null;
}

/**
 * Tendance d'une grandeur sur la fin de la fenêtre affichée.
 *
 * Troisième niveau du modèle d'Endsley, qui structure la norme ISA-101 :
 * percevoir, comprendre, **projeter**. Les deux premiers niveaux étaient
 * traités ; celui-ci manquait. Un opérateur doit voir non seulement où il est,
 * mais où il va.
 *
 * @param {Array<number|null>} list Série de valeurs.
 * @param {number} span Nombre de points pris en compte.
 * @returns {{slope:number, glyph:string, label:string}|null}
 */
function trendOf(list, span = 40) {
  if (!Array.isArray(list) || list.length < 8) return null;
  const tail = list.slice(-span).map(num).filter((v) => v !== null);
  if (tail.length < 8) return null;

  // Régression linéaire simple : la pente suffit, on n'affiche pas sa valeur.
  const n = tail.length;
  const meanX = (n - 1) / 2;
  const meanY = tail.reduce((a, b) => a + b, 0) / n;
  let cov = 0;
  let varX = 0;
  tail.forEach((y, i) => { cov += (i - meanX) * (y - meanY); varX += (i - meanX) ** 2; });
  const slope = varX ? cov / varX : 0;

  // LA ZONE MORTE SE MESURE SUR LA DISPERSION, PAS SUR LA MOYENNE.
  //
  // La version précédente déclarait une pente significative dès qu'elle
  // déplaçait la grandeur de 0,5 % de son NIVEAU MOYEN. Pour l'écart de
  // consigne, dont la moyenne vaut environ zéro par construction, ce seuil
  // tombait à zéro : la moindre oscillation lisait « en hausse ». Les six
  // grandeurs du bandeau affichaient alors la même flèche montante, et
  // l'indicateur devenait décoratif.
  //
  // On compare désormais le déplacement total sur la fenêtre à l'écart-type
  // résiduel autour de la droite. En dessous d'un demi écart-type, ce que l'on
  // voit est du bruit, et on le dit.
  let sse = 0;
  tail.forEach((y, i) => { sse += (y - (meanY + slope * (i - meanX))) ** 2; });
  const noise = Math.sqrt(sse / Math.max(n - 2, 1));
  const move = Math.abs(slope) * (n - 1);

  if (!(move > Math.max(noise * 0.5, 1e-9))) {
    return { slope: 0, glyph: "→", label: "stable" };
  }
  return slope > 0
    ? { slope, glyph: "↗", label: "en hausse" }
    : { slope, glyph: "↘", label: "en baisse" };
}

function drawReadouts() {
  const series = S.series;
  if (!series) return;
  const byAlias = new Map((S.topology?.sensors || []).map((s) => [s.alias, s]));
  const faults = twinStateFrom(S.latest).sensors;

  $("readouts").innerHTML = READOUTS.map((r) => {
    const key = r.alias || r.key;
    const value = lastValue(series[key]);
    const meta = byAlias.get(r.alias);
    const unit = r.unit ?? displayUnit(meta?.unit);
    const sev = r.alias ? faults[r.alias] : null;
    const tone = sev === "CRITICAL" ? "fault" : sev === "WARNING" ? "warn" : "";
    const trend = trendOf(series[key]);
    return `<button class="readout" data-tone="${tone}" ${r.alias ? `data-sensor="${esc(r.alias)}"` : ""}>
      <span class="micro">${esc(r.label)}</span>
      <span class="readout-val">${fmt(value, r.digits)}<em>${esc(unit)}</em></span>
      <span class="readout-foot">
        <span class="readout-sub" data-derived="${!r.alias}">${
          esc(r.source || meta?.tag || key)}</span>
        ${trend ? `<span class="trend" data-dir="${trend.slope > 0 ? "up" : trend.slope < 0 ? "down" : "flat"}"
           title="${esc(trend.label)}"><i aria-hidden="true">${trend.glyph}</i>${esc(trend.label)}</span>` : ""}
      </span>
    </button>`;
  }).join("");

  // Alimente les etiquettes 3D avec les memes valeurs que le bandeau.
  const values = {};
  for (const s of S.topology?.sensors || []) values[s.alias] = lastValue(series[s.alias]);
  S.twin?.setValues(values);

  // L'ÉCRAN NE DOIT PAS DIRE LE CONTRAIRE DE CE QU'IL MONTRE.
  // La plaque annonçait « Aucune donnée rejouée » alors que les étiquettes du
  // jumeau portaient déjà des valeurs : avant tout rejeu, le poste affiche le
  // dernier point disponible du corpus. On le dit.
  if (!S.replay?.running && !S.cursor) {
    const dernier = S.governance?.health?.data_end;
    $("assetStamp").textContent = dernier
      ? `Dernier point disponible · ${stamp(dernier)}`
      : "En attente de données";
  }
}

/* ═══ Etat courant ════════════════════════════════════════════════════════ */

function renderLatest(event) {
  if (!event) return;
  S.latest = event;

  const sev = event.severity || "NORMAL";
  const plate = $("verdictPlate");
  plate.dataset.sev = sev;
  $("verdictLabel").innerHTML = sevMark(sev);
  // DEUX NOMBRES SUR DEUX ÉCHELLES DIFFÉRENTES NE SE LISENT PAS CÔTE À CÔTE.
  // Le bandeau affichait « Contrôle 9,9/10 · score 0,992 » : une note de
  // cohérence sur dix accolée à un score d'isolation forest sur un, sans
  // unité ni séparation. Le second sature d'ailleurs près de 1 pour tout
  // point signalé, donc il n'informe pas. Seule la note du contrôleur reste
  // ici ; le score statistique est présenté avec son seuil dans le panneau de
  // diagnostic, seul endroit où il a un sens.
  $("verdictDetail").textContent = event.judge_agreement === false
    ? `Rejeté par le contrôleur de cohérence · ${fmt(event.judge_score, 1)}/10`
    : `Contrôle de cohérence ${fmt(event.judge_score, 1)}/10`;

  $("assetState").textContent = etatLisible(event.process_state);
  $("assetStamp").textContent = stamp(event.timestamp);

  $("diagConfidence").textContent = `confiance ${fmt((event.confidence || 0) * 100, 0)} %`;
  const tone = sev === "CRITICAL" ? "fault" : sev === "WARNING" ? "warn" : "";
  $("diag").innerHTML = `
    <div class="diag-block" data-tone="${tone}">
      <span class="micro">Conclusion</span>
      <p>${esc(event.diagnosis || "Aucun diagnostic")}</p>
    </div>
    <div class="diag-block">
      <span class="micro">Action recommandée · ${esc(urgenceLisible(event.urgency))}</span>
      <p>${esc(event.action || "Aucune action")}</p>
    </div>
    <div class="diag-block">
      <span class="micro">Rattachement AMDEC</span>
      <div class="mode-tags">${
        (event.amdec_modes || []).map((m) => `<span class="mode-tag">${esc(m)}</span>`).join("")
        || '<span class="mode-tag">aucun mode</span>'}</div>
    </div>
    ${event.judge_issues?.length ? `<div class="diag-block" data-tone="warn">
      <span class="micro">Réserves du contrôleur</span>
      <ul class="reserves">${event.judge_issues
        .map((code) => `<li><b>${esc(RESERVE_LABEL[code]?.titre || code)}</b>${
          RESERVE_LABEL[code] ? ` — ${esc(RESERVE_LABEL[code].sens)}` : ""}</li>`)
        .join("")}</ul></div>` : ""}
  `;

  S.twin?.setState(twinStateFrom(event));
}

/**
 * Journal du rejeu.
 *
 * DEUX DÉFAUTS CORRIGÉS ICI.
 *
 * 1. LE DÉFILEMENT SAUTAIT. Le journal était réécrit intégralement toutes les
 *    1,6 s. Un opérateur en train de lire une entrée plus ancienne était
 *    ramené en haut à chaque cycle, et la liste clignotait. On ne réécrit
 *    désormais que si le contenu a réellement changé, et la position de
 *    défilement est restituée.
 *
 * 2. LE TEXTE ÉTAIT COUPÉ EN PLEIN MOT. Une troncature brutale à 150
 *    caractères produisait « ne peut etre formule a par », sans ellipse ni
 *    moyen de lire la suite. La coupe se fait à la dernière frontière de mot,
 *    l'ellipse est visible, et le texte intégral reste accessible en survol.
 */
function renderFeed(events) {
  const box = $("feed");
  if (!events?.length) {
    S.feedEvents = [];
    box.innerHTML = '<p class="void">Aucun événement pour ce filtre.</p>';
    return;
  }
  // Les événements restent en mémoire JavaScript. La version précédente les
  // sérialisait en JSON dans un attribut DOM à chaque cycle de 1,6 s : un
  // contournement, pas une conception.
  S.feedEvents = events.slice(0, 60);

  const html = S.feedEvents.map((e, i) => {
    const complet = e.diagnosis || "";
    const abrege = ellipse(complet, 148);
    const modes = (e.amdec_modes || []).join(" · ") || "hors mode AMDEC";
    return `
    <button class="event" data-sev="${esc(e.severity)}" data-idx="${i}"
            title="${esc(complet)}">
      <span class="event-time">${esc(stamp(e.timestamp))}</span>
      <span class="event-body">
        ${sevMark(e.severity)}
        <strong>${esc(abrege)}</strong>
        <small>${esc(modes)}${
          e.urgency && e.urgency !== "AUCUNE" ? ` — ${esc(urgenceLisible(e.urgency))}` : ""}</small>
      </span>
      <span class="event-score">${fmt(e.judge_score, 1)}/10</span>
    </button>`;
  }).join("");

  if (box.dataset.sig === html.length.toString() && box.innerHTML === html) return;
  const scroll = box.scrollTop;
  box.innerHTML = html;
  box.dataset.sig = html.length.toString();
  box.scrollTop = scroll;
}

/**
 * Abrège à la dernière frontière de mot avant la limite.
 *
 * @param {string} texte Texte complet.
 * @param {number} limite Longueur maximale.
 * @returns {string} Texte abrégé, suivi d'une ellipse s'il a été coupé.
 */
function ellipse(texte, limite) {
  const t = String(texte ?? "").trim();
  if (t.length <= limite) return t;
  const coupe = t.slice(0, limite);
  const espace = coupe.lastIndexOf(" ");
  return `${(espace > limite * 0.6 ? coupe.slice(0, espace) : coupe).replace(/[,;:.\s]+$/, "")}…`;
}

function openEvent(event) {
  $("modalTitle").textContent = `Décision du ${stamp(event.timestamp)}`;
  const m = event.measurements || {};
  $("modalBody").innerHTML = `
    <dl>
      <div><dt>Sévérité</dt><dd>${esc(SEV_LABEL[event.severity] || event.severity)}</dd></div>
      <div><dt>État procédé</dt><dd>${esc(etatLisible(event.process_state))}</dd></div>
      <div><dt>Score d'anomalie</dt><dd>${fmt(event.anomaly_score, 3)}</dd></div>
      <div><dt>Contrôle de cohérence</dt><dd>${fmt(event.judge_score, 2)} / 10</dd></div>
    </dl>
    <p style="color:var(--ink-2);font-size:13px;line-height:1.65">${esc(event.diagnosis)}</p>
    <p style="color:var(--ink-3);font-size:13px;line-height:1.65"><b>Action :</b> ${esc(event.action)}</p>
    <h3 style="font:400 15px var(--disp);margin:22px 0 10px">Constatations</h3>
    <div class="tbl"><table><thead><tr><th>Code</th><th>Source</th><th>Sév.</th><th>Message</th></tr></thead><tbody>
      ${(event.findings || []).map((f) => `<tr>
        <td class="num">${esc(f.code)}</td><td>${esc(f.source)}</td>
        <td>${esc(f.severity)}</td><td>${esc(f.message)}</td></tr>`).join("")}
    </tbody></table></div>
    <h3 style="font:400 15px var(--disp);margin:22px 0 10px">Mesures citées</h3>
    <p class="modal-note">Valeurs sur lesquelles le contrôleur a confronté le
       diagnostic. Chacune est une mesure de l'instant analysé, pas une moyenne.</p>
    <div class="tbl"><table><tbody>
      ${Object.entries(m).map(([k, v]) => `<tr>
        <td>${esc(MESURE_LABEL[k]?.nom || k)}</td>
        <td class="num">${fmt(v, MESURE_LABEL[k]?.decimales ?? 2)}
          <em>${esc(MESURE_LABEL[k]?.unite || "")}</em></td></tr>`).join("")}
    </tbody></table></div>`;
  $("modal").showModal();
}

/* ═══ Rejeu ═══════════════════════════════════════════════════════════════ */

function renderFrieze(replay, health) {
  const start = health?.data_start;
  const end = health?.data_end;
  if (!start || !end) return;
  $("friezeStart").textContent = stamp(start);
  $("friezeEnd").textContent = stamp(end);

  const t0 = new Date(start).getTime();
  const t1 = new Date(end).getTime();
  const cursor = replay?.cursor ? new Date(replay.cursor).getTime() : t0;
  const pct = Math.max(0, Math.min(100, ((cursor - t0) / (t1 - t0)) * 100));
  $("friezeFill").style.right = `${100 - pct}%`;
  $("friezeRange").textContent = replay?.running
    ? `Curseur ${stamp(replay.cursor)} · ${replay.n_processed} instants analysés`
    : `${Math.round((t1 - t0) / 36e5).toLocaleString("fr-FR")} heures disponibles`;

  if (!$("friezeMarks").dataset.done && S.episodes.length) {
    $("friezeMarks").innerHTML = S.episodes.map((ep) => {
      const at = new Date(ep.start).getTime();
      const x = ((at - t0) / (t1 - t0)) * 100;
      // Le repère marqué distingue les épisodes les plus francs. Le score
      // saturant à 1,0000, il ne séparait rien : c'est la marge qui décide.
      return `<i style="left:${x.toFixed(2)}%" data-sev="${ep.margin_max >= 3 ? "high" : ""}"
        title="${esc(stamp(ep.start))} · ${fmt(ep.margin_max, 1)} σ"></i>`;
    }).join("");
    $("friezeMarks").dataset.done = "1";
  }
}

async function pump() {
  if (S.busy) return;
  S.busy = true;
  try {
    const replay = await api("/api/replay/state");
    S.replay = replay;
    S.cursor = replay.cursor;
    $("play").disabled = replay.running;
    $("halt").disabled = !replay.running;
    setLink(replay.running ? "live" : "idle", replay.running ? "Rejeu actif" : "En attente");
    renderFrieze(replay, S.governance?.health);

    const path = S.feed === "alerts" ? "/api/replay/alerts"
      : S.feed === "disagreements" ? "/api/replay/disagreements"
        : "/api/replay/stream";
    const events = await api(`${path}?n=60`);
    renderFeed(events);
    if (events.length) renderLatest(events[0]);

    if (replay.running || !S.series) await loadSeries(!S.series);
  } catch {
    setLink("down", "Service injoignable");
  } finally {
    S.busy = false;
  }
}

const SERIES_MIN_INTERVAL_MS = 8000;

/**
 * Recharge la série affichée.
 *
 * Le rejeu avance de quelques heures simulées par seconde réelle, mais la
 * courbe couvre 21 jours sur 650 points : redemander la série entière à chaque
 * cycle de 1,6 s retransmettait 650 points pour déplacer le curseur d'un pixel.
 * On ne recharge donc que si la fenêtre a réellement changé, ou après un délai
 * minimal.
 *
 * @param {boolean} force Ignorer le cache (changement de période, démarrage).
 */
async function loadSeries(force = false) {
  const hours = num($("trendSpan").value);
  const end = S.cursor || S.governance?.health?.data_end;

  // Un curseur arrondi à l'heure suffit à identifier la fenêtre demandée.
  const key = `${hours}|${String(end).slice(0, 13)}`;
  const now = Date.now();
  if (
    !force
    && key === S.seriesKey
    && now - (S.seriesAt || 0) < SERIES_MIN_INTERVAL_MS
  ) {
    return;
  }

  let path = "/api/timeseries?max_points=650";
  if (end && hours) {
    const e = new Date(end);
    const s = new Date(e.getTime() - hours * 36e5);
    path += `&start=${encodeURIComponent(s.toISOString())}&end=${encodeURIComponent(e.toISOString())}`;
  }
  S.series = await api(path);
  S.seriesKey = key;
  S.seriesAt = now;
  drawTrend();
  drawReadouts();
}

/* ═══ Vue Integrite ═══════════════════════════════════════════════════════ */

function renderKpi(kpi) {
  $("kpiRow").innerHTML = (kpi?.figures || []).map((f) => `
    <article class="kpi" data-evidence="${esc(f.evidence_level)}">
      <span class="micro">${esc(f.evidence_level === "derived" ? "grandeur dérivée" : "grandeur observée")}</span>
      <div class="kpi-val"><strong>${fmt(f.value, f.unit === "%" ? 1 : 0)}</strong><span>${esc(f.unit)}</span></div>
      <p><b style="color:var(--ink-2)">${esc(f.label)}</b><br>${esc(f.note)}</p>
    </article>`).join("");
}

function renderEpisodes(episodes) {
  S.episodes = episodes;
  $("episodeBadge").textContent = `${episodes.length} épisodes`;
  // LA COLONNE DE TRI EST LA MARGE, PAS LE SCORE.
  // Le score normalisé sature : les quatorze lignes affichaient « 1,000 », et
  // un tableau intitulé « les plus sévères » dont la colonne de sévérité est
  // constante ne hiérarchise rien. La marge — dépassement du seuil en
  // écarts-types — n'est pas bornée et sépare 57 épisodes sur 59.
  $("episodeRows").innerHTML = episodes.slice(0, 14).map((ep, i) => `
    <tr>
      <td class="num">${esc(stamp(ep.start))}</td>
      <td class="num">${ep.duration_h} h</td>
      <td class="num">${esc(stamp(ep.peak_at))}</td>
      <td class="num" data-alert="${ep.margin_max >= 4}"
          title="Dépassement du seuil de décision, en écarts-types de la période de référence">
        <b>+${fmt(ep.margin_max, 2)}</b> σ</td>
      <td><button class="table-btn" data-episode="${i}">Analyser</button></td>
    </tr>`).join("");

  const months = new Map();
  for (const ep of episodes) {
    const key = String(ep.start).slice(0, 7);
    months.set(key, (months.get(key) || 0) + 1);
  }
  $("cal").innerHTML = [...months.entries()].sort().map(([key, n]) => {
    const d = new Date(`${key}-01T00:00:00`);
    const label = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "2-digit" }).format(d);
    const heat = Math.min(1, n / 12);
    return `<div class="cal-cell" style="background:rgba(240,165,47,${(heat * .22).toFixed(3)});
      border-color:rgba(240,165,47,${(heat * .45 + .05).toFixed(3)})">
      <strong>${n}</strong><small>${esc(label)}</small></div>`;
  }).join("");
}

function renderSensorTable(rows) {
  $("sensorRows").innerHTML = rows.map((r) => {
    const a = num(r.availability_pct);
    const tone = a > 95 ? "ok" : a > 70 ? "warn" : "fault";
    return `<tr>
      <td><b>${esc(r.alias)}</b><br><small style="color:var(--ink-4);font-family:var(--mono)">${esc(r.tag)}</small></td>
      <td><span class="chip" data-tone="${tone}">${fmt(a, 1)} %</span></td>
      <td class="num">${r.n_frozen || 0}</td>
      <td class="num">${r.n_saturated || 0}</td></tr>`;
  }).join("");
}

function renderPlan(plan) {
  $("plan").innerHTML = Object.entries(plan || {}).map(([key, task]) => `
    <div class="plan-item">
      <span class="plan-key">${esc(key)}</span>
      <div><strong>${esc(task.tache)}</strong>
        <small>${esc(task.periodicite)} · ${esc(task.type)} · ${esc(task.etat)}</small></div>
    </div>`).join("");
}

/**
 * Provenance d'une ligne du référentiel AMDEC.
 *
 * LE DÉFAUT LE PLUS COÛTEUX DE CE TABLEAU.
 * Le référentiel mélange trois natures de lignes : la transcription fidèle de
 * l'AMDEC OCP du 23/09/2019, des règles que ce projet a dérivées d'une ligne
 * source, et une cotation entièrement proposée par l'application. Le domaine
 * les distingue rigoureusement — champ `provenance_category`, valeurs
 * d'origine conservées — puis le tableau les affichait toutes à l'identique.
 *
 * Un lecteur voyait donc « Chaîne de mesure · C = 108 » avec exactement la
 * même autorité que « PLAQUE SACRIFICIELLE · C = 112 », alors que la première
 * est une proposition du stage et la seconde une cotation OCP. C'est
 * précisément le genre de confusion qu'un jury cherche, et le travail de
 * traçabilité était déjà fait : il ne manquait qu'à le montrer.
 */
const PROVENANCE = {
  ocp_source: {
    court: "OCP", tone: "source",
    detail: "Ligne transcrite de l'AMDEC OCP du 23/09/2019 — cotation inchangée",
  },
  derived_rule: {
    court: "dérivée", tone: "derived",
    detail: "Dérivée d'une ligne OCP : libellé source scindé pour le rattachement des règles",
  },
  application_rule: {
    court: "projet", tone: "app",
    detail: "Proposée par ce projet, sans ligne correspondante dans l'AMDEC OCP",
  },
  hypothesis: {
    court: "hypothèse", tone: "app",
    detail: "Règle de risque construite à partir d'une cause citée par l'AMDEC",
  },
  field_validated: {
    court: "terrain", tone: "source",
    detail: "Confirmée par un constat terrain documenté",
  },
};

function renderAmdec(filter = "") {
  const q = filter.trim().toLowerCase();
  const rows = (S.equipment?.amdec || []).filter((m) => !q
    || `${m.element} ${m.mode} ${m.C} ${m.band} ${m.action}`.toLowerCase().includes(q));
  $("amdecRows").innerHTML = rows.map((m) => {
    const prov = PROVENANCE[m.provenance_category] || {
      court: m.provenance_category || "—", tone: "app", detail: "",
    };
    return `
    <tr>
      <td>
        <b>${esc(m.element)}</b>
        <span class="prov" data-tone="${prov.tone}"
              title="${esc(prov.detail)}${m.source_location ? ` — ${esc(m.source_location)}` : ""}">${
          esc(prov.court)}</span>
      </td>
      <td>${esc(m.mode)}</td>
      <td><span class="crit" data-band="${esc(m.band)}">${m.C}</span></td>
      <td>${m.observable ? "oui" : '<span style="color:var(--fault)">non — angle mort</span>'}</td>
      <td style="color:var(--ink-3)">${esc(m.action)}</td>
    </tr>`;
  }).join("");
}

/* ═══ Vue Controle ════════════════════════════════════════════════════════ */

const CHECKS = [
  ["V1", "Fidélité numérique", "22 %", "Chaque valeur citée est confrontée à la mesure recalculée, tolérance 1 %."],
  ["V2", "Sévérité", "16 %", "La sévérité annoncée correspond-elle aux faits recalculés ?"],
  ["V3", "Ancrage AMDEC", "14 %", "Les modes invoqués existent-ils, et sont-ils détectables par les capteurs ?"],
  ["V4", "Conformité de l'action", "14 %", "L'action est-elle proportionnée, conforme au plan préventif, exécutable ?"],
  ["V5", "Calibration", "15 %", "La confiance annoncée reflète-t-elle la force réelle des preuves ?"],
  ["V6", "État de marche", "8 %", "L'état de marche réel de la ligne est-il respecté ?"],
  ["V7", "Couverture", "5 %", "Le fait le plus grave est-il effectivement traité ?"],
  ["V8", "Incertitude", "6 %", "Les limites du diagnostic sont-elles énoncées ?"],
];

function renderChecks() {
  $("checks").innerHTML = CHECKS.map(([code, name, weight, note]) => `
    <div class="check">
      <div class="check-top"><b>${code} · ${esc(name)}</b><span>${weight}</span></div>
      <p>${esc(note)}</p>
    </div>`).join("");
}

function renderGovernance(g) {
  S.governance = { ...(S.governance || {}), ...g };

  const ing = g.ingestion || {};

  // La référence qui porte le diagnostic est celle du COEFFICIENT D'ÉCHANGE.
  // Ce bloc lisait encore `thermal_twin`, structure remplacée par les trois
  // références nommées : la carte affichait « R² — · n = undefined h ».
  const ua = g.references?.conductance;

  $("lineage").innerHTML = [
    ["Source", "DATA.xlsx", `${ing.n_rows} horodatages · pas ${duree(ing.step_nominal)}`],
    ["Qualité", `${ing.n_quality_events} événements`, ing.imputation_policy],
    ["États", Object.entries(ing.state_counts || {})
      .map(([k, v]) => `${etatLisible(k)} ${v} h`).join(" · "),
    "Seule la marche établie est jugée"],
    ["Coefficient d'échange", ua ? `UA ${fmt(ua.ua_reference, 1)} kW/K` : "—",
      ua ? `R² ${fmt(ua.r2, 3)} · σ ${fmt(ua.residual_std, 2)} kW/K · ${ua.n_train} h de référence`
        : "référence indisponible"],
    ["Modèle", g.model_source || "—", g.model_rejection_reason || `seuil ${fmt(g.detector?.threshold, 3)}`],
  ].map(([k, v, s]) => `<div class="lineage-node">
      <span class="micro">${esc(k)}</span><strong>${esc(v)}</strong><small>${esc(s || "")}</small></div>`).join("");

  $("blind").innerHTML = (g.blind_spots || []).map((b) => `
    <div class="blind-item">
      <span class="crit" data-band="${b.criticite >= 100 ? "majeure" : b.criticite >= 60 ? "significative" : "mineure"}">${b.criticite}</span>
      <div><strong>${esc(b.element)} — ${esc(b.mode)}</strong>
        <small>couverture préventive : tâche ${esc((b.couverture_preventive || []).join(", ") || "—")}</small></div>
    </div>`).join("") || '<p class="void">Aucun angle mort déclaré.</p>';
}

/**
 * Grandeurs citées dans une décision, avec leur unité et leur précision utile.
 *
 * La fenêtre d'analyse affichait dix-sept identifiants de code bruts — `duty_kw`,
 * `ua_residual_z`, `conc_min` — sans unité et tous à trois décimales. Trois
 * décimales sur une température de 66 °C annoncent une précision au millième de
 * degré que le capteur n'a pas ; sur une résistance d'encrassement de 0,0009
 * K/kW, elles effacent l'information.
 */
const MESURE_LABEL = {
  T_ACID_IN: { nom: "Entrée acide", unite: "°C", decimales: 1 },
  T_ACID_OUT: { nom: "Sortie acide", unite: "°C", decimales: 2 },
  F_ACID: { nom: "Débit acide", unite: "m³/h", decimales: 1 },
  LOAD_SULFUR: { nom: "Charge soufre", unite: "t/h", decimales: 1 },
  C_ACID_1100: { nom: "Titre acide circuit 1100", unite: "%", decimales: 2 },
  C_ACID_1200: { nom: "Titre acide circuit 1200", unite: "%", decimales: 2 },
  conc_min: { nom: "Titre acide gouvernant", unite: "%", decimales: 2 },
  delta_t: { nom: "Écart aux bornes", unite: "°C", decimales: 1 },
  duty_kw: { nom: "Puissance évacuée", unite: "kW", decimales: 0 },
  duty_expected: { nom: "Puissance attendue", unite: "kW", decimales: 0 },
  control_deviation: { nom: "Écart à la consigne", unite: "°C", decimales: 2 },
  T_SEAWATER: { nom: "Eau de mer (climatologie)", unite: "°C", decimales: 1 },
  ua_kw_per_k: { nom: "Coefficient d'échange", unite: "kW/K", decimales: 1 },
  ua_expected: { nom: "Coefficient d'échange attendu", unite: "kW/K", decimales: 1 },
  ua_residual_z: { nom: "Écart de coefficient d'échange", unite: "σ", decimales: 2 },
  fouling_resistance: { nom: "Résistance d'encrassement", unite: "K/kW", decimales: 4 },
  regulation_effort_z: { nom: "Effort de régulation", unite: "σ", decimales: 2 },
  regulation_effort_trend_14d: { nom: "Effort de régulation, 14 j", unite: "σ", decimales: 2 },
  anomaly_score: { nom: "Score du modèle statistique", unite: "", decimales: 3 },
};

/** Intitulés des portes de déploiement, côté exploitant. */
const GATE_LABEL = {
  causalite_temporelle: "Causalité temporelle",
  redondance_features: "Redondance des grandeurs",
  stabilite_hors_periode: "Stabilité hors référence",
  labels_gmao: "Vérité terrain GMAO",
  validation_externe: "Validation externe",
};

function renderValidation(report) {
  const gates = report?.deployment_gates || [];
  const passed = gates.filter((g) => g.passed).length;
  const chip = $("validationChip");
  chip.textContent = `${passed} / ${gates.length} portes franchies`;
  chip.dataset.tone = passed === gates.length ? "ok" : passed >= gates.length - 1 ? "warn" : "fault";

  const gen = report?.generated_from || {};
  const audit = report?.feature_audit || {};
  const bt = report?.temporal_backtest || {};

  const cells = [
    ["Plis temporels", gen.n_splits ?? (bt.folds || []).length, "apprentissage strictement sur le passé"],
    ["Gap train / test", gen.gap_calendar_hours ? `${gen.gap_calendar_hours} h` : "—", "empêche la fuite temporelle"],
    ["Features", audit.n_features ?? "—", `conditionnement ${fmt(audit.condition_number, 2)}`],
    ["Paires redondantes", (audit.redundant_pairs_abs_r_ge_0_90 || []).length, "|r| ≥ 0,90 entre features"],
  ];

  // Les portes portent un code machine en snake_case. L'écran affichait
  // « CAUSALITE TEMPORELLE » et « STABILITE HORS PERIODE » — le code
  // désoulignné, sans accents. Le code reste la référence pour l'API et les
  // tests ; l'écran affiche l'intitulé métier.
  const gateCells = gates.map((g) => [
    GATE_LABEL[g.gate] || g.gate.replace(/_/g, " "),
    g.passed ? "franchie" : "non franchie",
    g.evidence || "",
  ]);

  $("valid").innerHTML = [...cells, ...gateCells].map(([k, v, s]) => `
    <div class="valid-cell">
      <span class="micro">${esc(k)}</span>
      <strong style="${v === "non franchie" ? "color:var(--warn)" : ""}">${esc(v ?? "—")}</strong>
      <small>${esc(String(s).slice(0, 120))}</small>
    </div>`).join("");

  $("controlLimits").innerHTML = (report?.limitations || [])
    .map((l) => `<li>${esc(l)}</li>`).join("");
}

function renderBench(result) {
  const s = result?.summary || {};
  const aveugle = s.blind_mutations || {};
  $("benchScore").textContent = fmt(s.separation, 2);

  // LE CHIFFRE DE GÉNÉRALISATION ÉTAIT CALCULÉ, PUIS PERDU.
  //
  // Le projet construit deux mesures et explique partout que seule la seconde
  // vaut quelque chose : la non-régression des huit contrôles face à des
  // pièges conçus contre eux, et la généralisation face à des mutations qui
  // n'en visent aucun. Ce panneau n'affichait que la première. Le lecteur
  // repartait avec le taux flatteur, et l'aveu restait dans le code.
  $("benchMeta").innerHTML = `
    <span data-key="true">
      <strong data-alert="${(aveugle.flagged_rate ?? 1) < 0.5}">${
        aveugle.flagged_rate === undefined ? "—" : `${fmt(aveugle.flagged_rate * 100, 0)} %`
      }</strong>fautes d'un genre non anticipé
    </span>
    <span><strong>${fmt((s.trap_detection_rate ?? 0) * 100, 0)} %</strong>pièges conçus (non-régression)</span>
    <span><strong>${fmt(s.clean_score_mean, 2)}</strong>note des cas sains</span>
    <span><strong>${fmt((s.false_positive_rate ?? 0) * 100, 0)} %</strong>faux positifs</span>`;

  const traps = result?.by_trap || [];
  if (!traps.length) return;

  // Le tableau est trié par note croissante : la première ligne est la faute
  // que le contrôleur sanctionne le moins fermement, c'est-à-dire son point
  // faible. Trier par ordre alphabétique, comme auparavant, plaçait douze
  // « 100 % » les uns sous les autres sans rien hiérarchiser.
  const tries = [...traps].sort((a, b) => (a.score_mean ?? 0) - (b.score_mean ?? 0));
  $("bench").innerHTML = `
    <p class="panel-note">Ces pièges sont <b>conçus</b> contre les huit contrôles :
       un taux de détection élevé mesure la non-régression, pas la capacité à
       repérer une faute d'un genre nouveau. La colonne qui informe est la
       <b>note</b> : plus elle est basse, plus la sanction est ferme.</p>
    <div class="tbl"><table>
    <thead><tr><th>Faute injectée</th><th>Cas</th><th>Détection</th><th>Sanction</th><th>Note</th></tr></thead>
    <tbody>${tries.map((t) => `<tr>
      <td>${esc(t.trap)}</td>
      <td class="num">${t.n}</td>
      <td class="num">${fmt(t.detection_rate, 0)} %</td>
      <td class="num">${fmt(t.penalty_rate, 0)} %</td>
      <td class="num" data-alert="${(t.score_mean ?? 0) > 7}">${fmt(t.score_mean, 2)}</td></tr>`).join("")}
    </tbody></table></div>`;
}

function renderFlagRate(kpi) {
  const monthly = kpi?.signalement_mensuel || [];
  const figure = (kpi?.figures || []).find((f) => f.label.includes("signalement"));
  const target = kpi?.calibration?.contamination_visee_pct ?? 2;

  if (figure) {
    const chip = $("flagChip");
    chip.textContent = `${fmt(figure.value, 1)} % · cible ${fmt(target, 1)} %`;
    chip.dataset.tone = figure.value > target * 4 ? "fault"
      : figure.value > target * 2 ? "warn" : "ok";
  }
  if (!monthly.length) {
    $("flagBars").innerHTML = '<p class="void">Aucune heure de marche signalée.</p>';
    return;
  }

  // LES HAUTEURS SONT CALCULÉES EN PIXELS, PAS EN POURCENTAGE.
  //
  // Deux tentatives en pourcentage ont échoué : la hauteur d'un enfant se
  // résout contre celle de son bloc conteneur, et dans une grille CSS cette
  // hauteur reste indéfinie tant qu'elle n'est pas explicitement posée. Le
  // navigateur ramenait donc chaque barre à la hauteur de son contenu, c'est-
  // à-dire zéro, et le panneau affichait un rectangle noir avec les mois
  // écrasés en bas.
  //
  // La piste a une hauteur connue et fixe. On calcule directement des pixels :
  // il n'y a plus rien à résoudre, donc plus rien qui puisse échouer.
  const H = 158;
  const peak = Math.max(...monthly.map((m) => m.part_signalee_pct), target * 2);
  // 15 % de marge au-dessus du plus haut mois : une barre qui touche le bord
  // ne se lit plus comme une valeur.
  const max = peak * 1.15 || 1;
  const px = (pct) => Math.round((pct / max) * H);
  const moisCourt = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "2-digit" });

  const barres = monthly.map((m) => {
    const pct = m.part_signalee_pct;
    const tone = pct > target * 8 ? "fault" : pct > target * 3 ? "warn" : "ok";
    const label = moisCourt.format(new Date(m.periode));
    const h = Math.max(3, px(pct));
    return {
      label,
      html: `<div class="bar" data-tone="${tone}" tabindex="0"
        title="${esc(label)} — ${fmt(pct, 1)} % des ${m.heures_marche} h de marche signalées">
        <i style="height:${h}px"></i>
        <b style="bottom:${h + 5}px">${fmt(pct, pct < 10 ? 1 : 0)}</b></div>`,
    };
  });

  $("flagBars").innerHTML = `
    <div class="bars-track" style="height:${H}px">
      ${barres.map((b) => b.html).join("")}
      <div class="bar-target" style="bottom:${px(target)}px">
        <span>cible ${fmt(target, 0)} %</span>
      </div>
    </div>
    <div class="bars-labels">
      ${barres.map((b) => `<span>${esc(b.label)}</span>`).join("")}
    </div>`;
}

function renderCoverage(payload) {
  const risk = payload?.risque;
  const tags = payload?.tags;
  if (!risk) return;

  const chip = $("coverChip");
  chip.textContent = `${fmt(risk.part_couverte_pct, 1)} % de la criticité`;
  chip.dataset.tone = risk.part_couverte_pct > 75 ? "ok"
    : risk.part_couverte_pct > 45 ? "warn" : "fault";

  // TROIS DEGRES, PAS DEUX.
  // La jauge n'opposait que « couvert » et « aveugle ». Deux modes — corrosion
  // du faisceau, fuite de calandre — sont dans un état intermédiaire : le
  // système observe les conditions qui les favorisent, jamais l'état de la
  // pièce. Les compter comme couverts surévaluait la couverture de 18 points ;
  // les compter comme aveugles effacerait la surveillance réelle qui existe.
  $("coverBox").innerHTML = `
    <div class="cover-gauge">
      <i style="width:${risk.part_couverte_pct}%"></i>
      <i class="cover-partial" style="width:${risk.part_partielle_pct}%;
         left:${risk.part_couverte_pct}%"></i>
      <span>${fmt(risk.criticite_couverte, 0)} / ${fmt(risk.criticite_totale, 0)}</span>
    </div>
    <p class="cover-legend">
      <b>${fmt(risk.part_couverte_pct, 1)} %</b> détecté ·
      <b class="is-partial">${fmt(risk.part_partielle_pct, 1)} %</b> conditions
      surveillées sans mesure d'état
      (${(risk.modes_partiels || []).map((m) => esc(m.element)).join(", ") || "—"}) ·
      le reste relève du plan préventif
    </p>
    <p class="cover-note">${esc(risk.reading)}</p>
    <ul class="cover-list">
      ${risk.modes_aveugles.slice(0, 5).map((m) => `<li>
        <span class="crit" data-band="${m.criticite >= 100 ? "majeure" : m.criticite >= 60 ? "significative" : "mineure"}">${m.criticite}</span>
        <b>${esc(m.element)}</b> — ${esc(m.mode)}
        <small>tâche ${esc((m.taches_preventives || []).join(", ") || "—")}</small>
      </li>`).join("")}
    </ul>
    ${renderTagBasis(tags)}`;
}

/**
 * Base de détermination des tags du périmètre.
 *
 * DEUX DÉFAUTS CORRIGÉS ICI.
 *
 * 1. Le bloc lisait `tags.perimetre_confirme`, champ supprimé du référentiel.
 *    Le poste affichait donc « undefined / 6 tags » en clair à l'écran.
 * 2. Il annonçait des tags « confirmés par OCP ». Aucun ne l'est, et attendre
 *    cette confirmation revenait à ne rien conclure. Le sens des tags est
 *    établi par recoupement d'au moins deux bases indépendantes — nomenclature
 *    ISA-5.1, physique du procédé, comportement des données, cohérence
 *    stœchiométrique, climatologie — et c'est CELA qu'il faut publier : une
 *    détermination contestable point par point, pas une attente.
 */
function renderTagBasis(tags) {
  if (!tags?.detail?.length) return "";
  const surveilles = tags.detail.filter((t) => t.role === "primary" || t.role === "secondary");
  const solides = surveilles.filter((t) => (t.basis || []).includes("process"));
  const bases = Object.entries(tags.par_base || {})
    .sort((a, b) => b[1] - a[1])
    .map(([nom, n]) => `${esc(BASE_LABEL[nom] || nom)} (${n})`)
    .join(" · ");

  return `<p class="cover-note cover-tags" data-ok="${solides.length === surveilles.length}">
    <b>${solides.length} / ${surveilles.length}</b> tags du périmètre reposent sur la
    physique du procédé en plus de la nomenclature. Bases mobilisées : ${bases}.
    Chaque détermination cite sa preuve et reste contestable ligne à ligne.</p>`;
}

/** Noms lisibles des bases de détermination du sens d'un tag. */
const BASE_LABEL = {
  isa_5_1: "nomenclature ISA-5.1",
  process: "physique du procédé",
  data: "comportement des données",
  stoichio: "cohérence stœchiométrique",
  climatology: "climatologie",
};

function renderSensitivity(payload) {
  if (!payload) return;
  const cont = payload.contamination;
  const per = payload.periode_reference;

  const contRows = cont.grid.map((g) => `<tr${g.contamination === cont.valeur_retenue ? ' class="is-on"' : ""}>
      <td class="num">${fmt(g.contamination * 100, 1)} %</td>
      <td class="num">${fmt(g.taux_signalement_pct, 2)} %</td>
      <td class="num">×${fmt(g.ratio_sur_cible, 2)}</td>
      <td class="num">${g.heures_signalees} h</td></tr>`).join("");

  // LA COLONNE QUI COMPTE EST CELLE DE L'ENCRASSEMENT.
  // Le tableau ne publiait que la dérive du résidu d'entrée — une grandeur de
  // contexte — et sa lecture concluait pourtant sur le coefficient d'échange.
  // C'est la part d'heures que le système déclarerait en encrassement qui
  // décide du résultat central du projet ; elle figure donc ici, en dernière
  // colonne, avec sa qualité d'ajustement.
  const perRows = per.grid.map((g) => `<tr${g.fraction_reference === per.valeur_retenue ? ' class="is-on"' : ""}>
      <td class="num">${fmt(g.fraction_reference * 100, 0)} %</td>
      <td class="num">${esc(String(g.fin_reference).slice(0, 10))}</td>
      <td class="num">${fmt(g.r2_ua, 3)}</td>
      <td class="num">${g.min_ua_trend_sigma === null ? "—" : `${fmt(g.min_ua_trend_sigma, 2)} σ`}</td>
      <td class="num" data-alert="${g.part_fouling_pct > 0}">
        <b>${fmt(g.part_fouling_pct, 1)} %</b></td></tr>`).join("");

  $("sensBox").innerHTML = `
    <div class="sens-grid">
      <div>
        <span class="micro">Contamination du détecteur</span>
        <div class="tbl"><table>
          <thead><tr><th>Réglage</th><th>Taux réel</th><th>Écart</th><th>Heures</th></tr></thead>
          <tbody>${contRows}</tbody></table></div>
        <p class="sens-note">${esc(cont.reading)}</p>
      </div>
      <div>
        <span class="micro">Période de référence · effet sur le diagnostic d'encrassement</span>
        <div class="tbl"><table>
          <thead><tr>
            <th>Fenêtre</th><th>Fin</th><th>R² UA</th>
            <th>UA min</th><th>Heures en encrassement</th>
          </tr></thead>
          <tbody>${perRows}</tbody></table></div>
        <p class="sens-note" data-alert="${per.sensible}">${esc(per.reading)}</p>
      </div>
    </div>`;
}

/**
 * Banc d'injection d'encrassement.
 *
 * LA COLONNE PRINCIPALE EST LA PERTE DE UA, PAS UNE AMPLITUDE EN DEGRES.
 * Une version precedente lisait `c.amplitude_degC`, champ supprime lorsque
 * l'injection est passee d'un ajout de degres a une degradation physique du
 * coefficient d'echange. La colonne affichait donc « — » pour chaque ligne,
 * et l'appel envoyait `amplitudes=1,2,3` interpretes ensuite comme des
 * fractions : des scenarios a 100, 200 et 300 % de perte, physiquement
 * impossibles et detectes par construction.
 *
 * Le tableau est trie par severite croissante : on lit d'abord le cas le plus
 * discret, qui est celui qui met la detection en difficulte.
 */
function renderBenchFouling(payload) {
  if (!payload) return;
  const cases = [...payload.cases].sort((a, b) => a.perte_UA_pct - b.perte_UA_pct);
  const rows = cases.map((c) => {
    const utile = c.advancement_at_detection !== null
      && c.advancement_at_detection <= payload.useful_advancement_threshold;
    return `<tr>
      <td class="num"><b>${fmt(c.perte_UA_pct, 0)} %</b></td>
      <td class="num">${c.duration_days} j</td>
      <td>${c.detected ? sevMark(utile ? "WARNING" : "INFO") : sevMark("NORMAL")}</td>
      <td class="num" data-alert="${c.detected && !utile}">${
        c.advancement_at_detection === null ? "—" : `${fmt(c.advancement_at_detection * 100, 0)} %`}</td>
      <td class="num">${c.latency_h === null ? "—" : `${fmt(c.latency_h / 24, 0)} j`}</td>
      <td class="num">${fmt(c.peak_ua_residual_z, 1)} σ</td></tr>`;
  }).join("");

  const plusPetite = payload.smallest_loss_detected_pct;
  $("foulingBench").innerHTML = `
    <div class="bench-heads">
      <div>
        <span class="micro">Avancement médian à la détection</span>
        <strong data-alert="${(payload.median_advancement_at_detection ?? 1) > 0.5}">${
          payload.median_advancement_at_detection === null ? "—"
            : `${fmt(payload.median_advancement_at_detection * 100, 0)} %`}</strong>
      </div>
      <div>
        <span class="micro">Faux positifs témoin</span>
        <strong data-alert="${payload.false_positive_rate > 0.02}">${
          fmt(payload.false_positive_rate * 100, 1)} %</strong>
      </div>
      <div>
        <span class="micro">Plus petite perte vue</span>
        <strong>${plusPetite === null ? "—" : `${fmt(plusPetite, 0)} %`}</strong>
      </div>
    </div>
    <p class="sens-note">${esc(payload.reading)}</p>
    <div class="tbl"><table>
      <thead><tr>
        <th>Perte de UA</th><th>Durée</th><th>Vu</th>
        <th>Avancement</th><th>Délai</th><th>Écart max</th>
      </tr></thead>
      <tbody>${rows}</tbody></table></div>
    <ul class="limits">${payload.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`;
}

/**
 * État du canal e-mail : à qui partent réellement les alertes critiques.
 *
 * Un canal muet est le pire défaut possible pour un système d'astreinte, et il
 * est silencieux par nature. On affiche donc explicitement la cause : relais
 * SMTP absent, ou aucune session ouverte.
 */
function renderMail(status) {
  if (!status) return;
  const chip = $("mailChip");
  chip.textContent = status.enabled ? "Actif" : "Inactif";
  chip.dataset.tone = status.enabled ? "ok" : status.transport_ready ? "warn" : "fault";

  const MODE = {
    smtp: "relais SMTP",
    depot: "dépôt local (aucun relais)",
    inactif: "aucun exutoire",
  };
  const lines = [
    ["Acheminement", MODE[status.mode] || "—"],
    ["Destinataire", status.recipient || "aucun"],
    ["Sessions destinataires", status.active_recipients],
    ["Sévérité minimale", status.minimum_severity],
    ["Anti-répétition", `${status.cooldown_minutes} min`],
    ["Envoyés / déposés", `${status.sent} / ${status.spooled ?? 0}`],
    ["Échoués / retenus", `${status.failed} / ${status.suppressed ?? 0}`],
  ];

  // LE JOURNAL EST LA PREUVE QUE LA CHAINE VIT.
  // Un compteur à zéro ne distingue pas « rien à escalader » de « canal
  // mort ». Le journal, lui, montre chaque message que le poste a décidé
  // d'émettre et ce qu'il en est advenu — y compris quand rien n'est parti.
  const journal = status.journal || [];
  const ETAT = {
    envoye: ["ok", "envoyé"],
    depose: ["warn", "déposé"],
    echec: ["fault", "échec"],
  };

  $("mailBox").innerHTML = `
    ${status.reason ? `<p class="mail-reason">${esc(status.reason)}</p>` : ""}
    <dl class="drawer-facts">
      ${lines.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}
    </dl>
    <p class="sens-note">
      L'adresse saisie à l'ouverture de session devient destinataire des états
      critiques retenus par le contrôleur, et cesse de l'être à la déconnexion.
      ${status.requires_judge_agreement
        ? "Une décision rejetée par le contrôleur ne déclenche aucun envoi ; elle est comptée dans « retenus »."
        : ""}
      ${status.last_error ? `<br><b>Dernière erreur :</b> ${esc(status.last_error)}` : ""}
    </p>
    <h3 class="mail-journal-title">Journal d'escalade</h3>
    ${journal.length ? `<ul class="mail-journal">${journal.map((e) => {
      const [tone, label] = ETAT[e.etat] || ["", e.etat];
      return `<li data-tone="${tone}">
        <span class="mail-when">${esc(String(e.horodatage).replace("T", " ").replace("+00:00", " UTC"))}</span>
        <b>${esc(e.objet)}</b>
        <span class="mail-state">${esc(label)}</span>
        <span class="mail-to">${esc(e.destinataire)}</span>
        ${e.detail ? `<em>${esc(e.detail)}</em>` : ""}
      </li>`;
    }).join("")}</ul>`
    : `<p class="void">Aucune escalade émise depuis le démarrage du poste.
         Sur les quatorze mois disponibles, un seul instant atteint la sévérité
         critique en marche établie : le journal reste vide tant que le rejeu ne
         l'a pas franchi.</p>`}`;

  for (const id of ["mailTest", "mailGov"]) $(id).disabled = !status.enabled;
}

/**
 * Auto-surveillance du contrôleur.
 *
 * Le panneau se contentait de sérialiser le dictionnaire renvoyé par l'API :
 * `n 0,00` puis `status AUCUNE DONNEE`, et deux tiers de colonne vide. Avant
 * le premier rejeu il n'a effectivement rien à mesurer — mais c'est précisément
 * là qu'il doit expliquer ce qu'il surveillera, sans quoi le lecteur passe à
 * côté du seul dispositif du projet qui se retourne contre lui-même.
 */
const AUDIT_LIGNES = [
  ["Décisions jugées", (a) => a.n, ""],
  ["Note moyenne", (a) => fmt(a.score_mean, 2), "/10"],
  ["Dispersion des notes", (a) => fmt(a.score_std, 2), "point"],
  ["Étendue", (a) => `${fmt(a.score_min, 1)} – ${fmt(a.score_max, 1)}`, ""],
  ["Taux de validation", (a) => fmt((a.agreement_rate ?? 0) * 100, 0), "%"],
];

function renderAudit(audit) {
  if (!audit || !Object.keys(audit).length) return;
  const box = $("audit");

  if (!audit.n) {
    box.innerHTML = `
      <p class="audit-reading">${esc(audit.reading || "")}</p>
      <ul class="audit-watch">${(audit.controles || [])
        .map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`;
    return;
  }

  const issues = audit.top_issues || [];
  box.innerHTML = `
    ${AUDIT_LIGNES.map(([libelle, lire, unite]) => `
      <div class="audit-line"><span>${esc(libelle)}</span>
        <b>${esc(String(lire(audit)))}${unite ? ` <em>${esc(unite)}</em>` : ""}</b></div>`).join("")}
    <p class="audit-reading" data-tone="${(audit.self_check_warnings || []).length ? "warn" : ""}">${
      esc(audit.reading || "")}</p>
    ${(audit.self_check_warnings || []).map((w) => `
      <p class="audit-reading" data-tone="warn">${esc(w)}</p>`).join("")}
    ${issues.length ? `<div class="audit-issues">
      <span class="micro">Réserves les plus fréquentes</span>
      <ul>${issues.map(([code, n]) => `<li>
        <b>${esc(RESERVE_LABEL[code]?.titre || code)}</b><span>${n}</span></li>`).join("")}</ul>
    </div>` : ""}`;
}

/* ═══ Demarrage ═══════════════════════════════════════════════════════════ */

async function start() {
  renderChecks();
  tickClock();
  setInterval(tickClock, 20000);

  const [equipment, topology, health, episodes, governance, sensors] = await Promise.all([
    api("/api/equipment"), api("/api/topology"), api("/api/health"),
    api("/api/episodes?limit=200"), api("/api/governance"), api("/api/sensor-health"),
  ]);

  S.equipment = equipment;
  S.topology = topology;
  S.governance = { ...governance, health };
  S.sensors = sensors;

  // Le jumeau est construit APRÈS la fiche équipement : sa plaque signalétique
  // porte le constructeur, le code appareil et la taille réels plutôt que des
  // valeurs de repli.
  initTwin(equipment?.equipment || equipment);
  // Les libellés de pièces viennent du référentiel, pas du code de l'interface :
  // un repère de défaut doit nommer la pièce comme la nomme le dossier machine.
  if (S.twin) {
    S.twin.componentLabels = Object.fromEntries(
      (topology.components || []).map((c) => [c.code, c.label || c.code]),
    );
  }
  S.twin?.setSensors(topology.sensors);
  renderPlan(equipment.plan_maintenance);
  renderAmdec();
  renderEpisodes(episodes);
  renderSensorTable(sensors);
  renderGovernance(governance);
  renderFrieze(null, health);
  slideTab();

  // Les elements lents ne bloquent pas l'affichage du poste.
  api("/api/kpi").then((k) => { renderKpi(k); renderFlagRate(k); }).catch(() => {});
  api("/api/model/validation").then(renderValidation).catch(() => {});
  api("/api/judge/evaluation").then(renderBench).catch(() => { $("benchScore").textContent = "—"; });
  api("/api/judge/audit").then(renderAudit).catch(() => {});
  api("/api/coverage").then(renderCoverage).catch(() => {});
  api("/api/notifications/status").then(renderMail).catch(() => {});
  api("/api/sensitivity").then(renderSensitivity).catch(() => {
    $("sensBox").innerHTML = '<p class="void">Analyse indisponible.</p>';
  });
  api("/api/detection/fouling-bench?severities=0.05,0.10,0.20,0.30&duration_days=60")
    .then(renderBenchFouling)
    .catch(() => { $("foulingBench").innerHTML = '<p class="void">Banc indisponible.</p>'; });

  await loadSeries(true);
  await pump();
  S.timer = setInterval(pump, TICK);
}

/* ── Ecouteurs ───────────────────────────────────────────────────────────── */

function wire() {
  $("loginForm").addEventListener("submit", login);
  $("logout").addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    location.reload();
  });

  const onglets = $$(".view-tab");
  onglets.forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));

  // NAVIGATION AU CLAVIER DU GROUPE D'ONGLETS.
  // Elle devient OBLIGATOIRE dès lors qu'un seul onglet est atteignable par
  // tabulation : sans elle, les vues Intégrité et Contrôle deviendraient
  // inaccessibles au clavier. Flèches pour se déplacer, Origine et Fin pour
  // les extrémités — c'est la convention WAI-ARIA, et c'est ce qu'un
  // utilisateur au clavier essaie en premier.
  const TOUCHES = {
    ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1,
  };
  onglets.forEach((b, position) => {
    b.addEventListener("keydown", (e) => {
      let cible = null;
      if (e.key in TOUCHES) {
        cible = onglets[(position + TOUCHES[e.key] + onglets.length) % onglets.length];
      } else if (e.key === "Home") {
        cible = onglets[0];
      } else if (e.key === "End") {
        cible = onglets[onglets.length - 1];
      }
      if (!cible) return;
      e.preventDefault();
      switchView(cible.dataset.view);
      cible.focus();
    });
  });
  window.addEventListener("resize", slideTab);

  $("play").addEventListener("click", async () => {
    try {
      await api("/api/replay/start", {
        method: "POST",
        body: JSON.stringify({ speed: Number($("speed").value) }),
      });
      toast("Rejeu démarré", "ok");
      pump();
    } catch (err) { toast(err.message, "fault"); }
  });

  $("halt").addEventListener("click", async () => {
    await api("/api/replay/stop", { method: "POST" }).catch(() => {});
    toast("Rejeu arrêté");
    pump();
  });

  // LA VITESSE SE PASSE EN PARAMÈTRE D'URL, PAS EN CORPS JSON.
  //
  // L'endpoint déclare `speed: float = Query(...)` : un paramètre de requête
  // OBLIGATOIRE. Le poste l'envoyait dans le corps, sans query string, et
  // FastAPI répondait 422 — erreur avalée par le `.catch()` muet ci-dessous.
  // Changer la vitesse pendant un rejeu n'avait donc aucun effet, sans que
  // rien ne le dise.
  //
  // `test_api.py` appelait `?speed=500`, c'est-à-dire le contrat réel : le
  // test passait pendant que le poste échouait. Chaque côté était cohérent
  // avec lui-même, et les deux ne se parlaient pas.
  $("speed").addEventListener("change", async () => {
    if (!S.replay?.running) return;
    const vitesse = Number($("speed").value);
    try {
      S.replay = await api(`/api/replay/speed?speed=${encodeURIComponent(vitesse)}`, {
        method: "POST",
      });
    } catch (err) {
      // Un réglage qui échoue doit se voir : le silence laissait croire au
      // technicien que le rejeu avait changé d'allure.
      toast(`Vitesse inchangée — ${err.message}`, "fault");
    }
  });

  $("trendSet").addEventListener("change", drawTrend);
  $("trendSpan").addEventListener("change", () => loadSeries(true).catch(() => {}));

  $("toolCut").addEventListener("click", (e) => {
    const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
    e.currentTarget.setAttribute("aria-pressed", String(on));
    S.twin?.setCutaway(on);
  });
  $("toolReset").addEventListener("click", () => S.twin?.resetView());
  $("toolLabels").addEventListener("click", (e) => {
    const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
    e.currentTarget.setAttribute("aria-pressed", String(on));
    for (const s of S.twin?.sensors.values() || []) s.label.visible = on;
  });

  $("drawerClose").addEventListener("click", () => {
    $("drawer").hidden = true;
    S.openSensor = null;
  });

  $("readouts").addEventListener("click", (e) => {
    const alias = e.target.closest("[data-sensor]")?.dataset.sensor;
    if (alias) { S.twin?.focus(alias); openSensor(alias); }
  });

  $("feed").addEventListener("click", (e) => {
    const idx = e.target.closest("[data-idx]")?.dataset.idx;
    if (idx === undefined) return;
    const event = S.feedEvents?.[Number(idx)];
    if (event) openEvent(event);
  });

  $$(".seg button").forEach((b) => b.addEventListener("click", () => {
    $$(".seg button").forEach((o) => o.classList.toggle("is-on", o === b));
    S.feed = b.dataset.feed;
    pump();
  }));

  $("episodeRows").addEventListener("click", async (e) => {
    const idx = e.target.closest("[data-episode]")?.dataset.episode;
    if (idx === undefined) return;
    const ep = S.episodes[idx];
    try {
      const analysis = await api("/api/analyze", {
        method: "POST", body: JSON.stringify({ timestamp: ep.peak_at }),
      });
      openEvent({
        timestamp: analysis.detection.timestamp,
        severity: analysis.decision.severity,
        process_state: analysis.detection.process_state,
        anomaly_score: analysis.detection.anomaly_score,
        judge_score: analysis.verdict.global_score,
        diagnosis: analysis.decision.diagnosis,
        action: analysis.decision.recommended_action.description,
        findings: analysis.detection.findings,
        measurements: analysis.detection.measurements,
      });
    } catch (err) { toast(err.message, "fault"); }
  });

  $("amdecFilter").addEventListener("input", (e) => renderAmdec(e.target.value));

  $("runBench").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Injection en cours…";
    try {
      renderBench(await api("/api/judge/evaluation?n_cases=12"));
      toast("Banc d'injection relancé", "ok");
    } catch (err) { toast(err.message, "fault"); }
    btn.disabled = false;
    btn.textContent = "Relancer un échantillon";
  });

  $("runFouling").addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Injection…";
    try {
      renderBenchFouling(
        await api("/api/detection/fouling-bench?severities=0.05,0.10,0.15,0.20,0.30&duration_days=60"),
      );
      toast("Banc d'injection rejoué", "ok");
    } catch (err) { toast(err.message, "fault"); }
    btn.disabled = false;
    btn.textContent = "Rejouer le banc";
  });

  const sendMail = (path, label) => async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await api(path, { method: "POST" });
      toast(`${label} placé dans la file d'envoi`, "ok");
      renderMail(await api("/api/notifications/status"));
    } catch (err) { toast(err.message, "fault"); }
    btn.disabled = false;
  };
  $("mailTest").addEventListener("click", sendMail("/api/notifications/test", "E-mail de test"));
  $("mailGov").addEventListener("click",
    sendMail("/api/notifications/governance", "Synthèse de gouvernance"));

  $("modalClose").addEventListener("click", () => $("modal").close());
}

wire();
boot();

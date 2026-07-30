/**
 * Le poste dit-il quelque chose quand le service ne repond pas ?
 *
 * POURQUOI CE BANC EXISTE
 * ----------------------------------------------------------------------------
 * `frontend_smoke.mjs` verifie le poste quand tout va bien : chaque appel
 * repond, chaque panneau se remplit. Il ne pouvait donc pas voir le defaut le
 * plus visible du demarrage — `boot()` posait l'indicateur de lien sur
 * « Service injoignable » puis abandonnait, en laissant `data-boot="pending"`.
 * Dans cet etat la feuille de style met la coque a `opacity: 0` et le panneau
 * d'identification reste `hidden` : l'ecran etait ENTIEREMENT BLANC, sans un
 * message, sans un logo, sans une erreur.
 *
 * Ce n'est pas un cas de bord. Le service charge l'historique complet et
 * entraine le modele au demarrage : toute ouverture du poste pendant cette
 * fenetre — la premiere impression, en soutenance comme en salle — tombait sur
 * une page vide.
 *
 * Ce banc simule un service injoignable et exige que le poste l'annonce.
 *
 * Usage :
 *   node scripts/boot_smoke.mjs
 *
 * Author: Mounir Sanbouli — Stage OCP, Programme Bionic
 */

import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { JSDOM } from "jsdom";

const ROOT = resolve(new URL("..", import.meta.url).pathname);
const html = readFileSync(join(ROOT, "api", "dashboard.html"), "utf8");
const css = readFileSync(join(ROOT, "api", "static", "app.css"), "utf8");

const dom = new JSDOM(html, { url: "http://127.0.0.1:8000/", pretendToBeVisual: true });
const { window } = dom;

Object.assign(globalThis, {
  window,
  document: window.document,
  HTMLElement: window.HTMLElement,
  Node: window.Node,
  CustomEvent: window.CustomEvent,
  requestAnimationFrame: () => 0,
  devicePixelRatio: 1,
  AbortController,
});
globalThis.matchMedia = window.matchMedia = () => ({ matches: false, addEventListener() {} });
globalThis.Chart = window.Chart = class { constructor() {} update() {} destroy() {} };

// Le service ne repond pas : c'est tout le propos du banc.
let tentatives = 0;
globalThis.fetch = async () => { tentatives += 1; throw new Error("connexion refusee"); };

await import(`file://${join(ROOT, "api", "static", "app.js")}`);
await new Promise((r) => setTimeout(r, 500));

const doc = window.document;
const plaque = doc.getElementById("bootWait");
const texte = (plaque?.textContent || "").replace(/\s+/g, " ").trim();

const source = readFileSync(join(ROOT, "api", "static", "app.js"), "utf8");

/* La coque est-elle invisible dans l'etat courant ?
   On collecte les selecteurs de toute regle mettant `.shell` a `opacity: 0`,
   plutot que de chercher une ligne litterale : la regle est ecrite sur
   plusieurs selecteurs, et une recherche de chaine exacte ne l'aurait jamais
   trouvee — le controle aurait passe quoi qu'il arrive. */
const etat = doc.body.dataset.boot;
const coqueInvisible = [...css.matchAll(/([^{}]+)\{[^}]*opacity:\s*0\s*[;}]/g)]
  .some(([, selecteurs]) =>
    selecteurs.includes(".shell") && selecteurs.includes(`data-boot="${etat}"`));

const checks = [
  ["une tentative de contact a bien eu lieu", tentatives >= 1],

  // Le defaut lui-meme : un etat qui laisse la coque invisible ET aucun
  // substitut affiche est une page blanche, quel que soit le nom de l'etat.
  ["le poste n'est pas une page blanche",
    !(coqueInvisible && (!plaque || plaque.hidden))],

  ["un ecran d'attente est affiche", !!plaque && plaque.hidden === false],
  ["il nomme l'equipement", texte.includes("E7301")],
  ["il explique l'attente", texte.length > 40],
  ["il est annonce aux lecteurs d'ecran",
    plaque?.getAttribute("role") === "status"
    && plaque?.getAttribute("aria-live") === "polite"],
  ["l'indicateur de lien signale la coupure",
    doc.getElementById("linkState")?.dataset.link === "down"],

  // Abandonner apres un seul essai obligerait a recharger la page a la main
  // pendant que le service finit de demarrer. On verifie le CHEMIN D'ECHEC
  // lui-meme, pas la simple presence d'une fonction de reessai ailleurs dans
  // le fichier : c'est la difference entre un controle et un decor.
  ["le chemin d'echec enclenche un reessai",
    /catch\s*\{[^}]*attendreLeService\(/.test(source)],
  ["le reessai est plafonne", /Math\.min\([^)]*essai[^)]*\)/.test(source)],
];

let bad = 0;
for (const [name, ok] of checks) {
  console.log(`  ${ok ? "OK  " : "ECHEC"}  ${name}`);
  if (!ok) bad += 1;
}
console.log(`\n${checks.length - bad}/${checks.length} verifications passees.`);
process.exit(bad ? 1 : 0);

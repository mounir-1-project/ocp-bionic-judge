/**
 * Smoke test navigateur sans dépendance externe.
 *
 * Usage:
 *   msedge --headless=new --remote-debugging-port=9223 --remote-allow-origins=*
 *   node scripts/browser_smoke.mjs http://127.0.0.1:8765 9223
 */

import { writeFileSync } from "node:fs";

const baseUrl = process.argv[2] || "http://127.0.0.1:8000";
const debugPort = process.argv[3] || "9223";
const viewportWidth = Number(process.argv[4] || 430);
const viewportHeight = Number(process.argv[5] || 932);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function findPage() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
      const targets = await fetch(`http://127.0.0.1:${debugPort}/json`).then((response) => response.json());
      const page = targets.find((target) => target.type === "page");
      if (page) return page;
    } catch {
      // Edge démarre encore.
    }
    await sleep(200);
  }
  throw new Error("Aucune cible DevTools disponible");
}

const page = await findPage();
const socket = new WebSocket(page.webSocketDebuggerUrl);
let sequence = 0;
const pending = new Map();
const browserErrors = [];
const failedResources = [];

socket.addEventListener("message", ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
    return;
  }
  if (message.method === "Runtime.exceptionThrown") {
    browserErrors.push(message.params.exceptionDetails.text);
  }
  if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
    browserErrors.push(`${message.params.entry.text} ${message.params.entry.url || ""}`.trim());
  }
  if (message.method === "Network.responseReceived" && message.params.response.status >= 400) {
    failedResources.push(`${message.params.response.status} ${message.params.response.url}`);
  }
});

await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

function command(method, params = {}) {
  sequence += 1;
  socket.send(JSON.stringify({ id: sequence, method, params }));
  return new Promise((resolve, reject) => pending.set(sequence, { resolve, reject }));
}

async function evaluate(expression) {
  const response = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text);
  }
  return response.result.value;
}

await command("Runtime.enable");
await command("Log.enable");
await command("Page.enable");
await command("Network.enable");
await command("Emulation.setDeviceMetricsOverride", {
  width: viewportWidth,
  height: viewportHeight,
  deviceScaleFactor: 1,
  mobile: true,
});
await command("Page.navigate", { url: `${baseUrl}/?browser-smoke=1` });
await sleep(1400);
const loginRequired = await evaluate(`document.querySelector("#loginDialog")?.open === true`);
await evaluate(`(() => {
  document.querySelector("#loginEmail").value = "technicien.e7301@example.test";
  document.querySelector("#loginPassword").value = "E7301-Jury-2026!";
  document.querySelector("#loginForm").requestSubmit();
})()`);
await sleep(9000);

const initial = await evaluate(`(() => ({
  title: document.title,
  service: document.querySelector("#liveState span:last-child")?.textContent,
  charts: document.querySelectorAll(".chart-wrap canvas").length,
  overflow: document.documentElement.scrollWidth > window.innerWidth,
  width: window.innerWidth,
  process: document.querySelector("#processState")?.textContent,
  twin: Boolean(document.querySelector("#equipmentTwin")),
  webglReady: document.querySelector("#equipmentTwin")?.classList.contains("webgl-ready"),
  webgl: Boolean(document.querySelector("#twinCanvas")?.getContext("webgl2")),
  sensors: document.querySelectorAll(".sensor-orb").length,
  maintenanceTasks: document.querySelectorAll(".maintenance-task").length,
  lineageStages: document.querySelectorAll(".lineage-stage").length,
  operator: document.querySelector("#operatorName")?.textContent,
}))()`);

const screenshot = await command("Page.captureScreenshot", {
  format: "png",
  captureBeyondViewport: true,
});
const screenshotName = viewportWidth >= 1000 ? "dashboard-v30-desktop.png" : "dashboard-v30-mobile.png";
writeFileSync(`tmp/${screenshotName}`, Buffer.from(screenshot.data, "base64"));

const trendInteraction = await evaluate(`(() => {
  const metric = document.querySelector("#trendMetric");
  metric.value = "duty";
  metric.dispatchEvent(new Event("change", { bubbles: true }));
  const windowSelect = document.querySelector("#trendWindow");
  windowSelect.value = "168";
  windowSelect.dispatchEvent(new Event("change", { bubbles: true }));
  return document.querySelector("#primaryTrendTitle").textContent;
})()`);
await sleep(1200);

const twinNavigation = await evaluate(`(() => {
  document.querySelector('[data-problem="FAISCEAU_BOUCHAGE"]').click();
  return {
    reliabilityVisible: !document.querySelector('[data-view-panel="reliability"]').hidden,
    filter: document.querySelector("#amdecFilter").value,
  };
})()`);

const sensorInteraction = await evaluate(`(() => {
  const card = document.querySelector('[data-sensor="C_ACID_1100"]');
  card.click();
  return {
    selected: document.querySelector('[data-sensor="C_ACID_1100"]').classList.contains("selected"),
    metric: document.querySelector("#trendMetric").value,
    title: document.querySelector("#primaryTrendTitle").textContent,
  };
})()`);

const views = {};
for (const view of ["reliability", "governance", "business", "overview"]) {
  views[view] = await evaluate(`(() => {
    document.querySelector('[data-view="${view}"]').click();
    const panel = document.querySelector('[data-view-panel="${view}"]');
    return !panel.hidden && panel.classList.contains("active");
  })()`);
}

await evaluate(`document.querySelector("#startReplay").click()`);
await sleep(2200);
const replayStarted = await evaluate(`({
  running: !document.querySelector("#stopReplay").disabled,
  label: document.querySelector("#liveState span:last-child").textContent,
})`);
await evaluate(`document.querySelector("#stopReplay").click()`);
await sleep(800);
const replayStopped = await evaluate(`document.querySelector("#stopReplay").disabled`);

const result = {
  loginRequired,
  initial,
  trendInteraction,
  twinNavigation,
  sensorInteraction,
  views,
  replayStarted,
  replayStopped,
  browserErrors,
  failedResources,
};
console.log(JSON.stringify(result, null, 2));

const passed = (
  initial.title.includes("E7301")
  && loginRequired
  && initial.service
  && initial.charts >= 2
  && !initial.overflow
  && initial.twin
  && initial.webglReady
  && initial.webgl
  && initial.sensors === 12
  && initial.maintenanceTasks === 8
  && initial.lineageStages === 6
  && trendInteraction.includes("Performance thermique")
  && twinNavigation.reliabilityVisible
  && twinNavigation.filter === "faisceau"
  && sensorInteraction.selected
  && sensorInteraction.metric === "sensor:C_ACID_1100"
  && sensorInteraction.title.includes("Titre acide")
  && Object.values(views).every(Boolean)
  && replayStarted.running
  && replayStopped
  && browserErrors.length === 0
  && failedResources.length === 0
);

socket.close();
if (!passed) process.exitCode = 1;

import "./styles.css";
import { TelemetryClient } from "./network/client";
import type { CommandResult, ConnectionState, VisualizationStatus, WorldSnapshot } from "./network/types";
import { EntityStore } from "./scene/entityStore";
import { WorldScene } from "./scene/worldScene";
import { HudPanel } from "./ui/hud";
import { InspectorPanel } from "./ui/inspector";
import { ControlsPanel } from "./ui/controls";
import { DiagnosticsPanel } from "./ui/diagnostics";

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("Missing #app root");
}

const baseUrl = new URLSearchParams(window.location.search).get("server") ?? "http://127.0.0.1:8765";
const store = new EntityStore();

const shell = document.createElement("div");
shell.className = "shell";

const masthead = document.createElement("header");
masthead.className = "masthead";
masthead.innerHTML = `
  <div>
    <div class="eyebrow">bvr_sim / phase 1</div>
    <h1>Real-Time Debug Airspace</h1>
  </div>
  <div class="server-target">Target: <strong>${baseUrl}</strong></div>
`;

const sceneRoot = document.createElement("main");
sceneRoot.className = "scene-root";

const sideRail = document.createElement("aside");
sideRail.className = "side-rail";

const hud = new HudPanel();
const inspector = new InspectorPanel();
const diagnostics = new DiagnosticsPanel();

let connectionState: ConnectionState = "connecting";
let diagnosticsStatus: VisualizationStatus | null = null;
let activeScene: WorldScene | null = null;
let lastCommandResult: CommandResult | null = null;
let snapshotRateHz = 0;
let lastSnapshotAt = 0;

const renderPanels = (): void => {
  hud.render({
    snapshot: store.getSnapshot(),
    status: diagnosticsStatus,
    connection: connectionState,
    selectedObject: store.getSelectedObject(),
    snapshotRateHz
  });
  inspector.render(store.getSelectedObject());
  diagnostics.render(diagnosticsStatus);
  diagnostics.renderCommandResult(lastCommandResult);
};

const client = new TelemetryClient({
  baseUrl,
  onSnapshot: (snapshot: WorldSnapshot) => {
    const now = performance.now();
    if (lastSnapshotAt > 0) {
      const periodMs = now - lastSnapshotAt;
      if (periodMs > 0) {
        snapshotRateHz = 1000 / periodMs;
      }
    }
    lastSnapshotAt = now;
    store.setSnapshot(snapshot);
    renderPanels();
  },
  onDiagnostics: (status: VisualizationStatus) => {
    diagnosticsStatus = status;
    renderPanels();
  },
  onConnection: (state) => {
    connectionState = state;
    renderPanels();
  },
  onCommandResult: (result) => {
    lastCommandResult = result;
    renderPanels();
  }
});

const controls = new ControlsPanel({
  onPause: () => client.sendCommand({ kind: "pause" }),
  onResume: () => client.sendCommand({ kind: "resume" }),
  onStep: () => client.sendCommand({ kind: "step", payload: { steps: 1 } }),
  onFilter: (filter) => client.sendCommand({ kind: "set_subscription_filter", payload: filter })
});

sideRail.append(hud.element, controls.element, diagnostics.element, inspector.element);
shell.append(masthead, sceneRoot, sideRail);
app.append(shell);

const worldScene = new WorldScene(sceneRoot, store, {
  onSelect: (uid) => {
    store.setSelectedUid(uid);
    inspector.render(store.getSelectedObject());
    activeScene?.setFocus(uid);
    if (uid) {
      client.sendCommand({ kind: "set_focus_uid", target_uid: uid });
    }
  }
});
activeScene = worldScene;

store.subscribe(() => {
  renderPanels();
});

renderPanels();

client.fetchHealth().catch((error) => {
  console.error("Health request failed", error);
});
client.connect().catch((error) => {
  console.error("Telemetry connect failed", error);
});

window.addEventListener("beforeunload", () => {
  client.disconnect();
  worldScene.destroy();
});

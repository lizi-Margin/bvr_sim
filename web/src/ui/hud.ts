import type { ConnectionState, TelemetryObject, VisualizationStatus, WorldSnapshot } from "../network/types";

type HudRenderModel = {
  snapshot: WorldSnapshot | null;
  status: VisualizationStatus | null;
  connection: ConnectionState;
  selectedObject: TelemetryObject | null;
  snapshotRateHz: number;
};

export class HudPanel {
  readonly element: HTMLElement;
  private headline: HTMLElement;
  private detail: HTMLElement;

  constructor() {
    this.element = document.createElement("section");
    this.element.className = "panel hud-panel";

    this.headline = document.createElement("div");
    this.headline.className = "panel-kicker";
    this.headline.textContent = "Live Telemetry";

    this.detail = document.createElement("div");
    this.detail.className = "hud-grid";

    this.element.append(this.headline, this.detail);
  }

  render(model: HudRenderModel): void {
    const { snapshot, status, connection, selectedObject, snapshotRateHz } = model;
    const count = snapshot?.objects.length ?? 0;
    const simTime = snapshot?.sim_time ?? 0;
    const dt = snapshot?.dt ?? 0;
    const selectedRows = selectedObject
      ? `
        <div><span>Selected Speed</span><strong>${magnitude(selectedObject.velocity).toFixed(1)}</strong></div>
        <div><span>Selected Alt</span><strong>${selectedObject.position[2].toFixed(1)}</strong></div>
        <div><span>Selected Hdg</span><strong>${toHeading(selectedObject.orientation)}</strong></div>
      `
      : "";
    this.detail.innerHTML = `
      <div><span>Conn</span><strong>${connection}</strong></div>
      <div><span>Objects</span><strong>${count}</strong></div>
      <div><span>Sim Time</span><strong>${simTime.toFixed(2)}</strong></div>
      <div><span>dt</span><strong>${dt.toFixed(4)}</strong></div>
      <div><span>Rate</span><strong>${snapshotRateHz.toFixed(1)} Hz</strong></div>
      <div><span>Sim State</span><strong>${snapshot?.paused ? "paused" : snapshot?.running ? "running" : "idle"}</strong></div>
      <div><span>Port</span><strong>${status?.port ?? "-"}</strong></div>
      <div><span>Clients</span><strong>${status?.client_count ?? "-"}</strong></div>
      ${selectedRows}
    `;
  }
}

function magnitude(v: [number, number, number]): number {
  return Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

function toHeading(orientation?: [number, number, number]): string {
  if (!orientation) {
    return "-";
  }
  const heading = ((orientation[2] * 180) / Math.PI + 360) % 360;
  return `${heading.toFixed(0)}°`;
}

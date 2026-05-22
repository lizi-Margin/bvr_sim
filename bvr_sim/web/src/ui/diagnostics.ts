import type { CommandResult, TelemetryObject, VisualizationStatus, WorldSnapshot } from "../network/types";

type DiagnosticsRenderModel = {
  status: VisualizationStatus | null;
  snapshot: WorldSnapshot | null;
  selectedObject: TelemetryObject | null;
  snapshotRateHz: number;
};

export class DiagnosticsPanel {
  readonly element: HTMLElement;
  private content: HTMLTextAreaElement;
  private commandLine: HTMLElement;
  private lastJsonRenderAt = 0;
  private lastSignature = "";

  constructor() {
    this.element = document.createElement("section");
    this.element.className = "panel diagnostics-panel";

    const title = document.createElement("div");
    title.className = "panel-kicker";
    title.textContent = "Diagnostics";

    this.content = document.createElement("textarea");
    this.content.className = "code-panel";
    this.content.readOnly = true;
    this.content.spellcheck = false;

    this.commandLine = document.createElement("div");
    this.commandLine.className = "command-line";
    this.commandLine.textContent = "Last command: idle";

    this.element.append(title, this.commandLine, this.content);
  }

  render(model: DiagnosticsRenderModel, force = false): void {
    const { status, snapshot, selectedObject, snapshotRateHz } = model;
    const objects = snapshot?.objects ?? [];
    const signature = [
      snapshot?.sim_time ?? "none",
      objects.length,
      selectedObject?.uid ?? "",
      status?.client_count ?? "",
      status?.telemetry?.last_command_result
        ? JSON.stringify(status.telemetry.last_command_result)
        : ""
    ].join("|");
    const now = performance.now();
    if (!force && signature === this.lastSignature && now - this.lastJsonRenderAt < 1000) {
      return;
    }
    if (!force && now - this.lastJsonRenderAt < 500) {
      return;
    }
    this.lastJsonRenderAt = now;
    this.lastSignature = signature;

    const view = {
      connection: {
        server_running: status?.server_running ?? false,
        telemetry_running: status?.telemetry_running ?? false,
        port: status?.port ?? null,
        client_count: status?.client_count ?? null,
        snapshot_rate_hz: Number(snapshotRateHz.toFixed(2))
      },
      sim: {
        sim_time: snapshot?.sim_time ?? null,
        dt: snapshot?.dt ?? null,
        running: snapshot?.running ?? null,
        paused: snapshot?.paused ?? null,
        object_count: objects.length
      },
      selected_uid: selectedObject?.uid ?? null,
      diagnostics: status ?? { status: "unavailable" },
      objects: objects.map((object) => ({
        uid: object.uid,
        type: object.type,
        team: object.team,
        alive: object.alive,
        position: object.position,
        velocity: object.velocity,
        orientation: object.orientation ?? null,
        debug_register: object.debug_register ?? null
      }))
    };
    this.content.value = JSON.stringify(view, null, 2);
  }

  renderCommandResult(result: CommandResult | null): void {
    if (!result) {
      this.commandLine.textContent = "Last command: idle";
      return;
    }
    this.commandLine.textContent = `Last command: ${result.status} / ${result.message}`;
  }
}

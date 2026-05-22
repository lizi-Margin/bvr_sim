import type { TelemetryObject } from "../network/types";

export class InspectorPanel {
  readonly element: HTMLElement;
  private content: HTMLElement;

  constructor() {
    this.element = document.createElement("section");
    this.element.className = "panel inspector-panel";

    const title = document.createElement("div");
    title.className = "panel-kicker";
    title.textContent = "Object Inspector";

    this.content = document.createElement("pre");
    this.content.className = "code-panel";
    this.content.textContent = "Select an object in the scene.";

    this.element.append(title, this.content);
  }

  render(object: TelemetryObject | null): void {
    if (!object) {
      this.content.textContent = "Select an object in the scene.";
      return;
    }
    const speed = Math.sqrt(
      object.velocity[0] * object.velocity[0]
      + object.velocity[1] * object.velocity[1]
      + object.velocity[2] * object.velocity[2]
    );
    const view = {
      uid: object.uid,
      type: object.type,
      team: object.team,
      alive: object.alive,
      altitude: object.position[2],
      speed,
      position: object.position,
      velocity: object.velocity,
      orientation: object.orientation ?? null,
      telemetry_debug: extractTelemetryDebug(object.debug_register),
      debug_register: object.debug_register ?? null
    };
    this.content.textContent = JSON.stringify(view, null, 2);
  }
}

function extractTelemetryDebug(registerValue: TelemetryObject["debug_register"]): unknown {
  if (!registerValue || typeof registerValue !== "object") {
    return null;
  }
  const telemetryValue = registerValue["telemetry"];
  if (!telemetryValue || typeof telemetryValue !== "object") {
    return null;
  }
  const webValue = (telemetryValue as Record<string, unknown>)["web"];
  return webValue ?? null;
}

import type { CommandResult, VisualizationStatus } from "../network/types";

export class DiagnosticsPanel {
  readonly element: HTMLElement;
  private content: HTMLElement;
  private commandLine: HTMLElement;

  constructor() {
    this.element = document.createElement("section");
    this.element.className = "panel diagnostics-panel";

    const title = document.createElement("div");
    title.className = "panel-kicker";
    title.textContent = "Diagnostics";

    this.content = document.createElement("pre");
    this.content.className = "code-panel";

    this.commandLine = document.createElement("div");
    this.commandLine.className = "command-line";
    this.commandLine.textContent = "Last command: idle";

    this.element.append(title, this.commandLine, this.content);
  }

  render(status: VisualizationStatus | null): void {
    this.content.textContent = JSON.stringify(status ?? { status: "unavailable" }, null, 2);
  }

  renderCommandResult(result: CommandResult | null): void {
    if (!result) {
      this.commandLine.textContent = "Last command: idle";
      return;
    }
    this.commandLine.textContent = `Last command: ${result.status} / ${result.message}`;
  }
}

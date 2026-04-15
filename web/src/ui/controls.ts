import type { SubscriptionFilter } from "../network/types";

type ControlHandlers = {
  onPause: () => void;
  onResume: () => void;
  onStep: () => void;
  onFilter: (filter: SubscriptionFilter) => void;
  onTagSelected: () => void;
  onClearSelectedTag: () => void;
  onWriteSelectedRegister: (registerKey: string, rawValue: string) => void;
};

export class ControlsPanel {
  readonly element: HTMLElement;
  private readonly filterSelect: HTMLSelectElement;
  private readonly registerKeyInput: HTMLInputElement;
  private readonly registerValueInput: HTMLInputElement;

  constructor(handlers: ControlHandlers) {
    this.element = document.createElement("section");
    this.element.className = "panel controls-panel";

    const title = document.createElement("div");
    title.className = "panel-kicker";
    title.textContent = "Debug Controls";

    const row = document.createElement("div");
    row.className = "controls-row";

    row.append(
      this.makeButton("Pause", handlers.onPause),
      this.makeButton("Resume", handlers.onResume),
      this.makeButton("Step +1", handlers.onStep)
    );

    const objectRow = document.createElement("div");
    objectRow.className = "controls-row";
    objectRow.append(
      this.makeButton("Tag Selected", handlers.onTagSelected),
      this.makeButton("Clear Tag", handlers.onClearSelectedTag)
    );

    const objectDebugWrap = document.createElement("div");
    objectDebugWrap.className = "object-debug-wrap";

    const objectDebugTitle = document.createElement("div");
    objectDebugTitle.className = "panel-kicker";
    objectDebugTitle.textContent = "Object Register Write";

    this.registerKeyInput = document.createElement("input");
    this.registerKeyInput.type = "text";
    this.registerKeyInput.value = "telemetry.web.note";
    this.registerKeyInput.placeholder = "register key";

    this.registerValueInput = document.createElement("input");
    this.registerValueInput.type = "text";
    this.registerValueInput.value = "\"debug\"";
    this.registerValueInput.placeholder = "JSON value";

    const applyButton = this.makeButton("Write To Selected", () => {
      handlers.onWriteSelectedRegister(this.registerKeyInput.value, this.registerValueInput.value);
    });
    applyButton.classList.add("wide-button");

    objectDebugWrap.append(
      objectDebugTitle,
      this.registerKeyInput,
      this.registerValueInput,
      applyButton
    );

    const filterWrap = document.createElement("label");
    filterWrap.className = "filter-wrap";
    filterWrap.innerHTML = `<span class="panel-kicker">Render Filter</span>`;

    this.filterSelect = document.createElement("select");
    this.filterSelect.innerHTML = `
      <option value="all">All Objects</option>
      <option value="aircraft">Aircraft</option>
      <option value="missile">Missiles</option>
      <option value="ground">Ground / Other</option>
      <option value="blue">Blue Team</option>
      <option value="red">Red Team</option>
    `;
    this.filterSelect.addEventListener("change", () => {
      handlers.onFilter(parseFilter(this.filterSelect.value));
    });

    filterWrap.append(this.filterSelect);

    this.element.append(title, row, objectRow, objectDebugWrap, filterWrap);
  }

  private makeButton(label: string, onClick: () => void): HTMLButtonElement {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }
}

function parseFilter(value: string): SubscriptionFilter {
  if (value === "aircraft") {
    return { type: "Aircraft" };
  }
  if (value === "missile") {
    return { type: "Missile" };
  }
  if (value === "ground") {
    return { type: "Ground" };
  }
  if (value === "blue") {
    return { team: "Blue" };
  }
  if (value === "red") {
    return { team: "Red" };
  }
  return {};
}

import type { CommandPayload, CommandResult, ConnectionState, VisualizationStatus, WorldSnapshot } from "./types";

type ClientOptions = {
  baseUrl: string;
  onSnapshot: (snapshot: WorldSnapshot) => void;
  onDiagnostics: (status: VisualizationStatus) => void;
  onConnection: (state: ConnectionState) => void;
  onCommandResult: (result: CommandResult) => void;
};

export class TelemetryClient {
  private readonly options: ClientOptions;
  private socket: WebSocket | null = null;
  private reconnectTimer = 0;
  private closedByUser = false;

  constructor(options: ClientOptions) {
    this.options = options;
  }

  async connect(): Promise<void> {
    this.closedByUser = false;
    this.options.onConnection("connecting");
    const diagnostics = await this.fetchDiagnostics();
    this.options.onDiagnostics(diagnostics);

    const url = new URL(this.options.baseUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/ws";

    this.socket = new WebSocket(url.toString());
    this.socket.addEventListener("open", () => {
      this.options.onConnection("open");
    });
    this.socket.addEventListener("close", () => {
      this.options.onConnection("closed");
      if (!this.closedByUser) {
        this.scheduleReconnect();
      }
    });
    this.socket.addEventListener("error", () => {
      this.options.onConnection("error");
    });
    this.socket.addEventListener("message", (event) => {
      const data = JSON.parse(String(event.data)) as Record<string, unknown>;
      if ("objects" in data) {
        this.options.onSnapshot(data as unknown as WorldSnapshot);
        return;
      }
      if ("status" in data && "message" in data) {
        this.options.onCommandResult(data as unknown as CommandResult);
      }
      this.fetchDiagnostics().then((status) => {
        this.options.onDiagnostics(status);
      }).catch(() => {
        this.options.onConnection("error");
      });
    });
  }

  disconnect(): void {
    this.closedByUser = true;
    clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }

  async fetchHealth(): Promise<Record<string, unknown>> {
    const response = await fetch(`${this.options.baseUrl}/health`);
    return response.json() as Promise<Record<string, unknown>>;
  }

  async fetchDiagnostics(): Promise<VisualizationStatus> {
    const response = await fetch(`${this.options.baseUrl}/diagnostics`);
    return response.json() as Promise<VisualizationStatus>;
  }

  sendCommand(command: CommandPayload): void {
    this.socket?.send(JSON.stringify(command));
  }

  private scheduleReconnect(): void {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = window.setTimeout(() => {
      this.connect().catch(() => {
        this.options.onConnection("error");
      });
    }, 1500);
  }
}

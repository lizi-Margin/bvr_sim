export type TelemetryObject = {
  uid: string;
  type: string;
  team: string;
  alive: boolean;
  position: [number, number, number];
  velocity: [number, number, number];
  orientation?: [number, number, number];
  debug_register?: Record<string, unknown>;
};

export type WorldSnapshot = {
  sim_time: number;
  dt: number;
  running?: boolean;
  paused?: boolean;
  objects: TelemetryObject[];
};

export type VisualizationStatus = {
  server_running: boolean;
  telemetry_running: boolean;
  port: number;
  base_url: string;
  client_count: number;
  telemetry: Record<string, unknown>;
};

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export type CommandResult = {
  status: string;
  message: string;
};

export type SubscriptionFilter = {
  type?: string;
  team?: string;
};

export type CommandPayload = {
  kind: string;
  target_uid?: string;
  payload?: unknown;
};

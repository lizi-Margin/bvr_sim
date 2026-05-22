import type { TelemetryObject, WorldSnapshot } from "../network/types";

type StoreListener = (snapshot: WorldSnapshot | null) => void;

export class EntityStore {
  private snapshot: WorldSnapshot | null = null;
  private listeners = new Set<StoreListener>();
  private selectedUid: string | null = null;

  setSnapshot(snapshot: WorldSnapshot): void {
    this.snapshot = snapshot;
    if (this.selectedUid && !snapshot.objects.some((obj) => obj.uid === this.selectedUid)) {
      this.selectedUid = null;
    }
    this.emit();
  }

  getSnapshot(): WorldSnapshot | null {
    return this.snapshot;
  }

  getObjects(): TelemetryObject[] {
    return this.snapshot?.objects ?? [];
  }

  setSelectedUid(uid: string | null): void {
    this.selectedUid = uid;
    this.emit();
  }

  getSelectedObject(): TelemetryObject | null {
    if (!this.selectedUid || !this.snapshot) {
      return null;
    }
    return this.snapshot.objects.find((obj) => obj.uid === this.selectedUid) ?? null;
  }

  getSelectedUid(): string | null {
    return this.selectedUid;
  }

  subscribe(listener: StoreListener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private emit(): void {
    for (const listener of this.listeners) {
      listener(this.snapshot);
    }
  }
}

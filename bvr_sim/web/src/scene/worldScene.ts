import * as THREE from "three";
import { EntityStore } from "./entityStore";
import type { TelemetryObject, WorldSnapshot } from "../network/types";

type SceneHooks = {
  onSelect: (uid: string | null) => void;
};

export class WorldScene {
  private renderer: any;
  private scene: any;
  private camera: any;
  private store: EntityStore;
  private hooks: SceneHooks;
  private frameHandle = 0;
  private entities = new Map<string, any>();
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private root: HTMLElement;
  private atmosphere: any;
  private focusUid: string | null = null;
  private selectionRing: any;
  private taggedRing: any;
  private lastAutoFrameAt = 0;
  private autoFrameEnabled = true;

  constructor(root: HTMLElement, store: EntityStore, hooks: SceneHooks) {
    this.root = root;
    this.store = store;
    this.hooks = hooks;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(root.clientWidth, root.clientHeight);
    this.root.append(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x081019, 0.0007);

    this.camera = new THREE.PerspectiveCamera(48, 1, 1, 300000);
    this.camera.position.set(9000, 12000, 9000);
    this.camera.lookAt(0, 0, 0);

    const ambient = new THREE.AmbientLight(0xe8f2ff, 1.7);
    const sun = new THREE.DirectionalLight(0xfff2c7, 1.6);
    sun.position.set(3000, 5000, 2500);
    this.scene.add(ambient, sun);

    const grid = new THREE.GridHelper(70000, 40, 0x6aa0a9, 0x1e3740);
    grid.position.y = -2;
    this.scene.add(grid);

    const plane = new THREE.Mesh(
      new THREE.CircleGeometry(35000, 64),
      new THREE.MeshStandardMaterial({
        color: 0x0f2027,
        roughness: 0.95,
        metalness: 0.05
      })
    );
    plane.rotation.x = -Math.PI / 2;
    this.scene.add(plane);

    this.atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(65000, 48, 24),
      new THREE.MeshBasicMaterial({
        color: 0x11384a,
        transparent: true,
        opacity: 0.08,
        side: THREE.BackSide
      })
    );
    this.scene.add(this.atmosphere);

    this.selectionRing = new THREE.Mesh(
      new THREE.TorusGeometry(220, 14, 12, 48),
      new THREE.MeshBasicMaterial({
        color: 0xd3f6b5,
        transparent: true,
        opacity: 0.9
      })
    );
    this.selectionRing.rotation.x = Math.PI / 2;
    this.selectionRing.visible = false;
    this.scene.add(this.selectionRing);

    this.taggedRing = new THREE.Mesh(
      new THREE.TorusGeometry(300, 10, 10, 48),
      new THREE.MeshBasicMaterial({
        color: 0x67d7ff,
        transparent: true,
        opacity: 0.45
      })
    );
    this.taggedRing.rotation.x = Math.PI / 2;
    this.taggedRing.visible = false;
    this.scene.add(this.taggedRing);

    window.addEventListener("resize", this.handleResize);
    this.renderer.domElement.addEventListener("click", this.handleClick);

    this.store.subscribe((snapshot) => {
      this.syncSnapshot(snapshot);
    });

    this.animate();
    this.handleResize();
  }

  destroy(): void {
    window.removeEventListener("resize", this.handleResize);
    this.renderer.domElement.removeEventListener("click", this.handleClick);
    cancelAnimationFrame(this.frameHandle);
    this.renderer.dispose();
  }

  setFocus(uid: string | null): void {
    this.focusUid = uid;
  }

  private syncSnapshot(snapshot: WorldSnapshot | null): void {
    const seen = new Set<string>();

    for (const entity of snapshot?.objects ?? []) {
      seen.add(entity.uid);
      let object = this.entities.get(entity.uid);
      if (!object) {
        object = this.createEntityMesh(entity);
        object.userData.uid = entity.uid;
        this.entities.set(entity.uid, object);
        this.scene.add(object);
      }
      object.position.set(entity.position[0], entity.position[2], entity.position[1]);
      const orientation = entity.orientation ?? [0, 0, 0];
      object.rotation.set(orientation[1], -orientation[2], orientation[0]);
      const material = object.userData.material as any;
      const tagged = isTelemetryTagged(entity);
      object.userData.tagged = tagged;
      material.emissiveIntensity = entity.alive ? 0.25 : 0.02;
      material.opacity = entity.alive ? 1 : 0.25;
      material.transparent = !entity.alive;
      material.color.setHex(tagged ? 0xd3f6b5 : object.userData.baseColor);
      material.emissive.setHex(tagged ? 0xd3f6b5 : object.userData.baseColor);
      object.scale.setScalar(tagged ? 1.18 : 1);
      object.visible = true;
    }

    for (const [uid, object] of this.entities.entries()) {
      if (seen.has(uid)) {
        continue;
      }
      this.scene.remove(object);
      this.entities.delete(uid);
    }

    if (this.autoFrameEnabled && !this.focusUid) {
      this.frameObjects(snapshot?.objects ?? []);
    }

    const selected = this.store.getSelectedUid() ? this.entities.get(this.store.getSelectedUid() as string) : null;
    if (selected) {
      this.selectionRing.visible = true;
      this.selectionRing.position.copy(selected.position);
      this.selectionRing.position.y += 60;
    } else {
      this.selectionRing.visible = false;
    }

    const taggedObject = [...this.entities.values()].find((object) => object.userData.tagged === true);
    if (taggedObject) {
      this.taggedRing.visible = true;
      this.taggedRing.position.copy(taggedObject.position);
      this.taggedRing.position.y += 120;
    } else {
      this.taggedRing.visible = false;
    }
  }

  private createEntityMesh(entity: TelemetryObject): any {
    const color = entity.team === "Blue" ? 0x57d4ff : 0xff746b;
    const common = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.25,
      metalness: 0.3,
      roughness: 0.5
    });

    let mesh: any;
    if (entity.type.includes("Aircraft")) {
      mesh = new THREE.Mesh(new THREE.ConeGeometry(140, 420, 4), common);
      mesh.rotation.z = Math.PI;
    } else if (entity.type.includes("Missile")) {
      mesh = new THREE.Mesh(new THREE.CylinderGeometry(24, 24, 220, 8), common);
      const fin = new THREE.Mesh(
        new THREE.BoxGeometry(10, 90, 40),
        new THREE.MeshStandardMaterial({
          color: 0xf7f4d6,
          emissive: 0xf7f4d6,
          emissiveIntensity: 0.08,
          metalness: 0.25,
          roughness: 0.55
        })
      );
      mesh.add(fin);
    } else {
      mesh = new THREE.Mesh(new THREE.BoxGeometry(180, 90, 180), common);
    }
    const halo = new THREE.Mesh(
      new THREE.TorusGeometry(320, 12, 10, 48),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.7,
        depthTest: false
      })
    );
    halo.rotation.x = Math.PI / 2;
    mesh.add(halo);

    const label = makeTextSprite(`${entity.team} ${entity.type}\n${entity.uid}`, color);
    label.position.set(0, 520, 0);
    mesh.add(label);

    mesh.userData.material = common;
    mesh.userData.baseColor = color;
    mesh.userData.tagged = false;
    return mesh;
  }

  private animate = (): void => {
    this.frameHandle = requestAnimationFrame(this.animate);
    this.updateCamera();
    this.renderer.render(this.scene, this.camera);
  };

  private updateCamera(): void {
    const focusObject = this.focusUid ? this.entities.get(this.focusUid) : null;
    if (!focusObject) {
      return;
    }
    const target = focusObject.position.clone();
    const desired = target.clone().add(new THREE.Vector3(4000, 2800, 4000));
    this.camera.position.lerp(desired, 0.03);
    this.camera.lookAt(target);
  }

  private frameObjects(objects: TelemetryObject[]): void {
    const now = performance.now();
    if (objects.length === 0 || now - this.lastAutoFrameAt < 1000) {
      return;
    }
    this.lastAutoFrameAt = now;

    const bounds = new THREE.Box3();
    for (const object of this.entities.values()) {
      bounds.expandByPoint(object.position);
    }
    if (bounds.isEmpty()) {
      return;
    }

    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z, 2500);
    const distance = Math.min(Math.max(radius * 1.5, 9000), 120000);
    const desired = center.clone().add(new THREE.Vector3(distance, distance * 0.7, distance));
    this.camera.position.lerp(desired, 0.08);
    this.camera.lookAt(center);
  }

  private handleResize = (): void => {
    const width = this.root.clientWidth;
    const height = this.root.clientHeight;
    if (width <= 0 || height <= 0) {
      return;
    }
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  };

  private handleClick = (event: MouseEvent): void => {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const intersections = this.raycaster.intersectObjects([...this.entities.values()], true);
    const uid = intersections[0] ? findEntityUid(intersections[0].object) : null;
    this.hooks.onSelect(uid);
    this.autoFrameEnabled = uid === null;
  };
}

function findEntityUid(object: any): string | null {
  let current: any = object;
  while (current) {
    if (typeof current.userData?.uid === "string") {
      return current.userData.uid;
    }
    current = current.parent;
  }
  return null;
}

function makeTextSprite(text: string, color: number): any {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 160;
  const context = canvas.getContext("2d");
  if (!context) {
    return new THREE.Object3D();
  }
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "rgba(2, 10, 16, 0.76)";
  context.strokeStyle = `#${color.toString(16).padStart(6, "0")}`;
  context.lineWidth = 4;
  roundRect(context, 10, 10, 492, 140, 22);
  context.fill();
  context.stroke();
  context.fillStyle = "#dfeff5";
  context.font = "600 28px IBM Plex Sans, sans-serif";
  const lines = text.split("\n");
  lines.forEach((line, index) => {
    context.fillText(line, 28, 58 + index * 42);
  });

  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(2200, 688, 1);
  return sprite;
}

function roundRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number): void {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
}

function isTelemetryTagged(entity: TelemetryObject): boolean {
  const registerValue = entity.debug_register;
  if (!registerValue || typeof registerValue !== "object") {
    return false;
  }
  const telemetryValue = registerValue["telemetry"];
  if (!telemetryValue || typeof telemetryValue !== "object") {
    return false;
  }
  const webValue = (telemetryValue as Record<string, unknown>)["web"];
  if (!webValue || typeof webValue !== "object") {
    return false;
  }
  return (webValue as Record<string, unknown>)["selected"] === true;
}

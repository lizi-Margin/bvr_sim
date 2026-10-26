"""Build a self-contained, redistribution-safe Windows F-16 game package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


REPO = Path(__file__).resolve().parents[2]
RELEASE_MANIFEST = REPO / "game/releases/regional-horizon-v327-2026-10-26.json"
PACKAGE_NAME = "BVR-SIM"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def portable_path(path: Path, bundle: Path) -> str:
    return path.resolve().relative_to(bundle.resolve()).as_posix()


def asset_is_redistributable(manifest: dict) -> bool:
    if manifest.get("distribution_allowed") is False:
        return False
    license_name = str(manifest.get("license") or "").lower()
    return any(term in license_name for term in ("cc0", "gpl", "mit", "ofl", "public domain"))


def prepare_payload(stage: Path, release: dict) -> tuple[dict, list[str]]:
    bundle = stage / "payload"
    game = bundle / "game"
    assets = game / "assets"
    source_game = REPO / "game"
    exclusions: list[str] = []

    runtime = read_json(source_game / "runtime-ui.json")
    runtime["renderer_module"] = "game/renderer"
    runtime["engine_source"] = "game/engine"
    runtime["shader_cache"] = "game/shader-cache"
    runtime["audio"] = {}
    runtime["imported_models"] = {}
    kept_models = {}
    copied_assets: set[str] = set()
    for model_id, raw_path in runtime["models"].items():
        source_file = Path(raw_path).resolve()
        source_dir = source_file.parent
        manifest_path = source_dir / "manifest.json"
        manifest = read_json(manifest_path) if manifest_path.is_file() else {}
        if not asset_is_redistributable(manifest):
            exclusions.append(f"model:{model_id}:{manifest.get('license', 'unknown license')}")
            continue
        if source_dir.name not in copied_assets:
            copy_tree(source_dir, assets / "registered" / source_dir.name)
            copied_assets.add(source_dir.name)
        kept_models[model_id] = portable_path(
            assets / "registered" / source_dir.name / source_file.name, bundle
        )
    if "F16" not in kept_models:
        raise RuntimeError("The F-16 runtime model is missing or not redistributable")
    runtime["models"] = kept_models

    for field, packaged_name in (("asphalt_texture", "asphalt.jpg"), ("terrain_texture", "terrain.jpg")):
        source = Path(runtime[field]).resolve()
        destination = assets / "textures" / packaged_name
        copy_file(source, destination)
        runtime[field] = portable_path(destination, bundle)
        provider = source.parent.parent / "provider.json"
        if provider.is_file():
            copy_file(provider, destination.with_name(destination.stem + "-provider.json"))

    runtime_path = game / "runtime-ui.json"
    write_json(runtime_path, runtime)
    write_json(game / "runtime.json", runtime)

    native = read_json(source_game / "native-runtime.json")
    core = Path(release["artifacts"]["core_module"]["path"]).resolve()
    renderer = Path(release["artifacts"]["renderer_module"]["path"]).resolve()
    compiler = Path(release["artifacts"]["dxcompiler"]["path"]).resolve()
    if sha(core) != release["artifacts"]["core_module"]["sha256"]:
        raise RuntimeError("Frozen core hash does not match the release record")
    if sha(renderer) != release["artifacts"]["renderer_module"]["sha256"]:
        raise RuntimeError("Frozen renderer hash does not match the release record")
    if sha(core) != native["core_sha256"]:
        raise RuntimeError("Native runtime config and release core hashes differ")
    core_copy = game / "native" / core.name
    renderer_copy = game / "renderer" / renderer.name
    compiler_copy = game / "renderer" / compiler.name
    copy_file(core, core_copy)
    copy_file(renderer, renderer_copy)
    copy_file(compiler, compiler_copy)
    native["core_module"] = Path("native", core.name).as_posix()
    write_json(game / "native-runtime.json", native)

    profile = read_json(source_game / "recipes/player_daylight.json")
    profile["shader_source"] = "game/engine/WickedEngine/shaders"
    profile["shader_cache"] = "game/shader-cache"
    profile["aircraft_exhaust_profiles_file"] = "../config/aircraft_exhaust_profiles.json"
    # These LOD recipes source local War Thunder/user-provided models. The
    # baseline CC0 scenery models remain available in the packaged runtime.
    for asset_id in profile.get("vegetation_distance_lods", {}):
        exclusions.append(f"vegetation-distance-lod:{asset_id}:local-only source")
    profile["vegetation_distance_lods"] = {}
    profile.pop("cloud_weather_map", None)
    write_json(game / "recipes/player_daylight.json", profile)

    # runtime has already been rewritten above, use the frozen manifest's
    # original paths for the cache/source directories.
    source_runtime = read_json(source_game / "runtime-ui.json")
    shader_cache_source = Path(source_runtime["shader_cache"]).resolve()
    shader_source_source = Path(profile.get("shader_source", ""))
    # The source recipe's shader path is authoritative; profile above was
    # copied to the bundle, so recover the machine-local path from source.
    source_profile = read_json(source_game / "recipes/player_daylight.json")
    shader_source_source = Path(source_profile["shader_source"]).resolve()
    copy_tree(shader_cache_source, game / "shader-cache")
    copy_tree(shader_source_source, game / "engine/WickedEngine/shaders")
    copy_file(compiler, game / "engine/WickedEngine/dxcompiler.dll")

    # Keep the portable product focused on the distributable F-16 client.
    resources_source = REPO / "bvr_sim/resources"
    copy_tree(resources_source, bundle / "bvr_sim/resources")
    aircraft_catalog = read_json(bundle / "bvr_sim/resources/aircraft_catalog.json")
    aircraft_catalog["aircraft"] = [row for row in aircraft_catalog["aircraft"] if row["id"] == "F16"]
    aircraft_catalog["aircraft"][0]["missions"] = [
        mission for mission in aircraft_catalog["aircraft"][0]["missions"] if mission != "convoy"
    ]
    write_json(bundle / "bvr_sim/resources/aircraft_catalog.json", aircraft_catalog)
    stations = read_json(bundle / "bvr_sim/resources/aircraft_stations.json")
    station_rows = stations.get("aircraft", [])
    if isinstance(station_rows, list):
        stations["aircraft"] = [row for row in station_rows if row.get("aircraft_id", row.get("id")) == "F16"]
    elif isinstance(station_rows, dict):
        stations["aircraft"] = {key: value for key, value in station_rows.items() if key == "F16"}
    write_json(bundle / "bvr_sim/resources/aircraft_stations.json", stations)
    imported = read_json(bundle / "bvr_sim/resources/imported_aircraft_catalog.json")
    imported["aircraft"] = []
    write_json(bundle / "bvr_sim/resources/imported_aircraft_catalog.json", imported)

    # Only the selected F-16 thumbnail is needed; the package excludes aircraft
    # whose registered models are marked local-only.
    thumbnail_dir = assets / "ui/aircraft"
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    for source in (source_game / "assets/ui/aircraft").glob("F16.*"):
        copy_file(source, thumbnail_dir / source.name)

    copy_file(source_game / "maps/training.json", game / "maps/training.json")
    write_json(game / "maps/catalog.json", {
        "schema_version": 1,
        "maps": [],
        "storage_roots": {},
        "default_storage_root": None,
        "registered_storage_roots": [],
    })
    copy_tree(source_game / "config", game / "config")

    payload_manifest = {
        "schema_version": 1,
        "release_id": "bvr-sim-portable-2026-10-26",
        "source_release_id": release["release_id"],
        "redistribution_profile": "F-16 with training map; only assets with explicit open redistribution licenses",
        "excluded_local_only_assets": exclusions,
        "map": "game/maps/training.json",
        "aircraft": ["F16"],
        "core_sha256": sha(core_copy),
        "renderer_sha256": sha(renderer_copy),
    }
    write_json(game / "portable-release.json", payload_manifest)
    return payload_manifest, exclusions


def write_distribution_docs(product: Path, payload_manifest: dict) -> None:
    license_file = REPO / "LICENSE"
    copy_file(license_file, product / "LICENSE.txt")
    readme = f"""BVR SIM Portable — 2026-10-26

Start the game by double-clicking BVR-SIM.exe. The first start loads the
renderer and may take about a minute. The cancellable progress window remains
visible until the game window is ready.

This portable build starts the F-16 on the self-contained training map. It
contains only game assets whose manifests allow redistribution. The local
Regional Horizon v327 map and War Thunder-derived/user-provided assets are not
included. This is a portable distribution build of the same game code/core,
not a copy of that local-only map package.

Requirements: 64-bit Windows 10/11 with DirectX 12 and a compatible GPU.
The system Microsoft YaHei font is used when installed; otherwise Windows
uses its available fallback font. Extract the whole BVR-SIM folder before
running; do not move BVR-SIM.exe out of its _internal folder.

The game and native core are GPL-3.0-or-later; the bundled F-16 model and
FlightGear source data retain their GPL-2.0 notices. Other bundled model
licenses are recorded in each assets/registered/*/manifest.json. Wicked
shader source is included with its upstream license. Third-party Python
component licenses are listed in THIRD-PARTY-NOTICES.txt.

Package ID: {payload_manifest['release_id']}
Frozen source game: {payload_manifest['source_release_id']}
"""
    (product / "README-DISTRIBUTION.txt").write_text(readme, encoding="utf-8")
    notices = """Third-party notices

Python 3.14 — Python Software Foundation License.
PyInstaller — GPL-2.0-or-later with bootloader exception.
NumPy — BSD-3-Clause.
SciPy — BSD-3-Clause.
Shapely — BSD-3-Clause.
Pillow — HPND license.
F-16 source model — GPL-2.0; see bvr_sim/resources/aircraft_catalog.json.
Other bundled model and shader licenses — see their asset manifests and the
upstream Wicked Engine license accompanying the shader-source files.
"""
    (product / "THIRD-PARTY-NOTICES.txt").write_text(notices, encoding="utf-8")


def write_checksums(product: Path) -> None:
    rows = []
    for path in sorted(p for p in product.rglob("*") if p.is_file()):
        rows.append(f"{sha(path)}  {path.relative_to(product).as_posix()}")
    (product / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def build(output: Path, *, make_archive: bool = True) -> Path:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing distribution: {output}")
    if os.name != "nt":
        raise RuntimeError("The portable renderer build currently targets 64-bit Windows")
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 14) or sys.maxsize < 2**32:
        raise RuntimeError("Build with 64-bit CPython 3.14; the frozen native core is cp314-win_amd64")
    release = read_json(RELEASE_MANIFEST)
    stage = output.with_name(output.name + ".staging")
    if stage.exists():
        raise FileExistsError(f"Refusing to reuse existing staging directory: {stage}")
    stage.mkdir(parents=True)
    try:
        payload_manifest, exclusions = prepare_payload(stage, release)
        source_package = stage / "source-package"
        copy_tree(REPO / "bvr_game", source_package / "bvr_game")
        copy_tree(REPO / "bvr_sim/src_cxx", source_package / "bvr_sim/src_cxx")
        copy_tree(REPO / "bvr_sim/resources", source_package / "bvr_sim/resources")
        copy_tree(REPO / "game/native", source_package / "game/native")
        copy_tree(REPO / "game/packaging", source_package / "game/packaging")
        copy_file(REPO / "pyproject.toml", source_package / "pyproject.toml")
        copy_file(REPO / "LICENSE", source_package / "LICENSE")
        source_zip = stage / "BVR-SIM-Source.zip"
        with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for file in sorted(p for p in source_package.rglob("*") if p.is_file()):
                archive.write(file, file.relative_to(source_package).as_posix())

        game_data = stage / "payload/game"
        resources_data = stage / "payload/bvr_sim/resources"
        core_source = game_data / "native" / Path(release["artifacts"]["core_module"]["path"]).name
        renderer_source = game_data / "renderer" / Path(release["artifacts"]["renderer_module"]["path"]).name
        dxcompiler_source = game_data / "renderer" / Path(release["artifacts"]["dxcompiler"]["path"]).name
        entry = REPO / "game/packaging/frozen_entry.py"
        work = stage / "pyinstaller-work"
        args = [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
            "--name", PACKAGE_NAME, "--distpath", str(output), "--workpath", str(work),
            "--specpath", str(stage), "--paths", str(REPO),
            "--add-data", f"{game_data};game",
            "--add-data", f"{resources_data};bvr_sim/resources",
            "--add-data", f"{REPO / 'bvr_game/data'};bvr_game/data",
            "--hidden-import", "bvr_game.app",
            "--hidden-import", "bvr_game.launcher",
            "--hidden-import", "bvr_sim.bvr_env_cpp",
            str(entry),
        ]
        subprocess.run(args, cwd=REPO, check=True)
        product = output / PACKAGE_NAME
        copy_file(source_zip, product / "BVR-SIM-Source.zip")
        write_distribution_docs(product, payload_manifest)
        write_checksums(product)
        if make_archive:
            archive_path = output / f"{PACKAGE_NAME}-Portable-2026-10-26.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for file in sorted(p for p in product.rglob("*") if p.is_file()):
                    archive.write(file, Path(PACKAGE_NAME) / file.relative_to(product))
        (output / "BUILD-REPORT.json").write_text(
            json.dumps({"status": "built", "package": str(product), "archive": str(archive_path) if make_archive else None,
                        "excluded_local_only_assets": exclusions, "payload": payload_manifest}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        return product
    finally:
        # Remove only the staging directory created above; all build outputs
        # remain under the caller-selected fresh output directory.
        shutil.rmtree(stage, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("D:/BVR-SIM-Portable-2026-10-26"))
    parser.add_argument("--no-archive", action="store_true", help="Build the runnable folder without the shareable ZIP")
    args = parser.parse_args()
    product = build(args.output, make_archive=not args.no_archive)
    print(product)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

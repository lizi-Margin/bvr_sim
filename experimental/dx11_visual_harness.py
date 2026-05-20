import argparse
import json
import os
import subprocess
import sys
import time
import ctypes
from ctypes import wintypes

import commentjson
from PIL import ImageGrab


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bvr_sim.bvr_env_cpp import BVR3DEnvCpp


WINDOW_TITLE = "BVR Sim DX11 Game Mode"
WINDOW_CLASS = "BvrSimGameModeWindow"


def get_user32():
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    return user32


def get_root_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def find_window_rect(title: str):
    user32 = get_user32()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        hwnd = user32.FindWindowW(WINDOW_CLASS, None)
    if not hwnd:
        for candidate_hwnd, candidate_title in enum_visible_windows():
            if title in candidate_title or "BVR Sim" in candidate_title:
                hwnd = candidate_hwnd
                break
    if not hwnd:
        return None

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return hwnd, (rect.left, rect.top, rect.right, rect.bottom)


def enum_visible_windows():
    user32 = get_user32()
    results = []

    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, 256)
        class_name = class_buffer.value.strip()
        if title or class_name:
            results.append((hwnd, f"{class_name}::{title}"))
        return True

    user32.EnumWindows(enum_proc_type(enum_proc), 0)
    return results


def wait_for_window(title: str, timeout_sec: float):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        found = find_window_rect(title)
        if found:
            return found
        time.sleep(0.05)
    visible_titles = [window_title for _, window_title in enum_visible_windows()]
    raise RuntimeError(f"Timed out waiting for window: {title}; visible windows: {visible_titles}")


def wait_for_status(core, predicate, timeout_sec: float = 8.0) -> dict:
    deadline = time.time() + timeout_sec
    last_status = core.get_game_mode_status()
    while time.time() < deadline:
        last_status = core.get_game_mode_status()
        if predicate(last_status):
            return last_status
        time.sleep(0.05)
    raise RuntimeError(f"Timed out waiting for GameMode status: {last_status}")


def run_build(root_dir: str) -> None:
    subprocess.run([os.path.join(root_dir, "bvr_sim", "build_windows.bat")], cwd=root_dir, check=True)


def capture_window_png(output_path: str, settle_sec: float, allow_fullscreen_fallback: bool) -> None:
    try:
        hwnd, rect = wait_for_window(WINDOW_TITLE, timeout_sec=8.0)
    except RuntimeError as exc:
        if not allow_fullscreen_fallback:
            raise
        print(f"[dx11_visual_harness] Window lookup failed, falling back to full-screen capture: {exc}")
        hwnd = None
        rect = None
    if hwnd:
        user32 = get_user32()
        title_buffer = ctypes.create_unicode_buffer(256)
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title_buffer, 256)
        user32.GetClassNameW(hwnd, class_buffer, 256)
        print(
            "[dx11_visual_harness] Capturing hwnd="
            f"{hwnd} class={class_buffer.value!r} title={title_buffer.value!r} rect={rect}"
        )
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetWindowPos(hwnd, wintypes.HWND(-1).value, 80, 80, 1440, 900, 0x0040)  # HWND_TOPMOST, SWP_SHOWWINDOW
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.20)
        found = find_window_rect(WINDOW_TITLE)
        if found:
            hwnd, rect = found
            print(f"[dx11_visual_harness] Capture rect after raise: {rect}")
    time.sleep(settle_sec)
    image = ImageGrab.grab(bbox=rect)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    image.save(output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch DX11 GameMode and capture a close aircraft screenshot.")
    parser.add_argument("--config", default="tests/demo_config_cpp.jsonc")
    parser.add_argument("--output", default="test_logs/dx11_visual_harness.png")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--steps", type=int, default=80)
    parser.add_argument("--settle-sec", type=float, default=0.5)
    parser.add_argument("--no-fullscreen-fallback", action="store_true")
    args = parser.parse_args()

    root_dir = get_root_dir()
    if args.build:
        run_build(root_dir)

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(root_dir, config_path)
    with open(config_path, "r", encoding="utf-8") as fin:
        env_config = commentjson.load(fin)

    os.makedirs(os.path.join(root_dir, "test_logs"), exist_ok=True)
    sim = BVR3DEnvCpp(
        env_config,
        [],
        log_file_path=os.path.join(root_dir, "test_logs", "dx11_visual_harness.log"),
        acmi_file_path=os.path.join(root_dir, "test_logs", "dx11_visual_harness.acmi"),
    )

    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(root_dir, output_path)

    try:
        sim.reset(seed=None)
        sim.core.step_sync(1)
        sim.core.start_game_mode()
        sim.core.handle(
            "game_mode set "
            + json.dumps(
                {
                    "mode": "follow",
                    "focus_index": 0,
                    "distance": 750.0,
                    "yaw": 0.82,
                    "pitch": 0.38,
                    "fov_y": 72.0,
                    "roll_locked": True,
                },
                separators=(",", ":"),
            )
        )
        wait_for_status(sim.core, lambda status: status["running"] is True)

        for _ in range(max(1, args.steps)):
            sim.step({})
            time.sleep(0.01)

        rendered_status = wait_for_status(
            sim.core,
            lambda status: status["last_object_count"] > 0
            and status["last_draw_calls"] >= 3
            and status["last_vertex_count"] > 0,
        )
        print(f"[dx11_visual_harness] GameMode status: {rendered_status}")
        visible_windows = [title.encode("ascii", "backslashreplace").decode("ascii") for _, title in enum_visible_windows()]
        print(f"[dx11_visual_harness] Visible windows: {visible_windows}")
        capture_window_png(output_path, args.settle_sec, not args.no_fullscreen_fallback)
        print(output_path)
    finally:
        sim.core.stop_game_mode()
        del sim

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

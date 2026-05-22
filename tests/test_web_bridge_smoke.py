import os
import sys
import importlib.util
import types
import json
import socket
import base64
import hashlib
import subprocess
import urllib.request
import struct
import time


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOT = os.path.join(REPO_ROOT, "bvr_sim")
BVR_ENV_CPP_PATH = os.path.join(PACKAGE_ROOT, "bvr_env_cpp.py")


def load_local_bvr_env_cpp():
    package = types.ModuleType("bvr_sim")
    package.__path__ = [PACKAGE_ROOT]
    sys.modules["bvr_sim"] = package

    spec = importlib.util.spec_from_file_location("bvr_sim.bvr_env_cpp", BVR_ENV_CPP_PATH)
    assert spec is not None and spec.loader is not None, BVR_ENV_CPP_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules["bvr_sim.bvr_env_cpp"] = module
    spec.loader.exec_module(module)
    return module


bvr_env_cpp = load_local_bvr_env_cpp()
bvr_sim_cpp = bvr_env_cpp.bvr_sim_cpp


def main() -> int:
    os.makedirs("./test_logs", exist_ok=True)
    module_path = os.path.abspath(bvr_sim_cpp.__file__)
    assert "web-visualization-phase1" in module_path.replace("\\", "/"), module_path
    npm_executable = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run(
        [npm_executable, "--prefix", os.path.join("bvr_sim", "web"), "run", "build"],
        check=True,
    )
    dist_dir = os.path.join(REPO_ROOT, "bvr_sim", "web", "dist")
    assert os.path.isdir(dist_dir), dist_dir
    assert os.path.isfile(os.path.join(dist_dir, "index.html"))
    assets_dir = os.path.join(dist_dir, "assets")
    assert os.path.isdir(assets_dir), assets_dir
    asset_files = os.listdir(assets_dir)
    assert any(name.endswith(".js") for name in asset_files), asset_files

    core = bvr_sim_cpp.SimCore(
        dt=0.2,
        log_file_path="./test_logs/test_web_bridge_smoke.log",
        acmi_file_path=""
    )

    status = core.get_telemetry_status()
    assert status["telemetry_running"] is False
    assert status["dt"] == 0.2

    core.start_telemetry_bridge()
    status = core.get_telemetry_status()
    assert status["telemetry_running"] is True

    core.step_sync(1)
    snapshot = core.get_telemetry_snapshot()
    assert snapshot["dt"] == 0.2
    assert snapshot["sim_time"] == 0.2
    assert isinstance(snapshot["objects"], list)

    core.stop_telemetry_bridge()
    status = core.get_telemetry_status()
    assert status["telemetry_running"] is False

    core.set_visualization_static_root(dist_dir)
    core.start_visualization_server(8765)
    viz_status = core.get_visualization_status()
    assert viz_status["server_running"] is True
    assert viz_status["port"] == 8765
    assert viz_status["frontend_available"] is True
    assert os.path.normpath(viz_status["static_root"]) == os.path.normpath(dist_dir)
    assert viz_status["frontend_url"] == "http://127.0.0.1:8765/"

    with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=5) as response:
        health = json.loads(response.read().decode("utf-8"))
    assert health["status"] == "ok"

    with urllib.request.urlopen("http://127.0.0.1:8765/diagnostics", timeout=5) as response:
        diagnostics = json.loads(response.read().decode("utf-8"))
    assert diagnostics["server_running"] is True

    with urllib.request.urlopen("http://127.0.0.1:8765/", timeout=5) as response:
        html = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")
    assert "BVR Sim Live Debug View" in html
    assert '<div id="app"></div>' in html
    assert "text/html" in content_type

    first_asset = next(name for name in asset_files if name.endswith(".js"))
    with urllib.request.urlopen(f"http://127.0.0.1:8765/assets/{first_asset}", timeout=5) as response:
        asset_body = response.read().decode("utf-8")
        asset_content_type = response.headers.get("Content-Type", "")
    assert "modulepreload" in asset_body
    assert len(asset_body) > 1000
    assert "application/javascript" in asset_content_type

    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        "GET /ws HTTP/1.1\r\n"
        "Host: 127.0.0.1:8765\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")

    sock = socket.create_connection(("127.0.0.1", 8765), timeout=5)
    sock.sendall(request)
    handshake = sock.recv(4096).decode("latin1")
    assert "101 Switching Protocols" in handshake
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")
    assert f"Sec-WebSocket-Accept: {accept}" in handshake

    header = sock.recv(2)
    assert len(header) == 2
    assert header[0] & 0x0F == 1
    payload_length = header[1] & 0x7F
    if payload_length == 126:
        payload_length = int.from_bytes(sock.recv(2), "big")
    elif payload_length == 127:
        payload_length = int.from_bytes(sock.recv(8), "big")
    payload = sock.recv(payload_length).decode("utf-8")
    first_message = json.loads(payload)
    assert first_message["dt"] == 0.2
    assert "objects" in first_message

    send_ws_text(
        sock,
        json.dumps({
            "kind": "set_focus_uid",
            "target_uid": "focus:test"
        })
    )
    command_message = recv_ws_command_result(sock)
    assert command_message["status"] == "ok"

    diagnostics = wait_for_diagnostics(
        "http://127.0.0.1:8765/diagnostics",
        lambda data: data["telemetry"]["focus_uid"] == "focus:test"
    )
    assert diagnostics["telemetry"]["focus_uid"] == "focus:test"

    send_ws_text(
        sock,
        json.dumps({
            "kind": "set_subscription_filter",
            "payload": {"type": "Aircraft"}
        })
    )
    filter_message = recv_ws_command_result(sock)
    assert filter_message["status"] == "ok"

    diagnostics = wait_for_diagnostics(
        "http://127.0.0.1:8765/diagnostics",
        lambda data: data["telemetry"]["subscription_filter"]["type"] == "Aircraft"
    )
    assert diagnostics["telemetry"]["subscription_filter"]["type"] == "Aircraft"

    send_ws_text(
        sock,
        json.dumps({
            "kind": "object_debug",
            "target_uid": "missing:uid",
            "payload": {
                "register_key": "telemetry.web.selected",
                "value": True
            }
        })
    )
    object_debug_message = recv_ws_command_result(sock)
    assert object_debug_message["status"] == "ok"

    diagnostics = wait_for_diagnostics(
        "http://127.0.0.1:8765/diagnostics",
        lambda data: data["telemetry"]["last_command_result"]["kind"] == "object_debug"
        and data["telemetry"]["last_command_result"]["status"] == "error"
    )
    assert diagnostics["telemetry"]["last_command_result"]["message"] == "target object not found"
    sock.close()

    core.stop_visualization_server()
    viz_status = core.get_visualization_status()
    assert viz_status["server_running"] is False

    return 0


def send_ws_text(sock: socket.socket, payload: str) -> None:
    payload_bytes = payload.encode("utf-8")
    frame = bytearray()
    frame.append(0x81)
    if len(payload_bytes) < 126:
        frame.append(0x80 | len(payload_bytes))
    elif len(payload_bytes) <= 0xFFFF:
        frame.append(0x80 | 126)
        frame.extend(struct.pack("!H", len(payload_bytes)))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack("!Q", len(payload_bytes)))

    mask = os.urandom(4)
    frame.extend(mask)
    frame.extend(byte ^ mask[index % 4] for index, byte in enumerate(payload_bytes))
    sock.sendall(frame)


def recv_ws_text(sock: socket.socket) -> str:
    header = sock.recv(2)
    assert len(header) == 2
    assert header[0] & 0x0F == 1
    payload_length = header[1] & 0x7F
    if payload_length == 126:
        payload_length = int.from_bytes(sock.recv(2), "big")
    elif payload_length == 127:
        payload_length = int.from_bytes(sock.recv(8), "big")
    return sock.recv(payload_length).decode("utf-8")


def recv_ws_command_result(sock: socket.socket, timeout_sec: float = 2.0) -> dict:
    previous_timeout = sock.gettimeout()
    sock.settimeout(timeout_sec)
    try:
        while True:
            message = json.loads(recv_ws_text(sock))
            if "status" in message and "message" in message:
                return message
    finally:
        sock.settimeout(previous_timeout)


def wait_for_diagnostics(url: str, predicate, timeout_sec: float = 2.0) -> dict:
    deadline = time.time() + timeout_sec
    last_data = None
    while time.time() < deadline:
        with urllib.request.urlopen(url, timeout=5) as response:
            last_data = json.loads(response.read().decode("utf-8"))
        try:
            matched = predicate(last_data)
        except (KeyError, IndexError, TypeError):
            matched = False
        if matched:
            return last_data
        time.sleep(0.02)
    raise AssertionError(last_data)


if __name__ == "__main__":
    raise SystemExit(main())

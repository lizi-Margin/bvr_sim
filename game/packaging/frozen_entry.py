"""PyInstaller entry point for the portable game launcher and its worker."""
from __future__ import annotations

import os
import sys


def main() -> int:
    args = list(sys.argv[1:])
    if args and args[0] == "--bvr-game-worker":
        # PyInstaller starts a second copy of this executable so the UI can
        # cancel native/map startup independently. Strip the private switch
        # before handing ordinary game arguments to the client parser.
        sys.argv = [sys.argv[0], *args[1:]]
        os.environ["BVR_GAME_STARTUP_WORKER"] = "1"
        from bvr_game.app import main as run_game

        return run_game()

    if os.name == "nt":
        # The application presents its own cancellable Tk loading window.
        # Keep the console-subsystem executable from leaving a console behind
        # when the user starts the distributable by double-clicking it.
        try:
            import ctypes

            ctypes.windll.kernel32.FreeConsole()
        except (AttributeError, OSError):
            pass

    if not args:
        args = [
            "play",
            "--runtime",
            "game/runtime-ui.json",
            "--map",
            "game/maps/training.json",
            "--aircraft",
            "F16",
            "--quality",
            "high",
        ]
    from bvr_game.launcher import main as run_launcher

    return run_launcher(args)


if __name__ == "__main__":
    raise SystemExit(main())

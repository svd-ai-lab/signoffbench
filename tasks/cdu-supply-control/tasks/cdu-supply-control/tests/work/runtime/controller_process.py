"""Private child-process entry point; never import this in verifier memory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from controller_interface import load_controller

    try:
        controller = load_controller(args.controller)
        controller.reset()
    except Exception as exc:
        print(json.dumps({"type": "fatal", "error": str(exc)}), flush=True)
        raise SystemExit(2) from exc
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        request = json.loads(line)
        try:
            if request.get("type") == "reset":
                controller.reset()
                response = {"type": "reset", "ok": True}
            elif request.get("type") == "step":
                response = {"type": "commands", "commands": controller.step(request["observation"])}
            else:
                response = {"type": "fatal", "error": "unknown request type"}
        except Exception as exc:  # noqa: BLE001 - candidate errors become protocol failure
            response = {"type": "fatal", "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(response, allow_nan=False), flush=True)

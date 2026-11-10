"""Causal line-delimited JSON boundary around a candidate controller."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

from .controller_interface import validate_commands, validate_observation


class SubprocessController:
    def __init__(self, controller_path: str | Path):
        self.controller_path = Path(controller_path).resolve()
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("controller_process.py")), "--controller", str(self.controller_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, errors="replace",
            cwd=self.controller_path.parent,
        )

        self._start_stderr_drain()

    def _start_stderr_drain(self) -> None:
        """Continuously drain untrusted diagnostics while retaining a bounded tail."""
        self._stderr_tail = ""

        def drain():
            try:
                while chunk := self.process.stderr.read(4096):
                    self._stderr_tail = (self._stderr_tail + chunk)[-65536:]
            except (OSError, ValueError):
                pass

        self._stderr_thread = threading.Thread(target=drain, daemon=True)
        self._stderr_thread.start()

    def reset(self) -> None:
        request = {"type": "reset"}
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        response = self._response()
        if response != {"type": "reset", "ok": True}:
            raise RuntimeError(f"controller reset failed: {response}")

    def step(self, observation: dict) -> dict[str, float]:
        validate_observation(observation)
        request = {"type": "step", "observation": observation}
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        response = self._response()
        if response.get("type") != "commands":
            raise RuntimeError(f"controller step failed: {response}")
        return validate_commands(response.get("commands"))

    def _response(self) -> dict:
        line = self.process.stdout.readline()
        if not line:
            self.process.wait(timeout=2)
            self._stderr_thread.join(timeout=1)
            raise RuntimeError("controller process exited: " + self._stderr_tail.strip())
        response = json.loads(line)
        if not isinstance(response, dict):
            raise TypeError("controller response is not an object")
        return response

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()
        self._stderr_thread.join(timeout=1)
        if not self._stderr_thread.is_alive() and self.process.stderr is not None:
            self.process.stderr.close()

    def __enter__(self):
        try:
            self.reset()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_args):
        self.close()

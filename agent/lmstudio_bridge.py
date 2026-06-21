"""
lmstudio_bridge.py — Stable OpenAI-compatible agent server for OpenClaw (and others).

OpenClaw (and any OpenAI client) points at this bridge once:
    baseUrl: http://127.0.0.1:8765/v1
    model:   local/current

Swap models in LM Studio anytime — the bridge resolves the currently loaded LLM
on every request. No OpenClaw config changes needed.

Usage:
    uv run python agent/lmstudio_bridge.py
    uv run python agent/lmstudio_bridge.py --port 8765 --lmstudio http://127.0.0.1:1234
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

STABLE_MODEL = "local/current"
DEFAULT_PORT = 8765
DEFAULT_LM = "http://127.0.0.1:1234"


def _resolve_loaded_model(lm_base: str) -> str:
    """Pick the LLM currently loaded in LM Studio."""
    lm_base = lm_base.rstrip("/")

    # Native API — best signal (loaded_instances).
    try:
        with urllib.request.urlopen(f"{lm_base}/api/v1/models", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        loaded = [
            m["key"] for m in data.get("models", [])
            if m.get("type") == "llm" and m.get("loaded_instances")
        ]
        if loaded:
            return loaded[0]
    except Exception:  # noqa: BLE001
        pass

    # OpenAI-compat fallback — first non-embedding model.
    try:
        with urllib.request.urlopen(f"{lm_base}/v1/models", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for item in data.get("data", []):
            mid = item.get("id", "")
            if mid and "embed" not in mid.lower():
                return mid
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Cannot reach LM Studio at {lm_base}: {exc!r}") from exc

    raise RuntimeError(
        "No LLM available in LM Studio. Open LM Studio, load a model, and ensure "
        f"the server is running ({lm_base})."
    )


def _forward_json(lm_base: str, path: str, body: dict) -> tuple[int, bytes, dict]:
    url = f"{lm_base.rstrip('/')}{path}"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            headers = {k: v for k, v in resp.headers.items()}
            return resp.status, resp.read(), headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


class BridgeHandler(BaseHTTPRequestHandler):
    lm_base: str = DEFAULT_LM

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[lmstudio-bridge] {self.address_string()} {fmt % args}\n")

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._send_json(200, {
                "object": "list",
                "data": [{"id": STABLE_MODEL, "object": "model", "owned_by": "lmstudio-bridge"}],
            })
            return
        if self.path.rstrip("/") in ("/health", "/"):
            try:
                model = _resolve_loaded_model(self.lm_base)
                self._send_json(200, {"ok": True, "stable_model": STABLE_MODEL, "resolved": model})
            except RuntimeError as exc:
                self._send_json(503, {"ok": False, "error": str(exc)})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON"})
            return

        try:
            resolved = _resolve_loaded_model(self.lm_base)
        except RuntimeError as exc:
            self._send_json(503, {"error": str(exc)})
            return

        requested = body.get("model", STABLE_MODEL)
        body["model"] = resolved
        stream = bool(body.get("stream"))

        if stream:
            self._stream_completions(body, resolved, requested)
            return

        status, data, _ = _forward_json(self.lm_base, "/v1/chat/completions", body)
        try:
            out = json.loads(data.decode("utf-8"))
            if isinstance(out, dict):
                out["model"] = requested
        except json.JSONDecodeError:
            out = data
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data if isinstance(data, bytes) else str(out).encode())
            return

        self._send_json(status, out)

    def _stream_completions(self, body: dict, resolved: str, requested: str) -> None:
        """Stream SSE from LM Studio, rewriting model id in each chunk."""
        url = f"{self.lm_base.rstrip('/')}/v1/chat/completions"
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as exc:
            err_body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_body)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        while True:
            chunk = resp.readline()
            if not chunk:
                break
            line = chunk.decode("utf-8", errors="replace")
            if line.startswith("data: ") and line.strip() != "data: [DONE]":
                try:
                    evt = json.loads(line[6:].strip())
                    if isinstance(evt, dict):
                        evt["model"] = requested
                        line = f"data: {json.dumps(evt)}\n"
                except json.JSONDecodeError:
                    pass
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
        resp.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Stable LM Studio bridge for OpenClaw")
    ap.add_argument("--port", type=int, default=int(os.environ.get("BRIDGE_PORT", DEFAULT_PORT)))
    ap.add_argument("--lmstudio", default=os.environ.get("LMSTUDIO_URL", DEFAULT_LM))
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()

    BridgeHandler.lm_base = args.lmstudio.rstrip("/")
    server = ThreadingHTTPServer((args.bind, args.port), BridgeHandler)
    print(f"LM Studio bridge listening on http://{args.bind}:{args.port}/v1")
    print(f"  stable model id: {STABLE_MODEL}")
    print(f"  forwarding to:   {BridgeHandler.lm_base}")
    try:
        model = _resolve_loaded_model(BridgeHandler.lm_base)
        print(f"  currently loaded: {model}")
    except RuntimeError as exc:
        print(f"  warning: {exc}", file=sys.stderr)
    print("OpenClaw model ref: local-agent/local/current")
    server.serve_forever()


if __name__ == "__main__":
    main()

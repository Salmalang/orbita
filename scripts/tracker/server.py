"""Local build tracker for the team.

Run:  .venv/Scripts/python scripts/tracker/server.py   then open http://localhost:8765
Standard library only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PORT = 8765

_tests_lock = threading.Lock()
_last_tests: dict = {"state": "never run"}

STATUS_MAP = {"✅": "done", "🟡": "in_progress", "⬜": "todo", "➖": "n/a"}


def load_roadmap() -> dict:
    data = json.loads((ROOT / "docs" / "ROADMAP.json").read_text(encoding="utf-8"))
    total_w = sum(p["weight"] for p in data["parts"])
    data["overall_pct"] = round(sum(p["weight"] * p["progress"] for p in data["parts"]) / total_w, 1)
    return data


def parse_requirements() -> list[dict]:
    """Read the status column of every checklist row in docs/REQUIREMENTS.md."""
    sections, current = [], None
    for line in (ROOT / "docs" / "REQUIREMENTS.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current = {"title": line[3:].strip(), "items": []}
            sections.append(current)
            continue
        if current is None or not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        status = next((STATUS_MAP[e] for e in STATUS_MAP if e in cells[-1]), None)
        if status is None:
            continue
        current["items"].append({"id": cells[0], "text": cells[1], "status": status,
                                 "points": cells[2] if len(cells) >= 4 and re.match(r"^\d+\b", cells[2]) else ""})
    return [s for s in sections if s["items"]]


def git_log(n: int = 12) -> list[dict]:
    try:
        out = subprocess.run(["git", "log", f"-{n}", "--format=%h%x1f%ad%x1f%s", "--date=format:%d %b %H:%M"],
                             cwd=ROOT, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [dict(zip(("hash", "date", "message"), l.split("\x1f"))) for l in out.splitlines() if l]


def run_tests() -> dict:
    global _last_tests
    if not _tests_lock.acquire(blocking=False):
        return {"state": "running"}
    try:
        _last_tests = {"state": "running"}
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=line", "-p", "no:cacheprovider"],
                              cwd=ROOT, capture_output=True, text=True, timeout=600)
        summary = (proc.stdout.strip().splitlines() or ["no output"])[-1]
        counts = {k: int(v) for v, k in re.findall(r"(\d+) (passed|failed|errors?|skipped)", summary)}
        _last_tests = {"state": "ok" if proc.returncode == 0 else "failed", "summary": summary, "counts": counts,
                       "failures": [l for l in proc.stdout.splitlines() if " - " in l and ("Error" in l or "assert" in l)][:15],
                       "at": datetime.now(timezone.utc).isoformat()}
    except subprocess.TimeoutExpired:
        _last_tests = {"state": "failed", "summary": "timed out", "at": datetime.now(timezone.utc).isoformat()}
    finally:
        _tests_lock.release()
    return _last_tests


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj) -> None:
        self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/status":
            try:
                self._json({"roadmap": load_roadmap(), "requirements": parse_requirements(),
                            "commits": git_log(), "tests": _last_tests})
            except Exception as exc:  # show the problem on the page instead of a blank screen
                self._json({"error": f"{type(exc).__name__}: {exc}"})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        if self.path == "/api/tests":
            threading.Thread(target=run_tests, daemon=True).start()
            self._json({"state": "running"})
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args):  # keep the console quiet
        pass


if __name__ == "__main__":
    threading.Thread(target=run_tests, daemon=True).start()
    print(f"Build tracker on http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

"""Captures the README screenshots of the review page with headless Edge or Chrome.

    uv run python -m http.server 8765 --bind 127.0.0.1 --directory test-set/runs   (in another shell)
    uv run python portfolio/capture.py

Only dev run 2 is captured: the held-out runs are never opened while building.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
BASE = "http://localhost:8765/dev-2/run-report.html"
SHOTS = [  # (file, hash, dark)
    ("report-queue-light", "", False),
    ("report-detail-price-light", "#order=dev-012", False),
    ("report-detail-scan", "#order=dev-016", False),
    ("report-detail-auto", "#order=dev-003", False),
    ("report-queue", "", True),
    ("report-detail-price", "#order=dev-012", True),
]


def main() -> None:
    browser = next(b for b in BROWSERS if os.path.exists(b))
    bust = f"?v={int(time.time())}"
    for name, hash_, dark in SHOTS:
        out = HERE / f"{name}.png"
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1.5", "--window-size=1440,900",
                        f"--blink-settings=preferredColorScheme={0 if dark else 1}",
                        "--virtual-time-budget=5000", f"--screenshot={out}", BASE + bust + hash_],
                       check=True, capture_output=True, timeout=120)
        print(out.name, out.stat().st_size)


if __name__ == "__main__":
    main()

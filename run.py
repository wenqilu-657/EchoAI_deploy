#!/usr/bin/env python3
"""One-command runner for Emerging Artist Discovery Dashboard (Team EchoAI).
Usage:
    python run.py
Starts the local server and opens http://localhost:8000 in your browser.
"""
import sys
import os
import time
import webbrowser
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

def check_requirements():
    required = ["fastapi", "uvicorn", "duckdb", "pandas"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing requirements: {', '.join(missing)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

def main():
    print("=" * 60)
    print("  Emerging Artist Discovery Dashboard — Team EchoAI (USC DSO 576)")
    print("=" * 60)
    check_requirements()

    # Pre-check data
    from backend import analysis as an
    summary = an.data_summary()
    print(f"Data source: {summary['data_dir']}")
    print(f"Artists available: {summary['artists']:,}")
    print(f"Artists scored: {summary['artists_scored (baseline >= 5)']:,}")

    port = int(os.environ.get("PORT", 8000))
    url = f"http://127.0.0.1:{port}"
    print(f"\nStarting server at {url}...")
    print("Press Ctrl+C to stop.\n")

    # Schedule browser opening
    def open_browser():
        time.sleep(1.2)
        webbrowser.open(url)

    import threading
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run("api.app:app", host="127.0.0.1", port=port, reload=False)

if __name__ == "__main__":
    main()

"""One-time local setup: venv deps + merge .env from .env.example."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
REQUIREMENTS = ROOT / "requirements.txt"
EXTRA_PACKAGES = ("qdrant-client", "pypdf", "fastembed>=0.7.0")


def merge_env() -> None:
    if not ENV_EXAMPLE.exists():
        print("Missing .env.example")
        return

    example_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    existing: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            existing[key.strip()] = value

    out: list[str] = []
    for line in example_lines:
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, _, default = line.partition("=")
        key = key.strip()
        value = existing.get(key, default)
        if value:
            out.append(f"{key}={value}")
        else:
            out.append(f"{key}=")

    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {ENV_FILE}")


def install_deps() -> None:
    if not VENV_PYTHON.exists():
        print("Creating venv with Python 3.10...")
        subprocess.check_call(["py", "-3.10", "-m", "venv", str(ROOT / ".venv")])

    subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", *EXTRA_PACKAGES])
    print("Dependencies installed.")


def check_required_env() -> list[str]:
    if not ENV_FILE.exists():
        return [".env file missing"]
    missing: list[str] = []
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()

    for key in (
        "PG_HOST",
        "PG_DB",
        "PG_USER",
        "PG_PASSWORD",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "JWT_SECRET",
        "QDRANT_HOST",
        "QDRANT_API_KEY",
    ):
        if not values.get(key):
            missing.append(key)
    return missing


def main() -> int:
    merge_env()
    install_deps()
    missing = check_required_env()
    if missing:
        print("\nAdd these to .env before starting the API:")
        for key in missing:
            print(f"  - {key}")
        return 1
    print("\nLocal setup complete. Run: run_local_api.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

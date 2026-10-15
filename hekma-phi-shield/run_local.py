#!/usr/bin/env python3
"""Bootstrap a local PHI-PII environment and start the FastAPI server."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import time
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_ADMIN_PORT = 8083
VENV_DIRNAME = ".venv"
REQUIREMENTS_FILE = "requirements.txt"
DEPS_STAMP_NAME = ".deps_installed"
FRONTEND_REL = Path("admin_dashboard") / "frontend"
MODEL_REL = Path("models") / "roberta-pii-synthetic" / "model.safetensors"


class LocalRunnerError(RuntimeError):
    """Raised when local setup or startup cannot continue."""


def admin_port_for(api_port: int) -> int:
    """Agent binds 8083 next to the default API port, otherwise API port + 3."""
    if api_port == DEFAULT_PORT:
        return DEFAULT_ADMIN_PORT
    return api_port + 3


@dataclass(frozen=True)
class RunnerConfig:
    """CLI options for a local run."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    skip_deps: bool = False
    force_deps: bool = False
    skip_frontend: bool = False
    reload: bool = True
    free_port: bool = False


class ProjectPaths:
    """Resolves fixed paths for a PHI-PII checkout."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.venv_dir = self.root / VENV_DIRNAME
        self.requirements = self.root / REQUIREMENTS_FILE
        self.deps_stamp = self.venv_dir / DEPS_STAMP_NAME
        self.frontend_dir = self.root / FRONTEND_REL
        self.frontend_dist = self.frontend_dir / "dist"
        self.model_weights = self.root / MODEL_REL

    @property
    def venv_python(self) -> Path:
        """Return the venv interpreter path for the current OS."""
        if os.name == "nt":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"


class CommandRunner:
    """Runs subprocess commands with shared failure handling."""

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        check: bool = True,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a command; raise LocalRunnerError when check fails."""
        try:
            return subprocess.run(
                list(command),
                cwd=str(cwd) if cwd else None,
                check=check,
                capture_output=capture_output,
                text=True,
            )
        except FileNotFoundError as exc:
            raise LocalRunnerError(f"Command not found: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            message = f"Command failed ({exc.returncode}): {' '.join(command)}"
            if detail:
                message = f"{message}\n{detail}"
            raise LocalRunnerError(message) from exc


class DependencyInstaller:
    """Creates the project venv and installs Python requirements when needed."""

    def __init__(self, paths: ProjectPaths, commands: CommandRunner) -> None:
        self._paths = paths
        self._commands = commands

    def ensure_venv(self) -> Path:
        """Create `.venv` if missing; return the interpreter path."""
        python = self._paths.venv_python
        if python.is_file():
            return python
        print(f"Creating virtualenv at {self._paths.venv_dir} ...")
        venv.create(self._paths.venv_dir, with_pip=True)
        if not python.is_file():
            raise LocalRunnerError(f"Virtualenv created but interpreter missing: {python}")
        return python

    def requirements_hash(self) -> str:
        """SHA-256 of requirements.txt; used to detect when a reinstall is needed."""
        if not self._paths.requirements.is_file():
            raise LocalRunnerError(f"Missing requirements file: {self._paths.requirements}")
        digest = hashlib.sha256()
        digest.update(self._paths.requirements.read_bytes())
        return digest.hexdigest()

    def needs_install(self, force: bool = False) -> bool:
        """True on first install, after requirements change, or when force is set."""
        if force:
            return True
        stamp = self._paths.deps_stamp
        if not stamp.is_file():
            return True
        return stamp.read_text(encoding="utf-8").strip() != self.requirements_hash()

    def install_requirements(self, python: Path, *, force: bool = False) -> None:
        """Install requirements.txt only when missing, changed, or forced."""
        if not self.needs_install(force=force):
            print("Python dependencies already installed; skipping pip install.")
            return

        print("Installing Python dependencies (this can take a few minutes)...")
        self._commands.run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip"],
            cwd=self._paths.root,
        )
        self._commands.run(
            [str(python), "-m", "pip", "install", "-r", str(self._paths.requirements)],
            cwd=self._paths.root,
        )
        self._paths.deps_stamp.write_text(self.requirements_hash() + "\n", encoding="utf-8")
        print("Dependencies installed.")


class FrontendBuilder:
    """Builds the admin dashboard when Node/npm are available."""

    def __init__(self, paths: ProjectPaths, commands: CommandRunner) -> None:
        self._paths = paths
        self._commands = commands

    def build_if_possible(self) -> bool:
        """Build admin UI; return True when dist is ready, False when skipped."""
        if self._paths.frontend_dist.is_dir() and any(self._paths.frontend_dist.iterdir()):
            print(f"Admin UI already built at {self._paths.frontend_dist}")
            return True

        npm = shutil.which("npm")
        if not npm:
            print(
                "Skipping admin UI build (npm not found). "
                "Validation console still works at / ; /admin needs a frontend build."
            )
            return False

        package_json = self._paths.frontend_dir / "package.json"
        if not package_json.is_file():
            print(f"Skipping admin UI build (missing {package_json})")
            return False

        node_modules = self._paths.frontend_dir / "node_modules"
        if not node_modules.is_dir():
            print("Installing frontend npm dependencies...")
            self._commands.run([npm, "install"], cwd=self._paths.frontend_dir)

        print("Building admin dashboard...")
        self._commands.run([npm, "run", "build"], cwd=self._paths.frontend_dir)
        return True


class PortManager:
    """Optionally frees a TCP port before binding the API server."""

    def __init__(self, commands: CommandRunner) -> None:
        self._commands = commands

    def free(self, port: int) -> None:
        """Kill processes listening on port when lsof is available (Unix)."""
        if os.name == "nt":
            print("Port free skipped on Windows; ensure the port is unused.")
            return
        if not shutil.which("lsof"):
            print("Port free skipped (lsof not found).")
            return

        result = self._commands.run(
            ["lsof", "-t", f"-i:{port}"],
            check=False,
            capture_output=True,
        )
        pids = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        if not pids:
            return

        for pid in pids:
            print(f"Stopping process {pid} on port {port}...")
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                continue
        time.sleep(0.5)


class ApiServer:
    """Runs the FastAPI app via uvicorn in a child process."""

    def __init__(self, paths: ProjectPaths, commands: CommandRunner) -> None:
        self._paths = paths
        self._commands = commands
        self._proc: Optional[subprocess.Popen[str]] = None

    def start(
        self,
        python: Path,
        config: RunnerConfig,
        *,
        app: str = "api.main:app",
        port: Optional[int] = None,
        label: str = "API",
    ) -> subprocess.Popen[str]:
        """Launch uvicorn and return the running process handle."""
        bind_port = config.port if port is None else port
        cmd = [
            str(python),
            "-m",
            "uvicorn",
            app,
            "--host",
            config.host,
            "--port",
            str(bind_port),
        ]
        if config.reload:
            cmd.append("--reload")

        print(f"Starting {label} on http://{config.host}:{bind_port} ...")
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(self._paths.root),
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return self._proc

    def stop(self) -> None:
        """Terminate the uvicorn child if it is still running."""
        if self._proc is None or self._proc.poll() is not None:
            return
        print("\nShutting down API server...")
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)


class LocalRunner:
    """Orchestrates env checks, dependency install, optional UI build, and server start."""

    def __init__(
        self,
        paths: ProjectPaths,
        deps: DependencyInstaller,
        frontend: FrontendBuilder,
        ports: PortManager,
        server: ApiServer,
        agent: Optional[ApiServer] = None,
    ) -> None:
        self._paths = paths
        self._deps = deps
        self._frontend = frontend
        self._ports = ports
        self._server = server
        self._agent = agent or ApiServer(paths, server._commands)

    def validate_checkout(self) -> None:
        """Fail fast when the repo is missing required model weights or API package."""
        if not (self._paths.root / "api" / "main.py").is_file():
            raise LocalRunnerError(f"api/main.py not found under {self._paths.root}")
        if not self._paths.model_weights.is_file():
            raise LocalRunnerError(
                f"Model weights missing: {self._paths.model_weights}\n"
                "Clone the full repo (including models/roberta-pii-synthetic/)."
            )

    def resolve_python(self, skip_deps: bool, force_deps: bool = False) -> Path:
        """Return the interpreter to use, creating/installing into `.venv` unless skipped."""
        if skip_deps:
            existing = self._paths.venv_python
            if existing.is_file():
                return existing
            print("skip-deps set and no .venv found; using current Python interpreter.")
            return Path(sys.executable)

        python = self._deps.ensure_venv()
        self._deps.install_requirements(python, force=force_deps)
        return python

    def run(self, config: RunnerConfig) -> int:
        """Set up the environment, start the server, and block until exit."""
        self.validate_checkout()
        python = self.resolve_python(config.skip_deps, force_deps=config.force_deps)

        if not config.skip_frontend:
            self._frontend.build_if_possible()
        else:
            print("Skipping admin UI build (--skip-frontend).")

        agent_port = admin_port_for(config.port)
        if config.free_port:
            self._ports.free(config.port)
            self._ports.free(agent_port)

        proc = self._server.start(python, config)
        self._agent.start(
            python,
            config,
            app="admin_dashboard.backend.main:app",
            port=agent_port,
            label="Admin",
        )
        self._print_urls(config)

        def _shutdown(_signum: int, _frame: object) -> None:
            self._agent.stop()
            self._server.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        return_code = proc.wait()
        self._agent.stop()
        return int(return_code or 0)

    @staticmethod
    def _print_urls(config: RunnerConfig) -> None:
        """Print the local URLs operators should open after startup."""
        api_base = f"http://{config.host}:{config.port}"
        admin_base = f"http://{config.host}:{admin_port_for(config.port)}"
        print()
        print("=" * 60)
        print("  PHI-PII local servers are running")
        print(f"  Validation console : {api_base}/")
        print(f"  API docs           : {api_base}/docs")
        print(f"  API health         : {api_base}/health")
        print(f"  Admin dashboard    : {admin_base}/admin/")
        print(f"  Admin docs         : {admin_base}/docs")
        print(f"  Admin health       : {admin_base}/health")
        print("  Press Ctrl+C to stop.")
        print("=" * 60)
        print()


def build_runner(root: Optional[Path] = None) -> LocalRunner:
    """Wire default collaborators for the CLI entrypoint."""
    paths = ProjectPaths(root or Path(__file__).resolve().parent)
    commands = CommandRunner()
    return LocalRunner(
        paths=paths,
        deps=DependencyInstaller(paths, commands),
        frontend=FrontendBuilder(paths, commands),
        ports=PortManager(commands),
        server=ApiServer(paths, commands),
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> RunnerConfig:
    """Parse CLI flags into a RunnerConfig."""
    parser = argparse.ArgumentParser(
        description="Create a local venv, install deps, and run the PHI-PII API.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default {DEFAULT_HOST})")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Bind port (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip venv creation and pip install entirely",
    )
    parser.add_argument(
        "--force-deps",
        action="store_true",
        help="Reinstall Python deps even if already installed",
    )
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip admin dashboard npm build",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload (dev)",
    )
    parser.add_argument(
        "--free-port",
        action="store_true",
        help="Terminate processes already listening on --port before start",
    )
    args = parser.parse_args(argv)
    return RunnerConfig(
        host=args.host,
        port=args.port,
        skip_deps=args.skip_deps,
        force_deps=args.force_deps,
        skip_frontend=args.skip_frontend,
        reload=args.reload,
        free_port=args.free_port,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry: parse args and run the local stack."""
    config = parse_args(argv)
    runner = build_runner()
    try:
        return runner.run(config)
    except LocalRunnerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

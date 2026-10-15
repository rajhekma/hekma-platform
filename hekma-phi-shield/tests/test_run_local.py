"""Unit tests for the local PHI-PII bootstrap runner."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run_local import (
    ApiServer,
    CommandRunner,
    DependencyInstaller,
    FrontendBuilder,
    LocalRunner,
    LocalRunnerError,
    PortManager,
    ProjectPaths,
    RunnerConfig,
    admin_port_for,
    parse_args,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """Minimal checkout layout for path/validation tests."""
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "main.py").write_text("# stub\n", encoding="utf-8")
    model_dir = tmp_path / "models" / "roberta-pii-synthetic"
    model_dir.mkdir(parents=True)
    (model_dir / "model.safetensors").write_bytes(b"weights")
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    frontend = tmp_path / "admin_dashboard" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_project_paths_venv_python_posix(repo_root: Path) -> None:
    """Venv interpreter lives under bin/ on non-Windows."""
    paths = ProjectPaths(repo_root)
    with patch("run_local.os.name", "posix"):
        assert paths.venv_python == paths.venv_dir / "bin" / "python"


def test_parse_args_defaults() -> None:
    """CLI defaults bind localhost:8080 with installs enabled."""
    config = parse_args([])
    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.skip_deps is False
    assert config.force_deps is False
    assert config.skip_frontend is False
    assert config.reload is False
    assert config.free_port is False


def test_parse_args_flags() -> None:
    """Boolean flags map onto RunnerConfig."""
    config = parse_args(
        ["--skip-deps", "--force-deps", "--skip-frontend", "--reload", "--free-port", "--port", "9000"]
    )
    assert config.skip_deps is True
    assert config.force_deps is True
    assert config.skip_frontend is True
    assert config.reload is True
    assert config.free_port is True
    assert config.port == 9000


def test_deps_install_skipped_when_stamp_matches(repo_root: Path) -> None:
    """Matching stamp means pip install is not run again."""
    paths = ProjectPaths(repo_root)
    paths.venv_dir.mkdir()
    installer = DependencyInstaller(paths, MagicMock(spec=CommandRunner))
    paths.deps_stamp.write_text(installer.requirements_hash() + "\n", encoding="utf-8")
    assert installer.needs_install() is False
    installer.install_requirements(Path("/tmp/python"))
    installer._commands.run.assert_not_called()


def test_deps_install_runs_when_stamp_missing(repo_root: Path) -> None:
    """First run (no stamp) triggers pip install and writes the stamp."""
    paths = ProjectPaths(repo_root)
    paths.venv_dir.mkdir()
    commands = MagicMock(spec=CommandRunner)
    installer = DependencyInstaller(paths, commands)
    assert installer.needs_install() is True
    installer.install_requirements(Path("/tmp/python"))
    assert commands.run.call_count == 2
    assert paths.deps_stamp.is_file()
    assert paths.deps_stamp.read_text(encoding="utf-8").strip() == installer.requirements_hash()


def test_deps_install_runs_when_requirements_change(repo_root: Path) -> None:
    """Changed requirements.txt invalidates the stamp."""
    paths = ProjectPaths(repo_root)
    paths.venv_dir.mkdir()
    paths.deps_stamp.write_text("stale-hash\n", encoding="utf-8")
    commands = MagicMock(spec=CommandRunner)
    installer = DependencyInstaller(paths, commands)
    assert installer.needs_install() is True
    installer.install_requirements(Path("/tmp/python"))
    assert commands.run.call_count == 2


def test_deps_force_reinstall(repo_root: Path) -> None:
    """force=True reinstalls even when the stamp matches."""
    paths = ProjectPaths(repo_root)
    paths.venv_dir.mkdir()
    commands = MagicMock(spec=CommandRunner)
    installer = DependencyInstaller(paths, commands)
    paths.deps_stamp.write_text(installer.requirements_hash() + "\n", encoding="utf-8")
    assert installer.needs_install(force=True) is True
    installer.install_requirements(Path("/tmp/python"), force=True)
    assert commands.run.call_count == 2


def test_command_runner_raises_on_missing_binary() -> None:
    """Missing executables become LocalRunnerError."""
    runner = CommandRunner()
    with pytest.raises(LocalRunnerError, match="Command not found"):
        runner.run(["definitely-not-a-real-binary-xyz"])


def test_command_runner_raises_on_nonzero() -> None:
    """Non-zero exits surface as LocalRunnerError."""
    runner = CommandRunner()
    with patch("run_local.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["false"])):
        with pytest.raises(LocalRunnerError, match="Command failed"):
            runner.run(["false"])


def test_validate_checkout_requires_model(repo_root: Path) -> None:
    """Missing model weights fail validation."""
    (repo_root / "models" / "roberta-pii-synthetic" / "model.safetensors").unlink()
    paths = ProjectPaths(repo_root)
    commands = CommandRunner()
    runner = LocalRunner(
        paths=paths,
        deps=DependencyInstaller(paths, commands),
        frontend=FrontendBuilder(paths, commands),
        ports=PortManager(commands),
        server=ApiServer(paths, commands),
    )
    with pytest.raises(LocalRunnerError, match="Model weights missing"):
        runner.validate_checkout()


def test_validate_checkout_ok(repo_root: Path) -> None:
    """Complete checkout passes validation."""
    paths = ProjectPaths(repo_root)
    commands = CommandRunner()
    runner = LocalRunner(
        paths=paths,
        deps=DependencyInstaller(paths, commands),
        frontend=FrontendBuilder(paths, commands),
        ports=PortManager(commands),
        server=ApiServer(paths, commands),
    )
    runner.validate_checkout()


def test_frontend_builder_skips_without_npm(repo_root: Path) -> None:
    """No npm means build is skipped without error."""
    paths = ProjectPaths(repo_root)
    commands = MagicMock(spec=CommandRunner)
    builder = FrontendBuilder(paths, commands)
    with patch("run_local.shutil.which", return_value=None):
        assert builder.build_if_possible() is False
    commands.run.assert_not_called()


def test_frontend_builder_uses_existing_dist(repo_root: Path) -> None:
    """Existing dist short-circuits the build."""
    dist = repo_root / "admin_dashboard" / "frontend" / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    paths = ProjectPaths(repo_root)
    commands = MagicMock(spec=CommandRunner)
    builder = FrontendBuilder(paths, commands)
    assert builder.build_if_possible() is True
    commands.run.assert_not_called()


def test_frontend_builder_runs_npm(repo_root: Path) -> None:
    """When npm exists, install + build are invoked."""
    paths = ProjectPaths(repo_root)
    commands = MagicMock(spec=CommandRunner)
    builder = FrontendBuilder(paths, commands)
    with patch("run_local.shutil.which", return_value="/usr/bin/npm"):
        assert builder.build_if_possible() is True
    assert commands.run.call_count == 2
    first_cmd = commands.run.call_args_list[0].args[0]
    second_cmd = commands.run.call_args_list[1].args[0]
    assert first_cmd == ["/usr/bin/npm", "install"]
    assert second_cmd == ["/usr/bin/npm", "run", "build"]


def test_resolve_python_skip_deps_falls_back_to_sys(repo_root: Path) -> None:
    """skip-deps without a venv uses the current interpreter."""
    paths = ProjectPaths(repo_root)
    commands = MagicMock(spec=CommandRunner)
    runner = LocalRunner(
        paths=paths,
        deps=DependencyInstaller(paths, commands),
        frontend=FrontendBuilder(paths, commands),
        ports=PortManager(commands),
        server=ApiServer(paths, commands),
    )
    python = runner.resolve_python(skip_deps=True)
    assert python == Path(__import__("sys").executable)


def test_api_server_start_command(repo_root: Path) -> None:
    """uvicorn is launched with host/port from config."""
    paths = ProjectPaths(repo_root)
    commands = MagicMock(spec=CommandRunner)
    server = ApiServer(paths, commands)
    fake_proc = MagicMock()
    config = RunnerConfig(host="0.0.0.0", port=8081, reload=True)
    with patch("run_local.subprocess.Popen", return_value=fake_proc) as popen:
        proc = server.start(Path("/tmp/python"), config)
    assert proc is fake_proc
    cmd = popen.call_args.args[0]
    assert cmd[:4] == ["/tmp/python", "-m", "uvicorn", "api.main:app"]
    assert "--host" in cmd and "0.0.0.0" in cmd
    assert "--port" in cmd and "8081" in cmd
    assert "--reload" in cmd


def test_admin_port_for_default_and_override() -> None:
    """Default API port keeps the agent on 8083; any other port is API + 3."""
    assert admin_port_for(8080) == 8083
    assert admin_port_for(9000) == 9003


def test_run_starts_api_and_agent(repo_root: Path) -> None:
    """Local run starts detection on the API port and admin on the agent port."""
    paths = ProjectPaths(repo_root)
    commands = MagicMock(spec=CommandRunner)
    runner = LocalRunner(
        paths=paths,
        deps=DependencyInstaller(paths, commands),
        frontend=FrontendBuilder(paths, commands),
        ports=PortManager(commands),
        server=ApiServer(paths, commands),
    )
    config = RunnerConfig(port=8080, skip_frontend=True, free_port=True)
    fake_api = MagicMock()
    fake_api.wait.return_value = 0
    with (
        patch.object(runner, "resolve_python", return_value=Path("/tmp/python")),
        patch.object(runner._ports, "free") as free,
        patch.object(runner._server, "start", return_value=fake_api) as api_start,
        patch.object(runner._agent, "start", return_value=MagicMock()) as agent_start,
        patch.object(runner._agent, "stop") as agent_stop,
    ):
        code = runner.run(config)
    assert code == 0
    assert free.call_args_list[0].args == (8080,)
    assert free.call_args_list[1].args == (8083,)
    api_start.assert_called_once()
    agent_start.assert_called_once()
    assert agent_start.call_args.kwargs["app"] == "admin_dashboard.backend.main:app"
    assert agent_start.call_args.kwargs["port"] == 8083
    agent_stop.assert_called_once()

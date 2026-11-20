"""PR #39 — release script defaults to non-deploying help/check behavior."""

from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deploy_staging_host.sh"


def test_release_script_has_valid_bash_syntax():
    completed = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_release_script_help_is_non_deploying():
    completed = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert completed.returncode == 0
    assert "--check" in completed.stdout
    assert "--apply" in completed.stdout


def test_release_script_rejects_unknown_arguments():
    completed = subprocess.run(["bash", str(SCRIPT), "--production"], capture_output=True, text=True)
    assert completed.returncode == 2


def test_release_script_never_uses_demo_compose_or_volume_removal():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "compose.demo.yml" not in source
    assert "down --volumes" not in source
    assert "compose.staging.yml" in source
    assert "PMWIZARD_BACKUP_VERIFIED" in source
    assert "PMWIZARD_STAGING_ACCESS_APPROVED" in source

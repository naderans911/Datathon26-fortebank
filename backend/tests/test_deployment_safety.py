"""Retired publishing entry points must not access project inputs or services."""
from pathlib import Path
import subprocess
import sys


def test_retired_space_uploader_refuses_without_project_files(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "deploy_hf.py"
    before = set(tmp_path.iterdir())
    # Isolated Python and an empty cwd prove no app dependencies, .env or models are required.
    result = subprocess.run([sys.executable, "-I", str(script), "synthetic-owner/synthetic-space"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "retired and unsupported" in result.stderr
    assert "python scripts/serve.py start --public" in result.stderr
    assert result.stdout == ""
    assert set(tmp_path.iterdir()) == before

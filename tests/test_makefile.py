"""``make`` with no target lists the targets, with or without a local.mk."""

import shutil
import subprocess
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parent.parent / "Makefile"


@pytest.mark.skipif(shutil.which("make") is None, reason="needs make")
@pytest.mark.parametrize("local", [False, True])
def test_the_target_listing_reads_this_makefile(tmp_path, local):
    shutil.copy(MAKEFILE, tmp_path / "Makefile")
    if local:
        (tmp_path / "local.mk").write_text("PYTHON = python3\n")
    result = subprocess.run(
        ["make"], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert "Call a specific subcommand:" in result.stdout
    assert "preset" in result.stdout.split()

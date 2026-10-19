"""The demo preset switcher, ``scripts/preset.py``."""

import re
from pathlib import Path

from scripts import preset

ROOT = Path(__file__).resolve().parent.parent


def test_the_documented_settings_example_reads_cleanly(tmp_path):
    """Copying the setup guide's ``.preset-settings`` block gives values a
    server can use: a remark on a value's line would become part of it."""
    setup = (ROOT / "docs/developer/setup.md").read_text()
    block = re.search(r"# \.preset-settings\n(.*?)\n\n", setup, re.S).group(1)
    path = tmp_path / ".preset-settings"
    path.write_text(block)
    values = preset.read_env_file(path)
    assert values["DJANGO_EMAIL_HOST"] == "localhost"
    assert values["DJANGO_EMAIL_PORT"] == "1025"

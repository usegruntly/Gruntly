"""The suite can never start the real Claude Code (a paid call on your own login) by accident: see `never_start_the_real_claude` in tests/conftest.py."""
import os
import shutil
import subprocess
import sys

import pytest


def test_a_test_that_reaches_the_real_claude_fails_instead_of_spending_money():
    exe = shutil.which("claude")
    if not exe:
        pytest.skip("no claude on PATH, nothing to guard against here")
    with pytest.raises(RuntimeError, match="paid call"):
        subprocess.run([exe, "--version"])


def test_a_stand_in_under_the_temp_folder_is_allowed(tmp_path):
    name = "claude.cmd" if os.name == "nt" else "claude"
    fake = tmp_path / name
    fake.write_text("@echo off\r\necho stand-in\r\n" if os.name == "nt" else "#!/bin/sh\necho stand-in\n", encoding="utf8")
    fake.chmod(0o755)
    r = subprocess.run([str(fake)], capture_output=True, text=True)
    assert "stand-in" in r.stdout


def test_other_programs_are_not_touched():
    assert subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True).stdout.strip() == "ok"

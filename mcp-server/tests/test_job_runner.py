from __future__ import annotations

import unittest
from pathlib import Path
import shutil

from core.job_runner import _unique_output_dir

TEST_TMP_ROOT = Path(__file__).resolve().parent / ".tmp" / "job-runner"


class JobRunnerTests(unittest.TestCase):
    def test_unique_output_dir_keeps_base_when_missing(self) -> None:
        shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        base = TEST_TMP_ROOT / "job-a"
        self.assertEqual(_unique_output_dir(base), base)

    def test_unique_output_dir_avoids_existing_directory(self) -> None:
        shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)
        base = TEST_TMP_ROOT / "job-a"
        base.mkdir()
        resolved = _unique_output_dir(base)
        self.assertNotEqual(resolved, base)
        self.assertTrue(resolved.name.startswith("job-a-"))

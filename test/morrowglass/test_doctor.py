import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.morrowglass.doctor import (
    Check,
    _check_local_kokoro,
    required_checks_pass,
)


class DoctorTests(unittest.TestCase):
    def test_optional_failure_does_not_fail_doctor(self):
        checks = [
            Check("required", True, "ok"),
            Check(
                "optional",
                False,
                "missing",
                required=False,
            ),
        ]
        self.assertTrue(
            required_checks_pass(checks)
        )

    def test_required_failure_fails_doctor(self):
        checks = [
            Check(
                "required",
                False,
                "missing",
            ),
            Check(
                "optional",
                True,
                "ok",
                required=False,
            ),
        ]
        self.assertFalse(
            required_checks_pass(checks)
        )

    def test_local_kokoro_python_can_be_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            python_path = (
                Path(directory)
                / "python.exe"
            )
            python_path.write_bytes(b"x")
            result = Mock()
            result.returncode = 0
            result.stdout = "kokoro-ok"
            result.stderr = ""

            with patch(
                "app.morrowglass.doctor.subprocess.run",
                return_value=result,
            ) as run:
                check = _check_local_kokoro(
                    python_path
                )

        self.assertTrue(check.ok)
        self.assertFalse(check.required)
        self.assertEqual(
            run.call_args.args[0][0],
            str(python_path),
        )

    def test_missing_local_kokoro_is_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            check = _check_local_kokoro(
                Path(directory)
                / "missing.exe"
            )
        self.assertFalse(check.ok)
        self.assertFalse(check.required)


if __name__ == "__main__":
    unittest.main()

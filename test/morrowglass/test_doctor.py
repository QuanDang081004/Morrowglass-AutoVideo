import unittest

from app.morrowglass.doctor import Check, required_checks_pass


class DoctorTests(unittest.TestCase):
    def test_optional_failure_does_not_fail_doctor(self):
        checks = [
            Check("required", True, "ok"),
            Check("optional", False, "missing", required=False),
        ]
        self.assertTrue(required_checks_pass(checks))

    def test_required_failure_fails_doctor(self):
        checks = [
            Check("required", False, "missing"),
            Check("optional", True, "ok", required=False),
        ]
        self.assertFalse(required_checks_pass(checks))


if __name__ == "__main__":
    unittest.main()

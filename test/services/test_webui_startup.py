import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).parent.parent.parent
WEBUI_MAIN = ROOT_DIR / "webui" / "Main.py"


class TestWebuiStartup(unittest.TestCase):
    def test_pending_project_switch_applies_before_widget_state(self):
        source = (
            ROOT_DIR
            / "webui"
            / "Morrowglass.py"
        ).read_text(
            encoding="utf-8"
        )
        namespace = {}
        start = source.index(
            "def _apply_pending_project_switch("
        )
        end = source.index(
            "\ndef _queue_project_switch(",
            start,
        )
        helper_source = source[
            start:end
        ]
        exec(
            helper_source,
            namespace,
        )
        apply_switch = namespace[
            "_apply_pending_project_switch"
        ]

        state = {
            "morrowglass_project_folder": (
                r"D:\Morrowglass-AutoVideo\storage\morrowglass\video-001"
            ),
            "morrowglass_pending_project_folder": (
                r"D:\Morrowglass-AutoVideo\storage\morrowglass\tiktok-test-01"
            ),
        }
        apply_switch(
            state,
            default_project="unused",
        )
        self.assertEqual(
            state[
                "morrowglass_project_folder"
            ],
            (
                r"D:\Morrowglass-AutoVideo\storage\morrowglass\tiktok-test-01"
            ),
        )
        self.assertNotIn(
            "morrowglass_pending_project_folder",
            state,
        )

    def test_external_directory_prefers_project_app_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            conflicting_root = temp_path / "site-packages"
            conflicting_app = conflicting_root / "app"
            conflicting_app.mkdir(parents=True)
            (conflicting_app / "__init__.py").write_text(
                'source = "conflicting dependency"\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            existing_pythonpath = env.get("PYTHONPATH")
            env["PYTHONPATH"] = os.pathsep.join(
                part
                for part in (str(conflicting_root), existing_pythonpath)
                if part
            )
            script = textwrap.dedent(
                f"""
                from pathlib import Path
                from streamlit.testing.v1 import AppTest

                app = AppTest.from_file({str(WEBUI_MAIN)!r}, default_timeout=30)
                app.run()
                if app.exception:
                    raise RuntimeError([str(item.value) for item in app.exception])

                import app.config

                project_root = Path({str(ROOT_DIR)!r}).resolve()
                imported_config = Path(app.config.__file__).resolve()
                if project_root not in imported_config.parents:
                    raise RuntimeError(
                        f"app.config resolved outside project: {{imported_config}}"
                    )
                """
            )

            result = subprocess.run(
                [sys.executable, "-X", "utf8", "-c", script],
                cwd=temp_path,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()

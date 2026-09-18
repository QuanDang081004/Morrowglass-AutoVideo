import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.morrowglass.comfyui import (
    ComfyUIClient,
    _extract_outputs,
    load_api_workflow,
    prepare_workflow,
)


class ComfyUIWorkflowTests(unittest.TestCase):
    def test_prepare_workflow_preserves_types(self):
        workflow = {
            "1": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": "{{SEED}}",
                    "prompt": "{{PROMPT}}",
                },
            },
            "2": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": "{{WIDTH}}",
                    "height": "{{HEIGHT}}",
                },
            },
        }
        result = prepare_workflow(
            workflow,
            prompt="historical scene",
            seed=123,
            width=1920,
            height=1080,
        )
        self.assertEqual(result["1"]["inputs"]["seed"], 123)
        self.assertEqual(
            result["1"]["inputs"]["prompt"],
            "historical scene",
        )
        self.assertEqual(result["2"]["inputs"]["width"], 1920)

    def test_load_rejects_ui_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.json"
            path.write_text(
                json.dumps({"nodes": [], "links": []}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_api_workflow(path)

    def test_extract_outputs_supports_video(self):
        entry = {
            "outputs": {
                "10": {
                    "gifs": [
                        {
                            "filename": "x.mp4",
                            "subfolder": "video",
                            "type": "output",
                        }
                    ]
                }
            }
        }
        outputs = _extract_outputs(entry)
        self.assertEqual(outputs[0].filename, "x.mp4")
        self.assertEqual(outputs[0].subfolder, "video")

    @patch("app.morrowglass.comfyui.requests.post")
    def test_queue_prompt_returns_id(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "prompt_id": "abc",
            "node_errors": {},
        }
        post.return_value = response
        client = ComfyUIClient("http://127.0.0.1:8188")
        prompt_id = client.queue_prompt(
            {
                "1": {
                    "class_type": "Test",
                    "inputs": {},
                }
            }
        )
        self.assertEqual(prompt_id, "abc")


if __name__ == "__main__":
    unittest.main()

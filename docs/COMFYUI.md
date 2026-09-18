# ComfyUI integration

Morrowglass supports a **generic ComfyUI API-workflow adapter** rather than
hard-coding one model. This lets the same integration drive Flux/SDXL image
workflows and Wan/other image-to-video workflows.

## Workflow format

In ComfyUI use:

```text
File -> Export Workflow (API)
```

Do not use the normal save-format JSON containing `nodes` and `links`.

## Supported placeholders

Place these literal values inside the exported API workflow wherever the
corresponding input belongs:

```text
{{PROMPT}}
{{NEGATIVE_PROMPT}}
{{MOTION_PROMPT}}
{{SEED}}
{{WIDTH}}
{{HEIGHT}}
{{INPUT_IMAGE}}
{{OUTPUT_PREFIX}}
```

Exact placeholders preserve the input type. For example `"{{SEED}}"` becomes
an integer and `"{{WIDTH}}"` becomes an integer before submission.

Example:

```json
{
  "3": {
    "class_type": "KSampler",
    "inputs": {
      "seed": "{{SEED}}"
    }
  },
  "6": {
    "class_type": "CLIPTextEncode",
    "inputs": {
      "text": "{{PROMPT}}"
    }
  },
  "9": {
    "class_type": "SaveImage",
    "inputs": {
      "filename_prefix": "{{OUTPUT_PREFIX}}"
    }
  }
}
```

## Default paths

A project can carry its own workflows:

```text
Video02/
  workflows/
    image.json
    video.json
```

Or set global paths:

```bat
set MORROWGLASS_COMFYUI_URL=http://127.0.0.1:8188
set MORROWGLASS_COMFYUI_IMAGE_WORKFLOW=D:\Morrowglass\workflows\image.json
set MORROWGLASS_COMFYUI_VIDEO_WORKFLOW=D:\Morrowglass\workflows\video.json
```

The adapter submits the API graph through ComfyUI, polls execution history,
then downloads the selected image/video output into the Morrowglass project.

# Morrowglass AutoVideo

Scene-aware automation layer for MoneyPrinterTurbo. Development happens on **morrowglass-dev**.

## Current pipeline

```text
final script
  -> auto Visual Bible
  -> Scene Director
  -> per-scene image + motion prompts
  -> Kokoro / MPT TTS
  -> faster-whisper word timing
  -> exact scene timeline
  -> AUTO / HYBRID / MANUAL assets
     -> ComfyUI image workflow OR MPT image backend
     -> technical + optional semantic QC/retry
     -> optional ComfyUI image-to-video for motion scenes
  -> exact-duration scene renderer
  -> incremental per-scene render cache
  -> readable subtitles + optional BGM
  -> output/morrowglass_final.mp4
```

## Implemented

### Phase 1 — scene intelligence
- final script -> chronological scene manifest
- MPT LLM reuse + deterministic fallback
- image and motion prompt per scene
- Visual Bible for historical continuity
- hybrid/manual asset discovery

### Phase 2 — narration and timing
- MPT TTS reuse, including Kokoro voices such as `kokoro:am_michael`
- narration audio generation
- faster-whisper word-level SRT
- automatic contiguous scene start/end timing written to `project.json`

### Phase 3 — scene-aware render
- exact-duration scene clips instead of a global `video_clip_duration`
- images hold for the exact scene duration
- videos trim or loop to the exact scene duration
- 1920x1080 cover/contain normalization through FFmpeg
- deterministic chronological concat
- word timing -> readable caption chunks
- reuse MPT final compositor for narration, subtitles and BGM
- final output: `output/morrowglass_final.mp4`

### Phase 4 — AUTO images and QC
- MPT OpenAI-compatible text-to-image backend is called with the **scene prompt**, not a generic keyword
- generated files use scene names such as `scene_001.png`
- technical image QC checks decodeability and useful resolution
- optional OpenAI-compatible vision QC checks scene match, anachronisms and visible generation defects
- failed candidates are moved to `cache/rejected_images/`
- AUTO mode retries candidates; HYBRID mode remains available

### Phase 5 — documentary motion, continuity and incremental rebuild
- Visual Bible can be auto-enriched from the final script
- user-supplied period/location/character facts always override inferred values
- still images can use subtle deterministic Ken Burns motion
- scene clip fingerprints allow unchanged scenes to reuse render cache
- replacing one visual does not require rebuilding every scene clip

### Phase 6 — direct ComfyUI image/video workflows
- generic ComfyUI API-format workflow adapter
- no hard-coded model or node IDs
- supported placeholders:
  - `{{PROMPT}}`
  - `{{NEGATIVE_PROMPT}}`
  - `{{MOTION_PROMPT}}`
  - `{{SEED}}`
  - `{{WIDTH}}`
  - `{{HEIGHT}}`
  - `{{INPUT_IMAGE}}`
  - `{{OUTPUT_PREFIX}}`
- AUTO image provider can select ComfyUI or fall back to MPT's existing image backend
- Scene Director marks motion-worthy scenes; only those scenes are sent to the ComfyUI video workflow
- input images are uploaded to ComfyUI automatically
- generated video files replace the still image for that scene; failed video scenes safely fall back to the still image
- project-local defaults:
  - `workflows/image.json`
  - `workflows/video.json`

See `docs/COMFYUI.md` for workflow export and placeholder details.

## One-click Windows WebUI

After dependencies are installed, double-click:

```text
morrowglass_webui.bat
```

The dedicated UI provides:

- script paste box
- optional period/location; blank values can be inferred from script
- AUTO / HYBRID / MANUAL mode
- Kokoro voice and speed
- ComfyUI URL
- automatic image provider selection
- ComfyUI image workflow path
- ComfyUI video workflow path
- optional animation of motion scenes
- image QC/retry
- scene table with planned asset type
- image/video preview
- per-scene replacement upload
- incremental rendering
- final render
- Full run button

## CLI

Check the local environment:

```bat
python morrowglass.py doctor
```

Check a specific project's ComfyUI workflow discovery too:

```bat
python morrowglass.py doctor --project-dir D:\Morrowglass\Video02
```

HYBRID workflow:

```bat
python morrowglass.py run script.txt --project-dir D:\Morrowglass\Video02 --voice kokoro:am_michael
```

First HYBRID run creates the scene plan, narration, timing and prompt pack, then stops if assets are missing.

Use filenames such as:

```text
images/scene_001.png
images/scene_002.jpg
videos/scene_003.mp4
```

Run the same command again to render.

AUTO workflow:

```bat
python morrowglass.py run script.txt --project-dir D:\Morrowglass\Video02 --asset-mode auto --voice kokoro:am_michael
```

AUTO image provider priority when `--image-provider auto` is used:

1. project/global ComfyUI image workflow if present
2. MoneyPrinterTurbo OpenAI-compatible image backend
3. error with a clear HYBRID/manual fallback message

Force ComfyUI:

```bat
python morrowglass.py images --project-dir D:\Morrowglass\Video02 --image-provider comfyui --comfyui-url http://127.0.0.1:8188 --comfyui-image-workflow D:\Morrowglass\workflows\image.json
```

Generate motion scenes separately:

```bat
python morrowglass.py videos --project-dir D:\Morrowglass\Video02 --comfyui-url http://127.0.0.1:8188 --comfyui-video-workflow D:\Morrowglass\workflows\video.json
```

If `asset-mode=auto` and the project contains `workflows/video.json`, the normal `run` command automatically attempts image-to-video for scenes marked as motion-worthy. Failed video generations keep their still image so final rendering can continue.

Optional local BGM:

```bat
python morrowglass.py render --project-dir D:\Morrowglass\Video02 --bgm D:\Music\history.mp3 --bgm-volume 0.12
```

## Optional semantic vision QC

Technical QC always works locally. Semantic scene matching is enabled when these environment variables are present:

```bat
set MORROWGLASS_VISION_BASE_URL=http://127.0.0.1:1234/v1
set MORROWGLASS_VISION_MODEL=your-vision-model
set MORROWGLASS_VISION_API_KEY=
```

The endpoint must expose OpenAI-compatible `/chat/completions` and accept image URLs/data URIs.

Without a vision model, generated images still receive technical QC and can be reviewed/replaced in the Morrowglass WebUI.

## Git workflow

Development branch:

```text
morrowglass-dev
```

Draft PR:

```text
#1 Morrowglass AutoVideo: scene-aware pipeline (Phases 1-6)
```

## Remaining work

1. run full Windows end-to-end test with the actual Morrowglass Kokoro setup
2. install/test a real ComfyUI image workflow on the target GPU
3. install/test an image-to-video workflow such as Wan and tune duration/resolution for the target GPU
4. tune subtitle styling, BGM defaults and still-image motion against real channel output
5. long-video stress test for cache/resume behavior
6. only after those tests, merge the draft PR into `main`

<!-- CI trigger marker: Actions enabled on fork -->

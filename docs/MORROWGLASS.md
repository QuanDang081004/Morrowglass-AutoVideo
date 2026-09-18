# Morrowglass AutoVideo

Scene-aware automation layer for MoneyPrinterTurbo. Development happens on **morrowglass-dev**.

## Current pipeline

```text
final script
  -> Scene Director
  -> Visual Bible + scene prompts
  -> Kokoro / MPT TTS
  -> faster-whisper word timing
  -> exact scene timeline
  -> AUTO or HYBRID assets
  -> optional image semantic QC + retry
  -> exact-duration scene renderer
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
- generated files are renamed to `scene_001.png`, `scene_002.png`, ...
- technical image QC checks decodeability and useful resolution
- optional OpenAI-compatible vision QC checks scene match, anachronisms and visible generation defects
- failed candidates are moved to `cache/rejected_images/`
- AUTO mode retries candidates; HYBRID mode remains available

## One-click Windows WebUI

After the repository dependencies are installed, double-click:

```text
morrowglass_webui.bat
```

The dedicated UI opens on a local address (normally port 8510). It provides:

- script paste box
- historical period/location
- AUTO / HYBRID / MANUAL mode
- Kokoro voice and speed
- scene planning
- voice + Whisper timing
- automatic missing-image generation
- scene table
- image/video preview
- per-scene replacement upload
- final render
- Full run button

## CLI

Check the local environment:

```bat
python morrowglass.py doctor
```

HYBRID workflow:

```bat
python morrowglass.py run script.txt --project-dir D:\Morrowglass\Video02 --period "13th-century Japan" --voice kokoro:am_michael
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

AUTO images use MoneyPrinterTurbo's existing OpenAI-compatible image configuration:

```toml
openai_image_base_url = "http://127.0.0.1:7860/v1"
openai_image_model = "your-image-model"
openai_image_api_keys = []
```

The endpoint must implement the OpenAI-compatible `/images/generations` protocol. A local gateway can be used without an API key.

Generate/retry images separately:

```bat
python morrowglass.py images --project-dir D:\Morrowglass\Video02 --image-attempts 3 --min-qc-score 75
```

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

Without a vision model, generated images still receive technical QC and the user can review/replace them in the Morrowglass WebUI.

## Git workflow

Development branch:

```text
morrowglass-dev
```

Draft PR:

```text
#1 Morrowglass AutoVideo: scene-aware pipeline (Phases 1-4)
```

The fork contains an upstream CI workflow, but GitHub Actions may need to be enabled once on a newly created fork before PR checks appear.

## Remaining work

1. run full Windows end-to-end test with the actual Kokoro setup
2. tune subtitle style / still-image motion against a real Morrowglass video
3. optionally add a direct ComfyUI workflow adapter (without an OpenAI-compatible gateway)
4. optionally add scene-specific AI video / image-to-video providers
5. harden cache/resume behavior after real long-video testing

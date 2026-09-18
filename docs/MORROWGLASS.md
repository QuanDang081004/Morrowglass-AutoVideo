# Morrowglass AutoVideo

Scene-aware automation layer for MoneyPrinterTurbo. Development happens on **morrowglass-dev**.

## Implemented

### Phase 1 — scene intelligence
- script -> chronological scene manifest
- MPT LLM reuse + deterministic fallback
- image/motion prompt per scene
- Visual Bible for historical continuity
- hybrid/manual asset discovery
- SRT-aware scene timing

### Phase 2 — narration and timing
- MPT TTS reuse, including Kokoro voices such as kokoro:am_michael
- narration audio generation
- faster-whisper word-level SRT
- automatic scene start/end timing written back to project.json

## Current CLI

python morrowglass.py plan script.txt --project-dir D:\\Morrowglass\\Video02 --period "13th-century Japan" --asset-mode hybrid
python morrowglass.py voice --project-dir D:\\Morrowglass\\Video02 --voice kokoro:am_michael
python morrowglass.py status --project-dir D:\\Morrowglass\\Video02

## Next

1. scene-aware renderer using MPT/FFmpeg
2. final subtitle/BGM integration
3. WebUI controls
4. ComfyUI provider
5. visual QC + retries
6. optional image-to-video provider

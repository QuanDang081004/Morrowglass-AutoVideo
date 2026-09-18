# Morrowglass AutoVideo

Scene-aware automation layer for MoneyPrinterTurbo. Development happens on **morrowglass-dev**.

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
- images: hold for the exact scene duration
- videos: trim or loop to the exact scene duration
- 1920x1080 cover/contain normalization through FFmpeg
- deterministic chronological concat
- word timing -> readable caption chunks
- reuse MPT final compositor for narration, subtitles and BGM
- final output: `output/morrowglass_final.mp4`

## HYBRID workflow

```bat
python morrowglass.py run script.txt --project-dir D:\Morrowglass\Video02 --period "13th-century Japan" --voice kokoro:am_michael
```

First run:
1. plans scenes
2. creates prompt files
3. creates narration
4. creates word timing + scene timing
5. checks `images/` and `videos/`
6. stops and lists missing scenes

Place assets using scene names such as:

```text
images/scene_001.png
images/scene_002.jpg
videos/scene_003.mp4
```

Run the same command again. Existing planning/audio is reused and the final render is produced.

Optional local BGM:

```bat
python morrowglass.py render --project-dir D:\Morrowglass\Video02 --bgm D:\Music\history.mp3 --bgm-volume 0.12
```

## Next
1. visual WebUI for scene review/replacement
2. ComfyUI image provider
3. visual QC + automatic retry
4. optional image-to-video provider
5. better still-image motion/transition presets
6. end-to-end Windows test on the Morrowglass machine

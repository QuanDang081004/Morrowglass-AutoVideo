# Morrowglass AutoVideo

Scene-aware automation layer for MoneyPrinterTurbo.

Current development branch: **morrowglass-dev**.

## Phase 1

- Final script -> chronological scene manifest.
- Reuses MoneyPrinterTurbo's configured LLM provider.
- Deterministic fallback scene splitting.
- One image prompt and one motion prompt per scene.
- Visual Bible for period/location/character/style continuity.
- Stable project.json manifest.
- Manual/hybrid asset discovery by scene id.
- SRT-aware scene timing.

End-state: script -> scene plan -> Kokoro -> word timing -> image/video assets -> visual QC -> scene renderer -> subtitles/BGM -> final MP4.

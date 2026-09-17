# Promotional video audio and caption QA

Checked on **17 September 2026** against the current `NARRATION.json`, cached Edge word boundaries, generated narration metadata, `video/public/captions.json`, and `video/public/ngeebula-promo.en.srt`.

## Result

- `scripts/prepare_video_audio.py` now reproduces all **40** reviewed caption cues exactly, including punctuation, whitespace, cue text, and millisecond timing.
- A read-only regeneration comparison reported exact equality for both the JSON cues and complete SRT text. Existing narration audio and caption outputs were not regenerated or overwritten during this change.
- Every cue is non-empty, ordered, non-overlapping, and bounded within the **114.000-second** composition.
- The composition duration is **3,420 frames at 30 fps**.
- `python -m py_compile scripts/prepare_video_audio.py` passes.

## Caption construction

The generator aligns each Edge `WordBoundary` record with the corresponding original non-whitespace token in the scene narration. It fails if the counts or normalized words differ. Cue text is sliced from the original narration, preserving punctuation and internal whitespace.

A cue closes on the first applicable rule:

- eight words;
- text longer than 64 characters;
- `.`, `!`, `?`, `;`, or `:` after at least three words; or
- a comma after at least five words.

The cue starts at the first word offset and ends 200 ms after the last word. Both offsets are divided by the effective tempo and placed at scene start + 550 ms. Ends are bounded to scene end − 200 ms and clipped to one millisecond before the next cue.

Audio rendering retains the higher-precision tempo in the six-decimal FFmpeg `atempo` value. Caption regeneration uses the published four-decimal metadata tempo so it remains byte-for-byte stable with the reviewed JSON and SRT; the observed difference from using the unrounded calculation was at most one millisecond.

## Narration placement

All narration begins 550 ms after its scene starts. Validation confirms each clip finishes inside its own scene and no clip overlaps the next. End margins are:

| Scene | Audio start | Audio duration | Audio end | Margin before scene end |
|---:|---:|---:|---:|---:|
| 1 | 0.550 s | 6.912 s | 7.462 s | 0.538 s |
| 2 | 8.550 s | 9.912 s | 18.462 s | 0.538 s |
| 3 | 19.550 s | 7.920 s | 27.470 s | 0.530 s |
| 4 | 28.550 s | 9.912 s | 38.462 s | 0.538 s |
| 5 | 39.550 s | 9.912 s | 49.462 s | 0.538 s |
| 6 | 50.550 s | 9.912 s | 60.462 s | 0.538 s |
| 7 | 61.550 s | 12.912 s | 74.462 s | 0.538 s |
| 8 | 75.550 s | 10.920 s | 86.470 s | 0.530 s |
| 9 | 87.550 s | 12.912 s | 100.462 s | 0.538 s |
| 10 | 101.550 s | 11.928 s | 113.478 s | 0.522 s |

The script also enforces the expected 40-cue count, 114-second caption boundary, scene order, clip-to-scene fit, and non-overlap before writing generated caption artifacts.

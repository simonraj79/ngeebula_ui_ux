# Final video validation

Verified on **17 September 2026** after two full renders and a framing refinement.

## Delivered media

| Check | Result |
| --- | --- |
| File | `video/out/ngeebula-stakeholder.mp4` |
| Video | H.264, 1920 × 1080, 30 fps, 3,420 frames |
| Video duration | 114.000 seconds |
| Container duration | 114.048 seconds, including AAC padding |
| Audio | AAC, 48 kHz, stereo |
| File size | 22,164,625 bytes |
| Full FFmpeg decode | Passed; no decoding errors |
| Integrated loudness | −15.84 LUFS |
| True peak | −2.08 dBTP; below clipping |
| Loudness range | 4.10 LU |
| Captions | 40 word-aligned, punctuated cues; burned in and separate SRT |
| SHA-256 | `c7507750ff1b055bec8bff314a26c20543bd9c9c398deb8772247c10a872ce57` |

The loudness values are FFmpeg measurements of the final mix, not a claim of a listening study. Audio timing and cue alignment checks are in [AUDIO_QA.md](AUDIO_QA.md).

## Visual review and refinement

Inspected rendered frames for every scene and the secondary asset-button, assessed-requirement, approval and execution shots. Reviewed a contact sheet extracted from the final MP4 and a full-resolution final requirements frame. Corrected screenshot clipping, removed leaked sidebars in contained crops, replaced an unrelated request screenshot, exposed approval/progress controls, and moved a callout away from a panel edge.

The final edit uses real screenshots with animated crops and annotations. It is a guided montage of an unsaved intake draft and prepared demo jobs, not one uninterrupted transaction. The assessed, approval and execution shots show the same prepared job #2. The 1/2, 1/2, 2/2 comparison is labelled synthetic and retains the fixed inspection. News figures have dated on-screen attribution; complete links and scope notes accompany the video. The ending keeps the prototype/dummy-data boundary and demo URL visible.

## Source and tooling checks

- `npm run lint` passed (ESLint and TypeScript).
- Python compilation passed for the four video helper scripts.
- Caption regeneration reproduces the reviewed JSON and SRT exactly; clips fit their scenes and do not overlap.
- Git ignore checks exclude `.env`, the disposable database, `video/node_modules` and `video/out`.
- The public-release audit passed with no known credential patterns or private paths in publication candidates. It does not inspect ignored files or establish complete secret detection.
- No application source changed during this video task, so the application test suite was not repeated. The existing hosted deployment remained healthy.

Output videos, review frames, raw TTS cache and capture database remain local generated artifacts. The editable video project and production documents are prepared in the working tree; this task did not push them or redeploy the app.

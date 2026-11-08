# Wilhelm playback: implementation and review

The native Python application now plays the original videos through a bounded background decoder. Conversation state and physical scene state are separate. The scene director completes a committed action before following a compatible route toward the visitor.

## What runs now

- Full-length 24 FPS look-up and return-to-book clips, including anticipation and settling.
- Full-length 24 FPS look-up from tinker box and return-to-tinker clips, connecting the tinkering activity directly to visitor engagement.
- Full-length 24 FPS walk-away and walk-in clips connecting the neutral desk to an unoccupied empty room (`empty_room.png`) for overnight absence and on-demand return.
- Autonomous activity switching between reading and tinkering via neutral desk transitions (`put_away_book`, `get_out_tinker_box`, `put_away_tinker`, `get_out_book`).
- Occasional complete page turns, scheduled 30-65 seconds after an action or interaction settles.
- Greeting synthesis during the approach; audio starts only after visual readiness.
- Typed test questions also wait for visual readiness.
- Listening begins after greeting playback completes.
- Cooldown waits for the physical return before admitting IDLE.
- The final video frame remains displayed throughout resting and conversation. No unrelated still, mouth sprite, blink, or whole-room drift replaces it.
- A shared 1280 x 720 scene canvas with contain framing by default. Fullscreen uses the actual display size.
- Original embedded audio remains muted; the existing speech voice and model routing remain in use.

All current interruption checkpoints are source endpoints. This deliberately finishes an action rather than cutting through hand or prop motion. New intermediate checkpoints need compatible footage and player support; unsupported checkpoint definitions are rejected.

The full-length core clips are marked `candidate`, not artistically approved. Review their joins on the intended screen before choosing shorter edit ranges. The implementation does not repeat the previous plan's claims of imperceptible joins.

## Start and preview

From the project root on the Pi, using the configured Python environment:

```bash
python main.py --fullscreen
```

For a hardware-free check of the application and synthetic demo audio:

```bash
python main.py --demo
```

For scene preview without camera, microphone, models, or speech:

```bash
python tools/preview_scenes.py --cycle
```

Preview and live hotkeys: 1 page turn, 2 box study, 3 retrieve book, 4 retrieve box, 5 look up from book, 6 return to book, 7 put away book, 8 put away box, 9 look up from box, 0 return to box, - walk away, = walk in. I toggles diagnostics; Esc exits. A selected action follows a compatible entry route first. It does not force-cut an active action.

Both reading and tinkering activities are enabled in visitor operation. Wilhelm acknowledges visitors from either activity using its respective look-up clip, holds the corresponding visitor-facing endpoint during conversation, and returns to that activity upon cooldown.

On Windows, replace `python` with `.\.venv\Scripts\python.exe`.

## Validate and review assets

```bash
python tools/process_wilhelm_assets.py --check
python tools/process_wilhelm_assets.py
```

The first command fully decodes every original and validates timing/ranges without writing files. The second publishes contact sheets, first/last frames, fingerprints, JSON metadata, and a Markdown report under `assets/review/<revision>/`. `assets/scene_catalog.json` points to the completed report.

Publication happens only after all clips and stills succeed. Failed runs leave the previous report pointer intact. Revisions are content-addressed by manifest and source fingerprints. Originals are not modified. Previous PNG caches and accelerated cropped MP4s remain on disk but are not used by the new playback path.

Review each predecessor -> clip -> successor sequence at normal speed. Check hands, book/box presence, head pose, lighting, camera alignment, and internal generative distortion. Neither numerical differences nor technically valid decoding establish visual continuity.

## Catalog and adding footage

Edit `wilhelm_asset_manifest.json`:

1. Define an endpoint scene with activity, pose, props, sprite fallback, and an engagement scene when appropriate.
2. Add a clip with a stable ID, source file, actual source FPS, and source in/out frames. The out frame is exclusive; null means the complete source.
3. Name its entry and exit scenes. Set category `transition`, `activity_action`, or `resting_loop` as appropriate. Current resting variations are scheduled actions, not automatically continuous looping footage.
4. Keep `audio` as `muted`, `face_motion` as `baked_in`, and checkpoints as `["source_end"]` for the existing player.
5. Begin with `runtime_enabled: false` and `review_status: "preview"`. Use the preview tool to evaluate the complete route.
6. After review, use `review_status: "approved"` and enable the intended clips. Candidate status is reserved for deliberate implementation review, not proof of seamlessness.
7. Rerun asset validation and the preview cycle.

Autonomous activity changes are considered after a configurable 180-420 second dwell. A new activity is eligible only if the director can reach it and find enabled routes both toward its engagement scene and back. Merely enabling the existing tinkering clips will not invent missing engagement footage.

Add explicit entry/exit footage for new props. Do not represent an activity switch by changing a still-image name.

## Playback configuration

`portrait_config.json` -> `renderer`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `scene_fit` | `contain` | Preserve the complete widescreen scene with letterboxing. `cover` crops to fill. |
| `use_display_resolution` | true | Fullscreen uses the display's reported dimensions. |
| `scene_director.enabled` | true | Use manifest-driven buffered playback. |
| `scene_director.video_memory_mb` | 64 | Shared RGB decode budget across one active and one prefetched decoder. |
| `scene_director.decode_width` | 960 | Maximum decoded width; aspect ratio is retained. |
| `scene_director.opencv_threads` | 1 | OpenCV image-processing workers. The FFmpeg codec also requests one thread when supported. |
| `scene_director.preparation_timeout_seconds` | 15 | Fail preparation rather than wait indefinitely for the first frame. |
| `scene_director.action_interval_min/max` | 30 / 65 | Idle action opportunity interval in seconds. |
| `scene_director.activity_interval_min/max` | 180 / 420 | Activity-change opportunity interval in seconds. |
| `scene_director.activities` | reading, tinkering | Allowed activity candidates, still subject to complete enabled route checks. |

The RGB budget is not a total application memory limit: codec buffers, display surfaces, still images, model memory, and optional benchmark screenshots are additional. No complete video is retained as a list of original and scaled surfaces. File reads/decoding/initial resize happen on workers; pygame surface conversion and one-frame display scaling happen on the display thread.

On underflow, the last valid frame remains visible. Playback pauses instead of skipping essential motion. A failed clip never commits its intended destination pose. If failure occurs after motion begins, the scene becomes unresolved and stays held for diagnosis; restart after repairing the asset rather than force-cutting back to a guessed pose. Failures and missing routes are exposed in scene diagnostics and the console.

## Measurements and testing

```bash
python -m unittest discover -s tests
python tools/benchmark_scenes.py --headless
python tools/benchmark_scenes.py --headless --preview-cycle --output .cache/scene-preview-cycle
```

Run the benchmark without `--headless` on the Pi's actual display. Output includes hardware/RAM information where supported, display dimensions, source/display rates, per-action preparation and presentation time, underflow count, render work, and screenshots. Screenshot compression happens after timed playback.

Desktop validation on November 3, 2026:

- All twelve original clips decoded successfully.
- Native application smoke test: greeting audio began at approximately 10.09 seconds in the settled `engaged_book` scene; listening followed audio completion; the return reached `reading` before IDLE.
- The six-action activity preview completed all 240 frames per action, with presentation durations of approximately 10.00-10.03 seconds and no playback underflows.
- Preview-cycle median display interval was approximately 33.34 ms, p95 34.12 ms; median render work was approximately 7.36 ms at 1024 x 768 with 960-pixel-wide decode.

These are Windows headless measurements, not Pi performance guarantees. The application smoke uses synthetic demo audio, not production voice-quality validation.

## Remaining asset and installation work

- Generate approved quiet reading/tinkering/resting footage.
- Supply additional subtle resting/thinking loops and conversation variations for reading and tinkering.
- Prototype the speaking method before generating many speaking assets. Generic talking video does not synchronize to arbitrary speech, and fixed mouth overlays cannot track a moving head.
- Add approved listening, thinking, and speech motion. The held video endpoint is a temporary conversation fallback.
- Visually approve source boundaries and any crossfade duration on the intended display. Current core entry dissolves are 160 ms; preview prop-changing edges default to direct joins.
- On the Pi, confirm display/RAM, microphone/voice behavior, frame pacing during simultaneous speech/camera load, memory, temperature, and a sustained run of at least 30 minutes.
- Presence-loss cancellation remains deferred: motion absence does not reliably establish that a visitor has left.

See the editable [implementation plan](wilhelm_animation_implementation_plan.md) for the intended final experience and remaining editorial decisions.

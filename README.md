# AI Director

![Synthetic timeline proof](docs/images/timeline.svg)

A small video-editing workflow prototype for turning a talking-head clip into
reviewable edit decisions and common interchange outputs.

## Workflow

```text
Video → FFmpeg audio extraction → silence detection → optional Whisper
      → optional semantic cuts → timeline → SRT / EDL / FCPXML → review/render
```

## What exists

- FFmpeg audio extraction and silence detection.
- Optional OpenAI-compatible Whisper transcription.
- Optional DeepSeek-compatible semantic cut suggestions.
- CMX3600 EDL and FCPXML generation; SRT when transcription is available.
- Optional local Premiere Pro bridge.

## Quick start

Requirements: Python 3.10+, FFmpeg and FFprobe. Optional provider credentials
are local-only; copy `.env.example` and never commit a real key.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python ai_director.py examples/synthetic-input.mp4 --silence-only --no-video --no-launch-pr
```

The repository contains no real video, voice or customer material.

A four-second FFmpeg-generated [synthetic input](examples/synthetic-input.mp4)
and [sample keep list](examples/sample-keep-list.json) are included for
repeatable offline inspection. Run the documented command with this sample to
exercise audio extraction, silence detection and interchange export. The
offline run retained one 4.017-second interval and generated this
[EDL output](examples/sample-davinci.edl) plus FCPXML. Silence-only mode has no
transcript, so it does not create an SRT file. The FCPXML references the local
source path and must be regenerated on each machine; it is not checked in.

## Output and truth boundary

The tool emits edit artifacts for review. Provider-backed transcription,
semantic quality, Premiere import and final-video quality are not proven by the
offline unit tests. Do not treat generated cuts as an automatic publishing
decision.

## Verification

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m compileall -q ai_director.py modules pr_agent
```

The tests cover kept-interval calculations, subtitle times after cuts, and
the structure of EDL/FCPXML exports. They do not validate a rendered video or
editing decisions from a model.

## Status

Public prototype. The deterministic timeline helpers are testable locally;
external provider, media and Premiere integrations remain environment-dependent.

## License

MIT. See [LICENSE](LICENSE).

See [architecture](docs/architecture.md), [resume bullets](docs/resume-bullets.md)
and [interview notes](docs/interview-notes.md). No provider-backed transcript
or semantic edit quality is claimed by the synthetic sample.

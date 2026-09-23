# Architecture

Video input passes through FFmpeg audio extraction, deterministic silence
detection, optional provider transcription and semantic cut selection, then a
timeline representation exported as SRT/EDL/FCPXML for human review. The
synthetic input is a generated test pattern with a tone. The sample run detected
zero silence intervals and retained the whole four-second clip. That proves
the mechanical path for this fixture, not editing quality or Premiere import.

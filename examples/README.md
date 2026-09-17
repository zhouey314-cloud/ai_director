# Synthetic media smoke test

Do not commit generated media. Create a local fixture with FFmpeg, for example
with a color card and a generated tone, then run `ai_director.py` in
`--silence-only` mode. The fixture is only a mechanical test of extraction,
silence detection and artifact generation; it is not evidence of speech or AI
cut quality.

# PREMIUM GOLF TOURNAMENT — vlog assembly

## Source facts (derived from the files, not assumed)

| | |
|---|---|
| Sequence rate | timebase 24 + `<ntsc>TRUE</ntsc>` → **23.976023 fps** (24000/1001) |
| Sequence start timecode | **00:00:00:00 / frame 0**, read from `<sequence><timecode>` |
| Timeline length | frames 0 → 139140 = **96:43.30** |
| V1 clipitems | 58, butt-cut end to end, no gaps, every clip `in`=0 `out`=duration |
| Audio | A1 + A2, 58 clipitems each, mirroring V1 |
| Transcript | 405 segments / 2823 sentences / 12123 words, spanning 0 → 5803.2975s |
| Speech coverage | 3457.7s = 59.6% of the timeline |

Transcript seconds map 1:1 onto timeline seconds — the transcript spans exactly
the sequence, and the sequence starts at zero, so no offset is applied.

## Phase 1 — `decisions.csv`

    python3 tools/build_decisions.py

* `tools/common.py` — frame/second/timecode maths and file loaders
* `tools/decisions_spec.py` — the editorial decisions (hand-written, hint timings)
* `tools/build_decisions.py` — snaps hints to sentence boundaries, derives CUT rows
  as the exact complement, applies the silence rule, validates, writes the CSV
* `build/transcript_readable.txt` — annotated transcript used to make the calls

Phase 2 (writing the FCP7 XML) is deliberately **not** run here.

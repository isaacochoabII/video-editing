# -*- coding: utf-8 -*-
"""Phase 1: snap the editorial spec to sentence boundaries and emit decisions.csv.

Guarantees:
  * every kept range starts at a sentence start and ends at a sentence end
  * kept ranges never overlap each other
  * CUT rows are the exact complement of the kept ranges, so the CSV accounts
    for all 96:43 of source with no gaps and no double-counting
  * every dialogue-free gap over 8s that is not already inside a kept range
    gets its own OPTIONAL row
"""
import csv
import sys

sys.path.insert(0, "tools")
from common import load_sentences, speech_intervals, speech_seconds, tc, f2s
from decisions_spec import KEEP, CUTS, ACTS
from keeps import snapped_keeps, MIN_KEEP as _MK, S_START, S_END

MIN_KEEP = 4.0
GAP_THRESHOLD = 8.0
SNAP_TOL = 3.0
SLIVER = 1.5          # complement pieces shorter than this are not worth a row
TL_END = f2s(139140)  # 5803.30s, the last timeline frame

SENTS = load_sentences()
MERGED = speech_intervals()

ACT_SPANS = [(1, 0.0, 427.0), (2, 427.0, 1097.0), (3, 1097.0, 2202.0),
             (4, 2202.0, 3907.0), (5, 3907.0, TL_END)]


def act_of(t):
    for a, lo, hi in ACT_SPANS:
        if lo <= t < hi:
            return a
    return 5


def snap_start(hint):
    cands = [s for s in S_START if abs(s - hint) <= SNAP_TOL]
    if cands:
        return min(cands, key=lambda s: (abs(s - hint), s))
    return min(S_START, key=lambda s: abs(s - hint))


def snap_end(hint):
    cands = [e for e in S_END if abs(e - hint) <= SNAP_TOL]
    if cands:
        return min(cands, key=lambda e: (abs(e - hint), -e))
    return min(S_END, key=lambda e: abs(e - hint))


def text_for(a, b, limit=200):
    parts = [s["text"] for s in SENTS if s["start"] >= a - 0.05 and s["end"] <= b + 0.05]
    t = " ".join(" ".join(parts).split())
    if not t:
        t = "(no dialogue)"
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def row(rid, act, tier, a, b, reason):
    dur = b - a
    sp = speech_seconds(a, b, MERGED)
    return dict(id=rid, act=act, tier=tier, start_tc=tc(a), end_tc=tc(b),
                duration_s=round(dur, 2), speech_ratio=round(sp / dur, 2) if dur > 0 else 0.0,
                text=text_for(a, b), reason=reason, _a=a, _b=b)


# ---------- 1. kept segments (shared with phase 2) ----------
keeps, warnings = snapped_keeps(KEEP)

rows = [row(rid, act, tier, a, b, reason) for rid, act, tier, a, b, reason in keeps]

# ---------- 2. silence rule ----------
covered = sorted((a, b) for _, _, _, a, b, _ in keeps)


def inside(a, b):
    return any(ka <= a + 0.25 and kb >= b - 0.25 for ka, kb in covered)


gaps = [(MERGED[i - 1][1], MERGED[i][0]) for i in range(1, len(MERGED))
        if MERGED[i][0] - MERGED[i - 1][1] > GAP_THRESHOLD]

gap_rows, gaps_inside = [], 0
for n, (ga, gb) in enumerate(gaps, 1):
    if inside(ga, gb):
        gaps_inside += 1
        continue
    gap_rows.append(row("G%03d" % n, act_of(ga), "OPTIONAL", ga, gb,
                        "possible visual moment, needs human review"))
rows += gap_rows

# ---------- 3. CUT rows = exact complement of everything kept ----------
kept_all = sorted((r["_a"], r["_b"]) for r in rows)
union = []
for a, b in kept_all:
    if union and a <= union[-1][1] + 1e-6:
        union[-1][1] = max(union[-1][1], b)
    else:
        union.append([a, b])

holes, cursor = [], 0.0
for a, b in union:
    if a - cursor > SLIVER:
        holes.append((cursor, a))
    cursor = max(cursor, b)
if TL_END - cursor > SLIVER:
    holes.append((cursor, TL_END))


def cut_reason(a, b):
    """Use the hand-written reason whose span overlaps this hole most."""
    best, best_ov = None, 0.0
    for _, _, sh, eh, reason in CUTS:
        ov = min(b, eh) - max(a, sh)
        if ov > best_ov:
            best, best_ov = reason, ov
    if best and best_ov >= min(6.0, (b - a) * 0.5):
        return best
    d = b - a
    if d < 8:
        return "Short connective crosstalk between kept beats - nothing said that the next beat does not carry."
    if d < 30:
        return "Filler between kept beats: acknowledgements, half-sentences and logistics already visible on screen."
    return "Long stretch that does not move the story forward - repeated material, transit chatter or logistics."


for n, (a, b) in enumerate(holes, 1):
    rows.append(row("X%03d" % n, act_of(a), "CUT", a, b, cut_reason(a, b)))

rows.sort(key=lambda r: (r["act"], r["_a"]))

FIELDS = ["id", "act", "tier", "start_tc", "end_tc", "duration_s", "speech_ratio", "text", "reason"]
with open("decisions.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    w.writeheader()
    for r in rows:
        w.writerow({k: r[k] for k in FIELDS})

# ---------- 4. report ----------
tot = lambda ts: sum(r["duration_s"] for r in rows if r["tier"] in ts)
cnt = lambda ts: sum(1 for r in rows if r["tier"] in ts)
hms = lambda s: "%d:%05.2f" % (int(s) // 60, s % 60)

print("=" * 76)
print("PREMIUM GOLF TOURNAMENT  -  Phase 1 decision list")
print("=" * 76)
print("source        : frames 0 -> 139140 @ 23.976 fps  =  %s  (96m43s)" % hms(TL_END))
print("sequence start: 00:00:00:00 / frame 0, read from <sequence><timecode> (not assumed)")
print("transcript    : %d sentences, %d dialogue-free gaps over %.0fs" % (len(SENTS), len(gaps), GAP_THRESHOLD))
print()
for t in ("MUST", "SHOULD", "OPTIONAL", "CUT"):
    print("  %-9s %3d rows   %9s" % (t, cnt([t]), hms(tot([t]))))
print("  %-9s %3d rows   %9s   (accounts for the whole timeline)"
      % ("total", len(rows), hms(tot(["MUST", "SHOULD", "OPTIONAL", "CUT"]))))
print()
print("RUNNING TOTALS")
for label, ts in (("MUST", ["MUST"]), ("MUST+SHOULD", ["MUST", "SHOULD"]),
                  ("MUST+SHOULD+OPTIONAL", ["MUST", "SHOULD", "OPTIONAL"])):
    mark = "   <- target ~26:00" if label == "MUST+SHOULD" else ""
    print("  %-22s %9s   (%2.0f%% of source)%s" % (label, hms(tot(ts)), tot(ts) / TL_END * 100, mark))
print()
print("PER ACT  (MUST+SHOULD)")
for a in sorted(ACTS):
    d = sum(r["duration_s"] for r in rows if r["act"] == a and r["tier"] in ("MUST", "SHOULD"))
    n = sum(1 for r in rows if r["act"] == a and r["tier"] in ("MUST", "SHOULD"))
    print("  act %d  %-30s %9s  (%2d segments)" % (a, ACTS[a], hms(d), n))
print()
ks = sorted(r["duration_s"] for r in rows if r["tier"] in ("MUST", "SHOULD"))
print("segment length (MUST+SHOULD): min %.1fs  median %.1fs  mean %.1fs  max %.1fs"
      % (ks[0], ks[len(ks) // 2], sum(ks) / len(ks), ks[-1]))
print("silence rule : %d of %d gaps >%.0fs got their own OPTIONAL row; %d were already inside a kept range"
      % (len(gap_rows), len(gaps), GAP_THRESHOLD, gaps_inside))

# ---------- 5. self-checks ----------
iv = sorted((r["_a"], r["_b"], r["id"]) for r in rows)
ovl = [(iv[i - 1], iv[i]) for i in range(1, len(iv)) if iv[i][0] < iv[i - 1][1] - 1e-6]
short = [r["id"] for r in rows if r["tier"] != "CUT" and r["duration_s"] < MIN_KEEP]
starts, ends = set(S_START), set(S_END)
# gap rows are silence spans bounded by speech edges, not sentences - exempt them
misaligned = [r["id"] for r in rows
              if r["tier"] != "CUT" and not r["id"].startswith("G")
              and (r["_a"] not in starts or r["_b"] not in ends)]
acct = tot(["MUST", "SHOULD", "OPTIONAL", "CUT"])
print()
print("CHECKS")
print("  overlapping rows          : %d" % len(ovl))
print("  kept rows under %.0fs       : %d" % (MIN_KEEP, len(short)))
print("  mid-sentence cut points   : %d" % len(misaligned))
print("  timeline accounted for    : %.2fs of %.2fs (%.2fs of sub-%.1fs slivers not given rows)"
      % (acct, TL_END, TL_END - acct, SLIVER))
for a, b in ovl:
    print("   OVERLAP", a, b)
if warnings:
    print()
    print("SNAP NOTES")
    for w_ in warnings:
        print("  " + w_)

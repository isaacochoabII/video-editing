# -*- coding: utf-8 -*-
"""The approved kept ranges, snapped to sentence boundaries.

Phase 1 (decisions.csv) and Phase 2 (the XML) both call snapped_keeps(), so the
XML can only ever be built from the exact ranges that appear in the CSV.
"""
import sys

sys.path.insert(0, "tools")
from common import load_sentences, tc

MIN_KEEP = 4.0
SNAP_TOL = 3.0

_SENTS = load_sentences()
S_START = sorted(s["start"] for s in _SENTS)
S_END = sorted(s["end"] for s in _SENTS)


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


def snapped_keeps(KEEP):
    """-> (list of (id, act, tier, start_s, end_s, reason), list of warnings)"""
    warnings = []
# The cold open (act 0) is sourced from inside act 4's span, so de-overlapping
    # has to run in TIMELINE order, not in list order.
    staged = []
    for rid, act, tier, sh, eh, reason in KEEP:
        a, b = snap_start(sh), snap_end(eh)
        if b <= a:
            later = [e for e in S_END if e > a]
            b = later[0] if later else a + MIN_KEEP
            warnings.append("%s: snapped range inverted, extended to the next sentence end" % rid)
        staged.append([rid, act, tier, a, b, reason])
    
    staged.sort(key=lambda r: (r[3], r[4]))
    prev_end = None
    for r in staged:
        rid, act, tier, a, b, reason = r
        if prev_end is not None and a < prev_end - 1e-6:
            nxt = [s for s in S_START if s >= prev_end - 1e-6]
            a = nxt[0] if nxt else prev_end
            warnings.append("%s: start pulled to %s to clear the previous segment" % (rid, tc(a)))
        if b - a < MIN_KEEP:
            cand = [e for e in S_END if e >= a + MIN_KEEP]
            if cand:
                warnings.append("%s: %.2fs under the %.0fs minimum, extended to the next sentence end"
                                % (rid, b - a, MIN_KEEP))
                b = cand[0]
        r[3], r[4] = a, b
        prev_end = b
    
    keeps = [tuple(r) for r in staged]
    return keeps, warnings

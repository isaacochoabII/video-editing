# -*- coding: utf-8 -*-
"""Phase 2: write the cut FCP7 XML from the approved MUST+SHOULD tiers.

Cut point policy
----------------
Every boundary of a kept range is moved off the word boundary and into the
adjacent pause, because cutting on the boundary clips consonants and breaths:

    pad = min(pause / 2, MAX_PAD)          # the midpoint of the pause
    head cut = range_start - pad
    tail cut = range_end   + pad

MIN_HANDLE (200 ms) is the target; a pause shorter than 400 ms cannot give the
full handle, so the midpoint is used and the segment is listed in the report.
MAX_PAD stops a long silence from dragging dead air into the cut.  Padding is
additionally clamped so it never crosses a source clip boundary - that would
flash a frame of a different camera angle before the intended shot.

All arithmetic runs in absolute seconds; s2f() rounds to the nearest frame once,
at the very end, per cut point.
"""
import copy
import sys
import xml.etree.ElementTree as ET
from bisect import bisect_left, bisect_right

sys.path.insert(0, "tools")
from common import FPS, XML_IN, f2s, s2f, tc, load_v1_clips, speech_intervals
from keeps import snapped_keeps
from decisions_spec import KEEP, ACTS

TIERS = ("MUST", "SHOULD")
MIN_HANDLE = 0.200
MAX_PAD = 0.600
TICKS_PER_FRAME = 10594584000  # 1001/24000 s * 254016000000 ticks/s, exact
XML_OUT = "PREMIUM_GOLF_TOURNAMENT_CUT.xml"
SEQ_NAME = "PREMIUM GOLF TOURNAMENT - CUT"
SEQ_UUID = "b7e1c0a4-6f2d-4a19-9c3b-2f8d51ae4c70"

CLIPS = load_v1_clips()
CLIP_STARTS = [c["start"] for c in CLIPS]
SPEECH = speech_intervals()
SP_START = [a for a, _ in SPEECH]
SP_END = [b for _, b in SPEECH]
TL_END_F = CLIPS[-1]["end"]


def clip_at(frame):
    return CLIPS[max(0, bisect_right(CLIP_STARTS, frame) - 1)]


def pause_before(t):
    """Length of the dialogue-free pause immediately before t."""
    i = bisect_left(SP_START, t)
    if i > 0 and SP_END[i - 1] > t:       # t sits inside speech: no pause
        return 0.0
    return t - SP_END[i - 1] if i > 0 else t


def pause_after(t):
    i = bisect_right(SP_END, t)
    if i < len(SP_START) and SP_START[i] < t:
        return 0.0
    return SP_START[i] - t if i < len(SP_START) else max(0.0, f2s(TL_END_F) - t)


# ---------------------------------------------------------------- selection
keeps, _ = snapped_keeps(KEEP)
sel = [k for k in keeps if k[2] in TIERS]
sel.sort(key=lambda k: k[3])

# Ranges left exactly abutting by phase 1 are one continuous piece of source -
# there is no cut between them, so merge rather than emit a redundant cut point.
merged, merges = [], []
for rid, act, tier, a, b, reason in sel:
    if merged and a - merged[-1]["b"] < 1.0 / FPS:
        merged[-1]["ids"].append(rid)
        merged[-1]["b"] = max(merged[-1]["b"], b)
        merges.append((merged[-1]["ids"][-2], rid))
    else:
        merged.append(dict(ids=[rid], act=act, a=a, b=b))

# ---------------------------------------------------------------- cut points
short_head, short_tail, clip_clamped = [], [], []
for m in merged:
    gh, gt = pause_before(m["a"]), pause_after(m["b"])
    ph, pt = min(gh / 2.0, MAX_PAD), min(gt / 2.0, MAX_PAD)
    if ph < MIN_HANDLE:
        short_head.append((m["ids"][0], gh, ph))
    if pt < MIN_HANDLE:
        short_tail.append((m["ids"][-1], gt, pt))
    m["cut_in_s"], m["cut_out_s"] = m["a"] - ph, m["b"] + pt
    m["pad_head"], m["pad_tail"] = ph, pt

# keep padded ranges from colliding
for i in range(1, len(merged)):
    p, c = merged[i - 1], merged[i]
    if c["cut_in_s"] < p["cut_out_s"]:
        mid = (p["b"] + c["a"]) / 2.0
        p["cut_out_s"], c["cut_in_s"] = mid, mid

# round to frames: once, per cut point
for m in merged:
    f0, f1 = s2f(m["cut_in_s"]), s2f(m["cut_out_s"])
    ch, ct = clip_at(s2f(m["a"])), clip_at(max(0, s2f(m["b"]) - 1))
    if f0 < ch["start"]:
        clip_clamped.append((m["ids"][0], "head", ch["name"]))
        f0 = ch["start"]
    if f1 > ct["end"]:
        clip_clamped.append((m["ids"][-1], "tail", ct["name"]))
        f1 = ct["end"]
    m["f0"], m["f1"] = f0, max(f1, f0 + 1)

# A collision clamp can leave two padded ranges exactly touching. That is a cut
# point with no cut behind it, so join them into one segment instead of writing
# a through-edit that inflates the segment count.
joined = []
for m in sorted(merged, key=lambda x: x["f0"]):
    if joined and m["f0"] <= joined[-1]["f1"]:
        merges.append((joined[-1]["ids"][-1], m["ids"][0]))
        joined[-1]["ids"] += m["ids"]
        joined[-1]["f1"] = max(joined[-1]["f1"], m["f1"])
        joined[-1]["pad_tail"] = m["pad_tail"]
        continue
    joined.append(m)
merged = joined

# cold open first, then chronological - never reorder story content
merged.sort(key=lambda m: (0 if m["act"] == 0 else 1, m["f0"]))

# ---------------------------------------------------------------- source XML
src_root = ET.parse(XML_IN).getroot()
src_seq = src_root.find("sequence")
src_v1 = src_seq.find("media").find("video").findall("track")[0]
src_atracks = src_seq.find("media").find("audio").findall("track")
SRC_V = {ci.get("id"): ci for ci in src_v1.findall("clipitem")}
SRC_A = [{ci.findtext("masterclipid"): ci for ci in tr.findall("clipitem")} for tr in src_atracks[:2]]
BY_ID = {c["id"]: c for c in CLIPS}


def sub(parent, tag, text=None, **attrib):
    e = ET.SubElement(parent, tag, attrib)
    if text is not None:
        e.text = str(text)
    return e


def rate_el(parent):
    r = sub(parent, "rate")
    sub(r, "timebase", "24")
    sub(r, "ntsc", "TRUE")


# ---------------------------------------------------------------- build
root = ET.Element("xmeml", {"version": "4"})
seq = sub(root, "sequence", id="sequence-1")
sub(seq, "uuid", SEQ_UUID)
dur_el = sub(seq, "duration", "0")
rate_el(seq)
sub(seq, "name", SEQ_NAME)
media = sub(seq, "media")
video = sub(media, "video")
video.append(copy.deepcopy(src_seq.find("media").find("video").find("format")))
vt = ET.SubElement(video, "track", dict(src_v1.attrib))

audio = sub(media, "audio")
audio.append(copy.deepcopy(src_seq.find("media").find("audio").find("format")))
ats = [ET.SubElement(audio, "track", dict(t.attrib)) for t in src_atracks[:2]]

emitted_files = set()
vid_n, a1_n, a2_n = 0, 0, 0
pieces, tl = [], 0
n_pieces = sum(
    len([c for c in CLIPS if c["start"] < m["f1"] and c["end"] > m["f0"]]) for m in merged
)
V_BASE, A1_BASE, A2_BASE = 0, n_pieces, n_pieces * 2

for m in merged:
    for c in [c for c in CLIPS if c["start"] < m["f1"] and c["end"] > m["f0"]]:
        f0, f1 = max(m["f0"], c["start"]), min(m["f1"], c["end"])
        if f1 <= f0:
            continue
        src_in = c["cin"] + (f0 - c["start"])
        src_out = c["cin"] + (f1 - c["start"])
        pieces.append(dict(seg=m, clip=c, tl_start=tl, tl_end=tl + (f1 - f0),
                           src_in=src_in, src_out=src_out, f0=f0, f1=f1))
        tl += f1 - f0

for idx, p in enumerate(pieces, 1):
    c, sv = p["clip"], SRC_V[p["clip"]["id"]]
    vid = "clipitem-%d" % (V_BASE + idx)
    a1 = "clipitem-%d" % (A1_BASE + idx)
    a2 = "clipitem-%d" % (A2_BASE + idx)

    def base(parent, cid, extra_attrib=None):
        at = {"id": cid}
        if extra_attrib:
            at.update(extra_attrib)
        ci = ET.SubElement(parent, "clipitem", at)
        sub(ci, "masterclipid", sv.findtext("masterclipid"))
        sub(ci, "name", sv.findtext("name"))
        sub(ci, "enabled", "TRUE")
        sub(ci, "duration", sv.findtext("duration"))
        rate_el(ci)
        sub(ci, "start", p["tl_start"])
        sub(ci, "end", p["tl_end"])
        sub(ci, "in", p["src_in"])
        sub(ci, "out", p["src_out"])
        sub(ci, "pproTicksIn", p["src_in"] * TICKS_PER_FRAME)
        sub(ci, "pproTicksOut", p["src_out"] * TICKS_PER_FRAME)
        return ci

    def add_file(ci):
        """Full <file> on first use, id-only reference after - paths untouched."""
        fid = c["file_id"]
        if fid in emitted_files:
            ET.SubElement(ci, "file", {"id": fid})
        else:
            ci.append(copy.deepcopy(sv.find("file")))
            emitted_files.add(fid)

    def add_links(ci):
        for ref, mt, ti in ((vid, "video", 1), (a1, "audio", 1), (a2, "audio", 2)):
            ln = sub(ci, "link")
            sub(ln, "linkclipref", ref)
            sub(ln, "mediatype", mt)
            sub(ln, "trackindex", ti)
            sub(ln, "clipindex", idx)
            if mt == "audio":
                sub(ln, "groupindex", 1)

    # --- video
    ci = base(vt, vid)
    sub(ci, "alphatype", "none")
    sub(ci, "pixelaspectratio", "square")
    sub(ci, "anamorphic", "FALSE")
    add_file(ci)
    # Basic Motion on these five clips is a 90/270 degree orientation fix, not an
    # effect - dropping it would leave the shot sideways, so it is carried over.
    for filt in sv.findall("filter"):
        ci.append(copy.deepcopy(filt))
    add_links(ci)

    # --- audio, one clipitem per source channel
    for n, (track, aid, ti) in enumerate(((ats[0], a1, 1), (ats[1], a2, 2))):
        sa = SRC_A[n].get(sv.findtext("masterclipid"))
        ca = base(track, aid, {"premiereChannelType": "stereo"})
        ET.SubElement(ca, "file", {"id": c["file_id"]})
        st = sub(ca, "sourcetrack")
        sub(st, "mediatype", "audio")
        sub(st, "trackindex", ti)
        add_links(ca)

for t in (vt,) + tuple(ats):
    sub(t, "enabled", "TRUE")
    sub(t, "locked", "FALSE")
for n, t in enumerate(ats, 1):
    sub(t, "outputchannelindex", n)

dur_el.text = str(tl)
seq.append(copy.deepcopy(src_seq.find("timecode")))

ET.indent(root, space="\t")
xml = ET.tostring(root, encoding="unicode")
with open(XML_OUT, "w", encoding="utf-8") as fh:
    fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + xml + "\n")

# ---------------------------------------------------------------- report
def hms(s):
    return "%d:%05.2f" % (int(s) // 60, s % 60)


act_dur = {}
for m in merged:
    act_dur[m["act"]] = act_dur.get(m["act"], 0) + f2s(m["f1"] - m["f0"])

L = []
L.append("# PREMIUM GOLF TOURNAMENT - cut report\n")
L.append("Built from the approved **MUST+SHOULD** tiers in `decisions.csv`.\n")
L.append("| | |")
L.append("|---|---|")
L.append("| Output file | `%s` |" % XML_OUT)
L.append("| Final duration | **%s** (%d frames @ 23.976 fps) |" % (hms(f2s(tl)), tl))
L.append("| Source duration | %s (%d frames) |" % (hms(f2s(TL_END_F)), TL_END_F))
L.append("| Kept | %.1f%% of the source |" % (tl / TL_END_F * 100))
L.append("| Segments | %d |" % len(merged))
L.append("| Clip instances written | %d video + %d audio = %d |" % (len(pieces), len(pieces) * 2, len(pieces) * 3))
L.append("| Sequence start timecode | 00:00:00:00 (frame 0, as in the source) |")
L.append("| Tracks | V1 + A1 + A2, no transitions, no nests |\n")

L.append("## Per-act duration\n")
L.append("| Act | | Duration | Segments |")
L.append("|---|---|---|---|")
for a in sorted(act_dur):
    n = sum(1 for m in merged if m["act"] == a)
    L.append("| %d | %s | %s | %d |" % (a, ACTS[a], hms(act_dur[a]), n))
L.append("")

seg_d = sorted(f2s(m["f1"] - m["f0"]) for m in merged)
L.append("| Segment length | min %.1fs, median %.1fs, mean %.1fs, max %.1fs |"
         % (seg_d[0], seg_d[len(seg_d) // 2], sum(seg_d) / len(seg_d), seg_d[-1]))
L.append("")
L.append("## Cut points\n")
L.append("`source in/out` are timecodes in the original 96:43 assembly, for spot-checking. ")
L.append("`new` is where the segment lands in the cut. `pad` is how far each cut point was ")
L.append("moved off the word boundary into the surrounding pause.\n")
L.append("| # | rows | act | source in | source out | new in | new out | dur | pad head | pad tail |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
run = 0
for i, m in enumerate(merged, 1):
    d = m["f1"] - m["f0"]
    L.append("| %d | %s | %d | `%s` | `%s` | `%s` | `%s` | %.2fs | %.0f ms | %.0f ms |"
             % (i, "+".join(m["ids"]), m["act"], tc(f2s(m["f0"])), tc(f2s(m["f1"])),
                tc(f2s(run)), tc(f2s(run + d)), f2s(d), m["pad_head"] * 1000, m["pad_tail"] * 1000))
    run += d
L.append("")

L.append("## Notes\n")
L.append("* Cut points sit at the **midpoint of the pause** between words, not on the word ")
L.append("  boundary. Target handle is %d ms per side; `pad` above is what each cut actually got.\n" % int(MIN_HANDLE * 1000))
if merges:
    L.append("* %d approved row pair(s) were exactly contiguous in the source, so they were joined "
             "into one segment rather than cut and re-joined: %s.\n"
             % (len(merges), ", ".join("%s+%s" % p for p in merges)))
tight = ([(r, "head", g, p) for r, g, p in short_head] + [(r, "tail", g, p) for r, g, p in short_tail])
zero = [t for t in tight if t[2] <= 1e-6]
near = sorted([t for t in tight if t[2] > 1e-6], key=lambda t: t[2])
if zero:
    L.append("* **%d cut point(s) have no pause at all to sit in** - a second speaker is still "
             "talking across the boundary, so there is no handle and the cut will clip them. "
             "These are the ones to check by ear first; nudging any of them means moving the "
             "approved range, so I left them where you approved them:\n" % len(zero))
    L.append("  | row | end | |")
    L.append("  |---|---|---|")
    for rid, side, g, p in zero:
        L.append("  | `%s` | %s | overlapping speech, 0 ms handle |" % (rid, side))
    L.append("")
if near:
    L.append("* %d cut point(s) sit in a pause shorter than %d ms, so the full %d ms handle was not "
             "available and the midpoint of the pause was used instead:\n"
             % (len(near), int(2 * MIN_HANDLE * 1000), int(MIN_HANDLE * 1000)))
    L.append("  | row | end | pause | handle |")
    L.append("  |---|---|---|---|")
    for rid, side, g, p in near:
        L.append("  | `%s` | %s | %.0f ms | %.0f ms |" % (rid, side, g * 1000, p * 1000))
    L.append("")
if clip_clamped:
    L.append("* %d handle(s) were clamped to a source clip boundary so the cut would not flash a "
             "frame of the neighbouring camera angle: %s.\n"
             % (len(clip_clamped), ", ".join("%s %s (%s)" % x for x in clip_clamped)))
rot = sorted({p["clip"]["name"] for p in pieces if SRC_V[p["clip"]["id"]].find("filter") is not None})
if rot:
    L.append("* %d source clip(s) carry a Basic Motion filter that is a 90/270 degree orientation "
             "fix, not an effect. It is preserved verbatim - dropping it would leave those shots "
             "sideways: %s.\n" % (len(rot), ", ".join(rot)))
L.append("* File paths and `<file>` definitions are copied from the source XML unchanged; the full ")
L.append("  definition is written on a file's first use and referenced by id after that.\n")

open("cut_report.md", "w", encoding="utf-8").write("\n".join(L))

print("wrote %s  (%s, %d segments, %d clip instances)" % (XML_OUT, hms(f2s(tl)), len(merged), len(pieces) * 3))
print("wrote cut_report.md")

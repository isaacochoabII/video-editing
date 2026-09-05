# -*- coding: utf-8 -*-
"""Five social clips cut from the flattened FINAL CUT render.

Each clip is ONE continuous range of the 20:23 master - no internal cuts, no
joining of distant moments - and the five run in timeline order. Output is a
single FCP7 XML holding five separate sequences, so each opens as its own
timeline in Premiere ready to export.

Cut points use the same policy as the long-form pass: the boundary is moved off
the word into the middle of the adjacent pause (200 ms target, 600 ms cap), and
rounding to frames happens once, at the end, per cut point.
"""
import copy
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, "tools")
from common2 import FPS, XML_IN, f2s, s2f, tc, mmss, load_sentences, speech_intervals

MIN_HANDLE, MAX_PAD = 0.200, 0.600
TICKS_PER_FRAME = 10594584000
SRC_FRAMES = 29337
OUT = "PREMIUM_GOLF_5_CLIPS.xml"

# (title, in_s, out_s, why)
CLIPS = [
    ("Meet Our Judo Athletes", 152.16, 184.16,
     "The athletes answer 'what's your connection with the premium group' themselves - he sponsors the club and founded it - and it buttons on the coach's 'They're my athletes. They're very annoying.'"),
    ("That Was Terrible", 357.92, 401.48,
     "A complete comic arc in one take: 'You're all looking at me, it's just stressing me out' - the stretch, 'I'm also like very not flexible' - the swing - 'That was terrible.' / 'But you hit it.'"),
    ("What Our Clients Say", 405.84, 444.76,
     "Pierre Karam of Cedar Mount on two projects with Premium - 'he's a commendable and respectful guy', 'they delivered even with whatever hurdles came their way' - then the modesty laugh."),
    ("They Both Come First", 1056.24, 1091.60,
     "Clients or employees: 'If I have 100 clients, no employees, I can't do nothing. If I have 100 employees with no clients, I can't do nothing. So for me, they both come first.'"),
    ("Thank You, Everyone", 1113.04, 1150.32,
     "The closing thanks - 'I try to make everybody the best version of themselves every day' through to 'nice course, nice weather and great people. So thank you very much.'"),
]

SENTS = load_sentences()
SP = speech_intervals()
S_START = {round(s["start"], 3) for s in SENTS}
S_END = {round(s["end"], 3) for s in SENTS}


def pause_before(t):
    pv = [y for _, y in SP if y <= t + 1e-9]
    return t - pv[-1] if pv else t


def pause_after(t):
    nx = [x for x, _ in SP if x >= t - 1e-9]
    return nx[0] - t if nx else max(0.0, f2s(SRC_FRAMES) - t)


def text_for(a, b, limit=260):
    t = " ".join(" ".join(s["text"] for s in SENTS
                          if s["start"] >= a - 0.05 and s["end"] <= b + 0.05).split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------- cut points
rows = []
for title, a, b, why in CLIPS:
    assert round(a, 3) in S_START, "%s: in is not a sentence start" % title
    assert round(b, 3) in S_END, "%s: out is not a sentence end" % title
    gh, gt = pause_before(a), pause_after(b)
    ph, pt = min(gh / 2.0, MAX_PAD), min(gt / 2.0, MAX_PAD)
    f0, f1 = s2f(a - ph), s2f(b + pt)
    f0, f1 = max(0, f0), min(SRC_FRAMES, f1)
    rows.append(dict(title=title, a=a, b=b, f0=f0, f1=f1, ph=ph, pt=pt,
                     gh=gh, gt=gt, why=why, text=text_for(a, b)))

for i in range(1, len(rows)):
    assert rows[i]["f0"] > rows[i - 1]["f1"], "clips must not overlap"

# ---------------------------------------------------------------- XML
src = ET.parse(XML_IN).getroot().find("sequence")
src_v = src.find("media").find("video").findall("track")[0].findall("clipitem")[0]
SRC_FILE = src_v.find("file")
vfmt = src.find("media").find("video").find("format")
afmt = src.find("media").find("audio").find("format")
aouts = src.find("media").find("audio").find("outputs")
vtrack_attr = dict(src.find("media").find("video").findall("track")[0].attrib)
atrack_attr = [dict(t.attrib) for t in src.find("media").find("audio").findall("track")[:2]]


def sub(p, tag, text=None, **at):
    e = ET.SubElement(p, tag, at)
    if text is not None:
        e.text = str(text)
    return e


def rate_el(p):
    r = sub(p, "rate")
    sub(r, "timebase", "24")
    sub(r, "ntsc", "TRUE")


root = ET.Element("xmeml", {"version": "4"})
first_file = True
cid = 0

for n, r in enumerate(rows, 1):
    length = r["f1"] - r["f0"]
    seq = sub(root, "sequence", id="sequence-%d" % n)
    sub(seq, "uuid", "9d1f4c%02d-3a7b-4e52-8c16-0b5d92e7af%02d" % (n, n))
    sub(seq, "duration", length)
    rate_el(seq)
    sub(seq, "name", "REEL %d - %s" % (n, r["title"]))
    media = sub(seq, "media")

    video = sub(media, "video")
    video.append(copy.deepcopy(vfmt))
    vt = ET.SubElement(video, "track", vtrack_attr)

    audio = sub(media, "audio")
    sub(audio, "numOutputChannels", "2")
    audio.append(copy.deepcopy(afmt))
    audio.append(copy.deepcopy(aouts))
    ats = [ET.SubElement(audio, "track", a) for a in atrack_attr]

    ids = []
    for _ in range(3):
        cid += 1
        ids.append("clipitem-%d" % cid)
    vid, a1, a2 = ids

    def base(parent, myid, extra=None):
        at = {"id": myid}
        if extra:
            at.update(extra)
        ci = ET.SubElement(parent, "clipitem", at)
        sub(ci, "masterclipid", "masterclip-1")
        sub(ci, "name", src_v.findtext("name"))
        sub(ci, "enabled", "TRUE")
        sub(ci, "duration", SRC_FRAMES)
        rate_el(ci)
        sub(ci, "start", 0)
        sub(ci, "end", length)
        sub(ci, "in", r["f0"])
        sub(ci, "out", r["f1"])
        sub(ci, "pproTicksIn", r["f0"] * TICKS_PER_FRAME)
        sub(ci, "pproTicksOut", r["f1"] * TICKS_PER_FRAME)
        return ci

    def links(ci):
        for ref, mt, ti in ((vid, "video", 1), (a1, "audio", 1), (a2, "audio", 2)):
            ln = sub(ci, "link")
            sub(ln, "linkclipref", ref)
            sub(ln, "mediatype", mt)
            sub(ln, "trackindex", ti)
            sub(ln, "clipindex", 1)
            if mt == "audio":
                sub(ln, "groupindex", 1)

    ci = base(vt, vid)
    sub(ci, "alphatype", "none")
    sub(ci, "pixelaspectratio", "square")
    sub(ci, "anamorphic", "FALSE")
    if first_file:
        ci.append(copy.deepcopy(SRC_FILE))   # full definition, path untouched
        first_file = False
    else:
        ET.SubElement(ci, "file", {"id": "file-1"})
    links(ci)

    for k, (track, aid, ti) in enumerate(((ats[0], a1, 1), (ats[1], a2, 2))):
        ca = base(track, aid, {"premiereChannelType": "stereo"})
        ET.SubElement(ca, "file", {"id": "file-1"})
        st = sub(ca, "sourcetrack")
        sub(st, "mediatype", "audio")
        sub(st, "trackindex", ti)
        links(ca)

    for t in (vt,) + tuple(ats):
        sub(t, "enabled", "TRUE")
        sub(t, "locked", "FALSE")
    for k, t in enumerate(ats, 1):
        sub(t, "outputchannelindex", k)

    seq.append(copy.deepcopy(src.find("timecode")))

ET.indent(root, space="\t")
open(OUT, "w", encoding="utf-8").write(
    '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
    + ET.tostring(root, encoding="unicode") + "\n")

# ---------------------------------------------------------------- report
L = ["# Five clips from FINAL CUT\n",
     "Source: `PREMIUM GOLF TOURNAMENT - CUT FOR REELS.mp4` (20:23.60, 29337 frames @ 23.976 fps).",
     "Every clip is one continuous range of that master - no internal cuts - and the five run in",
     "timeline order. `PREMIUM_GOLF_5_CLIPS.xml` holds five separate sequences.\n",
     "| # | Title | In | Out | Duration | Handle in/out |",
     "|---|---|---|---|---|---|"]
for n, r in enumerate(rows, 1):
    L.append("| %d | **%s** | `%s` | `%s` | %.2fs | %.0f / %.0f ms |"
             % (n, r["title"], tc(f2s(r["f0"])), tc(f2s(r["f1"])), f2s(r["f1"] - r["f0"]),
                r["ph"] * 1000, r["pt"] * 1000))
L.append("")
for n, r in enumerate(rows, 1):
    L.append("### %d. %s" % (n, r["title"]))
    L.append("`%s` - `%s`  (%s - %s, %.1fs)\n" % (tc(f2s(r["f0"])), tc(f2s(r["f1"])),
                                                  mmss(r["a"]), mmss(r["b"]), f2s(r["f1"] - r["f0"])))
    L.append("> %s\n" % r["text"])
    L.append("%s\n" % r["why"])
tight = [(n, r) for n, r in enumerate(rows, 1) if min(r["ph"], r["pt"]) < MIN_HANDLE]
if tight:
    L.append("## Note\n")
    for n, r in tight:
        side = "in" if r["ph"] < MIN_HANDLE else "out"
        L.append("* Clip %d's %s point sits in a %.0f ms pause, so the handle is %.0f ms rather than "
                 "the usual 200 ms." % (n, side, (r["gh"] if side == "in" else r["gt"]) * 1000,
                                        (r["ph"] if side == "in" else r["pt"]) * 1000))
    L.append("")
open("clips_report.md", "w", encoding="utf-8").write("\n".join(L))

print("wrote %s and clips_report.md\n" % OUT)
for n, r in enumerate(rows, 1):
    print("  REEL %d  %s -> %s  %5.2fs   %s" % (n, tc(f2s(r["f0"])), tc(f2s(r["f1"])),
                                                f2s(r["f1"] - r["f0"]), r["title"]))

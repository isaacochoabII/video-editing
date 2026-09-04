# -*- coding: utf-8 -*-
"""Independent validation of the generated cut XML against the source XML."""
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, "tools")
from common import FPS, XML_IN, f2s, tc, load_v1_clips

OUT = "PREMIUM_GOLF_TOURNAMENT_CUT.xml"
fails, warns = [], []


def check(cond, msg):
    (fails if not cond else warns).append(msg) if not cond else None
    print(("  ok   " if cond else "  FAIL ") + msg)


root = ET.parse(OUT).getroot()
seq = root.find("sequence")
v1 = seq.find("media").find("video").findall("track")[0]
ats = seq.find("media").find("audio").findall("track")
V = v1.findall("clipitem")
A = [t.findall("clipitem") for t in ats]

src_root = ET.parse(XML_IN).getroot()
SRC_FILES = {f.get("id"): f.findtext("pathurl")
             for f in src_root.iter("file") if f.findtext("pathurl")}
CLIPS = {c["id"]: c for c in load_v1_clips()}
BY_FILE = {c["file_id"]: c for c in load_v1_clips()}

print("STRUCTURE")
check(root.tag == "xmeml" and root.get("version") == "4", "root is <xmeml version=4>")
check(len(seq.findall("media")) == 1, "exactly one <media>")
check(len(seq.find("media").find("video").findall("track")) == 1, "exactly one video track")
check(len(ats) == 2, "two audio tracks (A1+A2, mirroring the source stereo pair)")
check(len(list(root.iter("transitionitem"))) == 0, "no transitions")
check(len(list(root.iter("sequence"))) == 1, "no nested sequences")
check(seq.findtext("timecode/string") == "00:00:00:00", "sequence start timecode is 00:00:00:00")
check(seq.findtext("rate/timebase") == "24" and seq.findtext("rate/ntsc") == "TRUE",
      "sequence rate is 24 + NTSC (23.976 fps)")

print("\nTIMELINE")
ints = lambda els, tag: [int(e.findtext(tag)) for e in els]
vs, ve = ints(V, "start"), ints(V, "end")
check(all(isinstance(x, int) for x in vs + ve), "all start/end values are integers")
check(vs[0] == 0, "first clip starts at frame 0")
contig = all(vs[i] == ve[i - 1] for i in range(1, len(V)))
check(contig, "video track is contiguous butt-cut, no gaps or overlaps (%d clips)" % len(V))
check(all(ve[i] > vs[i] for i in range(len(V))), "every clip is at least one frame long")
total = ve[-1]
check(int(seq.findtext("duration")) == total, "<duration> %d matches last clip end %d" % (int(seq.findtext("duration")), total))

print("\nAUDIO MIRRORS VIDEO")
for n, alist in enumerate(A, 1):
    check(len(alist) == len(V), "A%d has the same clip count as V1 (%d)" % (n, len(alist)))
    same = all(
        alist[i].findtext("start") == V[i].findtext("start")
        and alist[i].findtext("end") == V[i].findtext("end")
        and alist[i].findtext("in") == V[i].findtext("in")
        and alist[i].findtext("out") == V[i].findtext("out")
        and alist[i].findtext("name") == V[i].findtext("name")
        for i in range(len(V)))
    check(same, "A%d start/end/in/out/name match V1 clip for clip" % n)
    check(all(c.findtext("sourcetrack/trackindex") == str(n) for c in alist),
          "A%d clipitems all reference source audio channel %d" % (n, n))

print("\nSOURCE MEDIA MAPPING")
bad_range, bad_map = [], []
for ci in V:
    i, o = int(ci.findtext("in")), int(ci.findtext("out"))
    fid = ci.find("file").get("id")
    c = BY_FILE[fid]
    if not (c["cin"] <= i < o <= c["cout"]):
        bad_range.append((ci.get("id"), ci.findtext("name"), i, o, c["cin"], c["cout"]))
    if (o - i) != (int(ci.findtext("end")) - int(ci.findtext("start"))):
        bad_map.append(ci.get("id"))
check(not bad_range, "every in/out lies inside its source clip's media range")
for b in bad_range:
    print("        ", b)
check(not bad_map, "source length equals timeline length for every clip (no speed change)")
tick_bad = [ci.get("id") for ci in V
            if int(ci.findtext("pproTicksIn")) != int(ci.findtext("in")) * 10594584000
            or int(ci.findtext("pproTicksOut")) != int(ci.findtext("out")) * 10594584000]
check(not tick_bad, "pproTicksIn/Out are exact for every clip")

print("\nFILE REFERENCES")
full = [f for f in root.iter("file") if f.findtext("pathurl")]
ids_full = [f.get("id") for f in full]
check(len(ids_full) == len(set(ids_full)), "each file's full definition appears exactly once")
paths_ok = all(f.findtext("pathurl") == SRC_FILES[f.get("id")] for f in full)
check(paths_ok, "every pathurl is byte-identical to the source XML (%d files)" % len(full))
refd = {f.get("id") for f in root.iter("file")}
check(refd <= set(SRC_FILES), "no invented file ids")
check(refd == set(ids_full), "every referenced file id has a full definition in the document")

print("\nIDS AND LINKS")
all_ids = [c.get("id") for c in root.iter("clipitem")]
check(len(all_ids) == len(set(all_ids)), "all %d clipitem ids are unique" % len(all_ids))
idset = set(all_ids)
dangling = {l.findtext("linkclipref") for l in root.iter("link")} - idset
check(not dangling, "no dangling link references")

print("\nCONTENT")
sys.path.insert(0, "tools")
from keeps import snapped_keeps
from decisions_spec import KEEP
keeps, _ = snapped_keeps(KEEP)
ms = [k for k in keeps if k[2] in ("MUST", "SHOULD")]
raw = sum(k[4] - k[3] for k in ms)
print("        approved MUST+SHOULD content   : %.2fs" % raw)
print("        written cut                    : %.2fs" % f2s(total))
print("        difference (handles)           : %+.2fs over %d segments" % (f2s(total) - raw, len(V)))
check(f2s(total) > raw, "cut is longer than the raw ranges (handles were added)")
check(f2s(total) - raw < len(ms) * 2 * 0.6 + 1, "added handles stay within the MAX_PAD budget")
rot = {c.findtext("name") for c in V if c.find("filter") is not None}
print("        clips carrying the rotation fix: %s" % (", ".join(sorted(rot)) or "none"))

# cold open must come first, the rest chronological
order = [int(ci.findtext("in")) + BY_FILE[ci.find("file").get("id")]["start"] for ci in V]
cold = order[0]
rest = order[1:]
mono = all(rest[i] >= rest[i - 1] for i in range(1, len(rest)))
check(cold > rest[0], "cold open is sourced from later in the day but placed first")
check(mono, "everything after the cold open runs in original timeline order (no reordering)")

print()
print("RESULT: %d failure(s)" % len(fails))
sys.exit(1 if fails else 0)

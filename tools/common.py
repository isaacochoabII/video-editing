"""Shared helpers for the PREMIUM GOLF TOURNAMENT vlog assembly.

Timeline facts (derived, never assumed):
  - sequence rate: timebase 24 + ntsc TRUE  ->  24000/1001 = 23.976023... fps
  - sequence start timecode: 00:00:00:00 (frame 0), read from <sequence><timecode>
  - transcript seconds map 1:1 onto timeline seconds (transcript spans 0 -> 5803.2975s,
    timeline spans frame 0 -> 139140 == 5803.30s)
"""
import json
import xml.etree.ElementTree as ET

FPS = 24000 / 1001
XML_IN = "input/PREMIUM_GOLF_TOURNAMENT.xml"
JSON_IN = "input/PREMIUM_GOLF_TOURNAMENT.json"


def f2s(frame):
    return frame / FPS


def s2f(sec):
    """Round to nearest frame. Call this once, at the very end, per cut point."""
    return int(round(sec * FPS))


def tc(sec):
    """Non-drop 23.976 timecode string HH:MM:SS:FF from absolute seconds."""
    f = s2f(sec)
    ff = f % 24
    total_s = f // 24
    return "%02d:%02d:%02d:%02d" % (total_s // 3600, (total_s // 60) % 60, total_s % 60, ff)


def load_words():
    """Flat, time-ordered word list across all transcript segments."""
    d = json.load(open(JSON_IN))
    words = []
    for si, seg in enumerate(d["segments"]):
        for w in seg["words"]:
            words.append(
                dict(
                    start=w["start"],
                    end=w["start"] + w["duration"],
                    text=w["text"],
                    eos=bool(w["eos"]),
                    seg=si,
                    speaker=seg.get("speaker"),
                )
            )
    words.sort(key=lambda w: (w["start"], w["end"]))
    return words


def load_sentences():
    """Group words into sentences on the transcript's eos flag."""
    sents, cur = [], []
    for w in load_words():
        cur.append(w)
        if w["eos"]:
            sents.append(_mk_sent(cur))
            cur = []
    if cur:
        sents.append(_mk_sent(cur))
    return sents


def _mk_sent(ws):
    return dict(
        start=ws[0]["start"],
        end=ws[-1]["end"],
        text=" ".join(w["text"] for w in ws),
        speaker=ws[0]["speaker"],
        words=ws,
    )


def speech_intervals():
    """Merged word-level speech intervals over the whole timeline."""
    merged = []
    for w in load_words():
        if merged and w["start"] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], w["end"])
        else:
            merged.append([w["start"], w["end"]])
    return merged


def speech_seconds(a, b, merged=None):
    merged = merged if merged is not None else speech_intervals()
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y in merged)


def load_v1_clips():
    """V1 clipitems from the source XML, in timeline order."""
    seq = ET.parse(XML_IN).getroot().find("sequence")
    track = seq.find("media").find("video").findall("track")[0]
    out = []
    for ci in track.findall("clipitem"):
        out.append(
            dict(
                id=ci.get("id"),
                name=ci.findtext("name"),
                start=int(ci.findtext("start")),
                end=int(ci.findtext("end")),
                cin=int(ci.findtext("in")),
                cout=int(ci.findtext("out")),
                file_id=ci.find("file").get("id"),
            )
        )
    return out

# -*- coding: utf-8 -*-
"""Helpers for the reels pass: source is the flattened FINAL CUT render."""
import json
import xml.etree.ElementTree as ET

FPS = 24000 / 1001
XML_IN = "input2/FINAL_CUT.xml"
JSON_IN = "input2/FINAL_CUT.json"


def s2f(sec):
    return int(round(sec * FPS))


def f2s(f):
    return f / FPS


def tc(sec):
    f = s2f(sec)
    return "%02d:%02d:%02d:%02d" % (f // 24 // 3600, (f // 24 // 60) % 60, (f // 24) % 60, f % 24)


def mmss(sec):
    return "%d:%02d" % (int(sec) // 60, int(sec) % 60)


def load_words():
    d = json.load(open(JSON_IN))
    w = [dict(start=x["start"], end=x["start"] + x["duration"], text=x["text"],
              eos=bool(x["eos"]), speaker=s.get("speaker"))
         for s in d["segments"] for x in s["words"]]
    w.sort(key=lambda x: (x["start"], x["end"]))
    return w


def load_sentences():
    out, cur = [], []
    for w in load_words():
        cur.append(w)
        if w["eos"]:
            out.append(dict(start=cur[0]["start"], end=cur[-1]["end"],
                            text=" ".join(x["text"] for x in cur), words=cur))
            cur = []
    if cur:
        out.append(dict(start=cur[0]["start"], end=cur[-1]["end"],
                        text=" ".join(x["text"] for x in cur), words=cur))
    return out


def speech_intervals():
    m = []
    for w in load_words():
        if m and w["start"] <= m[-1][1]:
            m[-1][1] = max(m[-1][1], w["end"])
        else:
            m.append([w["start"], w["end"]])
    return m

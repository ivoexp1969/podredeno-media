#!/usr/bin/env python3
"""Compose 5 original background tracks (MIDI) for @podredeno.bg.
All material is written here; rendered with FluidR3_GM (MIT licence) -> no third-party music rights."""
import random, sys, os
import pretty_midi as pm

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def n(name, octave):
    return 12 * (octave + 1) + NOTE[name]


class Song:
    def __init__(self, bpm, seed):
        self.bpm = bpm; self.beat = 60.0 / bpm
        self.midi = pm.PrettyMIDI(initial_tempo=bpm)
        self.inst = {}
        self.rnd = random.Random(seed)

    def ins(self, key, program, drum=False):
        if key not in self.inst:
            i = pm.Instrument(program=program, is_drum=drum, name=key)
            self.inst[key] = i; self.midi.instruments.append(i)
        return self.inst[key]

    def add(self, key, program, pitch, start_beat, dur_beats, vel, drum=False, jitter=0.012):
        t = start_beat * self.beat + self.rnd.uniform(-jitter, jitter)
        t = max(0.0, t)
        v = max(1, min(127, int(vel + self.rnd.randint(-6, 6))))
        self.ins(key, program, drum).notes.append(
            pm.Note(velocity=v, pitch=pitch, start=t, end=t + dur_beats * self.beat * 0.98))

    def save(self, name):
        self.midi.write(os.path.join(OUT, name + ".mid"))


def chord(root, quality, octave=4):
    iv = {"maj": [0, 4, 7], "min": [0, 3, 7], "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10],
          "6": [0, 4, 7, 9], "add9": [0, 4, 7, 14], "sus2": [0, 2, 7], "dom7": [0, 4, 7, 10]}[quality]
    r = n(root, octave)
    return [r + i for i in iv]


# ---------- 1. Утро: lo-fi rhodes, 80 bpm, C major ----------
def utro():
    s = Song(80, 1)
    prog = [("C", "maj7"), ("A", "min7"), ("F", "maj7"), ("G", "6")]
    bars = 14  # 42 s
    mel = [(0, 1.5, "E", 5), (1.5, .5, "G", 5), (2, 2, "A", 5),
           (4, 1, "G", 5), (5, 1, "E", 5), (6, 2, "C", 5),
           (8, 1.5, "A", 4), (9.5, .5, "C", 5), (10, 2, "D", 5),
           (12, 1, "E", 5), (13, 1, "D", 5), (14, 2, "G", 4)]
    for b in range(bars):
        root, q = prog[b % 4]; t0 = b * 4
        ch = chord(root, q, 3 if root in ("A", "G") else 4)
        if root in ("A", "G"): ch = [x + 12 for x in ch]
        # rhodes: chord on 1 and a soft push on the "and" of 2
        for x in ch: s.add("rhodes", 4, x, t0, 1.9, 58)
        for x in ch[1:]: s.add("rhodes", 4, x, t0 + 2.5, 1.4, 44)
        s.add("bass", 32, n(root, 2), t0, 1.5, 70); s.add("bass", 32, n(root, 2) + 7, t0 + 2.5, 1.0, 58)
        if 2 <= b < bars - 1:  # drums, swung hats
            s.add("dr", 0, 36, t0, .5, 78, True); s.add("dr", 0, 36, t0 + 2.75, .5, 60, True)
            s.add("dr", 0, 37, t0 + 1, .5, 62, True); s.add("dr", 0, 37, t0 + 3, .5, 62, True)
            for k in range(4):
                s.add("dr", 0, 42, t0 + k, .25, 40, True); s.add("dr", 0, 42, t0 + k + .66, .25, 28, True)
        if 6 <= b < bars - 1:  # melody on vibraphone, 4-bar phrase
            ph = (b - 6) % 4
            for (st, d, nm, o) in mel:
                if ph * 4 <= st < ph * 4 + 4:
                    s.add("vib", 11, n(nm, o), t0 + st - ph * 4, d, 62)
    for x in chord("C", "maj7", 4): s.add("rhodes", 4, x, bars * 4, 4, 52)
    s.add("bass", 32, n("C", 2), bars * 4, 4, 60)
    s.save("utro")


# ---------- 2. Крачка: bright pop pluck, 112 bpm, D major ----------
def krachka():
    s = Song(112, 2)
    prog = [("D", "maj"), ("A", "maj"), ("B", "min"), ("G", "maj")]
    bars = 20  # ~43 s
    mel = [(0, .5, "F#", 5), (.5, .5, "A", 5), (1, 1, "B", 5), (2, 1, "A", 5), (3, 1, "F#", 5),
           (4, .5, "E", 5), (4.5, .5, "F#", 5), (5, 1.5, "E", 5), (6.5, 1.5, "C#", 5),
           (8, .5, "D", 5), (8.5, .5, "F#", 5), (9, 1, "B", 5), (10, 1, "A", 5), (11, 1, "F#", 5),
           (12, 1, "G", 5), (13, 1, "F#", 5), (14, 2, "D", 5)]
    for b in range(bars):
        root, q = prog[b % 4]; t0 = b * 4
        ch = chord(root, q, 4)
        if root in ("A", "B"): ch = [x - 12 if x > n("E", 5) else x for x in ch]
        arp = [ch[0], ch[1], ch[2], ch[1] + 12 if False else ch[2] + 5 - 5, ch[0] + 12, ch[2], ch[1], ch[2]]
        for k in range(8):
            s.add("pluck", 46, arp[k], t0 + k * .5, .45, 66 if k % 2 == 0 else 54)  # harp
        s.add("bass", 38, n(root, 2), t0, .9, 84); s.add("bass", 38, n(root, 2), t0 + 1.5, .4, 70)
        s.add("bass", 38, n(root, 2), t0 + 2, .9, 80); s.add("bass", 38, n(root, 2) + 12, t0 + 3.5, .4, 66)
        if 2 <= b < bars - 1:
            for k in range(4): s.add("dr", 0, 36, t0 + k, .4, 82, True)
            s.add("dr", 0, 39, t0 + 1, .4, 70, True); s.add("dr", 0, 39, t0 + 3, .4, 70, True)
            for k in range(8): s.add("dr", 0, 42 if k % 2 == 0 else 46, t0 + k * .5 + .0, .2, 38 if k % 2 == 0 else 30, True)
        if 6 <= b < bars - 2:
            ph = (b - 6) % 4
            for (st, d, nm, o) in mel:
                if ph * 4 <= st < ph * 4 + 4:
                    s.add("mar", 12, n(nm, o), t0 + st - ph * 4, d, 74)
    for x in chord("D", "maj", 4): s.add("pluck", 46, x, bars * 4, 3, 66)
    s.add("bass", 38, n("D", 2), bars * 4, 2, 76); s.add("dr", 0, 49, bars * 4, 2, 60, True)
    s.save("krachka")


# ---------- 3. Фокус: ambient pad + piano, 68 bpm, A minor ----------
def fokus():
    s = Song(68, 3)
    prog = [("A", "min7"), ("F", "maj7"), ("C", "add9"), ("G", "sus2")]
    bars = 12  # ~42 s
    pno = [(0, "E", 5), (1.5, "C", 5), (2.5, "A", 4), (4, "A", 5), (5.5, "E", 5), (6.5, "C", 5),
           (8, "G", 5), (9.5, "E", 5), (10.5, "D", 5), (12, "D", 5), (13.5, "B", 4), (14.5, "G", 4)]
    for b in range(bars):
        root, q = prog[b % 4]; t0 = b * 4
        ch = chord(root, q, 3 if root in ("A", "G") else 4)
        if root in ("A", "G"): ch = [x + 12 for x in ch]
        for x in ch: s.add("pad", 89, x, t0, 4, 56, jitter=0)
        s.add("bass", 89, n(root, 2), t0, 4, 50, jitter=0)
        if 1 <= b < bars - 1:
            ph = b % 4
            for (st, nm, o) in pno:
                if ph * 4 <= st < ph * 4 + 4:
                    s.add("piano", 0, n(nm, o), t0 + st - ph * 4, 2.5, 52)
        if 4 <= b < bars - 1:
            for k in range(4): s.add("dr", 0, 70, t0 + k + .5, .2, 30, True)  # soft shaker
    for x in chord("A", "min7", 3): s.add("pad", 89, x + 12, bars * 4, 4, 48, jitter=0)
    s.add("piano", 0, n("A", 4), bars * 4, 4, 50)
    s.save("fokus")


# ---------- 4. Серия: nylon guitar + glockenspiel, 96 bpm, G major ----------
def seria():
    s = Song(96, 4)
    prog = [("G", "maj"), ("E", "min"), ("C", "maj"), ("D", "maj")]
    bars = 17  # ~42 s
    mel = [(0, 1, "B", 5), (1, .5, "D", 6), (1.5, .5, "B", 5), (2, 2, "G", 5),
           (4, 1, "G", 5), (5, .5, "B", 5), (5.5, .5, "G", 5), (6, 2, "E", 5),
           (8, 1, "E", 5), (9, .5, "G", 5), (9.5, .5, "E", 5), (10, 2, "C", 5),
           (12, 1, "D", 5), (13, 1, "F#", 5), (14, 2, "A", 5)]
    strum = [(0, 1, 70), (1, .5, 50), (1.5, .5, 58), (2.5, .5, 56), (3, 1, 62)]
    for b in range(bars):
        root, q = prog[b % 4]; t0 = b * 4
        ch = chord(root, q, 3)
        voic = [ch[0], ch[2], ch[0] + 12, ch[1] + 12, ch[2] + 12]
        for (st, d, v) in strum:
            for i, x in enumerate(voic):
                s.add("gtr", 24, x, t0 + st + i * 0.015, d, v - i * 2, jitter=0.004)
        s.add("bass", 32, n(root, 2), t0, 1.5, 72); s.add("bass", 32, n(root, 2) + 7, t0 + 2, 1.5, 62)
        if 2 <= b < bars - 1:
            s.add("dr", 0, 36, t0, .4, 64, True); s.add("dr", 0, 36, t0 + 2, .4, 58, True)
            s.add("dr", 0, 37, t0 + 1, .4, 56, True); s.add("dr", 0, 37, t0 + 3, .4, 56, True)
            for k in range(8): s.add("dr", 0, 70, t0 + k * .5, .2, 40 if k % 2 == 0 else 30, True)
        if 5 <= b < bars - 1:
            ph = (b - 5) % 4
            for (st, d, nm, o) in mel:
                if ph * 4 <= st < ph * 4 + 4:
                    s.add("glock", 9, n(nm, o), t0 + st - ph * 4, d, 58)
    for x in chord("G", "maj", 3): s.add("gtr", 24, x, bars * 4, 4, 60)
    s.add("bass", 32, n("G", 2), bars * 4, 3, 60)
    s.save("seria")


# ---------- 5. Старт: piano + strings build, 100 bpm, F major ----------
def start():
    s = Song(100, 5)
    prog = [("F", "maj"), ("C", "maj"), ("D", "min"), ("A#", "maj")]
    bars = 17  # ~41 s
    for b in range(bars):
        root, q = prog[b % 4]; t0 = b * 4
        ch = chord(root, q, 4)
        if root in ("D", "A#"): ch = [x - 12 if x > n("F", 5) else x for x in ch]
        # piano eighth-note pulse
        for k in range(8):
            for x in ch: s.add("piano", 0, x, t0 + k * .5, .45, 60 if k % 2 == 0 else 46)
        s.add("piano", 0, n(root, 2), t0, 2, 70); s.add("piano", 0, n(root, 3), t0 + 2, 2, 62)
        if b >= 4:  # strings come in
            for x in chord(root, q, 3): s.add("str", 48, x + (12 if root in ("C", "D", "F") else 0), t0, 4, 52 + min(20, (b - 4) * 2), jitter=0)
        if b >= 8:
            s.add("str2", 48, chord(root, q, 5)[2] if root != "A#" else n("D", 6), t0, 4, 50 + min(16, (b - 8) * 2), jitter=0)
        if 4 <= b < bars - 1:
            s.add("dr", 0, 36, t0, .4, 80, True); s.add("dr", 0, 36, t0 + 2, .4, 74, True)
            if b >= 8:
                s.add("dr", 0, 38, t0 + 1, .4, 60, True); s.add("dr", 0, 38, t0 + 3, .4, 60, True)
                for k in range(8): s.add("dr", 0, 42, t0 + k * .5, .2, 36, True)
    for x in chord("F", "maj", 4): s.add("piano", 0, x, bars * 4, 4, 66)
    for x in chord("F", "maj", 3): s.add("str", 48, x + 12, bars * 4, 4, 60, jitter=0)
    s.add("piano", 0, n("F", 2), bars * 4, 4, 70); s.add("dr", 0, 49, bars * 4, 3, 64, True)
    s.save("start")


for f in (utro, krachka, fokus, seria, start):
    f()
print("ok")

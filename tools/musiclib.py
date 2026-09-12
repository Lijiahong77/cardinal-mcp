"""musiclib: a three-in-one knowledge base + applier for drum patterns, chord
progressions, and tone recipes.

Division of labour with paramlib
--------------------------------
- paramlib answers "what is knob #7?" — objective facts scraped from source.
- musiclib answers "how do I get a warm sound?" — recipes and material that can
  change with taste.

Three data layers
-----------------
1. drum_patterns   16-step grid, 'x'(accent) 'o'(soft) '.' (silent) per line, one
                   bar per line.
2. progressions    chord progressions as scale degrees (I/ii/vi...), transposable
                   to any key.
3. recipes         tone recipes: module + param NAME + suggested value + why.
                   Params are written by NAME (not number) and translated to numbers
                   by paramlib — so a recipe survives a module's renumbering.

USAGE
----
    python musiclib.py styles                       # list drum patterns
    python musiclib.py drums lofi_hiphop            # show a pattern's grid
    python musiclib.py chords pop_1564 D minor      # show a progression (D minor)
    python musiclib.py recipes                      # list tone recipes
    python musiclib.py recipe warm_pad               # show a recipe's detail
    python musiclib.py apply "D:/Cardinal/patches/helm_keys.vcv" warm_pad
                                                     # write a recipe into a patch
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "music")
OUT_FILE = os.path.join(OUT_DIR, "knowledge.json")

sys.path.insert(0, HERE)


# ================================================================ Drum patterns
# 16-step grid: 16 cells per bar. x=accent o=soft .=silent.
# Multiple lines = multiple bars, '|' added for readability (stripped on parse).

DRUM_PATTERNS = {
    "four_on_floor": {
        "name": "Four-on-the-floor / House",
        "bpm": [118, 128],
        "mood": "steady, danceable, universal",
        "desc": "kick on every beat (four on the floor), off-beat open hat is the soul of house.",
        "kick": "x...x...x...x...",
        "snare": "....x.......x...",
        "hat": "..o...o...o...o.",
    },
    "rock_basic": {
        "name": "Basic Rock",
        "bpm": [100, 140],
        "mood": "direct, driving",
        "desc": "kick on beats 1 & 3, snare on 2 & 4. The most classic groove.",
        "kick": "x.......x.......",
        "snare": "....x.......x...",
        "hat": "x.o.x.o.x.o.x.o.",
    },
    "lofi_hiphop": {
        "name": "Lo-fi Hip Hop",
        "bpm": [70, 92],
        "mood": "lazy, nostalgic, good study background",
        "desc": "kick pushed back (beat 1 and the 2.5 beat), snare on beat 3, a swung feel.",
        "kick": "x.....o.x.......",
        "snare": "........x.......",
        "hat": "o.o.o.o.o.o.o.o.",
    },
    "trap": {
        "name": "Trap",
        "bpm": [130, 150],
        "mood": "pressing, modern",
        "desc": "808 kick + dense rolling hi-hats. Snare on beat 3.",
        "kick": "x.....o...x.....",
        "snare": "........x.......",
        "hat": "xoxxooxxoxxoxoxx",
    },
    "breakbeat": {
        "name": "Breakbeat",
        "bpm": [160, 175],
        "mood": "broken, punchy, dnb-ish",
        "desc": "scatter the kick and snare to create a 'broken beat' tension.",
        "kick": "x.....x...x.....",
        "snare": "....x..x..x.x...",
        "hat": "o.o.o.o.o.o.o.o.",
    },
    "ballad": {
        "name": "Ballad / Story",
        "bpm": [60, 80],
        "mood": "calm, breathing room",
        "desc": "sparse kick and snare, leaving space for melody and voice.",
        "kick": "x.......o.......",
        "snare": "....x.......x...",
        "hat": "..o...o...o...o.",
    },
    "bossa": {
        "name": "Bossa Nova",
        "bpm": [90, 110],
        "mood": "relaxed, breathing",
        "desc": "a two-bar call-and-response; kick and snare interlock.",
        "kick": "x..o..x...x..o..",
        "snare": "..o..x..o..x..o.",
        "hat": "o.o.o.o.o.o.o.o.",
    },
    "halftime": {
        "name": "Halftime / Post-rock",
        "bpm": [60, 75],
        "mood": "heavy, vast",
        "desc": "snare lands on beat 3, feeling half as fast — good for long builds.",
        "kick": "x.......x.......",
        "snare": "........x.......",
        "hat": "o...o...o...o...",
    },
    "none": {
        "name": "No drums",
        "bpm": [0, 0],
        "mood": "pure ambience",
        "desc": "leave empty; keep only harmony and tone.",
        "kick": "." * 16, "snare": "." * 16, "hat": "." * 16,
    },
}


# ================================================================ Chord progressions
# `degrees` are scale degrees; upper/lower case marks major/minor triads; a numeric
# suffix marks a seventh chord (e.g. ii7, V7).

PROGRESSIONS = {
    "pop_1564": {
        "name": "Pop universal (I–V–vi–IV)",
        "degrees": ["I", "V", "vi", "IV"],
        "mood": "bright, generic, almost never wrong",
        "style": ["pop", "ballad"],
        "desc": "Overused but genuinely great. Good for a chorus.",
    },
    "pop_6415": {
        "name": "Minor-flavoured pop (vi–IV–I–V)",
        "degrees": ["vi", "IV", "I", "V"],
        "mood": "uplifting with a touch of melancholy",
        "style": ["pop", "edm"],
        "desc": "Starts on the sixth degree, emotionally 'grabs'. EDM chorus staple.",
    },
    "canon": {
        "name": "Canon progression (I–V–vi–iii–IV–I–IV–V)",
        "degrees": ["I", "V", "vi", "iii", "IV", "I", "IV", "V"],
        "mood": "narrative, forward-moving",
        "style": ["pop", "ballad"],
        "desc": "Full 8-bar version; the bass line walks down stepwise, easy to melody over.",
    },
    "jazz_251": {
        "name": "Jazz ii–V–I",
        "degrees": ["ii7", "V7", "Imaj7"],
        "mood": "warm, resolved",
        "style": ["jazz", "lofi"],
        "desc": "The core functional-harmony sentence. Add a vi7 and it loops.",
    },
    "lofi_2516": {
        "name": "Lo-fi loop (ii7–V7–Imaj7–vi7)",
        "degrees": ["ii7", "V7", "Imaj7", "vi7"],
        "mood": "relaxed, nostalgic, infinitely loopable",
        "style": ["lofi", "jazz"],
        "desc": "Seventh chords soften the colour; pairs well with lo-fi drums.",
    },
    "minor_epic": {
        "name": "Epic minor (i–VI–III–VII)",
        "degrees": ["i", "VI", "III", "VII"],
        "mood": "grand, cinematic",
        "style": ["epic", "edm"],
        "desc": "The 'hottest' minor progression; huge reverb sells it.",
    },
    "andalusian": {
        "name": "Andalusian (i–VII–VI–V)",
        "degrees": ["i", "VII", "VI", "V"],
        "mood": "exotic, fateful",
        "style": ["flamenco", "epic"],
        "desc": "Classic Spanish flamenco descent. The final V is major — full of tension.",
    },
    "blues_12": {
        "name": "12-bar Blues",
        "degrees": ["I7", "I7", "I7", "I7", "IV7", "IV7", "I7", "I7",
                    "V7", "IV7", "I7", "V7"],
        "mood": "rootsy, self-propelling",
        "style": ["blues", "rock"],
        "desc": "Standard 12 bars, all dominant sevenths.",
    },
    "ambient_drone": {
        "name": "Ambient drone (i suspended)",
        "degrees": ["i", "i", "VI", "VI"],
        "mood": "static, meditative",
        "style": ["ambient", "drone"],
        "desc": "Each chord holds a long time; motion comes from timbre, not harmony.",
    },
    "bedroom_4536": {
        "name": "Bedroom pop (IV–V–iii–vi)",
        "degrees": ["IV", "V", "iii", "vi"],
        "mood": "youthful, Japanese-ish",
        "style": ["pop"],
        "desc": "High-frequency progression in JP/anime songs.",
    },
}


# ================================================================ Tone recipes
# Params written by NAME (translated to numbers by paramlib). `value` is the
# module's internal scale value, NOT a percentage.

RECIPES = {
    "warm_pad": {
        "name": "Warm Pad",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "soft, spacious, unobtrusive",
        "desc": "slow attack, long release, slightly dark filter, plenty of reverb. Good under a melody.",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.45, "why": "slow attack, sound 'floats in' rather than 'hits'"},
            {"module": "ADSR", "param": "Decay", "value": 0.6, "why": "gentle fall"},
            {"module": "ADSR", "param": "Sustain", "value": 0.8, "why": "stays full while held"},
            {"module": "ADSR", "param": "Release", "value": 0.75, "why": "leaves a tail after release"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 6.0, "why": "a bit above centre — cuts harsh highs but keeps air"},
            {"module": "VCF", "param": "Resonance", "value": 0.12, "why": "a touch of resonance gives the sound 'body'"},
            {"module": "VCO", "param": "Frequency modulation", "value": 0.05, "why": "slight velocity response, keeps dynamics"},
            {"module": "Plateau", "param": "Wet level", "value": 0.45, "why": "plenty of reverb, creates space"},
            {"module": "Plateau", "param": "Size", "value": 0.75, "why": "large space"},
            {"module": "Plateau", "param": "Decay", "value": 0.8, "why": "long reverb tail"},
        ],
    },
    "bright_pluck": {
        "name": "Bright Pluck",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "crisp, granular",
        "desc": "short attack + fast decay, filter opened bright. Good for melody and arps.",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.02, "why": "near-instant attack is what makes it 'pluck'"},
            {"module": "ADSR", "param": "Decay", "value": 0.22, "why": "fast decay is the key to a pluck"},
            {"module": "ADSR", "param": "Sustain", "value": 0.0, "why": "no sustain, let it fade naturally"},
            {"module": "ADSR", "param": "Release", "value": 0.2, "why": "short tail"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 18.0, "why": "open bright, keep the overtones"},
            {"module": "VCF", "param": "Resonance", "value": 0.2, "why": "slight resonance adds a 'ting'"},
            {"module": "Plateau", "param": "Wet level", "value": 0.28, "why": "a little reverb, not too wet"},
        ],
    },
    "lofi_keys": {
        "name": "Lo-fi Keys",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "dull, old, tape-like",
        "desc": "filter pushed dark + slightly slow attack; pairs perfectly with lo-fi drums.",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.08, "why": "slightly delayed attack"},
            {"module": "ADSR", "param": "Decay", "value": 0.5, "why": "medium decay"},
            {"module": "ADSR", "param": "Sustain", "value": 0.45, "why": "keep some so chords connect"},
            {"module": "ADSR", "param": "Release", "value": 0.4, "why": "natural ending"},
            {"module": "VCF", "param": "Cutoff frequency", "value": -6.0, "why": "lower the cutoff, drop the bright highs"},
            {"module": "VCF", "param": "Resonance", "value": 0.05, "why": "almost no resonance — flatter = older"},
            {"module": "VCF", "param": "Drive", "value": 0.2, "why": "slight overdrive simulates tape saturation"},
            {"module": "Plateau", "param": "Wet level", "value": 0.3, "why": "a little reverb"},
            {"module": "Plateau", "param": "Size", "value": 0.4, "why": "small room, not a hall"},
        ],
    },
    "dark_bass": {
        "name": "Dark Bass",
        "target": ["VCO", "VCF", "ADSR"],
        "mood": "low, thick, supportive",
        "desc": "filter pushed very low + fast attack; solid low end without mud.",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.01, "why": "bass must come out immediately"},
            {"module": "ADSR", "param": "Decay", "value": 0.3, "why": "short decay"},
            {"module": "ADSR", "param": "Sustain", "value": 0.85, "why": "hold the low end"},
            {"module": "ADSR", "param": "Release", "value": 0.12, "why": "clean cut, no drag"},
            {"module": "VCF", "param": "Cutoff frequency", "value": -30.0, "why": "push very low, keep only the fundamental"},
            {"module": "VCF", "param": "Resonance", "value": 0.18, "why": "a little resonance makes the low end 'stand'"},
        ],
    },
    "bell": {
        "name": "Bell / Chime",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "clear, distant, ringing",
        "desc": "extremely short attack + long decay, with big reverb. Good as an accent.",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.01, "why": "instant attack"},
            {"module": "ADSR", "param": "Decay", "value": 0.7, "why": "long decay makes the 'ring'"},
            {"module": "ADSR", "param": "Sustain", "value": 0.0, "why": "no sustain at all"},
            {"module": "ADSR", "param": "Release", "value": 0.5, "why": "long release"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 24.0, "why": "open bright"},
            {"module": "Plateau", "param": "Wet level", "value": 0.5, "why": "big reverb"},
            {"module": "Plateau", "param": "Size", "value": 0.9, "why": "large hall"},
            {"module": "Plateau", "param": "Decay", "value": 0.85, "why": "very long tail"},
        ],
    },
    "lead_saw": {
        "name": "Lead Saw",
        "target": ["VCO", "VCF", "ADSR", "Plateau"],
        "mood": "powerful, cutting",
        "desc": "medium attack + high sustain, filter bright with resonance. Good as the main melody.",
        "settings": [
            {"module": "ADSR", "param": "Attack", "value": 0.06, "why": "keep a little attack so it isn't too harsh"},
            {"module": "ADSR", "param": "Decay", "value": 0.4, "why": "medium"},
            {"module": "ADSR", "param": "Sustain", "value": 0.75, "why": "hold it, long notes don't break"},
            {"module": "ADSR", "param": "Release", "value": 0.3, "why": "medium tail"},
            {"module": "VCF", "param": "Cutoff frequency", "value": 14.0, "why": "fairly bright, cuts through the mix"},
            {"module": "VCF", "param": "Resonance", "value": 0.3, "why": "resonance gives the tone 'character'"},
            {"module": "Plateau", "param": "Wet level", "value": 0.22, "why": "a little reverb, stay clear"},
        ],
    },
    "lofi_kick": {
        "name": "Softened Kick",
        "target": ["BassDrum9"],
        "mood": "dull, not piercing",
        "desc": "slow the kick a touch, pick a soft sample, don't play it too loud.",
        "settings": [
            {"module": "BassDrum9", "param": "Sample", "value": 0.0, "index": 0, "why": "switch sample (try 0–15 one by one)"},
            {"module": "BassDrum9", "param": "Playback Speed", "value": 0.85, "index": 0, "why": "slow it down, sounds 'older'"},
        ],
        "note": "Sample has multiple slots (0 and 1 each map to a voice); `index` picks which.",
    },
    "halftime_kit": {
        "name": "Halftime Kit",
        "target": ["Clocked", "BassDrum9", "ClosedHiHat", "CR78"],
        "mood": "low, slow, ambient",
        "desc": "drop the clock BPM to ~70, loosen the kick and snare.",
        "settings": [
            {"module": "Clocked", "param": "Master clock", "value": 72.0, "why": "slow the whole thing down"},
            {"module": "Clocked", "param": "Clk 1 ratio", "value": -1.0, "why": "slow the hat one step -> quarter notes"},
            {"module": "Clocked", "param": "Clk 2 ratio", "value": -3.0, "why": "slow the compound drum -> only on the bar"},
        ],
    },
}


# ================================================================ MIDI pitch

NOTE_BASE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
             "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}

# Degree -> semitone offset. Keep MAJOR and MINOR separate; do NOT use a lazy
# "shift the major scale down" trick — it miscomputes the III/VI/VII roots
# (D minor's i would come out as F).
MAJOR_SCALE = {"I": 0, "II": 2, "III": 4, "IV": 5, "V": 7, "VI": 9, "VII": 11}
MINOR_SCALE = {"I": 0, "II": 2, "III": 3, "IV": 5, "V": 7, "VI": 8, "VII": 10}

CHORD_INTERVALS = {
    "": [0, 4, 7],          # major triad
    "m": [0, 3, 7],         # minor triad
    "7": [0, 4, 7, 10],     # dominant seventh (major-minor seventh)
    "maj7": [0, 4, 7, 11],  # major seventh
    "m7": [0, 3, 7, 10],    # minor seventh
}


def parse_key(text):
    """'D minor' / 'F# major' / 'Bb' -> (root_pitch_class, is_minor)."""
    text = (text or "").strip()
    m = re.match(r"^([A-Ga-g][#b]?)\s*([a-zA-Z]*)", text)
    if not m:
        return 2, False
    root = m.group(1)[0].upper() + m.group(1)[1:]
    mode = m.group(2).lower()
    minor = mode.startswith("m") and not mode.startswith("maj")
    return NOTE_BASE.get(root, 0), minor


def degree_to_chord(degree, root_pc, minor_key):
    """Turn a scale degree (e.g. vi7, Imaj7) into a chord structure.

    Upper/lower case of the degree decides the triad quality: upper = major,
    lower = minor. So `ii7` is a minor seventh (Dm7) and `V7` a dominant seventh
    (G7) — both share the '7' suffix, distinguished by case.
    """
    m = re.match(r"^([ivIV]+)(.*)$", degree)
    if not m:
        return None
    roman, suffix = m.group(1), m.group(2)
    scale = MINOR_SCALE if minor_key else MAJOR_SCALE
    key = roman.upper()
    if key not in scale:
        return None

    is_minor_triad = roman.islower()
    if suffix == "maj7":
        quality = "maj7"
    elif suffix == "m7":
        quality = "m7"
    elif suffix == "7":
        quality = "m7" if is_minor_triad else "7"
    else:
        quality = "m" if is_minor_triad else ""

    return {"degree": degree, "root": (root_pc + scale[key]) % 12,
            "quality": quality, "intervals": CHORD_INTERVALS[quality]}


def chord_notes(chord, octave=4):
    """Turn a chord into a list of MIDI note numbers. Middle C = 60."""
    base = 12 * (octave + 1) + chord["root"]
    return [base + i for i in chord["intervals"]]


def voice_lead(prev, notes, anchor=None):
    """Voice leading: shift the whole chord by octaves so it sits closest to the
    previous chord.

    We do NOT invert (root stays at the bottom), only move octaves — this keeps the
    connection smooth without losing the chord's low root.

    `anchor` is the centre pitch for the whole passage. Without it, always choosing
    "closest to the previous" drifts systematically downward (observed: D minor
    i-VI-III-VII sank all the way to C3).
    """
    if not prev:
        return list(notes)
    center = sum(prev) / len(prev)
    best = None
    best_d = None
    for shift in (0, -12, 12, -24, 24):
        cand = [n + shift for n in notes]
        cc = sum(cand) / len(cand)
        if anchor is not None and abs(cc - anchor) > 9:
            continue
        d = abs(cc - center)
        if best_d is None or d < best_d:
            best, best_d = cand, d
    return best if best is not None else list(notes)


# ================================================================ Query interface

def drum_pattern(style):
    """Return one drum pattern with its 16-step grid split into per-bar rows."""
    p = DRUM_PATTERNS.get(style)
    if not p:
        return None
    out = dict(p)
    out["style"] = style
    out["bars"] = {k: [v[i:i + 16] for i in range(0, len(v), 16)]
                   for k, v in p.items() if k in ("kick", "snare", "hat")}
    return out


def progression(name, key="C major"):
    """Resolve a named progression into concrete chords in the requested key."""
    p = PROGRESSIONS.get(name)
    if not p:
        return None
    root_pc, minor_key = parse_key(key)
    chords = []
    prev = None
    anchor = None
    for d in p["degrees"]:
        c = degree_to_chord(d, root_pc, minor_key)
        if not c:
            continue
        raw = chord_notes(c)
        if anchor is None:
            anchor = sum(raw) / len(raw)
        c["notes"] = voice_lead(prev, raw, anchor)
        c["notes_plain"] = raw
        prev = c["notes"]
        chords.append(c)
    return {"name": p["name"], "mood": p["mood"], "desc": p["desc"],
            "key": key, "degrees": p["degrees"], "chords": chords}


def recipe(name):
    """Return one recipe dict (adds a name_key for reference)."""
    r = RECIPES.get(name)
    if not r:
        return None
    out = dict(r)
    out["name_key"] = name
    return out


def suggest(text):
    """Plain language -> candidate recipes/patterns. Returns [(score, kind, key, name, mood)]"""
    t = (text or "").lower()
    hits = []
    for k, r in RECIPES.items():
        score = 0
        if k.replace("_", "") in t.replace("_", "").replace(" ", ""):
            score += 3
        for w in re.split(r"[\s,，/]+", t):
            if not w:
                continue
            if w in r["name"].lower() or w in r.get("mood", "").lower() or w in r.get("desc", "").lower():
                score += 1
        if score:
            hits.append((score, "recipe", k, r["name"], r.get("mood", "")))
    for k, p in DRUM_PATTERNS.items():
        score = 0
        for w in re.split(r"[\s,，/]+", t):
            if not w:
                continue
            if w in p["name"].lower() or w in p.get("mood", "").lower():
                score += 1
        if score:
            hits.append((score, "drums", k, p["name"], p.get("mood", "")))
    for k, p in PROGRESSIONS.items():
        score = 0
        for w in re.split(r"[\s,，/]+", t):
            if not w:
                continue
            if w in p["name"].lower() or w in p.get("mood", "").lower():
                score += 1
        if score:
            hits.append((score, "chords", k, p["name"], p.get("mood", "")))
    hits.sort(key=lambda x: -x[0])
    return hits[:8]


# ================================================================ Apply to a patch

def apply_recipe(patch_path, name, dry_run=False):
    """Write a recipe into a .vcv file.

    Param NAME -> number translation is delegated to paramlib; any param we cannot
    find is reported explicitly (never silently skipped).
    """
    import patchio
    import paramlib as pl

    r = recipe(name)
    if not r:
        return {"error": "no such recipe: {}".format(name)}
    if not os.path.exists(patch_path):
        return {"error": "patch file not found: {}".format(patch_path)}

    patch = patchio.read_patch(patch_path)
    by_model = {}
    for m in patch.get("modules", []):
        by_model.setdefault(m["model"], []).append(m)

    applied, skipped = [], []
    for s in r["settings"]:
        model = s["module"]
        mods = by_model.get(model)
        if not mods:
            skipped.append({"module": model, "param": s["param"],
                            "why": "patch has no {} module".format(model)})
            continue
        mod = mods[0]
        plugin = mod["plugin"]
        entry = pl.lookup(plugin, model)
        if not entry:
            skipped.append({"module": model, "param": s["param"], "why": "module not in dictionary"})
            continue

        want = s["param"].lower()
        # A param name may have several slots (e.g. a drum's Sample); `index` picks which.
        cands = []
        for pid, p in entry["params"].items():
            if (p.get("name") or "").lower() == want:
                cands.append(int(pid))
        if not cands:
            for pid, p in entry["params"].items():
                if want in (p.get("name") or "").lower():
                    cands.append(int(pid))
        if not cands:
            skipped.append({"module": model, "param": s["param"],
                            "why": "no such param name in this module"})
            continue
        cands.sort()
        idx = s.get("index", 0)
        if idx >= len(cands):
            skipped.append({"module": model, "param": s["param"],
                            "why": "only {} same-name slots, cannot take #{}".format(len(cands), idx)})
            continue
        pid = cands[idx]

        params = mod.setdefault("params", [])
        found = False
        for q in params:
            if q.get("id") == pid:
                q["value"] = float(s["value"])
                found = True
                break
        if not found:
            params.append({"id": pid, "value": float(s["value"])})
        applied.append({"module": model, "param": s["param"], "param_id": pid,
                        "value": s["value"], "why": s.get("why", "")})

    if not dry_run and applied:
        patchio.write_patch(patch_path, patch)
    return {"recipe": r["name"], "file": os.path.basename(patch_path),
            "applied": applied, "skipped": skipped, "written": bool(applied and not dry_run)}


def dump():
    """Write the knowledge base to music/knowledge.json."""
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {"drum_patterns": DRUM_PATTERNS, "progressions": PROGRESSIONS,
            "recipes": RECIPES}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return OUT_FILE


# ================================================================ CLI

def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 0
    cmd = argv[1]

    if cmd == "styles":
        for k, p in DRUM_PATTERNS.items():
            print("  {:<16} {:<18} BPM {}-{}  {}".format(
                k, p["name"], p["bpm"][0], p["bpm"][1], p["mood"]))
    elif cmd == "drums":
        p = drum_pattern(argv[2]) if len(argv) > 2 else None
        if not p:
            print("no such pattern")
            return 1
        print("{}  (BPM {}-{})".format(p["name"], p["bpm"][0], p["bpm"][1]))
        print(p["desc"])
        for row in ("kick", "snare", "hat"):
            print("  {:<6} |{}|".format(row, p[row]))
        print("        x=accent o=soft .=empty (each cell is a 16th note)")
    elif cmd == "chords":
        if len(argv) < 3:
            for k, p in PROGRESSIONS.items():
                print("  {:<16} {:<32} {}".format(k, p["name"], p["mood"]))
            return 0
        key = " ".join(argv[3:]) if len(argv) > 3 else "C major"
        pr = progression(argv[2], key)
        if not pr:
            print("no such progression")
            return 1
        print("{}  [{}]".format(pr["name"], pr["key"]))
        print(pr["desc"])
        for c in pr["chords"]:
            print("  {:<4} {:<6} MIDI {}".format(c["degree"], c["quality"] or "major", c["notes"]))
    elif cmd == "recipes":
        for k, r in RECIPES.items():
            print("  {:<16} {:<18} {}".format(k, r["name"], r["mood"]))
    elif cmd == "recipe":
        r = recipe(argv[2]) if len(argv) > 2 else None
        if not r:
            print("no such recipe")
            return 1
        print("{}  ({})".format(r["name"], r["mood"]))
        print(r["desc"])
        for s in r["settings"]:
            print("  {:<14} {:<22} = {:<8} {}".format(
                s["module"], s["param"], s["value"], s.get("why", "")))
    elif cmd == "apply":
        if len(argv) < 4:
            print("usage: apply <patch.vcv> <recipe>")
            return 1
        res = apply_recipe(argv[2], argv[3])
        if res.get("error"):
            print("error:", res["error"])
            return 1
        print("{} -> {}".format(res["recipe"], res["file"]))
        for a in res["applied"]:
            print("  set {:<4} {} (param {}) = {}".format(
                a["module"], a["param"], a["param_id"], a["value"]))
        for s in res["skipped"]:
            print("  skip {:<4} {} -- {}".format(s["module"], s["param"], s["why"]))
    elif cmd == "suggest":
        for score, kind, k, nm, mood in suggest(" ".join(argv[2:])):
            print("  [{:<6}] {:<16} {:<20} {}".format(kind, k, nm, mood))
    elif cmd == "dump":
        print("written:", dump())
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

# cardinal-mcp

> A lightweight shell that lets an AI agent drive [Cardinal](https://github.com/DISTRHO/Cardinal)
> (a modular synth) directly.
> 12 MCP tools + 24 zero-dependency Python utilities = a version-controllable,
> automatable, remotely-controllable synth workflow.

---

> [!CAUTION]
> **AI-Generated Project — Verify Before You Trust It.**
> This repository was produced almost entirely by an **AI Agent (WorkBuddy)**, not by a
> human typing every line. The code, docs, and param dictionaries were generated and
> self-reviewed by the agent. They are shared in the hope they help — but **treat them
> as unverified**: review, test, and audit anything you intend to run, especially the
> OSC / file-editing tools that touch your running Cardinal. The agent can be wrong,
> and it cannot hear your audio.
>
> 中文读者见 **[`README.zh-CN.md`](README.zh-CN.md)**；完整声明见 **[`AI-DISCLOSURE.md`](AI-DISCLOSURE.md)**。

---

## What it is / isn't

**What it is**

Cardinal is a hard fork of VCV Rack (by DISTRHO), built to run as a plugin and a
standalone synth. But if you, like the author, want to "play keyboard + drums + tweak
tone" *and* keep a code-level copy an AI can edit, it's a black box — no MCP interface,
no structured output, module positions are all drag-and-drop in the GUI.

`cardinal-mcp` wraps a layer around it:
- Uses Cardinal's **OSC (4 messages)** + **Windows screenshots** + **live autosave
  read-back** to assemble **12 semantic MCP tools** (`cardinal_load_patch` /
  `cardinal_set_param` / `cardinal_read_live`, etc.).
- Ships a set of **zero-dependency probe tools**: DPI probe, MIDI sniffer, GDI
  screenshot, live-autosave read-back, layout gate.
- A `params/modules.json`: **15 modules / 248 named params**, scraped from Cardinal's
  bundled modules' C++ source.
- A `music/knowledge.json`: 9 drum patterns / 10 chord progressions / 8 tone recipes.
- A **layout gate**: every time you add a module or rewire, you must pass
  `layout_patch.py guard` before pushing.

**What it is NOT**

- **Not a Cardinal plugin** — it does not modify Cardinal itself; it only drives it
  externally via OSC + the file layer.
- **Not a music-teaching project** — it only solves "engineering + remote control";
  the music knowledge base is incidental scaffolding.
- **Ships no third-party works** — Cardinal's official example patches, MidiSuite
  config screenshots, and source caches are excluded from the repo. They belong to
  others; see `docs/ATTRIBUTION.md` for how to obtain them.

---

## Who it's for

- Anyone with Cardinal standalone + a MIDI keyboard who wants an MCP-aware AI
  (Cursor / WorkBuddy) to tweak params, swap tones, and rewire directly.
- Anyone who wants to turn a "mouse-built synth rack" into plain text they can `git diff`.
- Anyone who wants to pre-generate and pre-validate racks in a headless / CI environment.

---

## 30-second start

### 1. Install dependencies

Only two Python packages:

```bash
pip install -r requirements.txt
# or manually: python-osc + zstandard
```

Few dependencies because most tools use the standard library only
(`win32gui` / `ctypes` / `socket` / `tarfile` / `json`).

### 2. Launch Cardinal and enable OSC

```text
Open CardinalNative.exe
Menu: Engine → Enable OSC remote control   (top menu; ⚠️ click it again every launch)
```

Verify OSC is up:

```bash
python tools/cardinal_mcp.py --selftest
# last line should read: OK: All 12 tools reachable
```

If it doesn't connect, first check in PowerShell:
```powershell
Get-NetUDPEndpoint -LocalPort 2228 -ErrorAction SilentlyContinue
```
You should see `CardinalNative.exe` bound to that port.

### 3. Register the MCP server in your AI client

Add this to your MCP-aware client (WorkBuddy / Claude Desktop / Cursor all work):

```json
{
  "mcpServers": {
    "cardinal": {
      "command": "python",
      "args": ["D:/Cardinal/tools/cardinal_mcp.py"],
      "env": {
        "CARDINAL_PATCH_DIR": "D:/Cardinal/patches",
        "CARDINAL_IP": "127.0.0.1",
        "CARDINAL_PORT": "2228"
      }
    }
  }
}
```

See `mcp.example.json` for the full field list. Every env var has a sane default, so
it runs even with no config.

### 4. Try it

In your AI client, type: `List all current patches and tell me how many modules helm_full.vcv has.`

Behind the scenes it calls `cardinal_list_patches` + `cardinal_patch_info`.

---

## What it can do — the 12 MCP tools

| Tool | Does | Common use |
|---|---|---|
| `cardinal_ping` | send `/hello` to check Cardinal's OSC response | connectivity troubleshooting |
| `cardinal_list_patches` | list all .vcv patches in `patches/` | pick a rack to load |
| `cardinal_patch_info` | inspect a patch's module list (need moduleId to set params) | required lookup before tweaking |
| `cardinal_load_patch` | push a .vcv into running Cardinal (incl. zoom + gridOffset) | let the AI switch tones |
| `cardinal_set_param` | turn any module's knob: `moduleId + paramId + value` | change cutoff / release / etc. |
| `cardinal_set_host_param` | change one of Cardinal's 24 host params | audio device / sample rate / etc. |
| `cardinal_read_live` | read the rack Cardinal is currently running (via live autosave) | see what the user changed in the GUI |
| `cardinal_save_live` | persist current GUI state to a .vcv | user's manual changes vanish on close otherwise |
| `cardinal_module_params` | list a module's params (name → number) | find a param number |
| `cardinal_find_param` | translate plain language to a param number ("brighter" → Cutoff) | let the AI speak naturally |
| `cardinal_music` | query drum patterns / chord progressions / tone recipes | let the AI answer from the knowledge base |
| `cardinal_apply_recipe` | write a tone recipe into the current rack | one-click tone swap |

---

## Project structure

```
cardinal-mcp/
├── README.md                       ← this file (English)
├── README.zh-CN.md                 ← Chinese version
├── LICENSE                         ← MIT
├── requirements.txt                ← python-osc + zstandard
├── mcp.example.json                ← MCP config example
├── AI-DISCLOSURE.md                ← AI-generation notice (READ BEFORE USE)
│
├── tools/                          ← 24 Python utilities
│   ├── cardinal_mcp.py             ← MCP entry point (the 12 tools)
│   ├── patchio.py                  ← read/write .vcv in both formats (JSON / tar+zstd)
│   ├── layout_patch.py             ← layout gate + auto re-layout
│   ├── paramlib.py                 ← scrape the param dictionary from source
│   ├── musiclib.py                 ← tone recipes / chord progressions / drum patterns
│   ├── make_full.py                ← generate the "full keyboard controls" rack
│   ├── make_knobs.py               ← write HostMIDIMap mappings
│   ├── fix_drum_bus.py             ← drum-bus fix + input-port self-check
│   ├── winprobe.py                 ← DPI / window probe
│   ├── winmidi.py + midiprobe.py   ← native Windows MIDI tools
│   ├── shot.py                     ← GDI screenshot (zero-dependency)
│   └── ... more helper scripts
│
├── params/
│   └── modules.json                ← 15 modules / 248 named params
│
├── music/
│   └── knowledge.json              ← patterns / progressions / recipes
│
├── patches/
│   ├── helm_full.vcv               ← main rack: keys + knobs + touch + pads, all wired
│   ├── helm_keys.vcv               ← synth-only rack
│   ├── helm_drums.vcv              ← drum rack
│   └── ... (personal backups excluded by .gitignore)
│
└── docs/
    ├── DESIGN-NOTES.md             ← tech archive: how the whole thing was built
    ├── CARDINAL-REPO-NOTES.md      ← key findings from the upstream Cardinal repo
    ├── SMK25-midi-map.md           ← M-VAVE SMK25 keyboard MIDI measurement notes
    └── ATTRIBUTION.md              ← third-party resource attribution
```

---

## Workflow examples

### "Make the synth brighter"

```
You:  Raise the filter brightness of the current patch a bit
AI:   → cardinal_patch_info  (get the VCF moduleId)
     → cardinal_find_param (plain language → "Cutoff")
     → cardinal_set_param (Cutoff value = 0.75)
     → tells you in plain words: cutoff 0.5 → 0.75, sounds brighter
```

### "Swap in a chord progression"

```
You:  Give me a ii–V–I jazz accompaniment
AI:   → cardinal_music (progressions) to get ii–V–I voicings
     → cardinal_patch_info to see current ADSR / VCO config
     → cardinal_apply_recipe to write the new params
     → you press one key and hear ii–V–I
```

### "Change pad 3's sound to a short snare"

```
You:  I want pad #3 to be a shorter snare
AI:   → cardinal_patch_info to find SnareDrumN
     → see that voice i's sample is controlled by param(i)
     → cardinal_set_param to set SnareDrumN param(2) to a "shorter" sample number
     → ask you to hit the pad to verify
```

---

## Hardware / software environment (where this was verified)

> For anyone who wants to reproduce it — what environment it needs to run.

### Software

- **OS**: Windows 11 (10.0.26200, 64-bit)
- **Cardinal**: 26.02 ([DISTRHO/Cardinal](https://github.com/DISTRHO/Cardinal) 26.02
  standalone release, installed at `C:\Program Files\Cardinal-win64-26.02\`)
  - 4 variants: DISTRHO core / FX / Mini / Synth
  - launch with `CardinalNative.exe` (~100 MB, main standalone)
  - bundled module library (VCV Rack Fundamental + AudibleInstruments + community plugins)
- **Python**: 3.13.12 (managed interpreter, in an isolated venv under the user dir)
- **AI client**: WorkBuddy (via its MCP config) — Cursor / Claude Desktop work with the
  same `mcp.example.json`
- **MIDI companion software** (user-private, not shipped): M-VAVE MidiSuite, useful with
  the M-VAVE SMK25

### Hardware

- **CPU**: AMD64 (x86-64)
- **Screen**:
  - logical resolution 1600×1000
  - physical resolution 3200×2000 (200% scaling = DPI 192)
  - 1 HP (Cardinal module width unit) ≈ 21 physical px @ zoom=0.75
- **MIDI keyboard**: [M-VAVE SMK25](https://www.m-vave.com/) — 25 keys + 16 knobs +
  16 pads + touch strip + pedal + transport
  - USB + BLE
  - **full MIDI mapping measurements in `docs/SMK25-midi-map.md`**

### Network

- Works fully offline — every tool runs without a network.
- Network is used in exactly one place: `tools/paramlib.py` fetches C++ source from the
  GitHub repos of Cardinal's bundled modules on first run to extract params (cached in
  `tools/_srccache/`, **not in the repo**).

---

## Known limitations / unsupported scenarios

| Not supported | Why |
|---|---|
| Live MIDI/CV injection | Cardinal OSC only has 4 messages: `/load /param /host-param /hello`; no MIDI injection |
| Auto read-back of param changes | The live autosave is only written after structural events (see DESIGN-NOTES constraint 16); param changes are invisible until you look at the GUI |
| Unattended (headless) runs | Cardinal standalone has no headless build (VCV Rack Pro does; Cardinal doesn't) |
| Linux/macOS testing | Only verified on Windows; the Python tools are cross-platform, but `winmidi.py` / `winprobe.py` use the Win32 API |
| LMMS / DAW recording loop | That's a separate project (Cardinal.vst into a DAW); this repo stops at standalone + OSC |

---

## Documentation index

| Doc | Answers |
|---|---|
| `README.md` | Should I install this? How do I run it? |
| `README.zh-CN.md` | Chinese version of this README |
| `docs/DESIGN-NOTES.md` | How was it built? All 24 tools explained, 12 pitfalls, 5 reusable principles |
| `docs/CARDINAL-REPO-NOTES.md` | What's worth borrowing from upstream Cardinal? OSC boundaries / module list / non-existent features |
| `docs/SMK25-midi-map.md` | M-VAVE SMK25 MIDI measurements: what control sends what message, what channel, what gotcha |
| `docs/ATTRIBUTION.md` | Which third-party resources are used, and how to get them |
| `AI-DISCLOSURE.md` | **This project was generated by an AI Agent — verify before use** (bilingual notice) |
| `HANDOFF.md` | Status snapshot for a follow-up AI |

---

## Acknowledgements

- [DISTRHO/Cardinal](https://github.com/DISTRHO/Cardinal) — the target this project drives
- [VCV Rack](https://vcvrack.com/) — Cardinal is its hard fork; the module ecosystem is built on the Rack community
- [WorkBuddy](https://www.workbuddy.cn/) — the MCP host, the AI client the author uses
- python-osc / zstandard — the only two third-party Python dependencies

Use and copyright of third-party resources: see `docs/ATTRIBUTION.md`.

---

## AI generation notice (required reading)

**This project was produced almost entirely by an AI Agent (WorkBuddy), not written
line-by-line by a human.** The code, docs, and param dictionaries are AI self-reviewed
output and may contain errors. Before running any tool that edits your rack or your
running Cardinal, back up and test first.

- Full notice + a "suggested verification checklist" in **[`AI-DISCLOSURE.md`](AI-DISCLOSURE.md)** (bilingual).
- The top banner carries the same warning.

---

## License

MIT — see `LICENSE`.

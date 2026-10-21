# cardinal-mcp

> A lightweight shell that lets an AI agent drive [Cardinal](https://github.com/DISTRHO/Cardinal)
> (a modular synth) directly.
> **52 MCP tools** (MCP protocol 2025-06-18: tool annotations + structured output)
> + ~40 zero-dependency Python utilities = a version-controllable, automatable,
> remotely-controllable synth workflow.

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
- **Drive**: Cardinal's **OSC** (stock build: 4 write-only handlers) + **live autosave
  read-back** assemble **52 semantic MCP tools** (`cardinal_load_patch` /
  `cardinal_set_param` / `cardinal_read_live`, …).
- **See** (the part stock Cardinal cannot do): `tools/osc_patch/` is an idempotent
  source patch + WSL2 cross-build recipe that injects **22 OSC endpoints** into
  Cardinal — 5 read-only probes (`/modules` `/param-get` `/ports` `/signal` `/light`),
  6 runtime-fact readers, 10 simulated-human-operation endpoints, and the QuickJS
  binding. So the AI can finally *read* what the engine is doing (which modules
  loaded, a knob's real display value, per-port voltages — is this rack actually
  making sound?), and *act* on the running rack the way a human would (turn a knob,
  drag a wire, undo, send MIDI). The author's patched build is deployed and verified;
  on a stock build every such tool degrades gracefully to `probe_not_supported`.
- **Compute inside the host**: `cardinal_js_run` executes JavaScript in-process
  (QuickJS) — the same "run code inside the app" capability the blender / godot / UE
  MCPs have. Disabled by default, libc never initialized, 2000 ms wall-clock budget.
- **Validate before you load**: a 5-stage audit chain (`validate` → `ports` → `chain` →
  `values` → `flow`) aggregated into one `cardinal_audit` tool — catches the crash-on-load
  and never-makes-a-sound classes *before* pushing a rack into Cardinal.
- **Patches as code**: generators (`tools/make_*.py`, DSL in `tools/rackgen.py`) + a
  layout gate (`layout_patch.py`) — racks are plain text you can `git diff`.
- **Score export**: sequencer notes → editable `.abc` text score
  (`tools/abc_export.py` + `cardinal_export_abc`), both sequencer families supported.
- **Knowledge**: `params/modules.json` (param dictionary scraped from module C++ source,
  data-driven coverage) + 112 port-semantics entries extracted from real source enums +
  `music/knowledge.json` (9 drum patterns / 10 chord progressions / 8 tone recipes) +
  a style schema (`docs/STYLE-SCHEMA.md`) with real-rack-verified samples.

**What it is NOT**

- **Not a Cardinal plugin on the main path** — the 52 tools drive Cardinal externally
  via OSC + the file layer and work with a stock Cardinal. The optional `tools/osc_patch/`
  source patch *does* modify Cardinal (that is the only way to get read-back; Cardinal's
  OSC is write-only by design) — it is opt-in, idempotent, and ships a rollback.
- **Not a music-teaching project** — it only solves "engineering + remote control";
  the music knowledge base is incidental scaffolding.
- **Ships no third-party works** — Cardinal's official example patches, MidiSuite
  config screenshots, and source caches are excluded from the repo. They belong to
  others; see `docs/ATTRIBUTION.md` for how to obtain them.

---

## Who it's for

- Anyone with Cardinal standalone + a MIDI keyboard who wants an MCP-aware AI
  (Cursor / WorkBuddy / Claude Desktop) to tweak params, swap tones, and rewire directly.
- Anyone who wants to turn a "mouse-built synth rack" into plain text they can `git diff`.
- Anyone who wants to pre-generate and pre-validate racks in a headless / CI environment.

### Using this on your own machine

- **No personal paths are baked in.** `tools/cardinal_mcp.py` locates the repository from its
  own file location, and `CARDINAL_IP` / `CARDINAL_PORT` / `CARDINAL_PATCH_DIR` are all
  environment variables with working defaults. Clone it anywhere.
- **`mcp.example.json` is a template.** Replace `<REPO>` with your clone path.
- **Patches that use samples resolve them relative to the repository root.** If you move the
  repository, the bundled `samples/` still works. If you *delete* the `samples/` directory,
  the sampler-based patches (`demo_S4`, `demo_S5`, `quadeca_scrapyard*`) will load but be
  silent — nothing else breaks. `tools/relocate_samples.py` exists if you ever need to
  rewrite those paths for your own sample library.
- **Python 3.13 and a Cardinal standalone build are the only real prerequisites.** Two pip
  packages, both in `requirements.txt`.
- **Windows is the tested platform.** `winmidi.py` / `winprobe.py` use Win32 APIs and the
  screenshot tools assume a Windows desktop. The patch-authoring tools themselves are
  cross-platform, but MIDI input has only been exercised on Windows.
- **Any MCP client can connect.** The server is a spec-compliant MCP server
  (stdio + JSON-RPC 2.0, version-negotiated up to 2025-06-18) — not tied to WorkBuddy.

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

### 2. Launch Cardinal

```text
Open CardinalNative.exe
OSC remote control auto-starts by default (CARDINAL_OSC_AUTOSTART=1).
On a stock build you can also enable it manually:
Menu: Engine → Enable OSC remote control
```

Verify OSC is up:

```bash
python tools/cardinal_mcp.py --selftest
# last line should read: OK: All 52 tools reachable
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

## What it can do — the 52 MCP tools

### Drive (write into running Cardinal)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_ping` | send `/hello` to check Cardinal's OSC response | connectivity troubleshooting |
| `cardinal_load_patch` | push a .vcv into running Cardinal (incl. zoom + gridOffset) | let the AI switch tones |
| `cardinal_set_param` | turn any module's knob: `moduleId + paramId + value` | change cutoff / release / etc. |
| `cardinal_set_param_by_name` | set one knob by param NAME, refuses reserved/removed slots, multi-instance aware | "set the VCF cutoff" without looking up ids |
| `cardinal_set_params_batch` | set MANY knobs in one call (by param name), one read + one write, per-item receipt | adjust a whole chain of knobs in one shot |
| `cardinal_set_host_param` | change one of Cardinal's 24 host params | audio device / sample rate / etc. |
| `cardinal_save_live` | persist current GUI state to a .vcv | user's manual changes vanish on close otherwise |

### Inspect (read patches & the running rack)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_patch_info` | inspect a patch's module list (need moduleId to set params) | required lookup before tweaking |
| `cardinal_list_patches` | list all .vcv patches in `patches/` | pick a rack to load |
| `cardinal_read_live` | read the rack Cardinal is currently running (via live autosave; `stale` flag included) | see what the user changed in the GUI |
| `cardinal_module_params` | list a module's params (name → number) | find a param number |
| `cardinal_find_param` | translate plain language to a param number ("brighter" → Cutoff) | let the AI speak naturally |
| `cardinal_topology` | wiring + per-module roles + signal-reachability to HostAudio2 | "what is this rack actually doing" |

### Audit & deploy (the "never load a broken rack" chain)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_audit` | run ALL five pre-load audits in one call, verdict FAIL/WARN/PASS | gate before every `/load` |
| `cardinal_deploy` | backup → audit → load → read-back structure diff, refuses on FAIL | one-click safe deploy |
| `cardinal_diff` | on-disk .vcv vs. what the engine actually instantiated — **structure AND knob values** | catch silently dropped modules, and knobs that don't match |

### Live read probes (need the patched Cardinal build; degrade gracefully without it)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_live_modules` | every module the engine actually instantiated | ground truth after a load |
| `cardinal_get_param` | one knob's real DISPLAY value (275 ms, not 0.275) | verify a `set_param` actually landed |
| `cardinal_module_ports` | per-port wired state + live voltage | "is this input connected / silent / signaling" |
| `cardinal_scan_signal` | whole-rack scan: which modules emit non-zero voltage right now | the direct answer to "is it sounding?" |
| `cardinal_get_light` | LED brightness (e.g. Clocked's RUN lamp) | is the transport actually running |

### Module library browser (reads Cardinal's own PluginManifests — 1407 modules / 85 brands / 104 tags)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_module_search` | search the installed library by English keywords / tags / brand | pick modules from reality, not memory |
| `cardinal_module_tags` | all official tags + counts | when a search returns nothing useful |
| `cardinal_module_brands` | all brands + module counts | browse by maker |
| `cardinal_module_detail` | full manifest record for one module | manual URL, description, siblings |
| `cardinal_port_semantics` | per-socket pitch/gate/audio/cv semantics from real source | route cables by table, not by guessing |

### Sequencer & score (piano-roll equivalents)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_seq_read` | read sequencer notes as measures/note names (both families) | see the music as text |
| `cardinal_seq_edit_note` | edit ONE note (pitch / rest / velocity), refuses corrupt writes | click a piano-roll cell, remotely |
| `cardinal_seq_set_running` | start/stop a sequencer's transport (the RUN button) | start playback |
| `cardinal_export_abc` | export sequencer notes to an editable `.abc` text score | edit music outside the GUI |

### Sampler slots (right-click → "Load sample" equivalents)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_samples_list` | browse the sample library | pick from what exists, don't guess filenames |
| `cardinal_sample_inspect` | which sample each slot holds + flags dead files | find silently dead samplers |
| `cardinal_sample_load` | load a wav into a slot (path-style aware, backs up) | remote sample swapping |
| `cardinal_sample_clear` | empty one slot | clean up |

### Music & style knowledge

| Tool | Does | Common use |
|---|---|---|
| `cardinal_music` | drum patterns / chord progressions / tone recipes | let the AI answer from the knowledge base |
| `cardinal_apply_recipe` | write a tone recipe into a rack; `weight` 0..1 blends current ↔ target | one-click tone swap, or a gentle nudge |

### Runtime facts (batch B — need the patched build; degrade gracefully without it)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_build_info` | variant / gui-vs-thread / build stamp / safeMode / full endpoint list | P0: separates "OSC never started" from "Cardinal crashed" — from the client a timeout looks identical |
| `cardinal_cables` | the wiring as `id:input(mod,port)←output(mod,port)`, optionally one module | ground truth for "is it actually wired" |
| `cardinal_transport` | playing / bar / beat / bpm / tick / bypassed (zero hook) | is the sequencer transport actually running |
| `cardinal_engine_info` | sample rate / buffer size / CPU avg+max, with `cpu_refresh_ms` | CPU meters only refresh once per second — the reply says how old the data is |
| `cardinal_plugins` | which plugin slugs the CURRENT rack uses + safeMode; disk-layer check per slug | "my spelling looks right but it won't load" — safeMode means NO plugin loaded |

### Simulated human operations (batch C — these MUTATE the live rack, all undoable)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_set_param_by_display` | set a knob BY ITS DISPLAYED VALUE ("275 ms", not 0.275) | type what a human would type; the engine converts |
| `cardinal_cable_add` / `cardinal_cable_remove` | drag a wire / right-click → Disconnect | rewire without regenerating a patch. ⚠️ one cable per input port |
| `cardinal_module_move` | drag a module; `x` = grid cell, `y` = row index | fix layout surgically, never regenerate it wholesale |
| `cardinal_module_remove` | select + Delete (module and its cables) | undoable, but prefer editing a saved copy first |
| `cardinal_undo` / `cardinal_redo` | Ctrl+Z / Ctrl+Shift+Z, returns the action name | check the returned name before assuming what changed |
| `cardinal_module_json` | one live module's complete .vcv JSON | the authoritative shape for editing a module |
| `cardinal_midi_out` | inject a raw MIDI message (no hardware keyboard needed) | drive the rack from an agent. Reports `skipped:bypassed` rather than pretending |

### In-process JS (QuickJS — the host-code-execution capability blender/godot/UE MCPs have)

| Tool | Does | Common use |
|---|---|---|
| `cardinal_js_list` | list runnable JS scripts with their 1-based indexes | scripts live in `js/`, git-tracked |
| `cardinal_js_run` | execute a script inside the RUNNING Cardinal | the only path for operations needing free text or JSON |

**Why the JS route exists:** this build's liblo cannot *receive* string OSC arguments
(verified 2026-10-20 — every string-input endpoint is dead; *sending* strings still
works). Operations needing arbitrary text therefore go through a script file plus an
index argument, which is pure numeric. That also suits a workflow where rack recipes
are versioned assets rather than ad-hoc strings.

**Safety, three independent gates:**
1. **Disabled by default** — replies `disabled` unless `CARDINAL_JS_MODE` is `read`
   or `write` in Cardinal's own environment.
2. **libc is never initialized** — no `std`, no `require`, no `exec`. The runtime is
   bare `JS_NewRuntime` + `JS_NewContext`, so there is no outbound-execution path.
3. **Wall-clock budget** — 2000 ms by default (`CARDINAL_JS_BUDGET_MS` to change).
   A runaway script is interrupted and answers `budget-exceeded ms=2001`; the process
   survives (verified with a `while (true)` script).

Script contract: the script is wrapped in an IIFE, so **`return` your result** —
assigning `globalThis.result` gets overwritten with `undefined`.

| API (read, any enabled mode) | API (write, `CARDINAL_JS_MODE=write` only) |
|---|---|
| `cardinal.modules()` / `getParam(id, n)` / `ports(id)` / `cables()` / `transport()` / `moduleJson(id)` | `cardinal.setDisplayValue(id, n, v)` / `moduleFromJson(id, json)` / `addModule(slug, x, y)` / `cableAdd(...)` / `undo()` / `redo()` |

### Human-interaction index

| Tool | Does | Common use |
|---|---|---|
| `cardinal_actions` | 23 human UI operations: where the code lives, which tool covers it, status | before writing any script+reload, check what the human's button maps to |

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
├── tools/                          ← ~40 Python utilities
│   ├── cardinal_mcp.py             ← MCP entry point (the 52 tools)
│   ├── osc_patch/                  ← 3 injector sets, 22 OSC endpoints (read + act + JS)
│   │                               ← + idempotent injector (backup/verify/rollback)
│   ├── patchio.py                  ← read/write .vcv in both formats (JSON / tar+zstd)
│   ├── layout_patch.py             ← layout gate + auto re-layout
│   ├── paramlib.py                 ← scrape the param dictionary from source
│   ├── musiclib.py                 ← tone recipes / chord progressions / drum patterns
│   ├── modbrowser.py               ← module library search (reads PluginManifests)
│   ├── topology.py                 ← rack wiring / roles / reachability
│   ├── seq.py                      ← sequencer notes (piano-roll equivalent)
│   ├── abc_export.py               ← sequencer notes → .abc text score
│   ├── samplelib.py                ← sampler slots (right-click 'Load sample' equivalent)
│   ├── interaction_map.py          ← human UI operation → source code index
│   ├── style_schema.py             ← style schema validation + rack sample filling
│   ├── rackgen.py                  ← rack-generation DSL (blood-lessons preserved)
│   ├── audit_{ports,values,flow,chain}.py + validate.py  ← the audit chain
│   ├── cross_build_cardinal.sh     ← WSL2 cross-build recipe (win64)
│   ├── wslrun.py / wslout.py       ← WSL2 helpers (UTF-16 decoding, path safety)
│   ├── winprobe.py                 ← DPI / window probe
│   ├── winmidi.py + midiprobe.py   ← native Windows MIDI tools
│   ├── shot.py                     ← GDI screenshot (zero-dependency)
│   └── make_*.py                   ← per-rack generators (quadeca / yorushika / …)
│
├── params/
│   └── modules.json                ← param dictionary (data-driven coverage)
│
├── music/
│   └── knowledge.json              ← patterns / progressions / recipes
│
├── patches/
│   ├── helm_full.vcv               ← main rack: keys + knobs + touch + pads, all wired
│   ├── quadeca_life1_wdtg.vcv      ← the flagship musical rack (ear-verified)
│   ├── yorushika_shura/hana.vcv    ← style-driven racks (awaiting acceptance)
│   └── ... (personal backups excluded by .gitignore)
│
└── docs/
    ├── DESIGN-NOTES.md             ← tech archive: how the whole thing was built
    ├── CARDINAL-REPO-NOTES.md      ← key findings from the upstream Cardinal repo
    ├── TODO-BACKLOG.md             ← the single backlog (batch A done, B/C pending)
    ├── CARDINAL-MCP-SPEC.md        ← protocol spec + source-verified facts
    ├── CARDINAL-MCP-CAPABILITY-MAP.md ← what the engine can/can't do, with source lines
    ├── HUMAN-INTERACTION-MAP.md    ← human UI operations → source functions
    ├── STYLE-SCHEMA.md             ← style-as-data, with real-rack samples
    ├── SMK25-midi-map.md           ← M-VAVE SMK25 keyboard MIDI measurement notes
    └── ATTRIBUTION.md              ← third-party resource attribution
```

---

## Workflow examples

> The snippets below are **illustrations of how you would talk to the AI** — they show
> the intended conversation, not a transcript of a verified run.
>
> **What has actually been run on hardware** is recorded separately:
>
> | | |
> |---|---|
> | Quadeca-style racks | 5 racks loaded successfully in Cardinal (`docs/QUADECA-PATCHES-ACCEPTANCE.md`, real-hardware run 2026-10-17). That acceptance sheet also documents two bugs it caught — a port-index overflow that crashes, and a wrong clock source that loads fine but never plays |
> | `quadeca_life1_wdtg.vcv` | confirmed audible by ear |
> | `mini_arranger_expanded.vcv` | the MiniArranger package with its expander, accepted |
> | `mini_arranger_8voice*.vcv` | generated, **awaiting hardware acceptance** (`docs/8VOICE-PATCH-ACCEPTANCE.md`) |
> | All patches | parse cleanly under static audit |
> | OSC read probes | compiled (WSL2 cross-build) + deployed; verified by live OSC interrogation of the running engine (e.g. default rack's VCO reads 4.977 V on `/signal`) |

### "Make the synth brighter"

```
You:  Raise the filter brightness of the current patch a bit
AI:   → cardinal_patch_info  (get the VCF moduleId)
     → cardinal_find_param (plain language → "Cutoff")
     → cardinal_set_param (Cutoff value = 0.75)
     → cardinal_get_param (patched build: read back the DISPLAY value to confirm it landed)
     → tells you in plain words: cutoff 0.5 → 0.75, sounds brighter
```

### "Does this rack actually make sound?"

```
You:  I loaded the new patch but hear nothing — is it broken?
AI:   → cardinal_audit (static: ports/values/flow/chain/validate — FAIL = do not load)
     → cardinal_live_modules (did every module survive the load?)
     → cardinal_scan_signal (which modules emit non-zero voltage right now)
     → cardinal_module_ports on the suspect module (not wired / silent / signaling)
     → answers with the actual cause, not a guess
```

### "Swap in a chord progression"

```
You:  Give me a ii–V–I jazz accompaniment
AI:   → cardinal_music (progressions) to get ii–V–I voicings
     → cardinal_patch_info to see current ADSR / VCO config
     → cardinal_apply_recipe to write the new params
     → you press one key and hear ii–V–I
```

---

## The OSC layer: how 22 endpoints get into Cardinal

Stock Cardinal's OSC server is **write-only** (4 handlers, none replies with data) — that
is a hard design fact of the upstream project, not a bug. `tools/osc_patch/` closes it:

```
tools/osc_patch/
├── osc_read_handlers.cpp.inc    <- batch A: 5 read probes
├── inject_osc_read.py           <- idempotent injector: backup -> inject -> verify -> (--rollback)
├── osc_read_b_handlers.cpp.inc  <- batch B: 6 runtime-fact readers
├── inject_osc_b.py              <- same four guarantees, anchors on batch A's markers
├── osc_ops_c_handlers.cpp.inc   <- batch C: 9 simulated-human-operation endpoints
├── osc_js_handlers.cpp.inc      <- QuickJS binding (in-process JS)
└── inject_osc_c.py              <- same four guarantees, anchors on batch A's markers
```

- Each injector patches `src/CardinalCommon.cpp` (**both** the thread and non-thread
  registration sites — patching only one fails silently), backs up first, and verifies
  implementation x registration counts. All three support `--check` and `--rollback`.
- Build with the WSL2 cross-compile recipe: `bash tools/cross_build_cardinal.sh 8 true`
  followed by `make -C CardinalNative` (the second command is a required workaround for a
  pre-existing `CardinalMini_dsp.dll` link failure; see `docs/TODO-BACKLOG.md`).
- **All three batches landed and were verified live over OSC** (2026-10-19/20):
  - batch A -- `/modules` `/param-get` `/ports` `/signal` `/light`
  - batch B -- `/build-info` `/cables` (all + per-module) `/transport` `/engine-info` `/plugins`
  - batch C -- `/param-set-by-display` `/cable-add` `/cable-remove` `/undo` `/redo`
    `/module-json` `/module-remove` `/module-move` `/midi-out` + `/osc-js-run` `/osc-js-list`

  Verification is **runtime-level**, never file-level: a real process answering real OSC
  messages on a real rack. File-level evidence lies — the exe is stripped to an external
  PDB, so `nm` is useless and even short path strings get inlined away.
- On an unpatched build every one of these tools returns `probe_not_supported` — the rest
  of the 52 tools keep working unchanged.
- Verified live: `/modules` returns the engine's real module list, `/signal` reports
  per-module peak voltage (the default rack's VCO reads 4.977 V), the C-group undo names
  come back correct (`change parameter` / `add cable` / `move module`), and the JS budget
  interrupts a `while (true)` script at 2001 ms with the process still alive.

### Known limits of this layer (design facts, not bugs)

- **liblo cannot *receive* string OSC arguments on this build.** Verified 2026-10-20:
  every string-input endpoint is dead; *sending* strings works fine (all `/resp` payloads
  are strings). So operations needing free text or JSON go through a JS script file plus a
  numeric index — see `cardinal_js_run` above.
- **Knob display domains are module-specific and often non-linear.** Setting a display
  value of `0.8` and reading back `11.56 Hz` on a VCO is correct conversion, not a bug.
  Verify with `cardinal_get_param` instead of comparing numbers.
- **CPU meters refresh once per second** (`/engine-info` reports `cpuRefreshMs` so you know
  the data's age) and `/modules` has no pagination yet — a 200-module rack replies in one
  datagram, which is large but under the UDP limit.

---

## Hardware / software environment (where this was verified)

> For anyone who wants to reproduce it — what environment it needs to run.

### Software

- **OS**: Windows 11 (10.0.26200, 64-bit)
- **Cardinal**: 26.02 ([DISTRHO/Cardinal](https://github.com/DISTRHO/Cardinal))
  - 4 variants: DISTRHO core / FX / Mini / Synth
  - launch with `CardinalNative.exe` (~100 MB, main standalone)
  - bundled module library (VCV Rack Fundamental + AudibleInstruments + community plugins)
  - the author additionally runs a **self-built patched CardinalNative** (WSL2 cross-compile,
    OSC probes injected) deployed at `D:/Cardinal/win64/` — build recipe in `tools/`
- **Python**: 3.13.12 (managed interpreter, in an isolated venv under the user dir)
- **AI client**: WorkBuddy (via its MCP config) — Cursor / Claude Desktop work with the
  same `mcp.example.json`
- **MIDI companion software** (user-private, not shipped): M-VAVE MidiSuite, useful with
  the M-VAVE SMK25

### Hardware

- **CPU**: Intel(R) Core(TM) Ultra 9 275HX
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
| Batch-mode action applied atomically | OSC has no `/batch` endpoint. `ComplexAction` exists in the engine, but the C-group endpoints each go through history — so "apply N ops, then one undo" already works. If a real single-endpoint batch is ever needed, add C5 |
| Add a module by slug over OSC | **liblo on this build cannot receive string arguments** (verified 2026-10-20). Adding a module needs a plugin|model slug, so it goes through `cardinal_js_run` → `cardinal.addModule(slug, x, y)` instead of a plain OSC endpoint |
| Auto read-back of param changes on a **stock** build | The live autosave is only flushed on `/load` or an explicit GUI save — **not** on `/param` changes and **not** on a timer (measured on 26.02). With the **patched** build, `cardinal_get_param` reads the real display value via `/param-get` instead. See `docs/DESIGN-NOTES.md` 坑 8 |
| Trusting `read_live` blindly | If several Cardinal sessions leave autosaves behind, the newest file may belong to a *previous* session. `read_live` / `save_live` now return `stale` / `age_seconds` / `note`; check them. See 坑 8b |
| Audio in WSL2 | A WSL2 build can create windows (software GL) and answer OSC, but JACK audio does not work there — WSL is for build/verify, not for playing |
| Linux/macOS testing of the Windows-specific tools | Only verified on Windows; the Python tools are cross-platform, but `winmidi.py` / `winprobe.py` use the Win32 API |
| LMMS / DAW recording loop | That's a separate project (Cardinal.vst into a DAW); this repo stops at standalone + OSC |

---

## Documentation index

| Doc | Answers |
|---|---|
| `README.md` | Should I install this? How do I run it? |
| `README.zh-CN.md` | Chinese version of this README |
| `docs/DESIGN-NOTES.md` | How was it built? All the tools explained, pitfalls, reusable principles |
| `docs/CARDINAL-REPO-NOTES.md` | What's worth borrowing from upstream Cardinal? OSC boundaries / module list / non-existent features |
| `docs/TODO-BACKLOG.md` | What's done, what's next (batch A complete; B/C pending) |
| `docs/CARDINAL-MCP-SPEC.md` | The protocol spec + source-verified facts |
| `docs/CARDINAL-MCP-CAPABILITY-MAP.md` | Engine capabilities with exact source line references |
| `docs/HUMAN-INTERACTION-MAP.md` | Human UI operations → source functions |
| `docs/STYLE-SCHEMA.md` | Style-as-data with real-rack-verified samples |
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

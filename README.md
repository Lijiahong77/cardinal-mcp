# cardinal-mcp

[中文](README.zh-CN.md) · [Documentation](docs/README.md)

An MCP/OSC and file-tool workflow for inspecting, authoring and controlling
[Cardinal](https://github.com/DISTRHO/Cardinal) modular-synth racks.

> AI-assisted code and documentation can be wrong. Review and test on backed-up
> copies first; signal voltage is not proof of audible sound. The historical
> [AI disclosure](AI-DISCLOSURE.md) records the project's earlier WorkBuddy origin;
> subsequent work also uses Hermes. No agent's self-review replaces user acceptance.

## Capabilities and delivery status

- **64 MCP tools**, with matching `TOOLS`/`DISPATCH` names in
  [cardinal_mcp.py](tools/cardinal_mcp.py): patch inspection and five-stage audits,
  module/parameter lookup, live reads and edits, wiring, history, sequencers,
  SongRoll arrangement tables, samplers, ABC export and optional in-process JS.
- The optional [source patch chain](tools/osc_patch/README.md) contains **17 patches**
  and expects **33 OSC endpoints** / **36 diagnostic marks**. Diagnostic marks are
  not a full source-identity, build or runtime certification.
- Python safety fixes and persistent regression fixtures/harnesses are delivered.
  A local native17 Windows build was built and deployed with permission; a short
  user-operated SongRoll edit/undo/redo check passed. See the
  [delivery record](docs/DELIVERY-2026-10-26.md) for exact scope and reproduction.
- **This repository does not ship a Cardinal executable, binary release or complete
  build toolchain.** A local deployment is not a downloadable release.

## Safe quick start

Use Python 3.13 (the exercised series), Git and a checkout of this repository.
Install the two declared Python dependencies in your chosen environment:

```bash
python -m pip install -r requirements.txt
python -B tools/cardinal_mcp.py --tools
```

`--tools` lists the actual tool table without contacting Cardinal. It is not a
live self-test. Start with file-only inspection in your MCP client, for example:
“List saved patches, then inspect one without loading it.”

For live operations, install Cardinal standalone separately. Stock Cardinal does
**not** supply all patched live-read/write capabilities; use the source-patch and
build guide if you need them. Preserve your current rack and save a backup before
allowing loads, edits, undo/redo, MIDI or playback. Never auto-load a demo over an
unsaved rack. Leave playback under user control.

Only after choosing the target instance and enabling OSC there, an optional
read-only connectivity check is:

```bash
python -B tools/cardinal_mcp.py --call cardinal_ping
```

A UDP listener alone does not prove a reply; a timeout does not prove an endpoint
is unsupported. Inspect returned errors and verification fields, not just a
successful process launch. `--selftest` is broader and contacts the live instance;
its result is not proof that every mutating tool or audio path works.

## MCP configuration and prerequisites

Replace `<REPO>`, `<PYTHON>` and `<CARDINAL_RESOURCES>` with absolute paths on your
machine (forward slashes on Windows); placeholders are not shell expansions.
The resource path must match the Cardinal build you actually use.

```json
{
  "mcpServers": {
    "cardinal": {
      "command": "<PYTHON>",
      "args": ["-B", "<REPO>/tools/cardinal_mcp.py"],
      "env": {
        "CARDINAL_PATCH_DIR": "<REPO>/patches",
        "CARDINAL_MANIFEST_DIR": "<CARDINAL_RESOURCES>/PluginManifests",
        "CARDINAL_IP": "127.0.0.1",
        "CARDINAL_PORT": "2228",
        "CARDINAL_TIMEOUT": "1.5"
      }
    }
  }
}
```

See also [mcp.example.json](mcp.example.json). Keep confirmation enabled for writes.
The server uses stdio/JSON-RPC; environment values configure the Python client,
not an already-running Cardinal process. Windows desktop/MIDI helpers require
Windows; Linux/macOS parity has not been certified. Existing racks and legacy
helpers can contain machine-specific paths: inspect sample paths before loading,
use [relocate_samples.py](tools/relocate_samples.py) for relocation, and do not
assume a moved sampler rack will still sound.

The optional C++ patch route needs separate upstream sources, fixed Git objects,
third-party dependencies and a compiler/cross-build environment. Use
[recovery instructions](tools/osc_patch/README.md) and the
[delivery/build boundaries](docs/DELIVERY-2026-10-26.md), not the legacy injectors.
Do not replay onto a dirty production source tree or treat four recovery roots
as a complete build dependency lock.

## Tests

The explicit offline runner is [run_safety_regression.py](tools/run_safety_regression.py).
The last recorded run passed **295 unique unittest methods across 15 suites**;
that is recorded execution, not a new run or a claim of hosted CI coverage.
It requires Windows + Ubuntu-26.04 WSL, pinned source objects, Python dependencies,
g++, pthread and real Jansson development headers/runtime. Missing prerequisites
fail rather than skip. Output and scratch directories must be outside the repo;
use a new output directory and ordinary Python, **not `-O`**.

```text
python -B tools/run_safety_regression.py --help
python -B tools/run_safety_regression.py --out D:/external-audit/run-001 --tmpdir D:/external-scratch --wsl-source /home/USER/Cardinal --jansson-include-dir /path/to/jansson-development/include
```

These are replaceable example paths, not bundled dependencies.
[Delivery prerequisites](docs/DELIVERY-2026-10-26.md) and the
[test/harness index](tools/osc_patch/TESTING.md) explain fixed objects, Jansson,
standalone runners, source provenance and what the test shells substitute.

## Verification boundaries

- File audits, fixed-source replay, extracted C++ tests, complete Native build,
  limited live behavior and human listening are separate evidence layers.
- native17 user sound confirmation, long-duration/full-library coverage,
  downstream PianoRoll stop/mute and hard-real-time/latency acceptance remain open.
  MiniArranger snapshot risks are not fixed by SongRoll's lock.
- `read_live` / `save_live` use autosave snapshots, not authoritative current GUI
  state. Check staleness and session association; use live module/parameter reads
  where supported. Multi-writer and cross-output resource transactions remain
  unproven; do not upgrade `verified=false` to success.
- Raw parameter values and displayed units differ. Read back the actual value;
  a loadable rack, nonzero voltage or a passing static audit is not audio acceptance.

## Navigation

- [Documentation index](docs/README.md): usage, development/recovery, delivery/history,
  and reference materials. [HANDOFF](HANDOFF.md) is the handover entry;
  [TODO](docs/TODO-BACKLOG.md) is the single backlog. Both retain dated history.
- [Practical usage notes](docs/USAGE-NOTES.md): live/file distinctions, JS safety,
  sample relocation and workflow examples retained from the former long README.
- Repository areas stay in place: [tools](tools/), [patches](patches/), [params](params/),
  [music](music/), [samples](samples/), [refs](refs/) and [js](js/).

## License and sources

See [LICENSE](LICENSE) for the repository's MIT license. That does **not** relicense
upstream Cardinal/Rack/plugin code included in patches, fixtures or harness
`reference/` snapshots. Retain source headers and comply with the applicable
upstream licenses (including GPL where applicable). See
[source provenance](docs/DELIVERY-2026-10-26.md) and
[historical attribution](docs/ATTRIBUTION.md); the older attribution page's blanket
“no third-party source shipped” language predates these fixtures and is not the
current inventory. Cardinal, VCV Rack, community module authors, python-osc and
zstandard provide the upstream software and dependencies.

# Candidate17 source-extraction harness

Not registered in production PATCHES. Root for `candidate.patch`: `plugins/rcm-modules`.
`after16.json` contains exact compressed preimages of the seven changed files;
`reference/` contains actual candidate and Rack serialization/history source, not
invented expected implementation. `sources.json` pins their bytes.

Run in WSL (fresh output directory, real C++11/Jansson):

```
python3 -B /mnt/d/Cardinal/tools/osc_patch/songroll_stopfirst_harness/run.py --out /home/lijia/NEW-OUTPUT
python3 -B /mnt/d/Cardinal/tools/osc_patch/songroll_stopfirst_harness/replay.py --root /home/lijia/NEW-FIXTURE
```

Default Jansson include is the read-only full14 build lab; runtime is real system
libjansson.so.4. No install/network/device is needed. Missing dependencies fail,
not skip. Runtime cases have subprocess timeouts only in the outer unittest.
`test_replay_songroll_stopfirst_candidate.py` exposes 52 source cases +6 artifact
methods (58 unique methods); 12 B1 cases extend the old46. C++/TSan reruns are
not additional unittest methods and must not be counted twice.

## Actual versus substituted

Actual source: SongRoll class declaration; process, stopFirst/reset/enter/advance,
JSON, SongRollData; controls and Slice methods; RollArea constructor; Rack float
SchmittTrigger and PulseGenerator; Module JSON; history; modelFromJson. Parsing
extracts signatures/balanced braces and fails on absent signatures. Constructor
uses resetState without Rack configInput/configOutput bookkeeping; full original
constructor remains in the actual MinGW TU compilation.

Shells: Widget geometry/event/tree ownership/layout; no drawing/window; plugin
registry, empty params, Module non-SongRoll metadata; Port voltage/channel storage
and optional per-read/per-write deterministic barrier hooks; Engine lookup and std::mutex replacing its
SharedMutex. Actual SongRoll std::recursive_mutex/try_lock unchanged. Engine
worker scheduling, module lifetime/removal, actual port connection clearing,
audio devices, real GUI and hard realtime budgets are not certified.

Thread tests use promises/futures as explicit barriers: process is held inside
RUN input read while holding the real module mutex; writer cannot finish before
release. UI and JSON readers cannot complete while the writer holds half config.
Contention test holds owner until real process returns (2-second watchdog, not a
latency target); failure branch must not consume RUN. `process_contention` now
explicitly models a real editing owner (`stopFirst` before holding the lock);
its existing zero-event assertions are unchanged. Read-only contention is tested
separately with real pulses and both ports across failed and next-success samples.
Stress runs 10,000 process calls and 500 concurrent load/UI/JSON iterations.
ASan/UBSan is not race detection; separate actual TSan build/run logs are in the
workspace audit. B1 verification executes the original five threaded cases plus
all twelve B1 interleavings, not whole Rack.

## B1 event ownership and timing contract

Only process writes ports and the two cached event levels. Read-only UI/JSON
contention freezes those levels and the protected PulseGenerator time; pulse
width can lengthen without bound during owner stalls. This is not precise
wall-clock pulse-width preservation. Failed process touches no protected runtime,
trigger, pulse or configuration. True stopFirst/reset/JSON publishes one atomic
cancellation after resetting protected pulses; failed DSP loads it but does not
acknowledge it. Only a successful mutex-owning process exchanges it false, while
no writer can publish a new cancel. Thus repeated failures cannot lose a cancel
or resurrect the old pulse. One already-in-flight failed sample that read false
before a concurrent edit may still finish high; the next invocation clears it.
A fixed output-write barrier case exercises this exact ordering. UI never reads
or writes the DSP cache. Fresh observed-low RUN/EOP and subsequent real boundaries
still work; existing RUN RESET and held-PATTERN semantics are retained.

`b1.cpp` persists read-only Slice/JSON cases crossing SECTION_END and SONG_END,
128 failed samples, edit-before/after failed sampling, repeated cancellation,
no-contention success, reset/JSON cancellation and new-boundary rearming. Outer
recursive locks prolong real UI/JSON transactions without rewriting their methods.
Four actual old17 RED runs compiled and returned behavior failure; old B1 review
failure artifacts remain immutable. See workspace audit/songroll-stopfirst-b1-fix.md.

## Authorized old-expectation change

The old16 suite/report/fixtures remain unmodified. This candidate reruns its22
cases on17. Only `preserve_unrelated` changes expectation: selected configuration,
bypass/expander IDs/other channels remain preserved, but running/currentSection
normalize false/0 on edit, undo and redo. Old16 historical playback restoration
is no longer an expected behavior. Boundary noop clicks keep their history entry
and now stop-first too. No-op/NULL/outside controls still never create actions.

Production replay helper uses actual `replay_osc.apply_one`, not a mock. It
checks dry/apply/skip and exact reverse bytes/Linux modes, no Git index creation,
no git add/commit. Workspace audit also verifies reapply and equality against
candidate, actual MinGW build-lab source and fixtures.

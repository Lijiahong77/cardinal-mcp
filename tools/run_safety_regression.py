"""Explicit offline safety matrix. No discovery, OSC, deploy, or live-tree writes.
Requires Windows + Ubuntu-26.04 WSL, pinned source objects, g++ C++11/Jansson.
Missing prerequisites are errors, never skips. See docs/DELIVERY-2026-10-26.md.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

NAMES = [
    'test_cardinal_mcp', 'test_cardinal_safety', 'test_replay_osc',
    'test_patchio_safety', 'test_file_editor_integration', 'test_editor_safety',
    'test_editor_parent_contracts', 'test_value_safety', 'test_replay_safety',
    'test_replay_compat', 'test_replay_param_safety',
    'test_replay_songroll_history_candidate', 'test_replay_songroll_history_integration',
    'test_replay_songroll_stopfirst_candidate', 'test_replay_songroll_stopfirst_integration',
]


def identifiers(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from identifiers(item)
        else:
            yield item.id()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new external evidence directory')
    parser.add_argument('--wsl-source', required=True, help='read-only WSL source with pinned git objects')
    parser.add_argument('--jansson-include-dir', default=os.environ.get('JANSSON_INCLUDE_DIR'),
                        help='absolute Linux Jansson development-header directory (or JANSSON_INCLUDE_DIR)')
    parser.add_argument('--tmpdir', type=Path, default=None, help='external scratch parent (or TMPDIR)')
    args = parser.parse_args()
    if not args.jansson_include_dir or not args.jansson_include_dir.startswith('/'):
        parser.error('Jansson headers required: --jansson-include-dir or JANSSON_INCLUDE_DIR must be an absolute Linux directory containing jansson.h and jansson_config.h')
    root = Path(__file__).resolve().parent.parent
    out = args.out.resolve()
    scratch = (args.tmpdir or Path(os.environ['TMPDIR'])).resolve()
    for target in (out, scratch):
        if target == root or root in target.parents:
            parser.error('output and scratch must be outside the repository')
    if sys.flags.optimize:
        parser.error('ordinary Python required; -O disables fixture assertions')
    scratch.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=False)
    os.environ.update(CARDINAL_TEST_WSL_SOURCE=args.wsl_source, PYTHONDONTWRITEBYTECODE='1',
                      JANSSON_INCLUDE_DIR=args.jansson_include_dir)
    sys.dont_write_bytecode = True
    sockets = []

    def veto(event, unused):
        if event == 'socket.__new__':
            sockets.append(event)
            raise AssertionError('socket veto before product/test imports')

    sys.addaudithook(veto)
    # Prove the veto in a child; do not count its intentional attempt in this run.
    import subprocess
    canary = subprocess.run([sys.executable, '-B', '-c',
        "import sys\ndef veto(e,a):\n if e=='socket.__new__': raise RuntimeError('VETO')\n"
        "sys.addaudithook(veto)\nimport socket\ntry: socket.socket()\n"
        "except RuntimeError as e: assert str(e)=='VETO'; print('VETO')\n"
        "else: raise AssertionError('socket veto failed')"], capture_output=True, text=True, check=True)
    if canary.stdout.strip() != 'VETO':
        raise AssertionError('socket canary failed')
    # Validate Linux headers in the same WSL boundary as the C++ launchers.
    headers = subprocess.run(['wsl.exe', '-d', 'Ubuntu-26.04', '--', 'python3', '-B', '-c',
        "import pathlib,sys; p=pathlib.Path(sys.argv[1]); "
        "sys.exit(0 if p.is_absolute() and all((p/h).is_file() for h in "
        "('jansson.h','jansson_config.h')) else 'Jansson headers required: '+str(p))",
        args.jansson_include_dir], capture_output=True, timeout=60)
    if headers.returncode:
        parser.error('Jansson headers required at '+repr(args.jansson_include_dir)+
                     '; WSL prerequisite check failed: '+headers.stderr.decode('utf8', 'replace'))
    with tempfile.TemporaryDirectory(prefix='safety-regression-', dir=scratch) as tmp:
        os.environ.update(TMPDIR=tmp, TEMP=tmp, TMP=tmp)
        tempfile.tempdir = tmp
        sys.path[:0] = [str(root / 'tools'), str(root / 'tools/osc_patch')]
        loader = unittest.TestLoader()
        modules = {name: importlib.import_module(name) for name in NAMES}
        suites = {name: loader.loadTestsFromModule(module) for name, module in modules.items()}
        ids = [item for suite in suites.values() for item in identifiers(suite)]
        if loader.errors or not ids or len(ids) != len(set(ids)):
            raise AssertionError(('loader errors/duplicate methods', loader.errors))
        with (out / 'tests.log').open('w', encoding='utf8') as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.TestSuite(suites.values()))
        report = dict(tests_run=result.testsRun, unique_methods=len(set(ids)), ids=ids,
            counts={name: sum(i.startswith(name + '.') for i in ids) for name in NAMES},
            success=result.wasSuccessful() and not result.skipped and not loader.errors and not sockets,
            failures=[(t.id(), msg) for t, msg in result.failures],
            errors=[(t.id(), msg) for t, msg in result.errors],
            skips=[(t.id(), why) for t, why in result.skipped],
            loader_errors=loader.errors, socket_creation_attempts=sockets, optimize=sys.flags.optimize,
            socket_veto_before_import=True, socket_canary=canary.stdout.strip(),
            jansson_include_dir=args.jansson_include_dir,
            history_cpp_evidence=modules['test_replay_songroll_history_candidate'].EVIDENCE,
            stopfirst_cpp_evidence=modules['test_replay_songroll_stopfirst_candidate'].EVIDENCE)
        (out / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        print(json.dumps({key: report[key] for key in ('tests_run', 'unique_methods', 'counts', 'success',
              'loader_errors', 'socket_creation_attempts', 'optimize')}, indent=2))
        return 0 if report['success'] and result.testsRun == len(ids) else 1


if __name__ == '__main__':
    raise SystemExit(main())

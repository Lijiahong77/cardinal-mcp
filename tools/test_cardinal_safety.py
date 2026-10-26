#!/usr/bin/env python3
"""Offline safety contracts. Real network/socket creation is forbidden."""
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cardinal_mcp as m
from pythonosc.osc_message import OscMessage


class SafetyTest(unittest.TestCase):
    def setUp(self):
        guard = patch.object(m.socket, "socket", side_effect=AssertionError("real OSC forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def patch_file(self):
        tmp = tempfile.TemporaryDirectory(
            dir=os.environ['TMPDIR'],
            prefix="cardinal_safety_")
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "fixture.vcv"
        p.write_text(json.dumps({"version": "2.0", "modules": [], "cables": []}),
                     encoding="utf-8")
        return str(p)


class TestWireContracts(SafetyTest):
    def test_high_cable_ports_preserve_wire_order_and_int32_bounds(self):
        args = {"module_id": 11, "input_port": 47,
                "target_module_id": 22, "output_port": 42}
        with patch.object(m, "_ask_status", return_value=("ok replaced=0", "ok")) as ask:
            out = m._call_tool("cardinal_cable_add", args)
        self.assertTrue(out["ok"])
        self.assertEqual(OscMessage(m.build_msg(ask.call_args.args[1],
                                              ask.call_args.args[2])).params,
                         [22, 42, 11, 47])
        for field in ("input_port", "output_port"):
            for value in (-1, True, 1.5, 2 ** 31):
                with self.subTest(field=field, value=value), patch.object(m, "_ask_status") as ask:
                    self.assertFalse(m.cable_add(**{**args, field: value})["ok"])
                    ask.assert_not_called()

    def test_cable_serializes_output_before_input(self):
        with patch.object(m, "_ask_status", return_value=("ok replaced=0", "ok")) as ask:
            out = m.cable_add(11, 4, 22, 6)
        self.assertTrue(out["ok"])
        tag, address, args = ask.call_args.args
        msg = OscMessage(m.build_msg(address, args))
        self.assertEqual(tag, "cable-add")
        self.assertEqual(msg.address, "/cable-add")
        self.assertEqual(msg.params, [22, 6, 11, 4])
        self.assertEqual([typ for typ, _ in args], ["h", "i", "h", "i"])

    def test_midi_immediate_uses_four_integer_arguments(self):
        with patch.object(m, "_ask_status", return_value=("sent", "ok")) as ask:
            out = m.midi_out(0, 144, 60, 100)
        self.assertTrue(out["ok"])
        self.assertTrue(out["delivered"])
        args = ask.call_args.args[2]
        self.assertEqual([typ for typ, _ in args], ["i"] * 4)
        self.assertEqual(OscMessage(m.build_msg("/midi-out", args)).params,
                         [0, 144, 60, 100])

    def test_midi_never_claims_delivery_for_unsupported_or_failed_requests(self):
        with patch.object(m, "_ask_status", return_value=("sent", "ok")) as ask:
            out = m.midi_out(0, 144, 60, 100, frame=123)
        self.assertFalse(out["ok"])
        ask.assert_not_called()
        for payload, status in [("no-plugin", "err:E_NO_PLUGIN"),
                                ("unexpected", "ok")]:
            with self.subTest(payload=payload):
                with patch.object(m, "_ask_status", return_value=(payload, status)):
                    out = m.midi_out(0, 144, 60, 100)
                self.assertFalse(out["ok"])
                self.assertFalse(out.get("delivered", False))


class TestReplyContracts(SafetyTest):
    def test_probe_reply_shape_and_status_are_checked(self):
        for reply in [["param", "1", "surprise"], ["param"],
                      ["param", "1", "ok", "extra"]]:
            with self.subTest(reply=reply):
                fake = Mock()
                fake.ask.return_value = reply
                with patch.object(m, "link", return_value=fake):
                    payload, status = m._ask_status("param", "/param-get")
                self.assertEqual(status, "err:E_INTERNAL")

    def test_unknown_status_cannot_be_reported_as_success(self):
        for status in [None, "", "unexpected", 42]:
            with self.subTest(status=status):
                out = m._hist_status("payload", status)
                self.assertFalse(out["ok"])

    def test_load_preserves_three_segment_warnings_and_failure_details(self):
        p = self.patch_file()
        cases = [(["load", "warn missing module", "ok"], True, ["missing module"]),
                 (["load", "fail bad archive", "err:E_INTERNAL"], False, ["bad archive"]),
                 (["load", "ok"], True, []),
                 (["other", "ok", "ok"], False, [])]
        for reply, ok, warnings in cases:
            with self.subTest(reply=reply):
                fake = Mock()
                fake.ask.return_value = reply
                with patch.object(m, "link", return_value=fake):
                    out = m.load_patch(p)
                self.assertEqual(out["ok"], ok)
                if reply[0] == "load":
                    self.assertEqual(out["warnings"], warnings)

    def test_remote_error_status_is_never_successful_empty_data(self):
        cases = [(m.live_modules, ()), (m.scan_signal, ()), (m.build_info, ()),
                 (m.cables, ()), (m.transport, ()), (m.engine_info, ()),
                 (m.plugins, ()), (m.module_json, (11,)), (m.js_list, ()),
                 (m.js_run, (1,)), (m.set_param_by_display, (11, 0, 1.0))]
        for fn, args in cases:
            with self.subTest(function=fn.__name__):
                with patch.object(m, "_ask_status", return_value=("no-plugin", "err:E_NO_PLUGIN")):
                    out = fn(*args)
                self.assertFalse(out.get("ok", True))
                self.assertEqual(out["status"], "err:E_NO_PLUGIN")


class TestMcpBoundary(SafetyTest):
    def call(self, name, arguments):
        reply = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})
        assert reply is not None
        return reply["result"]

    def test_songroll_repeats_business_bounds_through_mcp_and_cli(self):
        p = self.patch_file()
        sections = [{"channels": [{"pattern": 1, "repeats": 200,
                                  "repeat_mode": 1, "clock_div": 1} for _ in range(8)]}]
        m.patchio.write_patch(p, {"version": "2.0", "modules": [
            {"id": 1, "plugin": "rcm", "model": "rcm-songroll", "params": [],
             "data": {"songRoll": {"sections": sections}}}], "cables": []})
        for tool, args in [
            ("cardinal_songroll_write", {"patch": p, "sections": sections, "load_after": False}),
            ("cardinal_songroll_edit", {"patch": p, "op": "set_channel", "section": 0,
                                       "channel": 1, "repeats": 200, "load_after": False})]:
            with self.subTest(tool=tool):
                out = self.call(tool, args)
                self.assertFalse(out["isError"], out)
                proc = subprocess.run([sys.executable, "-B", m.__file__, "--call", tool,
                                       json.dumps(args)], capture_output=True, text=True, timeout=15)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(m.songroll.read_sections(p)["sections"][0]["channels"][0]["repeats"], 200)
        for value in (1, 200, m.songroll.REPEATS_MAX):
            for tool, args in [("cardinal_songroll_write", {"patch": p, "sections": [
                    {"channels": [{"repeats": value} for _ in range(8)]}]}),
                    ("cardinal_songroll_edit", {"patch": p, "op": "set_channel", "repeats": value})]:
                fn = Mock(return_value={"ok": True})
                with patch.dict(m.DISPATCH, {tool: fn}):
                    self.assertFalse(self.call(tool, args)["isError"])
        for value in (0, 4097, True, float("nan"), float("inf")):
            args = {"patch": p, "op": "set_channel", "repeats": value}
            fn = Mock()
            with patch.dict(m.DISPATCH, {"cardinal_songroll_edit": fn}):
                self.assertTrue(self.call("cardinal_songroll_edit", args)["isError"])
            fn.assert_not_called()

    def test_invalid_arguments_are_rejected_before_dispatch(self):
        cases = [{"port": 0, "value": 2.0}, {"port": True, "value": 0.5},
                 {"port": 0, "value": float("nan")},
                 {"port": 0, "value": float("inf")},
                 {"port": "0", "value": 0.5}, {"port": 0},
                 {"port": 0, "value": 0.5, "unexpected": True}, [], None]
        for args in cases:
            with self.subTest(arguments=args):
                fn = Mock(return_value={"ok": True})
                with patch.dict(m.DISPATCH, {"cardinal_set_host_param": fn}):
                    out = self.call("cardinal_set_host_param", args)
                fn.assert_not_called()
                self.assertTrue(out["isError"])

    def test_valid_arguments_and_nested_schema_remain_usable(self):
        args = {"port": 0, "value": 0.5}
        fn = Mock(return_value={"ok": True})
        with patch.dict(m.DISPATCH, {"cardinal_set_host_param": fn}):
            self.assertFalse(self.call("cardinal_set_host_param", args)["isError"])
        fn.assert_called_once_with(args)
        schema = {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["mode"], "additionalProperties": False,
            "properties": {"mode": {"type": "string", "enum": ["safe"]}}}}
        m._validate_arguments([{"mode": "safe"}], schema)
        for value in [[], [{}], [{"mode": "other"}], [{"mode": "safe", "extra": 1}]]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                m._validate_arguments(value, schema)

    def test_auditor_crashes_propagate_but_normal_fail_is_a_query_result(self):
        import importlib
        p = self.patch_file()
        for check, module in [("ports", "audit_ports"), ("values", "audit_values"),
                              ("flow", "audit_flow"), ("chain", "audit_chain"),
                              ("validate", None)]:
            target = m if module is None else importlib.import_module(module)
            attr = "_audit_validate" if module is None else "audit"
            with self.subTest(check=check), patch.object(target, attr, side_effect=RuntimeError("fixture crash")):
                out = self.call("cardinal_audit", {"name": p, "checks": [check]})
            self.assertTrue(out["isError"], out)
            self.assertIn("structuredContent", out)
            self.assertIn("error", out["structuredContent"]["checks"][check])
        with patch.object(importlib.import_module("audit_values"), "audit", return_value=(1, 0)):
            out = self.call("cardinal_audit", {"name": p, "checks": ["values"]})
        self.assertFalse(out["isError"], out)
        self.assertEqual(out["structuredContent"]["verdict"], "FAIL")
        self.assertFalse(m._tool_failed({"match": False, "business": {"error": "not execution"}}))
        self.assertFalse(m._tool_failed({"checks": {"unrelated_business": {"error": "query detail"}}}))

    def test_auditor_crash_cli_exits_nonzero_normal_fail_exits_zero(self):
        p = self.patch_file()
        for crashed in (True, False):
            code = (f"import sys,runpy; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); "
                    "sys.addaudithook(lambda event,args: (_ for _ in ()).throw(AssertionError('socket forbidden')) "
                    "if event=='socket.__new__' else None); import audit_values; "
                    "audit_values.audit=lambda *a,**k: " +
                    ("(_ for _ in ()).throw(RuntimeError('fixture crash')); " if crashed else "(1,0); ") +
                    "sys.argv=" + repr([m.__file__, "--call", "cardinal_audit",
                                        json.dumps({"name": p, "checks": ["values"]})]) +
                    "; runpy.run_path(sys.argv[0], run_name='__main__')")
            proc = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True,
                                  text=True, timeout=15)
            self.assertEqual(proc.returncode, 1 if crashed else 0, proc.stdout + proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["verdict"], "FAIL")

    def test_business_failure_sets_mcp_error_flag(self):
        for data in [{"ok": False, "status": "err:E_BAD_ARGS"},
                     {"error": "failed"},
                     {"ok": True, "loaded": {"ok": False}}]:
            with self.subTest(data=data):
                with patch.dict(m.DISPATCH, {"cardinal_ping": Mock(return_value=data)}):
                    out = self.call("cardinal_ping", {})
                self.assertTrue(out["isError"])
                self.assertEqual(out["structuredContent"], data)

    def test_cli_failure_uses_nonzero_exit(self):
        proc = subprocess.run([sys.executable, "-B", m.__file__, "--call",
                               "cardinal_set_host_param", '{"port":24,"value":0.5}'],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(json.loads(proc.stdout).get("error"))

    def test_malformed_request_shapes_do_not_crash_handler(self):
        for req in [[1], {"method": "initialize", "id": 1, "params": [1]},
                    {"method": "tools/call", "id": 1, "params": {"name": []}}]:
            with self.subTest(request=req):
                reply = m.handle(req)
                assert isinstance(reply, dict)
                self.assertTrue(reply.get("error") or reply.get("result", {}).get("isError"))


class TestResponseMatching(SafetyTest):
    def test_js_waits_past_diagnostics_and_foreign_packets(self):
        def packet(tag, payload):
            return m.build_msg("/resp", [("s", tag), ("s", payload), ("s", "ok")])

        class FakeSocket:
            def __init__(self):
                self.timeout = None
                self.drain_timeouts = []
                self.replies = [(packet("js", "foreign"), ("203.0.113.9", 2228)),
                                (packet("js-diag", "mode=read"), ("127.0.0.1", 2228)),
                                (packet("js", "executed"), ("127.0.0.1", 2228))]
            def settimeout(self, value):
                self.timeout = value
            def recv(self, size):
                self.drain_timeouts.append(self.timeout)
                if self.timeout == 0:
                    raise BlockingIOError()
                raise m.socket.timeout()
            def sendto(self, data, target):
                return len(data)
            def recvfrom(self, size):
                if self.replies:
                    return self.replies.pop(0)
                raise m.socket.timeout()

        link = m.CardinalLink.__new__(m.CardinalLink)
        fake = FakeSocket()
        link.target = ("127.0.0.1", 2228)
        with patch.object(link, "sock", fake, create=True), \
             patch.object(m, "link", return_value=link):
            out = m.js_run(1)
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(out["result"], "executed")
        self.assertEqual(fake.drain_timeouts, [0.0])
        self.assertEqual(fake.replies, [])

    def test_no_response_does_not_claim_a_missing_build(self):
        with patch.object(m, "_ask_status", return_value=(None, None)):
            out = m.get_param(11, 0)
        self.assertEqual(out["error"], "probe_no_response")
        self.assertNotIn("Rebuild", out.get("note", ""))


class TestParameterGuard(SafetyTest):
    def test_valid_raw_write_preserves_int64_id_and_raw_units(self):
        fake = Mock()
        mid = 7775877489923468
        with patch.object(m, "link", return_value=fake), \
             patch.object(m, "get_param", return_value={"ok": True, "status": "ok"}) as check:
            out = m.set_param(mid, 0, 96.0)
        check.assert_called_once_with(mid, 0)
        fake.send.assert_called_once_with("/param", [("h", mid), ("i", 0), ("f", 96.0)])
        self.assertTrue(out["sent"])
        self.assertFalse(out["verified"])

    def test_direct_python_write_helpers_enforce_declared_inputs(self):
        cases = [(m.set_host_param, (0, float("nan"))), (m.set_host_param, (0, 2.0)),
                 (m.midi_out, (99, 144, 60)), (m.midi_out, (0, 144, -1)),
                 (m.cable_add, (11, -1, 22, 0))]
        for fn, args in cases:
            with self.subTest(function=fn.__name__, args=args):
                fake = Mock()
                with patch.object(m, "link", return_value=fake), \
                     patch.object(m, "_ask_status", return_value=("sent", "ok")) as ask:
                    out = fn(*args)
                fake.send.assert_not_called()
                ask.assert_not_called()
                self.assertFalse(out.get("ok", False))

    def test_invalid_parameter_inputs_never_reach_network(self):
        cases = [(-1, 0, 0.5), (True, 0, 0.5), (11, -1, 0.5),
                 (11, 0.5, 0.5), (11, 0, float("nan")),
                 (11, 0, float("inf")), (11, 0, 1e300),
                 (2 ** 63, 0, 0.5), (11, 2 ** 31, 0.5)]
        for fn in (m.set_param, m.set_param_by_display):
            for args in cases:
                with self.subTest(function=fn.__name__, args=args):
                    fake = Mock()
                    with patch.object(m, "link", return_value=fake), \
                         patch.object(m, "get_param", return_value={"ok": True, "status": "ok"}) as check, \
                         patch.object(m, "_ask_status", return_value=("ok old=0 new=1", "ok")) as ask:
                        out = fn(*args)
                    check.assert_not_called()
                    ask.assert_not_called()
                    fake.send.assert_not_called()
                    self.assertFalse(out["ok"])

    def test_raw_write_requires_successful_live_slot_preflight(self):
        fake = Mock()
        for validation in [{"ok": False, "status": "err:E_BAD_PARAM"},
                           {"error": "probe_not_supported"}]:
            with self.subTest(validation=validation):
                with patch.object(m, "link", return_value=fake), \
                     patch.object(m, "get_param", return_value=validation) as check:
                    out = m.set_param(11, 999, 0.5)
                fake.send.assert_not_called()
                check.assert_called_once_with(11, 999)
                self.assertFalse(out["ok"])


class TestDeployContracts(SafetyTest):
    def test_post_load_exceptions_preserve_structured_side_effects(self):
        p = self.patch_file()
        for target in ("sleep", "diff", "read_patch", "getmtime"):
            if target == "sleep":
                fault = patch.object(m.time, "sleep", side_effect=OSError("fixture sleep"))
            elif target == "diff":
                fault = patch.object(m, "cardinal_diff", side_effect=OSError("fixture diff"))
            elif target == "read_patch":
                fault = patch.object(m.patchio, "read_patch", side_effect=OSError("fixture read"))
            else:
                fault = patch.object(m.os.path, "getmtime", side_effect=OSError("fixture mtime"))
            with self.subTest(target=target), \
                 patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
                 patch.object(m, "load_patch", return_value={"ok": True}) as load, \
                 patch.object(m, "live_patch_path", return_value=(p, "fixture")), \
                 patch.object(m, "cardinal_proc_start", return_value=1), \
                 patch.object(m.time, "sleep"), fault:
                reply = m.handle({"id": 1, "method": "tools/call", "params": {
                    "name": "cardinal_deploy", "arguments": {"name": p}}})["result"]
                self.assertTrue(reply["isError"])
                self.assertIn("structuredContent", reply)
                out = reply["structuredContent"]
                self.assertTrue(out["loaded"])
                self.assertFalse(out["verified"])
                self.assertFalse(out["live_verified"])
                self.assertEqual(out["stage"], "verification_failed")
                self.assertEqual(out["backup"], p + ".bak-deploy")
                self.assertEqual(out["load_result"], {"ok": True})
                self.assertIn("fixture", out["error"])
                load.assert_called_once_with(p)

    def test_direct_deploy_rejects_nonboolean_load_flag(self):
        p = self.patch_file()
        for flag in [0, 1, "false"]:
            with self.subTest(flag=flag):
                with patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
                     patch.object(m, "load_patch", return_value={"ok": True}) as load, \
                     patch.object(m, "cardinal_diff", return_value={}), patch.object(m.time, "sleep"):
                    out = m.cardinal_deploy(p, load_after=flag)
                self.assertFalse(out["ok"])
                load.assert_not_called()

    def test_matching_snapshot_without_load_association_is_not_verified(self):
        p = self.patch_file()
        evidence = {"match": True, "params_checked": True, "params_match": True,
                    "stale": False, "freshness_known": True,
                    "params": {"params_unserialized": 0}}
        with patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
             patch.object(m, "load_patch", return_value={"ok": True}), \
             patch.object(m, "cardinal_diff", return_value=evidence), patch.object(m.time, "sleep"):
            out = m.cardinal_deploy(p)
        self.assertFalse(out["ok"])
        self.assertTrue(out["loaded"])
        self.assertFalse(out["verified"])
        self.assertFalse(out["load_association_proven"])
        self.assertTrue(out["snapshot_comparison_complete"])
        self.assertIn("association", out["why"])
        self.assertFalse(out["live_verified"])
        self.assertEqual(out["verification_scope"], "autosave_structure_and_params")

    def test_real_diff_fixture_cannot_verify_this_load_from_old_or_changed_snapshot(self):
        source = self.patch_file()
        live = str(Path(source).with_name("autosave.vcv"))
        raw = Path(source).read_bytes()
        Path(live).write_bytes(raw)
        for stamp in (200, 99.5):  # old in-process snapshot, and start-time grace window
            os.utime(live, (stamp, stamp))
            for changed in (False, True):
                def fake_load(path):
                    if changed:
                        # Real changed bytes/mtime are still not load causality/instance evidence.
                        Path(live).write_bytes(raw + b"\n")
                    return {"ok": True}
                with self.subTest(stamp=stamp, changed=changed), \
                     patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
                     patch.object(m, "load_patch", side_effect=fake_load), \
                     patch.object(m, "live_patch_path", return_value=(live, "fixture")), \
                     patch.object(m, "cardinal_proc_start", return_value=100), \
                     patch.object(m.time, "sleep"):
                    out = m.cardinal_deploy(source)
                self.assertTrue(out["loaded"])
                self.assertTrue(out["diff"]["match"])
                self.assertTrue(out["diff"]["params_match"])
                self.assertFalse(out["verified"])
                self.assertFalse(out["load_association_proven"])
                self.assertFalse(out["live_verified"])

    def test_real_diff_rejects_incomplete_parameter_evidence_through_deploy(self):
        source = self.patch_file()
        live = str(Path(source).with_name("autosave.vcv"))
        good = [{"id": 0, "value": 0.5}]
        invalid = [[{"id": 0, "value": "not-a-number"}], [{"id": 0}],
                   [{"value": 0.5}], [{"id": True, "value": 0.5}],
                   [{"id": -1, "value": 0.5}], [{"id": 0.5, "value": 0.5}],
                   [{"id": 0, "value": 0.5}, {"id": 0, "value": 0.5}],
                   [{"id": 0, "value": float("nan")}],
                   [{"id": 0, "value": float("inf")}],
                   [{"id": 99, "value": float("nan")}], [None], None, {}]
        def data(params):
            return {"version": "2.0", "modules": [{"id": 1, "plugin": "test",
                    "model": "fixture", "params": params}], "cables": []}
        for side in ("file", "live"):
            for bad in invalid:
                Path(source).write_text(json.dumps(data(bad if side == "file" else good)), encoding="utf-8")
                Path(live).write_text(json.dumps(data(bad if side == "live" else good)), encoding="utf-8")
                with self.subTest(side=side, bad=bad), \
                     patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
                     patch.object(m, "load_patch", return_value={"ok": True}), \
                     patch.object(m, "live_patch_path", return_value=(live, "fixture")), \
                     patch.object(m, "cardinal_proc_start", return_value=1), \
                     patch.object(m.time, "sleep"):
                    out = m.cardinal_deploy(source)
                    self.assertTrue(out["diff"]["match"])
                    self.assertIsNot(out["diff"]["params_match"], True)
                    self.assertFalse(out["diff"]["params_checked"])
                    self.assertIn("error", out["diff"]["params"])
                    self.assertFalse(out["snapshot_comparison_complete"])
                    self.assertFalse(out["verified"])
        for params in ([], good):
            Path(source).write_text(json.dumps(data(params)), encoding="utf-8")
            Path(live).write_text(json.dumps(data(params)), encoding="utf-8")
            with patch.object(m, "live_patch_path", return_value=(live, "fixture")), \
                 patch.object(m, "cardinal_proc_start", return_value=1):
                diff = m.cardinal_diff(source)
            self.assertTrue(diff["params_checked"])
            self.assertTrue(diff["params_match"])
            self.assertEqual(diff["params"]["params_compared"], len(params))

    def test_diff_unknown_freshness_and_nonfinite_values_are_not_verified(self):
        p = self.patch_file()
        with patch.object(m, "live_patch_path", return_value=(p, str(Path(p).parent))), \
             patch.object(m, "cardinal_proc_start", return_value=None):
            diff = m.cardinal_diff(p)
        self.assertIsNone(diff["stale"])
        self.assertFalse(diff["freshness_known"])
        data = lambda value: {"modules": [{"id": 1, "params": [{"id": 0, "value": value}]}]}
        with self.assertRaisesRegex(ValueError, "finite"):
            m._diff_params(data(float("nan")), data(0.5))

    def test_audit_only_does_not_load_or_diff(self):
        p = self.patch_file()
        with patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
             patch.object(m, "load_patch", return_value={"ok": True}) as load, \
             patch.object(m, "cardinal_diff", return_value={}) as diff, \
             patch.object(m.time, "sleep"):
            out = m.cardinal_deploy(p, load_after=False)
        load.assert_not_called()
        diff.assert_not_called()
        self.assertTrue(out["ok"])
        self.assertFalse(out["deployed"])
        self.assertFalse(out["verified"])

    def test_unknown_audit_or_load_warnings_cannot_pass(self):
        p = self.patch_file()
        good = {"match": True, "params_checked": True, "params_match": True,
                "stale": False, "freshness_known": True,
                "params": {"params_unserialized": 0}}
        for audit in [None, {}, {"verdict": "UNKNOWN"}, {"error": "audit unavailable"}]:
            with self.subTest(audit=audit):
                with patch.object(m, "cardinal_audit", return_value=audit), \
                     patch.object(m, "load_patch") as load:
                    out = m.cardinal_deploy(p)
                self.assertFalse(out["ok"])
                load.assert_not_called()
        with patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
             patch.object(m, "load_patch", return_value={"ok": True, "warnings": ["missing module"]}), \
             patch.object(m, "cardinal_diff", return_value=good), patch.object(m.time, "sleep"):
            out = m.cardinal_deploy(p)
        self.assertFalse(out["ok"])
        self.assertTrue(out["loaded"])
        self.assertFalse(out["verified"])

    def test_deploy_requires_complete_nonstale_verification_evidence(self):
        good = {"match": True, "params_checked": True, "params_match": True,
                "stale": False, "freshness_known": True,
                "params": {"params_unserialized": 0}}
        cases = [{"error": "no autosave"}, {},
                 {**good, "match": False}, {**good, "params_match": False},
                 {**good, "params_checked": False}, {**good, "stale": True},
                 {**good, "freshness_known": False},
                 {**good, "params": {"params_unserialized": 1}}]
        p = self.patch_file()
        for evidence in cases:
            with self.subTest(diff=evidence):
                with patch.object(m, "cardinal_audit", return_value={"verdict": "PASS"}), \
                     patch.object(m, "load_patch", return_value={"ok": True}), \
                     patch.object(m, "cardinal_diff", return_value=evidence), \
                     patch.object(m.time, "sleep"):
                    out = m.cardinal_deploy(p)
                self.assertFalse(out["ok"])
                self.assertFalse(out.get("verified", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)

import unittest
import os
from unittest.mock import Mock, patch

import mechanical_backend as backend_module
from mechanical_backend import MechanicalBackendManager, is_failover_error


class MechanicalBackendManagerTests(unittest.TestCase):
    def _manager(self, probe, mode="auto"):
        return MechanicalBackendManager(mode=mode, probe=probe)

    def test_selects_pyzwcadmech_when_read_only_probe_succeeds(self):
        manager = self._manager(lambda: {"ok": True, "steps": {"version": "2026"}})

        state = manager.preflight()

        self.assertEqual("pyzwcadmech", state["active_backend"])
        self.assertEqual(1, state["generation"])

    def test_auto_mode_uses_zrx_after_probe_failure(self):
        manager = self._manager(lambda: {"ok": False, "error": "typelib unavailable"})
        manager._active_app = lambda: object()
        manager._activate_zrx = lambda app: (True, None)

        state = manager.preflight()

        self.assertEqual("zrx", state["active_backend"])
        self.assertEqual("typelib unavailable", state["fallback_reason"])

    def test_relative_zrx_path_is_based_on_project_directory(self):
        manager = MechanicalBackendManager(
            mode="zrx",
            zrx_path="zrx\\ZWMechMCP.zrx",
            probe=lambda: {"ok": True},
        )

        self.assertEqual(
            (backend_module.PROJECT_ROOT / "zrx" / "ZWMechMCP.zrx").resolve(),
            manager._resolve_zrx_path(),
        )

    def test_use_zrx_switch_forces_zrx_backend(self):
        with patch.dict(os.environ, {"ZWMECH_USE_ZRX": "1"}, clear=False):
            manager = MechanicalBackendManager(probe=lambda: {"ok": True})

        self.assertEqual("zrx", manager.mode)
        self.assertTrue(manager.use_zrx_switch)
        self.assertTrue(manager.snapshot()["zrx_switch_enabled"])

    def test_use_zrx_switch_skips_pyzwcadmech_probe(self):
        probe = Mock(side_effect=AssertionError("probe must be skipped"))
        with patch.dict(os.environ, {"ZWMECH_USE_ZRX": "1"}, clear=False):
            manager = MechanicalBackendManager(probe=probe)
            manager._active_app = lambda: object()
            manager._activate_zrx = lambda app: (True, None)

            state = manager.preflight()

        self.assertEqual("zrx", state["active_backend"])
        probe.assert_not_called()

    def test_dual_failure_degrades_without_raising(self):
        manager = self._manager(lambda: {"ok": False, "error": "typelib unavailable"})
        manager._active_app = lambda: object()
        manager._activate_zrx = lambda app: (False, "bridge timeout")

        state = manager.preflight()

        self.assertEqual("unavailable", state["active_backend"])
        self.assertIn("bridge timeout", state["fallback_reason"])

    def test_forced_primary_does_not_fall_back(self):
        manager = self._manager(lambda: {"ok": False, "error": "typelib unavailable"}, "pyzwcadmech")

        state = manager.preflight()

        self.assertEqual("unavailable", state["active_backend"])

    def test_diagnose_can_recheck_an_initially_unavailable_backend(self):
        attempts = iter(({"ok": False, "error": "first failure"}, {"ok": True}))
        manager = self._manager(lambda: next(attempts), "pyzwcadmech")
        self.assertEqual("unavailable", manager.preflight()["active_backend"])

        state = manager.recheck_unavailable()

        self.assertEqual("pyzwcadmech", state["active_backend"])

    def test_runtime_failover_switches_only_once(self):
        manager = self._manager(lambda: {"ok": True})
        manager.preflight()
        manager._activate_zrx = lambda app: (True, None)
        error = RuntimeError("GetInterfaceObject failed for ZwmToolKit")

        self.assertTrue(manager.failover_from_pyzwcadmech(object(), error))
        generation = manager.generation
        self.assertTrue(manager.failover_from_pyzwcadmech(object(), error))

        self.assertEqual("zrx", manager.backend)
        self.assertEqual(generation, manager.generation)

    def test_only_transport_and_typelib_errors_trigger_failover(self):
        self.assertTrue(is_failover_error(RuntimeError("ZwmToolKit type library was not loaded")))
        self.assertTrue(is_failover_error(RuntimeError("RPC server unavailable 0x800706BA")))
        self.assertFalse(is_failover_error(ValueError("missing field_name")))
        self.assertFalse(is_failover_error(RuntimeError("no title object")))

    def test_pid_mismatch_rejects_another_zwcad_instance(self):
        class FakeBridge:
            def __init__(self, timeout):
                self.timeout = timeout

            def ping(self):
                return {"plugin": "ZWMechMCP", "process_id": 11}

        manager = self._manager(lambda: {"ok": True})
        with patch.object(backend_module, "MechBridge", FakeBridge), patch.object(
            backend_module, "_window_process_id", return_value=22
        ):
            with self.assertRaisesRegex(Exception, "expected PID 22"):
                manager._bridge_for_app(object())


class TargetAwarePreflightTests(unittest.TestCase):
    def test_preflight_passes_expected_pid_to_probe(self):
        seen = {}

        def probe(expected_pid=None):
            seen["expected"] = expected_pid
            return {"ok": True, "cad_pid": expected_pid}

        manager = MechanicalBackendManager(probe=probe)
        pinned = object()
        with patch.object(backend_module, "_window_process_id", return_value=42):
            state = manager.preflight(app=pinned)

        self.assertEqual("pyzwcadmech", state["active_backend"])
        self.assertEqual(42, seen["expected"])
        self.assertEqual(42, state["startup_probe"]["cad_pid"])

    def test_preflight_probe_pid_mismatch_falls_back_to_zrx_with_pinned_app(self):
        def probe(expected_pid=None):
            return {"ok": True, "cad_pid": 999}

        manager = MechanicalBackendManager(probe=probe)
        pinned = object()
        activated = []

        def activate(app):
            activated.append(app)
            return (True, None)

        with patch.object(backend_module, "_window_process_id", return_value=42), patch.object(
            manager, "_activate_zrx", side_effect=activate
        ):
            state = manager.preflight(app=pinned)

        self.assertEqual("zrx", state["active_backend"])
        self.assertIn("expected PID 42", state["startup_probe"]["error"])
        self.assertIs(pinned, activated[0])

    def test_preflight_identity_failure_degrades_to_zrx(self):
        manager = MechanicalBackendManager(
            probe=Mock(side_effect=AssertionError("probe must be skipped"))
        )

        def activate(app):
            return (True, None)

        with patch.object(
            backend_module, "_window_process_id", side_effect=RuntimeError("no hwnd")
        ), patch.object(manager, "_activate_zrx", side_effect=activate):
            state = manager.preflight(app=object())

        self.assertEqual("zrx", state["active_backend"])
        self.assertIn("无法读取目标 ZWCAD 实例身份", state["startup_probe"]["error"])

    def test_probe_wrapper_rejects_pid_mismatch(self):
        import json as json_module

        from mechanical_backend import run_pyzwcadmech_probe

        payload = {"ok": True, "cad_pid": 7, "steps": {}}
        completed = Mock(returncode=0, stdout=json_module.dumps(payload), stderr="")
        with patch.object(backend_module.subprocess, "run", return_value=completed):
            result = run_pyzwcadmech_probe(expected_pid=42)

        self.assertFalse(result["ok"])
        self.assertIn("expected PID 42", result["error"])

    def test_probe_wrapper_passes_expected_pid_via_env(self):
        import json as json_module

        from mechanical_backend import run_pyzwcadmech_probe

        captured = {}
        payload = {"ok": True, "cad_pid": 42}

        def fake_run(command, **kwargs):
            captured["env"] = kwargs.get("env")
            return Mock(returncode=0, stdout=json_module.dumps(payload), stderr="")

        with patch.object(backend_module.subprocess, "run", side_effect=fake_run):
            result = run_pyzwcadmech_probe(expected_pid=42)

        self.assertTrue(result["ok"])
        self.assertEqual("42", captured["env"].get("ZWMECH_PROBE_EXPECT_PID"))


if __name__ == "__main__":
    unittest.main()

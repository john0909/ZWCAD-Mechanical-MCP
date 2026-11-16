import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import server


class _Backend:
    backend = "pyzwcadmech"
    generation = 7

    def __init__(self):
        self.created_with = []

    def create_connection(self, cad_app):
        self.created_with.append(cad_app)
        return Mock(name="mech")


class _TargetManager:
    def __init__(self, mode="legacy", generation=0, app=None):
        self.mode = mode
        self.generation = generation
        self._app = app
        self.get_calls = 0

    def get(self):
        self.get_calls += 1
        if self._app is None:
            raise AssertionError("get() must not be called in legacy mode")
        return self._app

    def clear(self):
        self.mode = "legacy"
        self.generation += 1


class _StubZwCAD:
    """Real class so _PinnedZwCAD subclassing behaves like production."""

    def __init__(self, create_if_not_exists=False, visible=True):
        self.init_kwargs = {
            "create_if_not_exists": create_if_not_exists,
            "visible": visible,
        }
        self._app = Mock(name="default-app")
        self.model = Mock(name="model")
        self.model.Count = 1

    @property
    def app(self):
        return self._app


class GetCadConnectionTests(unittest.TestCase):
    def _context(self, manager):
        backend = _Backend()
        thread_state = SimpleNamespace()
        constructed = []

        class _RecordingZwCAD(_StubZwCAD):
            def __init__(self, create_if_not_exists=False, visible=True):
                super().__init__(create_if_not_exists=create_if_not_exists, visible=visible)
                constructed.append(self)

        stack = patch.object(server, "_mechanical_backend", backend), patch.object(
            server, "_target_manager", manager
        ), patch.object(server, "_thread_state", thread_state), patch.object(
            server, "ZwCAD", _RecordingZwCAD
        )
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        return backend, constructed

    def test_legacy_mode_uses_default_zwcad(self):
        manager = _TargetManager("legacy", generation=3)
        backend, zw_class = self._context(manager)

        cad, mech = server.get_cad_connection()

        self.assertEqual(1, len(zw_class))
        self.assertIsInstance(cad, _StubZwCAD)
        self.assertIs(backend.created_with[0], cad.app)
        self.assertIs(mech, backend.created_with and None or mech)

    def test_pinned_mode_binds_manager_app(self):
        sentinel_app = Mock(name="pinned-app")
        manager = _TargetManager("pinned", generation=5, app=sentinel_app)
        backend, zw_class = self._context(manager)

        cad, mech = server.get_cad_connection()

        self.assertEqual(
            {"create_if_not_exists": False, "visible": True}, cad.init_kwargs
        )
        self.assertIs(cad.app, sentinel_app)
        self.assertIs(backend.created_with[0], sentinel_app)
        self.assertEqual(2, manager.get_calls)  # bind + cad.app access

    def test_binding_generation_change_rebuilds_connection(self):
        manager = _TargetManager("legacy", generation=0)
        backend, zw_class = self._context(manager)

        server.get_cad_connection()
        server.get_cad_connection()  # cache hit: no rebuild
        manager.generation = 1
        server.get_cad_connection()  # rebuild

        self.assertEqual(2, len(zw_class))

    def test_cache_hit_does_not_rebuild(self):
        manager = _TargetManager("legacy", generation=2)
        backend, zw_class = self._context(manager)

        server.get_cad_connection()
        server.get_cad_connection()

        self.assertEqual(1, len(zw_class))


class ToolSurfaceTests(unittest.TestCase):
    def test_set_zwcad_target_rejects_bad_path(self):
        result = server.set_zwcad_target(
            pid=1, creation_time="123", executable_path=r"C:\x\acad.exe"
        )
        self.assertIn("error", result)

    def test_set_zwcad_target_clear_does_not_require_instance(self):
        manager = _TargetManager("pinned", generation=4, app=Mock())
        with patch.object(server, "_target_manager", manager), patch.object(
            server, "reset_cad_connection"
        ) as reset:
            result = server.set_zwcad_target(
                pid=1, creation_time="1", executable_path=r"C:\x\ZWCAD.exe", clear=True
            )
        self.assertEqual("legacy", result["target_mode"])
        self.assertEqual(5, manager.generation)
        reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()

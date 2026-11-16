import unittest

import process_binding as pb
from process_binding import TargetError, TargetManager, parse_target, same_identity


GOOD = {
    "pid": 123,
    "creation_time": "133456789012345678",
    "executable_path": r"C:\Apps\ZWCAD.exe",
}


def make_identity(pid, creation="133456789012345678", path=r"C:\Apps\ZWCAD.exe"):
    return {"pid": pid, "creation_time": creation, "executable_path": path}


class ParseTargetTests(unittest.TestCase):
    def test_accepts_dict(self):
        self.assertEqual(parse_target(GOOD), GOOD)

    def test_accepts_json_string(self):
        import json

        self.assertEqual(parse_target(json.dumps(GOOD)), GOOD)

    def test_normalizes_path(self):
        parsed = parse_target({**GOOD, "executable_path": r"C:\Apps\.\ZWCAD\..\ZWCAD.exe"})
        self.assertEqual(parsed["executable_path"], r"C:\Apps\ZWCAD.exe")

    def test_rejects_missing_field(self):
        bad = {k: v for k, v in GOOD.items() if k != "pid"}
        with self.assertRaises(TargetError):
            parse_target(bad)

    def test_rejects_extra_field(self):
        with self.assertRaises(TargetError):
            parse_target({**GOOD, "caption": "x"})

    def test_rejects_bad_pid(self):
        for pid in (0, -1, 1.5, True, "7", None):
            with self.assertRaises(TargetError):
                parse_target({**GOOD, "pid": pid})

    def test_rejects_bad_creation_time(self):
        for creation in ("", "abc", 123, None):
            with self.assertRaises(TargetError):
                parse_target({**GOOD, "creation_time": creation})

    def test_rejects_relative_path(self):
        with self.assertRaises(TargetError):
            parse_target({**GOOD, "executable_path": "ZWCAD.exe"})

    def test_rejects_wrong_basename(self):
        with self.assertRaises(TargetError):
            parse_target({**GOOD, "executable_path": r"C:\Apps\acad.exe"})

    def test_rejects_non_json_string(self):
        with self.assertRaises(TargetError):
            parse_target("not json")


class SameIdentityTests(unittest.TestCase):
    def test_matches_case_insensitive_path(self):
        a = make_identity(1, "10", r"C:\apps\zwcad.exe")
        b = make_identity(1, "10", r"C:\APPS\ZWCAD.EXE")
        self.assertTrue(same_identity(a, b))

    def test_rejects_pid_mismatch(self):
        self.assertFalse(same_identity(make_identity(1), make_identity(2)))

    def test_rejects_creation_mismatch(self):
        self.assertFalse(same_identity(make_identity(1, "10"), make_identity(1, "11")))


class _App:
    def __init__(self, identity=None, error=None):
        self.identity = identity
        self.error = error


def manager_for(apps):
    def candidates():
        return list(apps)

    def identity(app):
        if app.error is not None:
            raise app.error
        return app.identity

    return TargetManager(candidates=candidates, identity=identity)


class TargetManagerTests(unittest.TestCase):
    def test_set_and_get_returns_matching_app(self):
        target = parse_target(GOOD)
        app = _App(dict(target))
        manager = manager_for([_App(make_identity(999)), app])
        bound = manager.set_target(GOOD)
        self.assertIs(bound, app)
        self.assertIs(manager.get(), app)
        self.assertEqual(manager.mode, "pinned")

    def test_set_target_rejects_unresolvable_and_keeps_legacy(self):
        manager = manager_for([_App(make_identity(999))])
        with self.assertRaises(TargetError):
            manager.set_target(GOOD)
        self.assertEqual(manager.mode, "legacy")
        self.assertIsNone(manager.target)

    def test_lazy_target_resolves_on_get(self):
        target = parse_target(GOOD)
        app = _App(dict(target))
        manager = manager_for([app])
        manager.set_target(GOOD, resolve_now=False)
        self.assertEqual(manager.mode, "pinned")
        self.assertIs(manager.get(), app)

    def test_get_raises_when_no_candidate_matches(self):
        manager = manager_for([_App(make_identity(999))])
        manager.set_target(GOOD, resolve_now=False)
        with self.assertRaises(TargetError):
            manager.get()

    def test_identity_read_failure_skips_candidate(self):
        target = parse_target(GOOD)
        app = _App(dict(target))
        broken = _App(error=OSError("gone"))
        manager = manager_for([broken, app])
        manager.set_target(GOOD, resolve_now=False)
        self.assertIs(manager.get(), app)

    def test_cached_app_exit_raises(self):
        target = parse_target(GOOD)
        app = _App(dict(target))
        manager = manager_for([app])
        manager.set_target(GOOD)
        app.error = OSError("process exited")
        with self.assertRaises(TargetError) as ctx:
            manager.get()
        self.assertIn("已退出或不可访问", str(ctx.exception))

    def test_cached_app_change_raises(self):
        target = parse_target(GOOD)
        app = _App(dict(target))
        manager = manager_for([app])
        manager.set_target(GOOD)
        app.identity = make_identity(999)
        with self.assertRaises(TargetError) as ctx:
            manager.get()
        self.assertIn("已发生变化", str(ctx.exception))

    def test_clear_restores_legacy_and_bumps_generation(self):
        manager = manager_for([_App(dict(parse_target(GOOD)))])
        manager.set_target(GOOD)
        generation = manager.generation
        manager.clear()
        self.assertEqual(manager.mode, "legacy")
        self.assertEqual(manager.generation, generation + 1)

    def test_set_and_clear_bump_generation(self):
        manager = manager_for([_App(dict(parse_target(GOOD)))])
        base = manager.generation
        manager.set_target(GOOD)
        self.assertEqual(manager.generation, base + 1)

    def test_get_requires_target(self):
        manager = manager_for([])
        with self.assertRaises(TargetError):
            manager.get()


if __name__ == "__main__":
    unittest.main()

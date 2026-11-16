"""Mechanical backend selection and pyzwcadmech-to-ZRX failover."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from mech_bridge import MechBridge, MechBridgeError, ZwCADMech as BridgeZwCADMech


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_ZRX_PATH = Path("zrx") / "ZWMechMCP.zrx"
VALID_BACKENDS = {"auto", "pyzwcadmech", "zrx"}
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


class MechanicalBackendError(RuntimeError):
    """Base error for mechanical backend selection and routing."""


class MechanicalBackendUnavailable(MechanicalBackendError):
    """No mechanical backend is usable, while ordinary CAD remains usable."""


class _UnavailableMech:
    def __init__(self, message):
        self._message = message

    def __getattr__(self, _name):
        raise MechanicalBackendUnavailable(self._message)


def _window_process_id(app) -> int:
    hwnd = int(app.HWND)
    process_id = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    if not process_id.value:
        raise MechanicalBackendError(f"Could not resolve ZWCAD process ID from HWND {hwnd}")
    return int(process_id.value)


def _probe_pyzwcadmech_in_process(expected_pid: int | None = None) -> dict[str, Any]:
    """Read-only probe entry point, executed in a bounded child process."""
    import comtypes.client
    import pythoncom

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    result: dict[str, Any] = {"ok": False, "steps": {}}
    try:
        from pyzwcadmech import ZwCADMech
        from pyzwcadmech import api as zwm_api

        result["steps"]["typelib"] = {
            "loaded": zwm_api.ZWM is not None,
            "source": getattr(zwm_api, "TYPELIB_SOURCE", None),
            "error": str(getattr(zwm_api, "TYPELIB_ERROR", "") or ""),
        }
        if zwm_api.ZWM is None:
            raise MechanicalBackendError("ZwmToolKit type library was not loaded")

        # ZwCADMech.app creates ZWCAD when no active object exists.  A health
        # check must never launch CAD, so obtain the existing ROT object first.
        cad_app = comtypes.client.GetActiveObject("ZWCAD.Application", dynamic=True)
        mech = ZwCADMech(cad_app=cad_app)
        result["cad_pid"] = _window_process_id(cad_app)
        if expected_pid is not None and int(expected_pid) != result["cad_pid"]:
            raise MechanicalBackendError(
                f"probe attached to ZWCAD PID {result['cad_pid']}, expected PID {expected_pid}"
            )
        result["steps"]["version"] = mech.zwm_app.get_version()
        mech.open_file("")
        result["steps"]["database"] = "ok"

        title = mech.get_title()
        result["steps"]["title"] = None if title is None else title.get_item_count()
        bom = mech.get_bom()
        result["steps"]["bom"] = None if bom is None else bom.get_item_count()
        frame = mech.get_frame()
        result["steps"]["frame"] = None if frame is None else {
            "width": frame.width,
            "height": frame.height,
        }
        result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return result


def _probe_child_command() -> int:
    print(json.dumps(_probe_pyzwcadmech_in_process(), ensure_ascii=False))
    return 0


def run_pyzwcadmech_probe(timeout=10.0, expected_pid: int | None = None) -> dict[str, Any]:
    """Run the COM probe out of process so an unresponsive COM server cannot hang MCP startup."""
    command = [sys.executable, "-m", "mechanical_backend", "--probe-pyzwcadmech"]
    try:
        probe_env = dict(os.environ)
        if expected_pid is not None:
            probe_env["ZWMECH_PROBE_EXPECT_PID"] = str(expected_pid)
        completed = subprocess.run(
            command,
            cwd=str(Path(__file__).parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=probe_env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"pyzwcadmech probe timed out after {timeout:g}s"}
    except Exception as exc:
        return {"ok": False, "error": f"Could not start pyzwcadmech probe: {exc}"}

    try:
        payload = json.loads(completed.stdout.strip())
    except Exception:
        return {
            "ok": False,
            "error": "pyzwcadmech probe returned invalid JSON",
            "stdout": completed.stdout[-1000:],
            "stderr": completed.stderr[-1000:],
        }
    if completed.returncode:
        payload["ok"] = False
        payload.setdefault("error", f"pyzwcadmech probe exited with {completed.returncode}")
    if payload.get("ok") and expected_pid is not None:
        probe_pid = payload.get("cad_pid")
        if probe_pid is not None and int(probe_pid) != int(expected_pid):
            payload = {
                **payload,
                "ok": False,
                "error": (
                    f"pyzwcadmech probe attached to ZWCAD PID {probe_pid}, "
                    f"expected PID {expected_pid} (target instance mismatch)"
                ),
            }
    return payload


def is_failover_error(exc: Exception) -> bool:
    """Return true only for transport/type-library failures, not drawing business errors."""
    if isinstance(exc, (MechanicalBackendUnavailable, MechBridgeError)):
        return False
    text = str(exc).lower()
    excluded = ("no title object", "no bom object", "not found", "missing", "unsupported")
    if any(marker in text for marker in excluded):
        return False
    markers = (
        "zwmtoolkit", "typelib", "type library", "getinterfaceobject",
        "queryinterface", "failed to get zwmdb", "failed to create zwmapp",
        "could not import pyzwcadmech", "0x800706ba", "0x80010108",
        "0x800401fd", "0x800401f0", "-2147023174", "-2147417848",
        "-2147220995", "-2147221008",
        "rpc server", "object has disconnected", "coinitialize",
    )
    return any(marker in text for marker in markers)


class MechanicalBackendManager:
    """Process-wide backend state; COM connections remain owned by caller threads."""

    def __init__(
        self,
        mode: str | None = None,
        zrx_path: str | os.PathLike[str] | None = None,
        probe: Callable[[], dict[str, Any]] | None = None,
    ):
        switch_value = os.environ.get("ZWMECH_USE_ZRX", "0").strip().lower()
        self.use_zrx_switch = switch_value in TRUTHY_ENV_VALUES
        if mode is None and self.use_zrx_switch:
            requested_mode = "zrx"
        else:
            requested_mode = (mode or os.environ.get("ZWMECH_BACKEND", "auto")).strip().lower()
        self.mode = requested_mode if requested_mode in VALID_BACKENDS else "auto"
        self._invalid_mode = requested_mode if requested_mode not in VALID_BACKENDS else None
        self.zrx_path = Path(zrx_path or os.environ.get("ZWMECH_ZRX_PATH", DEFAULT_ZRX_PATH))
        self._probe = probe or run_pyzwcadmech_probe
        self._lock = threading.RLock()
        self._backend = "uninitialized"
        self._generation = 0
        self._fallback_reason = None
        self._startup: dict[str, Any] = {}
        self._last_zrx_error = None
        self._bridge_info: dict[str, Any] | None = None

    @property
    def backend(self) -> str:
        with self._lock:
            return self._backend

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requested_backend": self.mode,
                "zrx_switch_enabled": self.use_zrx_switch,
                "active_backend": self._backend,
                "generation": self._generation,
                "zrx_path": str(self.zrx_path),
                "fallback_reason": self._fallback_reason,
                "startup_probe": self._startup,
                "zrx_error": self._last_zrx_error,
                "bridge_info": self._bridge_info,
            }

    def _select(self, backend: str, reason: str | None = None) -> None:
        if self._backend != backend:
            self._generation += 1
        self._backend = backend
        if reason:
            self._fallback_reason = reason

    def _bridge_for_app(self, app, timeout=0.5) -> dict[str, Any]:
        expected_pid = _window_process_id(app)
        info = MechBridge(timeout=timeout).ping()
        if info.get("plugin") != "ZWMechMCP":
            raise MechanicalBackendError("Bridge did not identify as ZWMechMCP")
        bridge_pid = info.get("process_id")
        if bridge_pid is None:
            raise MechanicalBackendError("Bridge does not expose process_id; rebuild ZWMechMCP.zrx")
        if int(bridge_pid) != expected_pid:
            raise MechanicalBackendError(
                f"Bridge belongs to ZWCAD PID {bridge_pid}, expected PID {expected_pid}"
            )
        return info

    def _activate_zrx(self, app) -> tuple[bool, str | None]:
        try:
            try:
                self._bridge_info = self._bridge_for_app(app)
                return True, None
            except MechanicalBackendError as exc:
                if "belongs to ZWCAD PID" in str(exc):
                    return False, str(exc)
            except Exception:
                pass

            zrx_path = self._resolve_zrx_path()
            if not zrx_path.is_file():
                return False, f"ZRX file does not exist: {zrx_path}"
            app.LoadZrx(str(zrx_path))

            deadline = time.monotonic() + 5.0
            last_error = None
            while time.monotonic() < deadline:
                try:
                    self._bridge_info = self._bridge_for_app(app)
                    return True, None
                except Exception as exc:
                    last_error = str(exc)
                    time.sleep(0.1)
            return False, f"ZRX loaded but bridge did not become ready: {last_error}"
        except Exception as exc:
            return False, f"LoadZrx failed: {type(exc).__name__}: {exc}"

    def _resolve_zrx_path(self) -> Path:
        """Resolve relative ZRX settings from this project, not the process CWD."""
        path = self.zrx_path
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    def _active_app(self):
        from pyzwcad import ZwCAD

        return ZwCAD().app

    def preflight(self, app=None) -> dict[str, Any]:
        with self._lock:
            if self._backend != "uninitialized":
                return self.snapshot()
            if self._invalid_mode:
                self._startup = {"ok": False, "error": f"Invalid ZWMECH_BACKEND: {self._invalid_mode}"}
                self._select("unavailable", self._startup["error"])
                return self.snapshot()

            expected_pid = None
            identity_error = None
            if app is not None:
                try:
                    expected_pid = _window_process_id(app)
                except Exception as exc:
                    identity_error = f"无法读取目标 ZWCAD 实例身份: {exc}"

            if self.mode != "zrx":
                if identity_error:
                    self._startup = {"ok": False, "error": identity_error}
                else:
                    if expected_pid is not None:
                        self._startup = self._probe(expected_pid=expected_pid)
                    else:
                        self._startup = self._probe()
                    if (
                        self._startup.get("ok")
                        and expected_pid is not None
                        and self._startup.get("cad_pid") is not None
                        and int(self._startup["cad_pid"]) != int(expected_pid)
                    ):
                        self._startup = {
                            **self._startup,
                            "ok": False,
                            "error": (
                                f"pyzwcadmech probe attached to ZWCAD PID "
                                f"{self._startup['cad_pid']}, expected PID {expected_pid}"
                            ),
                        }
                if self._startup.get("ok"):
                    self._select("pyzwcadmech")
                    return self.snapshot()
                if self.mode == "pyzwcadmech":
                    self._select("unavailable", self._startup.get("error", "pyzwcadmech probe failed"))
                    return self.snapshot()
                reason = self._startup.get("error", "pyzwcadmech probe failed")
            else:
                switch_source = "ZWMECH_USE_ZRX=1" if self.use_zrx_switch else "ZWMECH_BACKEND=zrx"
                self._startup = {"ok": None, "skipped": switch_source}
                reason = switch_source

            try:
                target_app = app if app is not None else self._active_app()
                ready, error = self._activate_zrx(target_app)
            except Exception as exc:
                ready, error = False, f"Could not access active ZWCAD: {type(exc).__name__}: {exc}"
            if ready:
                self._select("zrx", reason)
            else:
                self._last_zrx_error = error
                self._select("unavailable", f"{reason}; ZRX fallback failed: {error}")
            return self.snapshot()

    def recheck_unavailable(self) -> dict[str, Any]:
        """Retry startup selection after an initially unavailable backend is repaired."""
        with self._lock:
            if self._backend != "unavailable":
                return self.snapshot()
            self._backend = "uninitialized"
            self._fallback_reason = None
            self._last_zrx_error = None
            self._bridge_info = None
        return self.preflight()

    def create_connection(self, cad_app):
        backend = self.backend
        if backend == "pyzwcadmech":
            try:
                from pyzwcadmech import ZwCADMech
            except Exception as exc:
                raise MechanicalBackendError(f"Could not import pyzwcadmech: {exc}") from exc
            return ZwCADMech(cad_app=cad_app)
        if backend == "zrx":
            return BridgeZwCADMech()
        return _UnavailableMech(self._fallback_reason or "Mechanical backend is unavailable")

    def failover_from_pyzwcadmech(self, cad_app, exc: Exception) -> bool:
        """Switch once.  Callers decide whether retrying their operation is safe."""
        if not is_failover_error(exc) or self.mode == "pyzwcadmech":
            return False
        with self._lock:
            if self._backend == "zrx":
                return True
            if self._backend != "pyzwcadmech":
                return False
            ready, error = self._activate_zrx(cad_app)
            if ready:
                self._select("zrx", f"Runtime pyzwcadmech failure: {type(exc).__name__}: {exc}")
                return True
            self._last_zrx_error = error
            return False


if __name__ == "__main__":
    if "--probe-pyzwcadmech" in sys.argv:
        raise SystemExit(_probe_child_command())

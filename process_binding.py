"""ZWCAD multi-instance process binding for the Mechanical MCP server.

Multi-instance control: enumerate every live ZWCAD application object visible
to COM (GetActiveObject plus a full ROT walk), fingerprint each candidate by
(pid, creation_time, executable_path) read from its main window, and pin all
subsequent tool calls to the user-selected instance.  A pinned instance is
re-verified on every access; a dead or replaced instance is an error instead
of a silent re-attachment.

Windows only.  COM imports are deferred into functions so the pure helper
logic stays unit-testable without a COM runtime.
"""

from __future__ import annotations

import ctypes
import json
import os
import threading
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_TARGET_FIELDS = {"pid", "creation_time", "executable_path"}


class TargetError(RuntimeError):
    """Raised for invalid targets or when the selected instance cannot be bound."""


def parse_target(value) -> dict:
    """Validate a target descriptor; accepts a dict or a JSON string."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise TargetError(f"目标描述不是合法 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise TargetError("目标描述必须是包含 pid/creation_time/executable_path 的对象")
    if set(value) != _TARGET_FIELDS:
        raise TargetError("目标字段必须且仅为 pid、creation_time、executable_path")

    pid = value["pid"]
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or pid > 0xFFFFFFFF:
        raise TargetError("pid 必须为正整数")

    creation_time = value["creation_time"]
    if not isinstance(creation_time, str) or not creation_time.isdigit():
        raise TargetError("creation_time 必须为数字字符串（FILETIME 100ns 刻度）")

    executable_path = value["executable_path"]
    if not isinstance(executable_path, str) or not executable_path.strip():
        raise TargetError("executable_path 必须为非空字符串")
    if not os.path.isabs(executable_path):
        raise TargetError("executable_path 必须为绝对路径")
    if os.path.basename(executable_path).lower() != "zwcad.exe":
        raise TargetError("executable_path 必须指向 ZWCAD.exe")

    return {
        "pid": pid,
        "creation_time": creation_time,
        "executable_path": os.path.normpath(executable_path),
    }


def same_identity(actual: dict, expected: dict) -> bool:
    """Compare two identity dicts; paths are compared case-insensitively."""
    return (
        int(actual["pid"]) == int(expected["pid"])
        and str(actual["creation_time"]) == str(expected["creation_time"])
        and os.path.normcase(os.path.normpath(actual["executable_path"]))
        == os.path.normcase(os.path.normpath(expected["executable_path"]))
    )


def application_identity(app) -> dict:
    """Fingerprint a COM ZWCAD application via its HWND: pid/creation time/path."""
    try:
        hwnd = int(app.HWND)
    except Exception as exc:
        raise TargetError(f"无法读取 ZWCAD 窗口句柄: {exc}") from exc
    if not hwnd:
        raise TargetError("ZWCAD 窗口句柄不可用（实例可能尚未完全启动）")

    pid = wintypes.DWORD()
    if not ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        raise TargetError("无法读取 ZWCAD 进程 ID")
    if not pid.value:
        raise TargetError("无法读取 ZWCAD 进程 ID")

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        raise TargetError(
            f"无法打开 ZWCAD 进程 (PID {pid.value}, WinError {ctypes.get_last_error()})。"
            "若 ZWCAD 以管理员权限运行，请用相同权限启动本 MCP。"
        )
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        kernel.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        if not kernel.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            raise TargetError(
                f"无法读取 ZWCAD 进程创建时间 (PID {pid.value}, WinError {ctypes.get_last_error()})"
            )

        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        kernel.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise TargetError(
                f"无法读取 ZWCAD 可执行文件路径 (PID {pid.value}, WinError {ctypes.get_last_error()})"
            )

        creation = str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        return {"pid": pid.value, "creation_time": creation, "executable_path": path.value}
    finally:
        kernel.CloseHandle(handle)


def _rot_applications():
    """Enumerate the COM Running Object Table and yield ZWCAD application objects.

    A ZWCAD instance may register either its Application or a document in the
    ROT, so both moniker shapes are resolved and the Application is unwrapped.
    Only GetObject/attach happens here; no document is opened.
    """
    import comtypes
    from comtypes import COMMETHOD, GUID, IUnknown
    from comtypes.automation import IDispatch
    from comtypes.client.dynamic import Dispatch
    from comtypes import COMError
    from ctypes import POINTER

    class IEnumMoniker(IUnknown):
        _iid_ = GUID("{00000102-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], comtypes.HRESULT, "Next",
                      (["in"], wintypes.ULONG, "celt"),
                      (["out"], POINTER(POINTER(IUnknown)), "rgelt"),
                      (["out"], POINTER(wintypes.ULONG), "pceltFetched")),
            COMMETHOD([], comtypes.HRESULT, "Skip",
                      (["in"], wintypes.ULONG, "celt")),
            COMMETHOD([], comtypes.HRESULT, "Reset"),
            COMMETHOD([], comtypes.HRESULT, "Clone",
                      (["out"], POINTER(POINTER(IUnknown)), "ppenum")),
        ]

    class IRunningObjectTable(IUnknown):
        _iid_ = GUID("{00000010-0000-0000-C000-000000000046}")
        _methods_ = [
            COMMETHOD([], comtypes.HRESULT, "Register",
                      (["in"], wintypes.DWORD, "grfFlags"),
                      (["in"], POINTER(IUnknown), "punkObject"),
                      (["in"], POINTER(IUnknown), "pmkObjectName"),
                      (["out"], POINTER(wintypes.DWORD), "pdwRegister")),
            COMMETHOD([], comtypes.HRESULT, "Revoke",
                      (["in"], wintypes.DWORD, "dwRegister")),
            COMMETHOD([], comtypes.HRESULT, "IsRunning",
                      (["in"], POINTER(IUnknown), "pmkObjectName")),
            COMMETHOD([], comtypes.HRESULT, "GetObject",
                      (["in"], POINTER(IUnknown), "pmkObjectName"),
                      (["out"], POINTER(POINTER(IUnknown)), "ppunkObject")),
            COMMETHOD([], comtypes.HRESULT, "NoteChangeTime",
                      (["in"], wintypes.DWORD, "dwRegister"),
                      (["in"], POINTER(wintypes.FILETIME), "filetime")),
            COMMETHOD([], comtypes.HRESULT, "GetTimeOfLastChange",
                      (["in"], POINTER(IUnknown), "pmkObjectName"),
                      (["out"], POINTER(wintypes.FILETIME), "pfiletime")),
            COMMETHOD([], comtypes.HRESULT, "EnumRunning",
                      (["out"], POINTER(POINTER(IEnumMoniker)), "ppenumMoniker")),
        ]

    ole = ctypes.OleDLL("ole32")
    ole.GetRunningObjectTable.argtypes = [wintypes.DWORD, POINTER(POINTER(IRunningObjectTable))]
    ole.GetRunningObjectTable.restype = comtypes.HRESULT
    table = POINTER(IRunningObjectTable)()
    ole.GetRunningObjectTable(0, ctypes.byref(table))

    enumerator = table.EnumRunning()
    while True:
        try:
            moniker, fetched = enumerator.Next(1)
        except (AttributeError, OSError, COMError, ValueError):
            break
        if not fetched:
            break
        try:
            unknown = table.GetObject(moniker)
            obj = Dispatch(unknown.QueryInterface(IDispatch))
            app = getattr(obj, "Application", obj)
            yield app
        except (AttributeError, OSError, COMError):
            continue


def running_applications():
    """Yield every live ZWCAD application COM proxy (best effort, may repeat)."""
    try:
        import comtypes
        import comtypes.client
    except Exception as exc:
        raise TargetError(f"comtypes 不可用: {exc}") from exc

    # Tool threads may run before any CoInitialize call; initialize COM first
    # and tolerate an already-initialized (possibly different-apartment) thread.
    try:
        comtypes.CoInitialize()
    except OSError:
        pass

    try:
        yield comtypes.client.GetActiveObject("ZWCAD.Application", dynamic=True)
    except Exception:
        pass
    yield from _rot_applications()


class TargetManager:
    """Holds the user-selected ZWCAD instance and re-verifies it on every access."""

    def __init__(self, candidates=running_applications, identity=application_identity):
        self._candidates = candidates
        self._identity = identity
        self._lock = threading.RLock()
        self._target: dict | None = None
        self._cached_app = None
        self._source: str | None = None
        self._generation = 0

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def mode(self) -> str:
        with self._lock:
            return "pinned" if self._target is not None else "legacy"

    @property
    def source(self) -> str | None:
        with self._lock:
            return self._source

    @property
    def target(self) -> dict | None:
        with self._lock:
            return dict(self._target) if self._target else None

    def set_target(self, target, source: str = "session", resolve_now: bool = True):
        """Pin a target; returns the bound COM app when resolve_now is true."""
        parsed = parse_target(target)
        bound = None
        if resolve_now:
            bound = self._resolve(parsed)
        with self._lock:
            self._target = parsed
            self._source = source
            self._cached_app = bound
            self._generation += 1
        return bound

    def clear(self) -> None:
        with self._lock:
            if self._target is not None:
                self._generation += 1
            self._target = None
            self._cached_app = None
            self._source = None

    def get(self):
        """Return the pinned COM app, re-verifying its identity first."""
        with self._lock:
            target = self._target
            if target is None:
                raise TargetError("未设置目标 ZWCAD 实例")
            cached = self._cached_app
        if cached is not None:
            try:
                if same_identity(self._identity(cached), target):
                    return cached
            except TargetError:
                raise
            except Exception as exc:
                raise TargetError("所选 ZWCAD 实例已退出或不可访问，请重新连接。") from exc
            raise TargetError("所选 ZWCAD 实例已发生变化，请重新连接。")

        bound = self._resolve(target)
        with self._lock:
            if self._target != target:
                raise TargetError("目标实例已被切换，请重试。")
            self._cached_app = bound
        return bound

    def _resolve(self, target: dict):
        seen = set()
        for candidate in self._candidates():
            try:
                identity = self._identity(candidate)
            except Exception:
                continue
            key = (
                int(identity["pid"]),
                str(identity["creation_time"]),
                os.path.normcase(os.path.normpath(identity["executable_path"])),
            )
            if key in seen:
                continue
            seen.add(key)
            if same_identity(identity, target):
                return candidate
        raise TargetError(
            f"无法通过 COM 连接所选 ZWCAD 实例 (PID {target['pid']})，"
            "请确认实例仍在运行并用 list_zwcad_processes 重新选择。"
        )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "generation": self._generation,
                "target": dict(self._target) if self._target else None,
                "source": self._source,
            }

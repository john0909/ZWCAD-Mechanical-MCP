"""Send AutoLISP through ZWCAD SendCommand without temp files.

Insert/Set fire-and-forget like insert_balloon. Get/eval round-trip via a
temporary XRECORD in named dictionary ZWM_MCP; Python reads it over COM then
deletes the record (and the dict if empty). New entity handles come from
ModelSpace count, not LISP return values.
"""

from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 8.0
EVAL_DICT_NAME = "ZWM_MCP"
EVAL_STATUS_OK = 0
EVAL_STATUS_ERROR = -2
XRECORD_STR_CHUNK = 255


class LispBridgeError(RuntimeError):
    """LISP evaluation failed, timed out, or returned an error."""


class LispHandle:
    """Tag a DWG handle so to_lisp emits (handent "...")."""

    __slots__ = ("handle",)

    def __init__(self, handle: str):
        text = str(handle).strip()
        if not text:
            raise ValueError("handle 不能为空")
        self.handle = text

    def __repr__(self):
        return f"LispHandle({self.handle!r})"

    def __eq__(self, other):
        return isinstance(other, LispHandle) and other.handle == self.handle


def format_number(value) -> str:
    """Format a number for evaluated AutoLISP source."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    number = float(value)
    if number == int(number) and abs(number) < 1e12:
        return f"{number:.1f}"
    return repr(number)


def _is_point(value) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    return all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)


def to_lisp(value) -> str:
    """Serialize a Python value to an evaluable AutoLISP literal."""
    if value is None:
        return "nil"
    if isinstance(value, LispHandle):
        return f'(handent {to_lisp(value.handle)})'
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format_number(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if _is_point(value):
        return "(list %s %s %s)" % tuple(format_number(v) for v in value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "()"
        return "(list %s)" % " ".join(to_lisp(item) for item in value)
    raise TypeError(f"无法转换为 LISP 字面量: {type(value).__name__}")


def parse_lisp(text: str):
    """Parse a vl-prin1-to-string / prin1 form into Python values."""
    if text is None:
        return None
    parser = _LispParser(str(text))
    value = parser.parse_value()
    parser.skip_ws()
    if parser.i < len(parser.s):
        trailing = parser.s[parser.i:].strip()
        if trailing:
            raise LispBridgeError(f"LISP 回传含无法解析的尾部: {trailing[:80]}")
    return value


class _LispParser:
    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.n = len(text)

    def skip_ws(self):
        while self.i < self.n and self.s[self.i] in " \t\r\n":
            self.i += 1

    def parse_value(self):
        self.skip_ws()
        if self.i >= self.n:
            return None
        ch = self.s[self.i]
        if ch == "(":
            return self._parse_list()
        if ch == '"':
            return self._parse_string()
        if ch == "'":
            self.i += 1
            return self.parse_value()
        return self._parse_atom()

    def _parse_list(self):
        self.i += 1
        items = []
        while True:
            self.skip_ws()
            if self.i >= self.n:
                raise LispBridgeError("LISP 列表缺少右括号")
            if self.s[self.i] == ")":
                self.i += 1
                return items
            if self.s[self.i] == ".":
                self.i += 1
                cdr = self.parse_value()
                self.skip_ws()
                if self.i < self.n and self.s[self.i] == ")":
                    self.i += 1
                if not items:
                    return cdr
                items.append(cdr)
                return items
            items.append(self.parse_value())

    def _parse_string(self):
        self.i += 1
        out = []
        while self.i < self.n:
            ch = self.s[self.i]
            if ch == "\\":
                self.i += 1
                if self.i >= self.n:
                    break
                nxt = self.s[self.i]
                mapping = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}
                out.append(mapping.get(nxt, nxt))
                self.i += 1
                continue
            if ch == '"':
                self.i += 1
                return "".join(out)
            out.append(ch)
            self.i += 1
        raise LispBridgeError("LISP 字符串缺少结束引号")

    def _parse_atom(self):
        start = self.i
        while self.i < self.n and self.s[self.i] not in ' \t\r\n()"':
            self.i += 1
        token = self.s[start:self.i]
        if not token:
            raise LispBridgeError("空的 LISP 原子")
        lowered = token.lower()
        if lowered == "nil":
            return None
        if token == "T" or lowered == "t":
            return True
        try:
            if any(c in token for c in ".eE"):
                return float(token)
            return int(token)
        except ValueError:
            return token


def send_lisp(doc, expr: str) -> None:
    """Queue an AutoLISP expression, same path as insert_balloon."""
    if doc is None:
        raise LispBridgeError("CAD 文档不可用")
    doc.SendCommand("\x03\x03" + expr.strip() + "\r")


def model_count(doc) -> int:
    try:
        return int(doc.ModelSpace.Count)
    except Exception:
        return 0


def handles_since(doc, old_count: int) -> list:
    """Handles of ModelSpace entities appended after old_count."""
    try:
        model = doc.ModelSpace
        n = int(model.Count)
    except Exception:
        return []
    if n <= old_count:
        return []
    out = []
    for i in range(old_count, n):
        try:
            out.append(str(model.Item(i).Handle))
        except Exception:
            continue
    return out


def wait_new_handles(doc, old_count: int, timeout: float = 0.3) -> list:
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        last = handles_since(doc, old_count)
        if last:
            return last
        time.sleep(0.05)
    return last


def _new_eval_rec_name() -> str:
    return "E" + uuid.uuid4().hex


def build_eval_progn(expr: str, rec_name: str = "EVAL") -> str:
    """Evaluate expr and store prin1 text in a temporary named-dict XRECORD."""
    body = expr.strip()
    dict_name = EVAL_DICT_NAME
    rec = rec_name.replace("\\", "").replace('"', "")
    chunk = XRECORD_STR_CHUNK
    return (
        "(progn"
        " (setq __zwm_err *error*)"
        " (defun __zwm_put (st txt / nod de old rec dxf i n)"
        "  (setq nod (namedobjdict))"
        f"  (setq de (cdr (assoc -1 (dictsearch nod \"{dict_name}\"))))"
        "  (if (null de)"
        "   (progn (setq de (entmakex (list (cons 0 \"DICTIONARY\") (cons 100 \"AcDbDictionary\"))))"
        f"          (dictadd nod \"{dict_name}\" de)))"
        f"  (setq old (dictsearch de \"{rec}\"))"
        f"  (if old (dictremove de \"{rec}\"))"
        "  (setq dxf (list (cons 0 \"XRECORD\") (cons 100 \"AcDbXrecord\") (cons 90 st))"
        f"        i 1 n (strlen txt))"
        "  (if (= n 0)"
        "   (setq dxf (append dxf (list (cons 1 \"\"))))"
        "   (while (<= i n)"
        f"    (setq dxf (append dxf (list (cons 1 (substr txt i {chunk}))))"
        f"          i (+ i {chunk}))))"
        "  (setq rec (entmakex dxf))"
        f"  (if rec (dictadd de \"{rec}\" rec)))"
        f" (defun *error* (m) (__zwm_put {EVAL_STATUS_ERROR} m)"
        "  (setq *error* __zwm_err) (princ))"
        f" (setq __zwm_v {body})"
        f" (__zwm_put {EVAL_STATUS_OK} (vl-prin1-to-string __zwm_v))"
        " (setq *error* __zwm_err)"
        " (princ))"
    )


def _as_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_seq(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _eval_dictionary(doc):
    try:
        return doc.Dictionaries.Item(EVAL_DICT_NAME)
    except Exception:
        return None


def _get_xrecord_pairs(xr):
    """Read DXF type/value arrays from an AcadXRecord.

    ZWCAD ActiveX GetXRecordData is a void method with two [out] VARIANT
    parameters; a zero-arg call raises DISP_E_BADPARAMCOUNT. Fake test
    objects may still return (types, values) directly.
    """
    try:
        raw = xr.GetXRecordData()
    except Exception:
        raw = None
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        types, values = raw
        types, values = _as_seq(types), _as_seq(values)
        if types:
            return types, values
    try:
        from ctypes import byref
        from comtypes.automation import VARIANT
        types_var, values_var = VARIANT(), VARIANT()
        xr.GetXRecordData(byref(types_var), byref(values_var))
        types, values = _as_seq(types_var.value), _as_seq(values_var.value)
        if types:
            return types, values
    except Exception:
        return None
    return None


def _read_eval_xrecord(doc, rec_name: str):
    d = _eval_dictionary(doc)
    if d is None:
        return None
    try:
        xr = d.GetObject(rec_name)
    except Exception:
        return None
    return _get_xrecord_pairs(xr)


def _payload_from_xrecord(types, values) -> tuple[int, str]:
    status = EVAL_STATUS_OK
    chunks = []
    for code, value in zip(types, values):
        dxf = _as_int(code, -1)
        if dxf == 90:
            status = _as_int(value, EVAL_STATUS_OK)
        elif dxf in (1, 300, 302):
            chunks.append("" if value is None else str(value))
    return status, "".join(chunks)


def _delete_eval_temp(doc, rec_name: str) -> None:
    """Remove the temporary XRECORD and drop the ZWM_MCP dict if possible."""
    d = _eval_dictionary(doc)
    if d is None:
        return
    try:
        d.Remove(rec_name)
    except Exception:
        try:
            xr = d.GetObject(rec_name)
            xr.Delete()
        except Exception:
            pass
    try:
        empty = int(getattr(d, "Count", 1)) == 0
    except Exception:
        empty = False
    if empty:
        try:
            d.Delete()
        except Exception:
            pass


def eval_lisp(doc, expr: str, timeout: float = DEFAULT_TIMEOUT):
    """Evaluate AutoLISP and parse the result stored in a temporary XRECORD."""
    if doc is None:
        raise LispBridgeError("CAD 文档不可用")
    rec_name = _new_eval_rec_name()
    send_lisp(doc, build_eval_progn(expr, rec_name=rec_name))

    deadline = time.time() + timeout
    record = None
    try:
        while time.time() < deadline:
            record = _read_eval_xrecord(doc, rec_name)
            if record is not None:
                break
            time.sleep(0.05)
        else:
            raise LispBridgeError("LISP 执行超时，未从命名字典 XRECORD 收到回传")

        status, payload = _payload_from_xrecord(*record)
        if status == EVAL_STATUS_ERROR:
            raise LispBridgeError(payload or "LISP 执行失败")
        if not payload or payload == "nil":
            return None
        return parse_lisp(payload)
    finally:
        _delete_eval_temp(doc, rec_name)

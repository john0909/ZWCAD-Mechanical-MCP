"""Mechanical symbol and bubble LISP codecs for MCP tools.

Converts named params <-> positional LISP slot lists for:
  surf_sym, fc_frame, datum_id, note, welding, bubble
"""

from __future__ import annotations

from lisp_bridge import (
    LispBridgeError,
    LispHandle,
    eval_lisp,
    model_count,
    send_lisp,
    to_lisp,
    wait_new_handles,
)

LOCATION_METHODS = {-1, 0, 45, 90, 135, 180, 225, 270, 315}

SYMBOL_ACTIONS = {"insert", "get", "set"}
BUBBLE_ACTIONS = {"auto", "manu", "manu_list", "get_substd", "fill_all", "fill_picked"}

# DXF group 0 names; matches ZwmBubCreate_IsSupportEntity
BUBBLE_TARGET_DXF_TYPES = (
    "DIMENSION,TOLERANCE,ZWMSURFSYM,ZWMFCFRAME,ZWMDATUMID,ZWMDATUMTARGET,"
    "ZWMNOTE,ZWMCHAMFER,ZWMWELDINGCHILDSYM,ZWMWELDING,ZWMHOLECHARTPOINT,"
    "ZWMHOLECHARTCOMPLETETABLE"
)
# XRECORD can return large prin1 payloads; keep ssget slices modest for command time.
BUBBLE_TARGET_ENUM_CHUNK = 200

INSERT_FN = {
    "surf_sym": "Zwm_SurfSymInsert",
    "fc_frame": "Zwm_FCFrameInsert",
    "datum_id": "Zwm_DatumIdInsert",
    "note": "Zwm_NoteInsert",
    "welding": "Zwm_WeldingInsert",
}
GET_FN = {
    "surf_sym": "Zwm_SurfSymGet",
    "fc_frame": "Zwm_FCFrameGet",
    "datum_id": "Zwm_DatumIdGet",
    "note": "Zwm_NoteGet",
    "welding": "Zwm_WeldingGet",
}
SET_FN = {
    "surf_sym": "Zwm_SurfSymSet",
    "fc_frame": "Zwm_FCFrameSet",
    "datum_id": "Zwm_DatumIdSet",
    "note": "Zwm_NoteSet",
    "welding": "Zwm_WeldingSet",
}
LABELS = {
    "surf_sym": "表面粗糙度符号",
    "fc_frame": "形位公差框",
    "datum_id": "基准代号",
    "note": "引线注释",
    "welding": "焊接符号",
    "bubble": "气泡图",
}


class SymbolError(ValueError):
    """Invalid symbol/bubble parameters."""


def _as_int(value, default=0) -> int:
    if value is None or value == "":
        return int(default)
    if isinstance(value, bool):
        return 1 if value else 0
    return int(value)


def _as_float(value, default=0.0) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _as_str(value, default="") -> str:
    if value is None:
        return default
    return str(value)


def _as_bool_int(value, default=0) -> int:
    if value is None:
        return int(default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return 1
        if lowered in ("0", "false", "no", "off", ""):
            return 0
    return 1 if value else 0


def _as_point(value, default=(0.0, 0.0, 0.0)):
    if value is None:
        return [float(default[0]), float(default[1]), float(default[2])]
    if isinstance(value, dict):
        return [
            float(value.get("x", default[0])),
            float(value.get("y", default[1])),
            float(value.get("z", default[2])),
        ]
    seq = list(value)
    z = seq[2] if len(seq) > 2 else default[2]
    return [float(seq[0]), float(seq[1]), float(z)]


def point_from_params(params, name, default=(0.0, 0.0, 0.0)):
    """Read a 3D point from `name` or `name_x`/`name_y`/`name_z`."""
    params = params or {}
    if name in params and isinstance(params[name], (list, tuple, dict)):
        return _as_point(params[name], default)
    px, py, pz = f"{name}_x", f"{name}_y", f"{name}_z"
    if px in params or py in params or pz in params:
        return [
            _as_float(params.get(px), default[0]),
            _as_float(params.get(py), default[1]),
            _as_float(params.get(pz), default[2]),
        ]
    return [float(default[0]), float(default[1]), float(default[2])]


def _require_range(name, value, lo, hi):
    if value < lo or value > hi:
        raise SymbolError(f"{name} 必须为 {lo}-{hi}，当前值: {value}")
    return value


def _require_handle(params) -> str:
    handle = (params or {}).get("handle")
    if not handle:
        raise SymbolError("get/set 需要 params.handle")
    return str(handle).strip()


def _empty_layer():
    return {"characteristic": 0, "tol1": "", "tol2": "", "datums": ["", "", ""]}


def _normalize_layer(layer) -> dict:
    layer = layer or {}
    datums = list(layer.get("datums") or ["", "", ""])
    while len(datums) < 3:
        datums.append("")
    characteristic = _as_int(layer.get("characteristic"), 0)
    _require_range("characteristic", characteristic, 0, 15)
    return {
        "characteristic": characteristic,
        "tol1": _as_str(layer.get("tol1")),
        "tol2": _as_str(layer.get("tol2")),
        "datums": [str(d) for d in datums[:3]],
    }


def _layer_slots(layer) -> list:
    layer = _normalize_layer(layer)
    return [layer["characteristic"], layer["tol1"], layer["tol2"], *layer["datums"]]


def _parse_layer(slots, offset) -> dict:
    datums = [
        _as_str(slots[offset + 3] if len(slots) > offset + 3 else ""),
        _as_str(slots[offset + 4] if len(slots) > offset + 4 else ""),
        _as_str(slots[offset + 5] if len(slots) > offset + 5 else ""),
    ]
    return {
        "characteristic": _as_int(slots[offset] if len(slots) > offset else 0),
        "tol1": _as_str(slots[offset + 1] if len(slots) > offset + 1 else ""),
        "tol2": _as_str(slots[offset + 2] if len(slots) > offset + 2 else ""),
        "datums": datums,
    }


def _flatten_extra(extra) -> list:
    if not extra:
        return []
    items = dict(extra)
    ordered = []
    if "OtherSideType" in items:
        ordered.append(("OtherSideType", items.pop("OtherSideType")))
    for key, value in items.items():
        ordered.append((str(key), value))
    out = []
    for key, value in ordered:
        out.append(str(key))
        out.append("" if value is None else str(value))
    return out


def _parse_extra(slots) -> dict:
    extra = {}
    i = 0
    while i + 1 < len(slots):
        extra[str(slots[i])] = "" if slots[i + 1] is None else str(slots[i + 1])
        i += 2
    return extra


# ---------------------------------------------------------------------------
# Surface roughness
# ---------------------------------------------------------------------------

def build_surf_slots(params, defaults=True) -> list:
    p = params or {}
    symbol_type = _as_int(p.get("symbol_type"), 2 if defaults else 0)
    pattern = _as_int(p.get("pattern"), 0)
    direction = _as_int(p.get("direction"), 0)
    _require_range("symbol_type", symbol_type, 0, 2)
    _require_range("pattern", pattern, 0, 7)
    _require_range("direction", direction, 0, 2)
    a1_default = "3.2" if defaults else ""
    return [
        point_from_params(p, "arrow"),
        point_from_params(p, "symbol"),
        _as_str(p.get("a1"), a1_default),
        symbol_type,
        _as_bool_int(p.get("has_leader"), 1 if defaults else 0),
        direction,
        pattern,
        _as_str(p.get("b")),
        _as_str(p.get("c")),
        _as_str(p.get("c1")),
        _as_str(p.get("e1")),
        _as_str(p.get("f")),
        _as_str(p.get("g")),
        _as_str(p.get("sub_std")),
        _as_float(p.get("rotation"), 0.0),
    ]


def parse_surf_slots(slots) -> dict:
    slots = list(slots or [])
    slots.extend([None] * (15 - len(slots)))
    return {
        "arrow": _as_point(slots[0]),
        "symbol": _as_point(slots[1]),
        "a1": _as_str(slots[2]),
        "symbol_type": _as_int(slots[3]),
        "has_leader": bool(_as_int(slots[4])),
        "direction": _as_int(slots[5]),
        "pattern": _as_int(slots[6]),
        "b": _as_str(slots[7]),
        "c": _as_str(slots[8]),
        "c1": _as_str(slots[9]),
        "e1": _as_str(slots[10]),
        "f": _as_str(slots[11]),
        "g": _as_str(slots[12]),
        "sub_std": _as_str(slots[13]),
        "rotation": _as_float(slots[14]),
    }


# ---------------------------------------------------------------------------
# Feature control frame
# ---------------------------------------------------------------------------

def build_fc_slots(params, defaults=True, full=None) -> list:
    if full is None:
        full = not defaults
    p = params or {}
    layer_count = _as_int(p.get("layer_count"), 1)
    _require_range("layer_count", layer_count, 1, 3)
    layers = [_normalize_layer(layer) for layer in (p.get("layers") or [])]
    if defaults and not layers:
        layers = [_normalize_layer({"characteristic": 1, "tol1": "0.02"})]
    while len(layers) < layer_count:
        layers.append(_empty_layer() if not defaults else _normalize_layer({"characteristic": 1}))
    layers = layers[:layer_count]
    if layers:
        _require_range("characteristic", layers[0]["characteristic"], 0, 15)

    modifier = _as_int(p.get("material_modifier"), 0)
    _require_range("material_modifier", modifier, 0, 11)
    direction = _as_int(p.get("direction"), 0)
    _require_range("direction", direction, 0, 2)

    slots = [
        point_from_params(p, "arrow"),
        point_from_params(p, "symbol"),
        _as_str(p.get("sub_std")),
        layer_count,
        _as_bool_int(p.get("has_leader"), 1 if defaults else 0),
        direction,
    ]
    for layer in layers:
        slots.extend(_layer_slots(layer))
    if full:
        while len(slots) < 24:
            slots.extend(_layer_slots(_empty_layer()))
        slots = slots[:24]
        slots.extend([
            _as_str(p.get("top_note")),
            _as_str(p.get("bottom_note")),
            _as_bool_int(p.get("all_around"), 0),
            modifier,
        ])
        return slots

    has_tail = any(
        k in p for k in ("top_note", "bottom_note", "all_around", "material_modifier")
    ) or bool(p.get("top_note") or p.get("bottom_note") or p.get("all_around") or modifier)
    if has_tail:
        slots.extend([
            _as_str(p.get("top_note")),
            _as_str(p.get("bottom_note")),
            _as_bool_int(p.get("all_around"), 0),
            modifier,
        ])
    return slots


def parse_fc_slots(slots) -> dict:
    slots = list(slots or [])
    layer_count = _as_int(slots[3] if len(slots) > 3 else 1, 1)
    layer_count = max(1, min(3, layer_count))
    layers = []
    for i in range(layer_count):
        layers.append(_parse_layer(slots, 6 + i * 6))
    # notes: Get always returns 28; insert-min has 12 then optional tail
    if len(slots) >= 28:
        top_note = _as_str(slots[24])
        bottom_note = _as_str(slots[25])
        all_around = bool(_as_int(slots[26]))
        modifier = _as_int(slots[27])
    elif len(slots) > 6 + layer_count * 6:
        tail = slots[6 + layer_count * 6:]
        top_note = _as_str(tail[0] if len(tail) > 0 else "")
        bottom_note = _as_str(tail[1] if len(tail) > 1 else "")
        all_around = bool(_as_int(tail[2] if len(tail) > 2 else 0))
        modifier = _as_int(tail[3] if len(tail) > 3 else 0)
    else:
        top_note = bottom_note = ""
        all_around = False
        modifier = 0
    return {
        "arrow": _as_point(slots[0] if slots else None),
        "symbol": _as_point(slots[1] if len(slots) > 1 else None),
        "sub_std": _as_str(slots[2] if len(slots) > 2 else ""),
        "layer_count": layer_count,
        "has_leader": bool(_as_int(slots[4] if len(slots) > 4 else 0)),
        "direction": _as_int(slots[5] if len(slots) > 5 else 0),
        "layers": layers,
        "top_note": top_note,
        "bottom_note": bottom_note,
        "all_around": all_around,
        "material_modifier": modifier,
    }


# ---------------------------------------------------------------------------
# Datum identifier
# ---------------------------------------------------------------------------

def build_datum_slots(params, defaults=True) -> list:
    p = params or {}
    arrow_type = _as_int(p.get("arrow_type"), 1 if defaults else 0)
    direction = _as_int(p.get("direction"), 0)
    _require_range("arrow_type", arrow_type, 0, 6)
    _require_range("direction", direction, 0, 2)
    letter_default = "A" if defaults else ""
    return [
        point_from_params(p, "end"),
        point_from_params(p, "jog"),
        point_from_params(p, "box"),
        _as_str(p.get("sub_std")),
        _as_str(p.get("letter"), letter_default),
        _as_str(p.get("note")),
        _as_str(p.get("thread_note")),
        arrow_type,
        direction,
    ]


def parse_datum_slots(slots) -> dict:
    slots = list(slots or [])
    slots.extend([None] * (9 - len(slots)))
    return {
        "end": _as_point(slots[0]),
        "jog": _as_point(slots[1]),
        "box": _as_point(slots[2]),
        "sub_std": _as_str(slots[3]),
        "letter": _as_str(slots[4]),
        "note": _as_str(slots[5]),
        "thread_note": _as_str(slots[6]),
        "arrow_type": _as_int(slots[7]),
        "direction": _as_int(slots[8]),
    }


# ---------------------------------------------------------------------------
# Leader note
# ---------------------------------------------------------------------------

def build_note_slots(params, defaults=True) -> list:
    p = params or {}
    justification = _as_int(p.get("leader_justification"), 0)
    h_align = _as_int(p.get("text_h_align"), 0)
    direction = _as_int(p.get("direction"), 0)
    arrow_type = _as_int(p.get("arrow_type"), 1 if defaults else 0)
    _require_range("leader_justification", justification, 0, 7)
    _require_range("text_h_align", h_align, 0, 2)
    _require_range("direction", direction, 0, 2)
    _require_range("arrow_type", arrow_type, 0, 6)
    text_default = "注释" if defaults else ""
    if isinstance(p.get("text_point"), (list, tuple, dict)):
        text_point = _as_point(p.get("text_point"))
    else:
        text_point = point_from_params(p, "text")
    return [
        point_from_params(p, "arrow"),
        text_point,
        _as_str(p.get("text"), text_default),
        _as_bool_int(p.get("has_leader"), 1 if defaults else 0),
        justification,
        _as_float(p.get("text_height"), 3.5 if defaults else 0.0),
        h_align,
        direction,
        arrow_type,
    ]


def parse_note_slots(slots) -> dict:
    slots = list(slots or [])
    slots.extend([None] * (9 - len(slots)))
    return {
        "arrow": _as_point(slots[0]),
        "text_point": _as_point(slots[1]),
        "text": _as_str(slots[2]),
        "has_leader": bool(_as_int(slots[3])),
        "leader_justification": _as_int(slots[4]),
        "text_height": _as_float(slots[5]),
        "text_h_align": _as_int(slots[6]),
        "direction": _as_int(slots[7]),
        "arrow_type": _as_int(slots[8]),
    }


def _note_params_from_parsed(parsed: dict) -> dict:
    """Keep annotation string and text_point as separate fields for rebuild."""
    out = dict(parsed)
    point = parsed.get("text_point")
    if point and "text_x" not in out:
        out["text_x"], out["text_y"], out["text_z"] = point
    return out


# ---------------------------------------------------------------------------
# Welding
# ---------------------------------------------------------------------------

def build_weld_slots(params, defaults=True) -> list:
    p = params or {}
    direction = _as_int(p.get("direction"), 0)
    text_align = _as_int(p.get("text_align"), 0)
    _require_range("direction", direction, 0, 2)
    _require_range("text_align", text_align, 0, 2)
    sub_default = "GB_2008" if defaults else ""
    slots = [
        point_from_params(p, "arrow"),
        point_from_params(p, "symbol"),
        _as_str(p.get("sub_std"), sub_default),
        _as_int(p.get("symbol_type"), 48 if defaults else 0),
        _as_bool_int(p.get("has_leader"), 1 if defaults else 0),
        direction,
        _as_float(p.get("angle"), 0.0),
        text_align,
    ]
    slots.extend(_flatten_extra(p.get("extra")))
    return slots


def parse_weld_slots(slots) -> dict:
    slots = list(slots or [])
    while len(slots) < 8:
        slots.append(None)
    return {
        "arrow": _as_point(slots[0]),
        "symbol": _as_point(slots[1]),
        "sub_std": _as_str(slots[2]),
        "symbol_type": _as_int(slots[3]),
        "has_leader": bool(_as_int(slots[4])),
        "direction": _as_int(slots[5]),
        "angle": _as_float(slots[6]),
        "text_align": _as_int(slots[7]),
        "extra": _parse_extra(slots[8:]),
    }


# ---------------------------------------------------------------------------
# Shared insert/get/set
# ---------------------------------------------------------------------------

BUILDERS = {
    "surf_sym": lambda p, defaults=True: build_surf_slots(p, defaults=defaults),
    "fc_frame": lambda p, defaults=True: build_fc_slots(p, defaults=defaults, full=not defaults),
    "datum_id": lambda p, defaults=True: build_datum_slots(p, defaults=defaults),
    "note": lambda p, defaults=True: build_note_slots(p, defaults=defaults),
    "welding": lambda p, defaults=True: build_weld_slots(p, defaults=defaults),
}
PARSERS = {
    "surf_sym": parse_surf_slots,
    "fc_frame": parse_fc_slots,
    "datum_id": parse_datum_slots,
    "note": parse_note_slots,
    "welding": parse_weld_slots,
}


def _params_for_rebuild(kind, parsed: dict) -> dict:
    if kind == "note":
        return _note_params_from_parsed(parsed)
    return parsed


def merge_symbol_params(kind, current: dict, updates: dict) -> dict:
    updates = dict(updates or {})
    updates.pop("handle", None)
    updates.pop("msg", None)
    merged = dict(current or {})
    if kind == "fc_frame" and "layers" in updates and updates["layers"] is not None:
        new_layers = [_normalize_layer(layer) for layer in (merged.get("layers") or [])]
        for i, layer in enumerate(updates["layers"]):
            layer = layer or {}
            if i < len(new_layers):
                base = dict(new_layers[i])
                if "characteristic" in layer:
                    base["characteristic"] = _require_range(
                        "characteristic", _as_int(layer["characteristic"]), 0, 15
                    )
                if "tol1" in layer:
                    base["tol1"] = _as_str(layer["tol1"])
                if "tol2" in layer:
                    base["tol2"] = _as_str(layer["tol2"])
                if "datums" in layer:
                    datums = list(base.get("datums") or ["", "", ""])
                    while len(datums) < 3:
                        datums.append("")
                    for j, item in enumerate(layer.get("datums") or []):
                        if j < 3:
                            datums[j] = str(item)
                    base["datums"] = datums[:3]
                new_layers[i] = base
            else:
                new_layers.append(_normalize_layer(layer))
        merged["layers"] = new_layers
        updates = {k: v for k, v in updates.items() if k != "layers"}
        if "layer_count" not in updates:
            merged["layer_count"] = max(_as_int(merged.get("layer_count"), 1), len(new_layers))
    if kind == "welding" and "extra" in updates:
        merged["extra"] = {**(merged.get("extra") or {}), **(updates.get("extra") or {})}
        updates = {k: v for k, v in updates.items() if k != "extra"}
    merged.update(updates)
    return merged


def _new_handles(doc, old_count: int) -> list:
    return wait_new_handles(doc, old_count, timeout=0.3)


def _do_insert(kind, params, doc) -> dict:
    slots = BUILDERS[kind](params, defaults=True)
    insert_expr = f"({INSERT_FN[kind]} {to_lisp(slots)})"
    old_count = model_count(doc)
    send_lisp(doc, insert_expr)
    handles = _new_handles(doc, old_count)
    data = PARSERS[kind](slots)
    if handles:
        data["handle"] = handles[-1]
        data["handles"] = handles
    data["msg"] = f"成功插入{LABELS[kind]}"
    data["command"] = insert_expr
    return data


def _do_get(kind, params, doc) -> dict:
    handle = _require_handle(params)
    expr = f"({GET_FN[kind]} {to_lisp(LispHandle(handle))})"
    raw = eval_lisp(doc, expr)
    if raw is None:
        raise LispBridgeError(f"查询{LABELS[kind]}失败，返回为空")
    if not isinstance(raw, list):
        raise LispBridgeError(f"查询{LABELS[kind]}返回了非列表: {raw!r}")
    data = PARSERS[kind](raw)
    data["handle"] = handle
    data["msg"] = f"成功查询{LABELS[kind]}"
    return data


def _do_set(kind, params, doc) -> dict:
    handle = _require_handle(params)
    current = _do_get(kind, {"handle": handle}, doc)
    current.pop("msg", None)
    merged = merge_symbol_params(kind, current, params)
    rebuild = _params_for_rebuild(kind, merged)
    slots = BUILDERS[kind](rebuild, defaults=False)
    expr = f"({SET_FN[kind]} {to_lisp([LispHandle(handle), *slots])})"
    send_lisp(doc, expr)
    data = PARSERS[kind](slots)
    data["handle"] = handle
    data["msg"] = f"成功修改{LABELS[kind]}"
    data["command"] = expr
    return data


# ---------------------------------------------------------------------------
# Bubble
# ---------------------------------------------------------------------------

def _bubble_handles(params) -> list:
    params = params or {}
    handles = params.get("handles")
    if handles is None and params.get("handle"):
        handles = [params["handle"]]
    if not handles:
        return []
    return [LispHandle(h) for h in handles]


def build_bubble_auto_slots(params) -> list:
    p = params or {}
    handles = _bubble_handles(p)
    scope = _as_int(p.get("scope"), 1 if handles else 0)
    if scope not in (0, 1):
        raise SymbolError(f"scope 必须为 0 或 1，当前值: {scope}")
    if scope == 1 and not handles:
        raise SymbolError("scope=1 时必须提供 params.handles")
    bubble_type = _as_int(p.get("bubble_type"), 0)
    bubble_order = _as_int(p.get("bubble_order"), 1)
    location = _as_int(p.get("location_method"), -1)
    _require_range("bubble_type", bubble_type, 0, 8)
    _require_range("bubble_order", bubble_order, 0, 2)
    if location not in LOCATION_METHODS:
        raise SymbolError(f"location_method 必须为 -1 或 0/45/.../315，当前值: {location}")
    id_list = handles if scope == 1 else []
    return [
        scope,
        id_list,
        _as_str(p.get("sub_std")),
        _as_str(p.get("process_name")),
        _as_str(p.get("bubble_text")),
        _as_str(p.get("prefix")),
        _as_str(p.get("suffix")),
        bubble_type,
        _as_bool_int(p.get("is_insert"), 0),
        bubble_order,
        location,
        _as_bool_int(p.get("has_leader"), 1),
        _as_bool_int(p.get("filter_duplicate"), 1),
        0,  # retMode: always return ename/handle list
    ]


def build_bubble_manu_slots(params, include_retmode=True) -> list:
    p = params or {}
    attached = p.get("handle") or p.get("id_attached")
    points = p.get("points") or []
    has_leader = _as_bool_int(p.get("has_leader"), 1)
    if has_leader and len(points) < 2:
        raise SymbolError("带引线的手动气泡至少需要 2 个点（箭头 + 符号基点）")
    if not has_leader and len(points) < 1:
        raise SymbolError("无引线的手动气泡至少需要 1 个点")
    bubble_type = _as_int(p.get("bubble_type"), 0)
    _require_range("bubble_type", bubble_type, 0, 8)
    slots = [LispHandle(attached) if attached else None]
    for pt in points:
        slots.append(_as_point(pt))
    slots.extend([
        _as_str(p.get("sub_std")),
        _as_str(p.get("process_name")),
        _as_str(p.get("bubble_text")),
        _as_str(p.get("prefix")),
        _as_str(p.get("suffix")),
        bubble_type,
        has_leader,
        _as_bool_int(p.get("b3d"), 0),
        _as_int(p.get("leader_style"), 0),
        _as_bool_int(p.get("is_insert"), 0),
    ])
    if include_retmode:
        slots.append(0)
    return slots


def _bubble_create(doc, expr: str) -> list:
    old_count = model_count(doc)
    send_lisp(doc, expr)
    return _new_handles(doc, old_count)


def _bubble_auto_common_params(params) -> dict:
    """Params shared by auto / fill_all (excludes scope, handles, enumeration)."""
    p = params or {}
    skip = {
        "handles", "handle", "scope", "limit", "exclude_handles",
        "entity_types", "layer", "stop_on_error",
    }
    return {k: v for k, v in p.items() if k not in skip}


def _do_bubble_auto(params, doc) -> dict:
    slots = build_bubble_auto_slots(params)
    expr = f"(Zwm_BubbleAuto {to_lisp(slots)})"
    handles = _bubble_create(doc, expr)
    return {
        "handles": handles,
        "count": len(handles),
        "command": expr,
        "msg": f"已发送气泡图自动创建命令，检测到 {len(handles)} 个新实体",
    }


def _bubble_target_dxf_filter(params) -> str:
    p = params or {}
    types = p.get("entity_types")
    if not types:
        return BUBBLE_TARGET_DXF_TYPES
    if isinstance(types, (list, tuple)):
        return ",".join(str(t).strip().upper() for t in types if str(t).strip())
    return str(types).strip().upper()


def _bubble_target_type_literals(params) -> str:
    """AutoLISP list of supported DXF type names (uppercase strings)."""
    dxf0 = _bubble_target_dxf_filter(params)
    return to_lisp([t.strip() for t in dxf0.split(",") if t.strip()])


def _parse_handle_list(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(h) for h in raw if h is not None and str(h).strip()]
    return [str(raw)]


def _bubble_ssget_filter_expr(params) -> str:
    dxf0 = _bubble_target_dxf_filter(params)
    layer = _as_str((params or {}).get("layer"), "")
    if layer:
        return f"(list (cons 0 {to_lisp(dxf0)}) (cons 8 {to_lisp(layer)}))"
    return f"(list (cons 0 {to_lisp(dxf0)}))"


def _list_bubble_handles_lisp_slice(
    doc,
    ss_mode: str,
    filter_expr: str | None,
    start: int,
    limit: int,
    *,
    types_lisp: str | None = None,
) -> list:
    start = max(0, int(start))
    limit = max(1, int(limit))
    if types_lisp is not None:
        ss_line = '(setq __ss (ssget "I"))'
        body = (
            "(setq __ent (entget __e)) "
            "(setq __t (strcase (cdr (assoc 0 __ent)))) "
            "(if (member __t (mapcar 'strcase __types)) "
            "(progn (setq __h (cdr (assoc 5 __ent))) (if __h (setq __out (cons __h __out))))) "
        )
        header = f"(setq __types {types_lisp}) "
    else:
        ss_line = f'(setq __ss (ssget "{ss_mode}" {filter_expr}))'
        body = (
            "(setq __h (cdr (assoc 5 (entget __e)))) "
            "(if __h (setq __out (cons __h __out))) "
        )
        header = ""
    expr = (
        f"(progn {ss_line} "
        "(setq __out ()) "
        f"(setq __start {start}) "
        f"(setq __lim {limit}) "
        f"{header}"
        "(if __ss (progn "
        "(setq __n (sslength __ss)) "
        "(setq __i __start) "
        "(setq __end (min (+ __start __lim) __n)) "
        "(while (< __i __end) "
        "(setq __e (ssname __ss __i)) "
        f"{body}"
        "(setq __i (1+ __i))))) "
        "(reverse __out))"
    )
    return _parse_handle_list(eval_lisp(doc, expr))


def _list_bubble_targets_chunked(
    doc,
    params,
    *,
    ss_mode: str,
    filter_expr: str | None = None,
    types_lisp: str | None = None,
) -> list:
    chunk = BUBBLE_TARGET_ENUM_CHUNK
    start = 0
    out = []
    while True:
        batch = _list_bubble_handles_lisp_slice(
            doc,
            ss_mode,
            filter_expr,
            start,
            chunk,
            types_lisp=types_lisp,
        )
        if not batch:
            break
        out.extend(batch)
        if len(batch) < chunk:
            break
        start += chunk
    return out


def _list_bubble_targets_from_pickfirst(doc, params) -> list:
    types_lisp = _bubble_target_type_literals(params)
    return _list_bubble_targets_chunked(
        doc, params, ss_mode="I", types_lisp=types_lisp
    )


def _list_bubble_targets_via_lisp(doc, params) -> list:
    filter_expr = _bubble_ssget_filter_expr(params)
    return _list_bubble_targets_chunked(
        doc, params, ss_mode="X", filter_expr=filter_expr
    )


def _resolve_bubble_fill_targets(params, doc, *, from_pickfirst: bool = False) -> list:
    p = params or {}
    explicit = p.get("handles")
    if from_pickfirst:
        targets = _list_bubble_targets_from_pickfirst(doc, p)
    elif explicit is not None:
        targets = [str(h).strip() for h in explicit if str(h).strip()]
    else:
        targets = _list_bubble_targets_via_lisp(doc, p)
    exclude = p.get("exclude_handles") or []
    if exclude:
        blocked = {str(h).strip() for h in exclude if str(h).strip()}
        targets = [h for h in targets if h not in blocked]
    limit = p.get("limit")
    if limit is not None and str(limit).strip() != "":
        targets = targets[: max(0, _as_int(limit, 0))]
    return targets


def _do_bubble_fill_picked(params, doc) -> dict:
    targets = _resolve_bubble_fill_targets(params, doc, from_pickfirst=True)
    if not targets:
        return {
            "handles": [],
            "count": 0,
            "targets": 0,
            "errors": [],
            "msg": (
                "当前选择集中没有可建气泡的对象（需尺寸、粗糙度、形位公差、基准、"
                "引线注释、焊接等；块内分解的直线/文字不可直接标注）"
            ),
        }
    return _do_bubble_fill_on_targets(targets, params, doc)


def _do_bubble_fill_all(params, doc) -> dict:
    targets = _resolve_bubble_fill_targets(params, doc)
    if not targets:
        return {
            "handles": [],
            "count": 0,
            "targets": 0,
            "errors": [],
            "msg": "未找到可标注对象（可传 params.handles 或检查图层/类型过滤）",
        }
    return _do_bubble_fill_on_targets(targets, params, doc)


def _do_bubble_fill_on_targets(targets: list, params, doc) -> dict:
    base = _bubble_auto_common_params(params)
    if "filter_duplicate" not in base:
        base["filter_duplicate"] = False
    created = []
    errors = []
    stop = _as_bool_int((params or {}).get("stop_on_error"), 0)
    for handle in targets:
        try:
            one = dict(base)
            one["scope"] = 1
            one["handles"] = [handle]
            result = _do_bubble_auto(one, doc)
            created.extend(result.get("handles") or [])
        except (SymbolError, LispBridgeError) as exc:
            errors.append({"handle": handle, "error": str(exc)})
            if stop:
                break
        except Exception as exc:
            errors.append({"handle": handle, "error": str(exc)})
            if stop:
                break
    msg = f"已对 {len(targets)} 个对象逐个自动标注，新建 {len(created)} 个气泡"
    if errors:
        msg += f"，{len(errors)} 个失败"
    return {
        "handles": created,
        "count": len(created),
        "targets": len(targets),
        "errors": errors,
        "msg": msg,
    }


def _do_bubble_manu(params, doc) -> dict:
    slots = build_bubble_manu_slots(params, include_retmode=True)
    expr = f"(Zwm_BubbleManu {to_lisp(slots)})"
    handles = _bubble_create(doc, expr)
    result = {
        "handles": handles,
        "count": len(handles),
        "command": expr,
        "msg": "已发送气泡图手动创建命令",
    }
    if len(handles) == 1:
        result["handle"] = handles[0]
    return result


def _do_bubble_manu_list(params, doc) -> dict:
    items = (params or {}).get("items") or []
    if not items:
        raise SymbolError("manu_list 需要 params.items 非空列表")
    sublists = [build_bubble_manu_slots(item, include_retmode=False) for item in items]
    expr = f"(Zwm_BubbleManuList {to_lisp(sublists)})"
    handles = _bubble_create(doc, expr)
    return {
        "handles": handles,
        "count": len(handles),
        "command": expr,
        "msg": f"已发送气泡图批量创建命令，检测到 {len(handles)} 个新实体",
    }


def _do_bubble_substd(doc) -> dict:
    raw = eval_lisp(doc, "(Zwm_BubbleSubStdGet)")
    name = "" if raw is None or raw is True else str(raw)
    return {
        "sub_std": name,
        "msg": f"当前气泡子标准: {name or '(默认)'}",
    }


def dispatch_bubble(action: str, params, doc) -> dict:
    action = (action or "").strip().lower()
    if action not in BUBBLE_ACTIONS:
        raise SymbolError(f"不支持的气泡图操作: {action}，可选: {', '.join(sorted(BUBBLE_ACTIONS))}")
    if action == "auto":
        return _do_bubble_auto(params, doc)
    if action == "fill_all":
        return _do_bubble_fill_all(params, doc)
    if action == "fill_picked":
        return _do_bubble_fill_picked(params, doc)
    if action == "manu":
        return _do_bubble_manu(params, doc)
    if action == "manu_list":
        return _do_bubble_manu_list(params, doc)
    return _do_bubble_substd(doc)


def dispatch(kind: str, action: str, params, doc) -> dict:
    kind = (kind or "").strip().lower()
    action = (action or "").strip().lower()
    if kind == "bubble":
        return dispatch_bubble(action, params, doc)
    if kind not in BUILDERS:
        raise SymbolError(f"不支持的符号类型: {kind}")
    if action not in SYMBOL_ACTIONS:
        raise SymbolError(f"不支持的操作: {action}，可选: insert|get|set")
    if action == "insert":
        return _do_insert(kind, params, doc)
    if action == "get":
        return _do_get(kind, params, doc)
    return _do_set(kind, params, doc)

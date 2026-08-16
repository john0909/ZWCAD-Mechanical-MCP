"""剖面线(Hatch)边界环提取工具。

COM GetLoopAt 的 [out] 参数在部分 ZWCAD 版本的类型库中声明缺失，
comtypes 无法封送，调用返回 None。回退方案: 通过 SendCommand 执行 LISP，
将 (entget) 数据整体写入临时文件回传 Python 解析，读后即删，
无长度上限，不占用系统变量等用户可见状态。
"""

import logging
import os
import re
import tempfile
import time

logger = logging.getLogger(__name__)

_END_MARK = "|END"
_POLL_TIMEOUT = 5.0


def _entity_geometry(ent, oname):
    """从边界实体提取几何信息，返回 dict。"""
    be = {"type": oname}
    try:
        be["handle"] = ent.Handle
    except Exception:
        pass
    try:
        be["layer"] = ent.Layer
    except Exception:
        pass
    try:
        be["closed"] = bool(ent.Closed)
    except Exception:
        pass
    try:
        coords = list(ent.Coordinates)
        if oname == "AcDbPolyline" or "LWPolyline" in oname:
            step = 2
        elif "Polyline" in oname:
            step = 3
        else:
            step = 2 if len(coords) % 2 == 0 else 3
        if step == 2:
            pts = [[round(coords[k], 6), round(coords[k + 1], 6)]
                   for k in range(0, len(coords) - 1, step)]
        else:
            pts = [[round(coords[k], 6), round(coords[k + 1], 6), round(coords[k + 2], 6)]
                   for k in range(0, len(coords) - 2, step)]
        be["vertices"] = pts
        be["vertex_count"] = len(pts)
    except Exception:
        pass
    try:
        bulges = []
        for k in range(be.get("vertex_count", 0)):
            bulges.append(round(ent.GetBulge(k), 6))
        if any(b != 0 for b in bulges):
            be["bulges"] = bulges
    except Exception:
        pass
    if oname == "AcDbLine":
        try:
            be["start"] = [round(x, 6) for x in ent.StartPoint]
            be["end"] = [round(x, 6) for x in ent.EndPoint]
        except Exception:
            pass
    elif oname == "AcDbArc":
        try:
            be["center"] = [round(x, 6) for x in ent.Center]
            be["radius"] = round(ent.Radius, 6)
            be["start_angle"] = round(ent.StartAngle, 6)
            be["end_angle"] = round(ent.EndAngle, 6)
        except Exception:
            pass
    elif oname == "AcDbCircle":
        try:
            be["center"] = [round(x, 6) for x in ent.Center]
            be["radius"] = round(ent.Radius, 6)
        except Exception:
            pass
    elif oname == "AcDbEllipse":
        try:
            be["center"] = [round(x, 6) for x in ent.Center]
            be["major_axis"] = [round(x, 6) for x in ent.MajorAxis]
            be["radius_ratio"] = round(ent.RadiusRatio, 6)
        except Exception:
            pass
    return be


def _extract_via_com(obj):
    """COM 路径: GetBestInterface + GetLoopAt。

    返回 (loops, com_ok)。GetLoopAt 有 [out] 参数，动态派发无法处理，
    需提升为类型化 IZcadHatch 接口。
    """
    loops = []
    com_ok = False
    try:
        import comtypes.client

        try:
            typed = comtypes.client.GetBestInterface(obj)
        except Exception:
            typed = None
        if typed is not None:
            try:
                num_loops = typed.NumberOfLoops
            except Exception:
                num_loops = 0
            for i in range(num_loops):
                loop_data = {"loop_index": i}
                try:
                    result = typed.GetLoopAt(i)
                    if not isinstance(result, tuple):
                        continue
                    entities = []
                    for item in result:
                        if item is None:
                            continue
                        try:
                            ent = comtypes.client.GetBestInterface(item)
                        except Exception:
                            continue
                        entities.append(_entity_geometry(ent, ent.ObjectName))
                    if entities:
                        loop_data["boundary_entities"] = entities
                except Exception as e:
                    loop_data["error"] = str(e)
                loops.append(loop_data)
            com_ok = any("boundary_entities" in ld for ld in loops)
    except Exception:
        pass
    return loops, com_ok


def _extract_via_lisp(zcad_conn, handle):
    """LISP 回退: (entget (handent ...)) 转储串写入临时文件回传。

    返回与 _extract_via_com 一致的 loops 结构，失败返回 None。
    """
    doc = zcad_conn.doc
    safe = re.sub(r"[^0-9A-Za-z]", "", handle or "") or "unknown"
    path = os.path.join(
        tempfile.gettempdir(),
        "zwm_hatch_%d_%s_%d.tmp" % (os.getpid(), safe, time.time_ns()),
    )
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    lisp_path = path.replace("\\", "/")
    lisp = (
        '(progn (setq al (entget (handent "%s")))'
        ' (setq s (apply (function strcat)'
        '   (mapcar (function (lambda (x) (strcat (vl-prin1-to-string x) "|"))) al)))'
        ' (setq s (strcat s "%s"))'
        ' (setq f (open "%s" "w"))'
        ' (write-line s f) (close f))'
    ) % (handle, _END_MARK, lisp_path)

    try:
        doc.SendCommand("\x03\x03" + lisp + "\r")

        content = ""
        deadline = time.time() + _POLL_TIMEOUT
        while time.time() < deadline:
            if os.path.exists(path):
                try:
                    with open(path, encoding="mbcs", errors="replace") as fh:
                        content = fh.read()
                except (OSError, ValueError):
                    content = ""
                if content.rstrip().endswith(_END_MARK):
                    break
            time.sleep(0.1)
        else:
            logger.warning("LISP 提取剖面线边界环超时(handle=%s)", handle)
            return None

        content = content.rstrip()
        if content.endswith(_END_MARK):
            content = content[: -len(_END_MARK)]
        if not content.strip():
            return None

        loops = _parse_loop_groups(_parse_dump_groups(content))
        return loops or None
    except Exception as e:
        logger.warning("LISP 提取剖面线边界环失败(handle=%s): %s", handle, e)
        return None
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _parse_dump_groups(content):
    """解析 LISP 回传的 "(组码 . 值)|(组码 v1 v2 ...)|" 转储串，返回 (组码, 值列表) 流。"""
    groups = []
    for m in re.finditer(r"\(\s*(-?\d+)\s+(.*?)\)", content):
        code = int(m.group(1))
        rest = m.group(2).strip()
        if rest.startswith("."):
            values = [rest[1:].strip()]
        else:
            values = rest.split()
        groups.append((code, values))
    return groups


def _parse_loop_groups(groups):
    """解析 HATCH entget 的 (组码, 值) 流，重建边界环结构。

    环类型 92: 1/3=显式边(直线/圆弧), 2/7=多段线路径。
    多段线路径: 72=是否有凸度, 73=是否闭合, 93=顶点数, 10=顶点, 42=凸度。
    显式边: 每条边以 72 开头(1=直线 10起点/11终点, 2=圆弧 10圆心/40半径/50/51起止角)。
    """
    loops = []
    pos = 0
    n = len(groups)
    while pos < n:
        code, vals = groups[pos]
        if code == 92:
            loop_type = int(vals[0])
            pos += 1
            has_bulge = 0
            is_closed = 1
            if loop_type in (2, 7):
                while pos < n and groups[pos][0] in (72, 73):
                    c, v = groups[pos]
                    pos += 1
                    if c == 72:
                        has_bulge = int(v[0])
                    elif c == 73:
                        is_closed = int(v[0])
            edge_count = 0
            if pos < n and groups[pos][0] == 93:
                edge_count = int(groups[pos][1][0])
                pos += 1
            loop_data = {"loop_index": len(loops)}
            entities = []
            if loop_type in (2, 7):
                vertices = []
                while pos < n and groups[pos][0] == 10 and len(vertices) < edge_count:
                    pts = [float(x) for x in groups[pos][1]]
                    pos += 1
                    vertices.append(pts[:2])
                bulges = []
                if has_bulge:
                    while pos < n and groups[pos][0] == 42 and len(bulges) < edge_count:
                        bulges.append(float(groups[pos][1][0]))
                        pos += 1
                ent = {
                    "type": "AcDbPolyline",
                    "closed": bool(is_closed),
                    "vertices": [[round(x, 6), round(y, 6)] for x, y in vertices],
                    "vertex_count": len(vertices),
                }
                if bulges:
                    ent["bulges"] = [round(b, 6) for b in bulges]
                entities.append(ent)
            elif loop_type in (1, 3):
                while pos < n and groups[pos][0] == 72:
                    edge_type = int(groups[pos][1][0])
                    pos += 1
                    if edge_type == 1:
                        start = end = None
                        while pos < n and groups[pos][0] in (10, 11):
                            c, v = groups[pos]
                            pos += 1
                            if c == 10:
                                start = v
                            elif c == 11:
                                end = v
                        if start is not None:
                            ent = {"type": "AcDbLine"}
                            ent["start"] = [round(float(x), 6) for x in start]
                            ent["end"] = [round(float(x), 6) for x in (end or start)]
                            entities.append(ent)
                    elif edge_type == 2:
                        center = radius = sa = ea = None
                        while pos < n and groups[pos][0] in (10, 40, 50, 51, 73):
                            c, v = groups[pos]
                            pos += 1
                            if c == 10:
                                center = v
                            elif c == 40:
                                radius = float(v[0])
                            elif c == 50:
                                sa = float(v[0])
                            elif c == 51:
                                ea = float(v[0])
                        if center is not None:
                            ent = {"type": "AcDbArc",
                                   "center": [round(float(x), 6) for x in center]}
                            if radius is not None:
                                ent["radius"] = round(radius, 6)
                            if sa is not None:
                                ent["start_angle"] = round(sa, 6)
                            if ea is not None:
                                ent["end_angle"] = round(ea, 6)
                            entities.append(ent)
                    else:
                        while pos < n and groups[pos][0] not in (72, 97):
                            pos += 1
            if entities:
                loop_data["boundary_entities"] = entities
            loops.append(loop_data)
            if pos < n and groups[pos][0] == 97:
                pos += 1
        elif code in (75, 76, 98):
            break
        else:
            pos += 1
    return loops


def extract_hatch_loops(obj, zcad_conn=None, handle=None):
    """提取剖面线边界环数据。

    COM GetLoopAt 失败时回退 LISP(临时文件通道)。
    返回 [{"loop_index", "boundary_entities": [...]}]。
    """
    loops, com_ok = _extract_via_com(obj)
    if not com_ok and zcad_conn is not None and handle:
        lisp_loops = _extract_via_lisp(zcad_conn, handle)
        if lisp_loops is not None:
            loops = lisp_loops
    return loops

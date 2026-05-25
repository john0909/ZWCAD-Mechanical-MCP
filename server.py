"""
ZWCAD Mechanical MCP Server - 基于 FastMCP 的中望机械CAD自动化服务
提供画直线、画圆、画弧、画椭圆、多段线、样条曲线、标注、图块、图层、
标题栏编辑、图框切换、明细表操作等功能

优化版：100 个工具合并为 ~28 个，减少 LLM 上下文占用
"""

from fastmcp import FastMCP
from pyzwcad import ZwCAD, APoint
from pyzwcad.types import aDouble, aInt
from pyzwcadmech import ZwCADMech
import json
import math
import sys
import pythoncom
import xml.etree.ElementTree as ET
import os
import logging

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

try:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
except Exception:
    pass

mcp = FastMCP(name="ZWCAD Mechanical Drawing Server")

STYLES_BASE_PATH = r"C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles"

def _parse_xml_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"XML 文件不存在: {file_path}")
    tree = ET.parse(file_path)
    return tree.getroot()


def _get_default_standard():
    xml_path = os.path.join(STYLES_BASE_PATH, "standard.xml")
    root = _parse_xml_file(xml_path)
    for standard in root.findall('Standard'):
        if standard.get('Default') == '1':
            return standard.get('Name')
    first = root.find('Standard')
    return first.get('Name') if first is not None else "GB"


def _get_title_styles(standard_name):
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "TitleStyles.xml")
    root = _parse_xml_file(xml_path)
    styles = []
    default_style = None
    for style in root.iter():
        if style.tag.endswith('TitleStyle') or style.tag == 'TitleStyle':
            name = style.get('Name')
            if name:
                is_default = style.get('Default') == '1'
                styles.append(name)
                if is_default:
                    default_style = name
    return styles, default_style or (styles[0] if styles else None)


def _get_bom_styles(standard_name):
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "BomStyles.xml")
    root = _parse_xml_file(xml_path)
    styles = []
    default_style = None
    for style in root.iter():
        if style.tag.endswith('BomStyle') or style.tag == 'BomStyle':
            name = style.get('Name')
            if name:
                is_default = style.get('Default') == '1'
                styles.append(name)
                if is_default:
                    default_style = name
    return styles, default_style or (styles[0] if styles else None)


def _get_frame_styles(standard_name, frame_size, orientation):
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "FrameStyles.xml")
    root = _parse_xml_file(xml_path)
    for frame_size_elem in root.findall('.//FrameSize'):
        if frame_size_elem.get('Name') == frame_size:
            for style in frame_size_elem.findall('.//FrameStyle'):
                if style.get('Orientation') == orientation:
                    return style.get('Name')
    return "分区图框"


def _get_default_frame_size(standard_name):
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "FrameStyles.xml")
    root = _parse_xml_file(xml_path)
    for frame_size_elem in root.iter():
        if frame_size_elem.tag.endswith('FrameSize') or frame_size_elem.tag == 'FrameSize':
            if frame_size_elem.get('Default') == '1':
                return frame_size_elem.get('Name')
    for frame_size_elem in root.iter():
        if frame_size_elem.tag.endswith('FrameSize') or frame_size_elem.tag == 'FrameSize':
            return frame_size_elem.get('Name')
    return "A3"


def get_cad_connection():
    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    except Exception:
        pass
    zcad_conn = ZwCAD()
    mech_conn = ZwCADMech()
    return zcad_conn, mech_conn


def _ok(message: str, **data) -> str:
    result = {"ok": True, "message": message}
    result.update(data)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _err(action: str, e: Exception) -> str:
    err_str = str(e)
    error_code = "COM_INIT_ERROR" if ("CoInitialize" in err_str or "-2147221008" in err_str) else "OPERATION_ERROR"
    msg = f"{action}失败: {err_str}"
    result = {"ok": False, "error": msg, "error_code": error_code}
    if error_code == "COM_INIT_ERROR":
        result["hint"] = (
            "1. 确保 中望机械 2026 已启动并运行; "
            "2. 重启 ZWCAD 和 MCP Server; "
            "3. 检查 pywin32 和 comtypes 库"
        )
    return json.dumps(result, ensure_ascii=False, indent=2)


def _find_entity(zcad_conn, object_type: str = None,
                 property_name: str = None, property_value: str = None,
                 handle: str = None, predicate=None):
    if handle:
        try:
            return zcad_conn.doc.HandleToObject(handle)
        except Exception:
            return None
    if predicate:
        return zcad_conn.find_one(object_type, predicate=predicate)
    if property_name and property_value is not None:
        def _prop_pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        return zcad_conn.find_one(object_type, predicate=_prop_pred)
    return None


def _flatten_points(vertices):
    flat = []
    for v in vertices:
        if isinstance(v, (list, tuple)):
            flat.extend(v)
        else:
            flat.append(v)
    return flat


# ============================================================
# 2D 绘图内部实现
# ============================================================

def _draw_line(model, p, layer):
    p1 = APoint(p["x1"], p["y1"], p.get("z1", 0))
    p2 = APoint(p["x2"], p["y2"], p.get("z2", 0))
    obj = model.AddLine(p1, p2)
    obj.Layer = layer
    return obj, f"直线: ({p['x1']},{p['y1']}) -> ({p['x2']},{p['y2']})"


def _draw_circle(model, p, layer):
    c = APoint(p["center_x"], p["center_y"], p.get("center_z", 0))
    obj = model.AddCircle(c, p["radius"])
    obj.Layer = layer
    return obj, f"圆: 圆心({p['center_x']},{p['center_y']}), r={p['radius']}"


def _draw_arc(model, p, layer):
    c = APoint(p["center_x"], p["center_y"], p.get("center_z", 0))
    obj = model.AddArc(c, p["radius"], p["start_angle"], p["end_angle"])
    obj.Layer = layer
    return obj, f"圆弧: 圆心({p['center_x']},{p['center_y']}), r={p['radius']}"


def _draw_ellipse(model, p, layer):
    c = APoint(p["center_x"], p["center_y"], p.get("center_z", 0))
    major = APoint(p["major_axis_x"], p["major_axis_y"], p.get("major_axis_z", 0))
    obj = model.AddEllipse(c, major, p["radius_ratio"])
    obj.Layer = layer
    return obj, "椭圆"


def _draw_lwpolyline(model, p, layer):
    flat = _flatten_points(p["vertices"])
    coords = aDouble(*flat)
    obj = model.AddLightWeightPolyline(coords)
    obj.Layer = layer
    if p.get("closed"):
        obj.Closed = True
    return obj, f"轻量多段线: {len(flat)//2}个顶点"


def _draw_polyline(model, p, layer):
    flat = _flatten_points(p["vertices"])
    coords = aDouble(*flat)
    obj = model.AddPolyline(coords)
    obj.Layer = layer
    if p.get("closed"):
        obj.Closed = True
    return obj, f"多段线: {len(flat)//3}个顶点"


def _draw_spline(model, p, layer):
    flat = _flatten_points(p["fit_points"])
    coords = aDouble(*flat)
    st = APoint(p.get("start_tangent_x", 0), p.get("start_tangent_y", 0), p.get("start_tangent_z", 0))
    et = APoint(p.get("end_tangent_x", 0), p.get("end_tangent_y", 0), p.get("end_tangent_z", 0))
    obj = model.AddSpline(coords, st, et)
    obj.Layer = layer
    return obj, f"样条曲线: {len(flat)//3}个拟合点"


def _draw_point(model, p, layer):
    pt = APoint(p["x"], p["y"], p.get("z", 0))
    obj = model.AddPoint(pt)
    obj.Layer = layer
    return obj, f"点: ({p['x']},{p['y']})"


def _draw_ray(model, p, layer):
    p1 = APoint(p["x1"], p["y1"], p.get("z1", 0))
    p2 = APoint(p["x2"], p["y2"], p.get("z2", 0))
    obj = model.AddRay(p1, p2)
    obj.Layer = layer
    return obj, f"射线: 起点({p['x1']},{p['y1']})"


def _draw_xline(model, p, layer):
    p1 = APoint(p["x1"], p["y1"], p.get("z1", 0))
    p2 = APoint(p["x2"], p["y2"], p.get("z2", 0))
    obj = model.AddXline(p1, p2)
    obj.Layer = layer
    return obj, f"构造线: ({p['x1']},{p['y1']})-({p['x2']},{p['y2']})"


def _draw_mline(model, p, layer):
    flat = _flatten_points(p["vertices"])
    coords = aDouble(*flat)
    obj = model.AddMLine(coords)
    obj.Layer = layer
    return obj, f"多线: {len(flat)//3}个顶点"


def _draw_3d_polyline(model, p, layer):
    flat = _flatten_points(p["vertices"])
    coords = aDouble(*flat)
    obj = model.Add3DPoly(coords)
    obj.Layer = layer
    return obj, f"3D多段线: {len(flat)//3}个顶点"


_DRAW_DISPATCH = {
    "line": _draw_line, "circle": _draw_circle, "arc": _draw_arc,
    "ellipse": _draw_ellipse, "lwpolyline": _draw_lwpolyline,
    "polyline": _draw_polyline, "spline": _draw_spline, "point": _draw_point,
    "ray": _draw_ray, "xline": _draw_xline, "mline": _draw_mline,
    "3d_polyline": _draw_3d_polyline,
}


# ============================================================
# 3D 实体内部实现
# ============================================================

def _draw_3d_face(model, p, layer):
    p1 = APoint(p["x1"], p["y1"], p["z1"])
    p2 = APoint(p["x2"], p["y2"], p["z2"])
    p3 = APoint(p["x3"], p["y3"], p["z3"])
    p4 = APoint(p.get("x4", p["x3"]), p.get("y4", p["y3"]), p.get("z4", p["z3"]))
    obj = model.Add3DFace(p1, p2, p3, p4)
    obj.Layer = layer
    return obj, "3D面"


def _draw_box(model, p, layer):
    origin = APoint(p["origin_x"], p["origin_y"], p["origin_z"])
    obj = model.AddBox(origin, p["length"], p["width"], p["height"])
    obj.Layer = layer
    return obj, f"长方体: {p['length']}x{p['width']}x{p['height']}"


def _draw_cylinder(model, p, layer):
    center = APoint(p["center_x"], p["center_y"], p["center_z"])
    obj = model.AddCylinder(center, p["radius"], p["height"])
    obj.Layer = layer
    return obj, f"圆柱体: r={p['radius']}, h={p['height']}"


def _draw_cone(model, p, layer):
    center = APoint(p["center_x"], p["center_y"], p["center_z"])
    obj = model.AddCone(center, p["base_radius"], p["height"])
    obj.Layer = layer
    return obj, f"圆锥体: r={p['base_radius']}, h={p['height']}"


def _draw_sphere(model, p, layer):
    center = APoint(p["center_x"], p["center_y"], p["center_z"])
    obj = model.AddSphere(center, p["radius"])
    obj.Layer = layer
    return obj, f"球体: r={p['radius']}"


def _draw_torus(model, p, layer):
    center = APoint(p["center_x"], p["center_y"], p["center_z"])
    obj = model.AddTorus(center, p["torus_radius"], p["tube_radius"])
    obj.Layer = layer
    return obj, f"圆环体: R={p['torus_radius']}, r={p['tube_radius']}"


def _draw_wedge(model, p, layer):
    center = APoint(p["center_x"], p["center_y"], p["center_z"])
    obj = model.AddWedge(center, p["length"], p["width"], p["height"])
    obj.Layer = layer
    return obj, f"楔体: {p['length']}x{p['width']}x{p['height']}"


_3D_DISPATCH = {
    "3d_face": _draw_3d_face, "box": _draw_box, "cylinder": _draw_cylinder,
    "cone": _draw_cone, "sphere": _draw_sphere, "torus": _draw_torus,
    "wedge": _draw_wedge,
}


# ============================================================
# 标注内部实现
# ============================================================

def _dim_aligned(model, p, layer):
    p1 = APoint(p["x1"], p["y1"], p.get("z1", 0))
    p2 = APoint(p["x2"], p["y2"], p.get("z2", 0))
    tp = APoint(p["text_x"], p["text_y"], p.get("text_z", 0))
    obj = model.AddDimAligned(p1, p2, tp)
    obj.Layer = layer
    return obj, "对齐标注"


def _dim_rotated(model, p, layer):
    p1 = APoint(p["x1"], p["y1"], p.get("z1", 0))
    p2 = APoint(p["x2"], p["y2"], p.get("z2", 0))
    tp = APoint(p["text_x"], p["text_y"], p.get("text_z", 0))
    obj = model.AddDimRotated(p1, p2, tp, p["rotation_angle"])
    obj.Layer = layer
    return obj, "旋转标注"


def _dim_diametric(model, p, layer):
    c = APoint(p["chord_x"], p["chord_y"], p.get("chord_z", 0))
    fc = APoint(p["far_chord_x"], p["far_chord_y"], p.get("far_chord_z", 0))
    obj = model.AddDimDiametric(c, fc, p["leader_length"])
    obj.Layer = layer
    return obj, "直径标注"


def _dim_radial(model, p, layer):
    c = APoint(p["center_x"], p["center_y"], p.get("center_z", 0))
    ch = APoint(p["chord_x"], p["chord_y"], p.get("chord_z", 0))
    obj = model.AddDimRadial(c, ch, p["leader_length"])
    obj.Layer = layer
    return obj, "半径标注"


def _dim_angular(model, p, layer):
    v = APoint(p["vertex_x"], p["vertex_y"], p.get("vertex_z", 0))
    f = APoint(p["first_x"], p["first_y"], p.get("first_z", 0))
    s = APoint(p["second_x"], p["second_y"], p.get("second_z", 0))
    tp = APoint(p["text_x"], p["text_y"], p.get("text_z", 0))
    obj = model.AddDimAngular(v, f, s, tp)
    obj.Layer = layer
    return obj, "角度标注"


def _dim_ordinate(model, p, layer):
    d = APoint(p["def_x"], p["def_y"], p.get("def_z", 0))
    l = APoint(p["leader_x"], p["leader_y"], p.get("leader_z", 0))
    obj = model.AddDimOrdinate(d, l, p["use_x_axis"])
    obj.Layer = layer
    return obj, "坐标标注"


_DIM_DISPATCH = {
    "aligned": _dim_aligned, "rotated": _dim_rotated,
    "diametric": _dim_diametric, "radial": _dim_radial,
    "angular": _dim_angular, "ordinate": _dim_ordinate,
}


# ============================================================
# 注释内部实现
# ============================================================

def _anno_text(model, p, layer):
    pt = APoint(p["x"], p["y"], p.get("z", 0))
    obj = model.AddText(p["text"], pt, p.get("height", 2.5))
    obj.Layer = layer
    return obj, f"单行文本: '{p['text']}'"


def _anno_mtext(model, p, layer):
    pt = APoint(p["x"], p["y"], p.get("z", 0))
    w = p.get("width", 0)
    obj = model.AddMText(pt, w, p["text"])
    obj.Height = p.get("height", 2.5)
    obj.Layer = layer
    return obj, f"多行文本: '{p['text'][:20]}...'" if len(p.get("text", "")) > 20 else f"多行文本: '{p.get('text', '')}'"


def _anno_leader(model, p, layer):
    flat = _flatten_points(p["points"])
    coords = aDouble(*flat)
    obj = model.AddLeader(coords, None, p.get("annotation_type", 0))
    obj.Layer = layer
    return obj, f"引线: {len(flat)//3}个点"


def _anno_tolerance(model, p, layer):
    pt = APoint(p["x"], p["y"], p.get("z", 0))
    d = APoint(p.get("dir_x", 0), p.get("dir_y", 0), p.get("dir_z", 1))
    obj = model.AddTolerance(p["text"], pt, d)
    obj.Layer = layer
    return obj, f"形位公差: '{p['text']}'"


def _anno_mleader(model, p, layer):
    flat = _flatten_points(p["points"])
    coords = aDouble(*flat)
    obj = model.AddMLeader(coords)
    obj.Layer = layer
    if p.get("text"):
        obj.TextString = p["text"]
        obj.TextHeight = p.get("text_height", 2.5)
    return obj, f"多重引线: {len(flat)//3}个点"


def _anno_hatch(model, p, layer):
    obj = model.AddHatch(p.get("pattern_type", 0), p["pattern_name"], p.get("associativity", True))
    obj.Layer = layer
    obj.PatternScale = p.get("pattern_scale", 1.0)
    obj.PatternAngle = p.get("pattern_angle", 0)
    return obj, f"填充: 图案='{p['pattern_name']}'"


def _anno_table(model, p, layer):
    pt = APoint(p["x"], p["y"], p.get("z", 0))
    obj = model.AddTable(pt, p["rows"], p["cols"], p["row_height"], p["col_width"])
    obj.Layer = layer
    return obj, f"表格: {p['rows']}行x{p['cols']}列"


_ANNO_DISPATCH = {
    "text": _anno_text, "mtext": _anno_mtext, "leader": _anno_leader,
    "tolerance": _anno_tolerance, "mleader": _anno_mleader,
    "hatch": _anno_hatch, "table": _anno_table,
}


# ============================================================
# 变换内部实现
# ============================================================

def _transform_copy(zcad, obj, p):
    dx = p.get("to_x", 0) - p.get("from_x", 0)
    dy = p.get("to_y", 0) - p.get("from_y", 0)
    dz = p.get("to_z", 0) - p.get("from_z", 0)
    new_obj = obj.Copy()
    new_obj.Move(APoint(0, 0, 0), APoint(dx, dy, dz))
    return f"复制实体, 偏移=({dx},{dy},{dz})", new_obj


def _transform_move(zcad, obj, p):
    f = APoint(p.get("from_x", 0), p.get("from_y", 0), p.get("from_z", 0))
    t = APoint(p["to_x"], p["to_y"], p.get("to_z", 0))
    obj.Move(f, t)
    return f"移动实体到({p['to_x']},{p['to_y']})", None


def _transform_rotate(zcad, obj, p):
    b = APoint(p["base_x"], p["base_y"], p.get("base_z", 0))
    obj.Rotate(b, p["angle"])
    return f"旋转实体, 角度={p['angle']:.4f}弧度", None


def _transform_mirror(zcad, obj, p):
    p1 = APoint(p["x1"], p["y1"], p.get("z1", 0))
    p2 = APoint(p["x2"], p["y2"], p.get("z2", 0))
    new_obj = obj.Mirror(p1, p2)
    return "镜像实体", new_obj


def _transform_scale(zcad, obj, p):
    b = APoint(p["base_x"], p["base_y"], p.get("base_z", 0))
    obj.ScaleEntity(b, p["factor"])
    return f"缩放实体, 比例={p['factor']}", None


def _transform_delete(zcad, obj, p):
    obj.Delete()
    return "删除实体", None


def _transform_array_polar(zcad, obj, p):
    c = APoint(p["center_x"], p["center_y"], p.get("center_z", 0))
    obj.ArrayPolar(p["count"], p.get("fill_angle", math.pi * 2), c)
    return f"环形阵列: {p['count']}个", None


def _transform_array_rect(zcad, obj, p):
    obj.ArrayRectangular(
        p["num_rows"], p["num_cols"], p.get("num_levels", 1),
        p["row_spacing"], p["col_spacing"], p.get("level_spacing", 0)
    )
    return f"矩形阵列: {p['num_rows']}行x{p['num_cols']}列", None


_TRANSFORM_DISPATCH = {
    "copy": _transform_copy, "move": _transform_move,
    "rotate": _transform_rotate, "mirror": _transform_mirror,
    "scale": _transform_scale, "delete": _transform_delete,
    "array_polar": _transform_array_polar, "array_rectangular": _transform_array_rect,
}


# ============================================================
# 几何修改内部实现
# ============================================================

def _modify_circle_impl(zcad, obj, p):
    updated = []
    if "radius" in p:
        obj.Radius = p["radius"]; updated.append(f"Radius={p['radius']}")
    if "center_x" in p or "center_y" in p or "center_z" in p:
        obj.Center = APoint(p.get("center_x", 0), p.get("center_y", 0), p.get("center_z", 0))
        updated.append("Center updated")
    return updated


def _modify_arc_impl(zcad, obj, p):
    updated = []
    if "radius" in p:
        obj.Radius = p["radius"]; updated.append(f"Radius={p['radius']}")
    if "center_x" in p or "center_y" in p:
        obj.Center = APoint(p.get("center_x", 0), p.get("center_y", 0), p.get("center_z", 0))
        updated.append("Center updated")
    if "start_angle" in p:
        obj.StartAngle = p["start_angle"]; updated.append(f"StartAngle={p['start_angle']:.4f}")
    if "end_angle" in p:
        obj.EndAngle = p["end_angle"]; updated.append(f"EndAngle={p['end_angle']:.4f}")
    return updated


def _modify_line_impl(zcad, obj, p):
    updated = []
    if "x1" in p or "y1" in p:
        obj.StartPoint = APoint(p.get("x1", 0), p.get("y1", 0), p.get("z1", 0))
        updated.append("StartPoint updated")
    if "x2" in p or "y2" in p:
        obj.EndPoint = APoint(p.get("x2", 0), p.get("y2", 0), p.get("z2", 0))
        updated.append("EndPoint updated")
    return updated


def _modify_text_impl(zcad, obj, p):
    updated = []
    if "text" in p:
        obj.TextString = p["text"]; updated.append(f"Text='{p['text']}'")
    if "height" in p:
        obj.Height = p["height"]; updated.append(f"Height={p['height']}")
    if "rotation" in p:
        obj.Rotation = p["rotation"]; updated.append(f"Rotation={p['rotation']:.4f}")
    if "stylename" in p:
        obj.StyleName = p["stylename"]; updated.append(f"Style={p['stylename']}")
    if "x" in p or "y" in p:
        obj.InsertionPoint = APoint(p.get("x", 0), p.get("y", 0), p.get("z", 0))
        updated.append("Position updated")
    return updated


def _modify_mtext_impl(zcad, obj, p):
    updated = []
    if "text" in p:
        obj.TextString = p["text"]; updated.append("Text updated")
    if "height" in p:
        obj.Height = p["height"]; updated.append(f"Height={p['height']}")
    if "width" in p:
        obj.Width = p["width"]; updated.append(f"Width={p['width']}")
    if "rotation" in p:
        obj.Rotation = p["rotation"]; updated.append(f"Rotation={p['rotation']:.4f}")
    if "attachment_point" in p:
        obj.AttachmentPoint = p["attachment_point"]; updated.append(f"Attachment={p['attachment_point']}")
    return updated


def _modify_polyline_impl(zcad, obj, p):
    updated = []
    if "closed" in p and hasattr(obj, 'Closed'):
        obj.Closed = p["closed"]; updated.append(f"Closed={p['closed']}")
    if "constant_width" in p and hasattr(obj, 'ConstantWidth'):
        obj.ConstantWidth = p["constant_width"]; updated.append(f"Width={p['constant_width']}")
    if "elevation" in p and hasattr(obj, 'Elevation'):
        obj.Elevation = p["elevation"]; updated.append(f"Elevation={p['elevation']}")
    return updated


def _modify_spline_impl(zcad, obj, p):
    updated = []
    if "closed" in p:
        obj.Closed = p["closed"]; updated.append(f"Closed={p['closed']}")
    if "fit_tolerance" in p:
        obj.FitTolerance = p["fit_tolerance"]; updated.append(f"FitTol={p['fit_tolerance']}")
    if "start_tangent_x" in p or "start_tangent_y" in p:
        obj.StartTangent = APoint(p.get("start_tangent_x", 0), p.get("start_tangent_y", 0), 0)
        updated.append("StartTangent updated")
    if "end_tangent_x" in p or "end_tangent_y" in p:
        obj.EndTangent = APoint(p.get("end_tangent_x", 0), p.get("end_tangent_y", 0), 0)
        updated.append("EndTangent updated")
    return updated


_MODIFY_DISPATCH = {
    "circle": ("Circle", _modify_circle_impl),
    "arc": ("Arc", _modify_arc_impl),
    "line": ("Line", _modify_line_impl),
    "text": ("Text", _modify_text_impl),
    "mtext": ("MText", _modify_mtext_impl),
    "polyline": (None, _modify_polyline_impl),
    "spline": ("Spline", _modify_spline_impl),
}


# ############################################################
#                   合并后的 MCP 工具
# ############################################################


@mcp.tool
def draw_entity(entity_type: str, params: dict, layer: str = "0") -> str:
    """
    绘制2D实体

    参数:
    - entity_type: 实体类型，可选值:
      "line" - 直线: params需要 {x1,y1,x2,y2} (z1,z2可选,默认0)
      "circle" - 圆: params需要 {center_x,center_y,radius} (center_z可选)
      "arc" - 圆弧: params需要 {center_x,center_y,radius,start_angle,end_angle}（角度为弧度）
      "ellipse" - 椭圆: params需要 {center_x,center_y,major_axis_x,major_axis_y,radius_ratio}
      "lwpolyline" - 轻量多段线: params需要 {vertices:[[x1,y1],[x2,y2],...]} (closed可选)
      "polyline" - 多段线: params需要 {vertices:[[x1,y1,z1],...]} (closed可选)
      "spline" - 样条曲线: params需要 {fit_points:[[x1,y1,z1],...]}
      "point" - 点: params需要 {x,y} (z可选)
      "ray" - 射线: params需要 {x1,y1,x2,y2}
      "xline" - 构造线: params需要 {x1,y1,x2,y2}
      "mline" - 多线: params需要 {vertices:[[x1,y1,z1],...]}
      "3d_polyline" - 3D多段线: params需要 {vertices:[[x1,y1,z1],...]}
    - params: 根据类型不同的参数字典
    - layer: 图层名称（默认"0"）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        fn = _DRAW_DISPATCH.get(entity_type)
        if not fn:
            return _err("绘图", ValueError(f"不支持的实体类型: {entity_type}，支持: {', '.join(_DRAW_DISPATCH.keys())}"))
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(f"成功绘制{desc}，图层: {layer}", handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"绘制{entity_type}", e)


@mcp.tool
def draw_3d_solid(solid_type: str, params: dict, layer: str = "0") -> str:
    """
    绘制3D实体

    参数:
    - solid_type: 实体类型，可选值:
      "box" - 长方体: params需要 {origin_x,origin_y,origin_z,length,width,height}
      "cylinder" - 圆柱体: params需要 {center_x,center_y,center_z,radius,height}
      "cone" - 圆锥体: params需要 {center_x,center_y,center_z,base_radius,height}
      "sphere" - 球体: params需要 {center_x,center_y,center_z,radius}
      "torus" - 圆环体: params需要 {center_x,center_y,center_z,torus_radius,tube_radius}
      "wedge" - 楔体: params需要 {center_x,center_y,center_z,length,width,height}
      "3d_face" - 3D面: params需要 {x1,y1,z1,x2,y2,z2,x3,y3,z3} (x4,y4,z4可选)
    - params: 根据类型不同的参数字典
    - layer: 图层名称（默认"0"）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        fn = _3D_DISPATCH.get(solid_type)
        if not fn:
            return _err("3D绘图", ValueError(f"不支持的3D类型: {solid_type}，支持: {', '.join(_3D_DISPATCH.keys())}"))
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(f"成功绘制{desc}，图层: {layer}", handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"绘制{solid_type}", e)


@mcp.tool
def add_annotation(annotation_type: str, params: dict, layer: str = "0") -> str:
    """
    添加注释对象（文本、引线、公差、填充、表格等）

    参数:
    - annotation_type: 注释类型，可选值:
      "text" - 单行文本: params需要 {text,x,y} (z,height可选)
      "mtext" - 多行文本: params需要 {text,x,y} (z,width,height可选)
      "leader" - 引线: params需要 {points:[[x1,y1,z1],...]} (annotation_type可选:0无/1文字/2图块)
      "tolerance" - 形位公差: params需要 {text,x,y} (z,dir_x,dir_y,dir_z可选)
      "mleader" - 多重引线: params需要 {points:[[x1,y1,z1],...]} (text,text_height可选)
      "hatch" - 填充: params需要 {pattern_name} (pattern_type,pattern_scale,pattern_angle可选)
      "table" - 表格: params需要 {x,y,rows,cols,row_height,col_width}
    - params: 根据类型不同的参数字典
    - layer: 图层名称（默认"0"）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        fn = _ANNO_DISPATCH.get(annotation_type)
        if not fn:
            return _err("添加注释", ValueError(f"不支持的注释类型: {annotation_type}，支持: {', '.join(_ANNO_DISPATCH.keys())}"))
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(f"成功添加{desc}，图层: {layer}", handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"添加{annotation_type}", e)


@mcp.tool
def add_dimension(dim_type: str, params: dict, layer: str = "0") -> str:
    """
    添加标注

    参数:
    - dim_type: 标注类型，可选值:
      "aligned" - 对齐标注: params需要 {x1,y1,x2,y2,text_x,text_y}
      "rotated" - 旋转标注: params需要 {x1,y1,x2,y2,text_x,text_y,rotation_angle}
      "diametric" - 直径标注: params需要 {chord_x,chord_y,far_chord_x,far_chord_y,leader_length}
      "radial" - 半径标注: params需要 {center_x,center_y,chord_x,chord_y,leader_length}
      "angular" - 角度标注: params需要 {vertex_x,vertex_y,first_x,first_y,second_x,second_y,text_x,text_y}
      "ordinate" - 坐标标注: params需要 {def_x,def_y,leader_x,leader_y,use_x_axis}
    - params: 根据类型不同的参数字典（z坐标可选，默认0）
    - layer: 图层名称（默认"0"）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        fn = _DIM_DISPATCH.get(dim_type)
        if not fn:
            return _err("添加标注", ValueError(f"不支持的标注类型: {dim_type}，支持: {', '.join(_DIM_DISPATCH.keys())}"))
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(f"成功添加{desc}，图层: {layer}", handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"添加{dim_type}标注", e)


@mcp.tool
def insert_block(block_name: str, x: float, y: float, z: float = 0,
                 x_scale: float = 1.0, y_scale: float = 1.0, z_scale: float = 1.0,
                 rotation: float = 0, layer: str = "0") -> str:
    """
    在指定位置插入图块

    参数:
    - block_name: 图块名称
    - x, y, z: 插入点坐标
    - x_scale, y_scale, z_scale: 各轴缩放比例（默认1.0）
    - rotation: 旋转角度（弧度，默认0）
    - layer: 图层名称（默认"0"）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        ref = zcad_conn.model.InsertBlock(point, block_name, x_scale, y_scale, z_scale, rotation)
        ref.Layer = layer
        return _ok(f"成功插入图块: '{block_name}' at ({x},{y},{z})", handle=ref.Handle, layer=layer)
    except Exception as e:
        return _err("插入图块", e)


@mcp.tool
def transform_entity(action: str, params: dict,
                     object_type: str = None, property_name: str = None,
                     property_value: str = None, handle: str = None) -> str:
    """
    对实体执行变换操作（通过handle或属性定位实体）

    参数:
    - action: 变换类型，可选值:
      "copy" - 复制: params需要 {from_x,from_y,to_x,to_y} (z可选)
      "move" - 移动: params需要 {from_x,from_y,to_x,to_y} (z可选)
      "rotate" - 旋转: params需要 {base_x,base_y,angle}（角度为弧度）
      "mirror" - 镜像: params需要 {x1,y1,x2,y2}（镜像轴两点）
      "scale" - 缩放: params需要 {base_x,base_y,factor}
      "delete" - 删除: params可为空{}
      "array_polar" - 环形阵列: params需要 {center_x,center_y,count} (fill_angle可选,默认2π)
      "array_rectangular" - 矩形阵列: params需要 {num_rows,num_cols,row_spacing,col_spacing}
    - params: 根据操作类型不同的参数字典
    - object_type: 对象类型（如"Line","Circle"）
    - property_name: 定位属性名
    - property_value: 定位属性值
    - handle: 实体句柄（优先于属性定位）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type=object_type,
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _ok("未找到符合条件的对象", found=False)
        fn = _TRANSFORM_DISPATCH.get(action)
        if not fn:
            return _err("变换", ValueError(f"不支持的变换: {action}，支持: {', '.join(_TRANSFORM_DISPATCH.keys())}"))
        desc, new_obj = fn(zcad_conn, obj, params)
        result = {"handle": handle}
        if new_obj and hasattr(new_obj, 'Handle'):
            result["new_handle"] = new_obj.Handle
        return _ok(f"成功{desc}", **result)
    except Exception as e:
        return _err(f"变换({action})", e)


@mcp.tool
def modify_entity(entity_type: str, params: dict,
                  object_type: str = None, property_name: str = None,
                  property_value: str = None, handle: str = None) -> str:
    """
    修改实体的几何属性（通过handle或属性定位实体）

    参数:
    - entity_type: 实体类型，可选值:
      "circle" - 修改圆: params可含 {radius, center_x, center_y, center_z}
      "arc" - 修改圆弧: params可含 {radius, center_x, center_y, start_angle, end_angle}
      "line" - 修改直线: params可含 {x1, y1, z1, x2, y2, z2}
      "text" - 修改文本: params可含 {text, height, rotation, stylename, x, y}
      "mtext" - 修改多行文本: params可含 {text, height, width, rotation, attachment_point}
      "polyline" - 修改多段线: params可含 {closed, constant_width, elevation}
      "spline" - 修改样条: params可含 {closed, fit_tolerance, start_tangent_x/y, end_tangent_x/y}
      "offset" - 偏移实体: params需要 {distance}
      "explode" - 分解实体: params可为空{}
    - params: 修改参数字典
    - object_type, property_name, property_value, handle: 定位实体
    """
    try:
        zcad_conn, _ = get_cad_connection()
        if entity_type == "offset":
            obj = _find_entity(zcad_conn, object_type=object_type,
                               property_name=property_name, property_value=property_value,
                               handle=handle)
            if not obj:
                return _ok("未找到符合条件的对象", found=False)
            if not hasattr(obj, 'Offset'):
                return _ok("此对象不支持偏移操作")
            result = obj.Offset(params["distance"])
            return _ok(f"成功偏移实体, 距离={params['distance']}")

        if entity_type == "explode":
            obj = _find_entity(zcad_conn, object_type=object_type,
                               property_name=property_name, property_value=property_value,
                               handle=handle)
            if not obj:
                return _ok("未找到符合条件的对象", found=False)
            result = obj.Explode()
            cnt = len(result) if result else 0
            return _ok(f"成功分解实体，生成对象数: {cnt}")

        entry = _MODIFY_DISPATCH.get(entity_type)
        if not entry:
            return _err("修改实体", ValueError(f"不支持的实体类型: {entity_type}"))
        obj_type_hint, modify_fn = entry
        obj = _find_entity(zcad_conn, object_type=obj_type_hint or object_type,
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _ok(f"未找到符合条件的{entity_type}", found=False)
        updated = modify_fn(zcad_conn, obj, params)
        if updated and hasattr(obj, 'Update'):
            obj.Update()
        return _ok(f"成功修改{entity_type}: {', '.join(updated)}") if updated else _ok("未提供修改参数")
    except Exception as e:
        return _err(f"修改{entity_type}", e)


@mcp.tool
def get_entity_info(handle: str = None, object_type: str = None,
                    property_name: str = None, property_value: str = None) -> str:
    """
    获取实体的详细信息（属性、几何数据、边界框等）

    参数:
    - handle: 实体句柄（优先使用）
    - object_type: 对象类型
    - property_name: 定位属性名
    - property_value: 定位属性值
    """
    try:
        zcad_conn, _ = get_cad_connection()
        if handle and not object_type and not property_name:
            try:
                obj = zcad_conn.doc.HandleToObject(handle)
            except Exception:
                obj = None
        else:
            obj = _find_entity(zcad_conn, object_type=object_type,
                               property_name=property_name, property_value=property_value,
                               handle=handle)
        if not obj:
            return _ok("未找到实体", found=False)

        info = {"object_name": obj.ObjectName}
        if hasattr(obj, 'Handle'):
            info['handle'] = obj.Handle
        if hasattr(obj, 'ObjectID'):
            info['object_id'] = str(obj.ObjectID)

        for prop in ['Layer', 'Color', 'Linetype', 'LinetypeScale',
                      'Lineweight', 'Visible']:
            try:
                info[prop] = getattr(obj, prop)
            except Exception:
                pass

        geo_props = ['StartPoint', 'EndPoint', 'Center', 'Radius',
                     'StartAngle', 'EndAngle', 'Area', 'Length',
                     'TextString', 'Height', 'Rotation', 'InsertionPoint',
                     'Normal', 'Closed']
        for prop in geo_props:
            try:
                val = getattr(obj, prop)
                info[prop] = list(val) if hasattr(val, '__iter__') and not isinstance(val, str) else val
            except Exception:
                pass

        try:
            min_pt, max_pt = obj.GetBoundingBox()
            info['bounding_box'] = {'min': list(min_pt), 'max': list(max_pt)}
        except Exception:
            pass

        return _ok("获取成功", data=info)
    except Exception as e:
        return _err("获取实体信息", e)


@mcp.tool
def set_entity_properties(layer: str = None, color: int = None,
                          linetype: str = None, linetype_scale: float = None,
                          lineweight: float = None, visible: bool = None,
                          object_type: str = None, property_name: str = "Layer",
                          property_value: str = "", handle: str = None) -> str:
    """
    设置实体的通用属性（通过handle或属性定位实体）

    参数:
    - layer: 新图层名（可选）
    - color: 新颜色索引（可选）
    - linetype: 新线型名（可选）
    - linetype_scale: 新线型比例（可选）
    - lineweight: 新线宽（可选）
    - visible: 可见性（可选）
    - object_type, property_name, property_value: 定位参数
    - handle: 实体句柄（优先于属性定位）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type=object_type,
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _ok("未找到符合条件的对象", found=False)
        updated = []
        if layer is not None:
            obj.Layer = layer; updated.append(f"Layer={layer}")
        if color is not None:
            obj.color = color; updated.append(f"Color={color}")
        if linetype is not None:
            obj.Linetype = linetype; updated.append(f"Linetype={linetype}")
        if linetype_scale is not None:
            obj.LinetypeScale = linetype_scale; updated.append(f"LinetypeScale={linetype_scale}")
        if lineweight is not None:
            obj.Lineweight = lineweight; updated.append(f"Lineweight={lineweight}")
        if visible is not None:
            obj.Visible = visible; updated.append(f"Visible={visible}")
        return _ok(f"成功更新实体属性: {', '.join(updated)}") if updated else _ok("未提供任何属性")
    except Exception as e:
        return _err("设置实体属性", e)


@mcp.tool
def find_object(object_type: str = None, property_name: str = None,
                property_value: str = None, handle: str = None) -> str:
    """
    查找符合条件的第一个对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 属性名称（如 "Layer", "Color" 等）
    - property_value: 属性值
    - handle: 实体句柄（可选，优先于属性定位）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type=object_type,
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if obj:
            obj_info = {
                "object_name": obj.ObjectName,
                "handle": obj.Handle if hasattr(obj, 'Handle') else None,
                "layer": obj.Layer if hasattr(obj, 'Layer') else "N/A"
            }
            return _ok("查找到对象", found=True, data=obj_info)
        else:
            return _ok("未找到匹配对象", found=False)
    except Exception as e:
        return _err("查找对象", e)


@mcp.tool
def get_objects_in_model(object_type: str = None, limit: int = None) -> str:
    """
    获取模型空间中的对象列表

    参数:
    - object_type: 对象类型过滤（如 "Line", "Circle", "Text" 等，可选）
    - limit: 最大返回数量（可选，默认全部）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        objects = []
        count = 0
        for obj in zcad_conn.iter_objects(object_type, limit=limit):
            obj_info = {
                "index": count,
                "object_name": obj.ObjectName,
                "layer": obj.Layer if hasattr(obj, 'Layer') else "N/A"
            }
            if hasattr(obj, 'Handle'):
                obj_info['handle'] = obj.Handle
            if hasattr(obj, 'Color'):
                obj_info['color'] = obj.Color
            objects.append(obj_info)
            count += 1
        return _ok("获取对象列表成功", total_count=count, data=objects)
    except Exception as e:
        return _err("获取对象列表", e)


@mcp.tool
def zoom(mode: str, params: dict = None) -> str:
    """
    控制视图缩放

    参数:
    - mode: 缩放模式，可选值:
      "extents" - 缩放到全部对象范围
      "all" - 缩放到图形界限
      "window" - 窗口缩放: params需要 {x1,y1,x2,y2}
      "center" - 中心缩放: params需要 {center_x,center_y} (magnify可选,默认1.0)
      "scale" - 比例缩放: params需要 {scale} (scale_type可选: 0=相对全图/1=相对当前)
      "previous" - 返回上一个视图
    - params: 根据模式不同的参数字典（部分模式不需要）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p = params or {}
        if mode == "extents":
            zcad_conn.app.ZoomExtents()
        elif mode == "all":
            zcad_conn.app.ZoomAll()
        elif mode == "window":
            p1 = APoint(p["x1"], p["y1"], 0)
            p2 = APoint(p["x2"], p["y2"], 0)
            zcad_conn.app.ZoomWindow(p1, p2)
        elif mode == "center":
            c = APoint(p["center_x"], p["center_y"], 0)
            zcad_conn.app.ZoomCenter(c, p.get("magnify", 1.0))
        elif mode == "scale":
            zcad_conn.app.ZoomScaled(p["scale"], p.get("scale_type", 0))
        elif mode == "previous":
            zcad_conn.app.ZoomPrevious()
        else:
            return _err("缩放", ValueError(f"不支持的缩放模式: {mode}"))
        return _ok(f"成功执行缩放: {mode}")
    except Exception as e:
        return _err(f"缩放({mode})", e)


@mcp.tool
def manage_style(style_type: str, action: str, name: str = None,
                 properties: dict = None) -> str:
    """
    管理图层、线型、文字样式、标注样式（CRUD操作）

    参数:
    - style_type: 样式类型 "layer"|"linetype"|"textstyle"|"dimstyle"
    - action: 操作类型 "list"|"add"|"set_active"|"set_properties"
    - name: 样式名称（list时不需要）
    - properties: 属性字典（set_properties/add时使用）
      layer的add: {color:int, linetype:str, on:bool, locked:bool, freeze:bool}
      layer的set_properties: {on:bool, locked:bool, freeze:bool, color:int, linetype:str}
      textstyle的add: {font_file:str, big_font_file:str, height:float}
      textstyle的set_properties: {font_file, big_font_file, height, width, oblique_angle}
      linetype的add: {filename:str} (线型文件名，默认"acad.lin")
      dimstyle的add: {}
    """
    try:
        zcad_conn, _ = get_cad_connection()
        props = properties or {}

        if style_type == "layer":
            if action == "list":
                layers = []
                for lay in zcad_conn.iter_layers():
                    info = {"name": lay.Name, "on": lay.LayerOn, "color": lay.color,
                            "linetype": lay.Linetype, "locked": lay.Lock, "freeze": lay.Freeze}
                    layers.append(info)
                return _ok("获取成功", data=layers)
            elif action == "add":
                new_layer = zcad_conn.doc.Layers.Add(name)
                if "color" in props:
                    new_layer.color = props["color"]
                if "linetype" in props:
                    new_layer.Linetype = props["linetype"]
                return _ok(f"成功创建图层: {name}", name=name)
            elif action == "set_active":
                zcad_conn.doc.ActiveLayer = zcad_conn.doc.Layers.Item(name)
                return _ok(f"成功设置活动图层: {name}")
            elif action == "set_properties":
                lay = zcad_conn.doc.Layers.Item(name)
                updated = []
                if "on" in props:
                    lay.LayerOn = props["on"]; updated.append(f"On={props['on']}")
                if "locked" in props:
                    lay.Lock = props["locked"]; updated.append(f"Locked={props['locked']}")
                if "freeze" in props:
                    lay.Freeze = props["freeze"]; updated.append(f"Freeze={props['freeze']}")
                if "color" in props:
                    lay.color = props["color"]; updated.append(f"Color={props['color']}")
                if "linetype" in props:
                    lay.Linetype = props["linetype"]; updated.append(f"Linetype={props['linetype']}")
                return _ok(f"成功更新图层 '{name}': {', '.join(updated)}")

        elif style_type == "linetype":
            if action == "list":
                lts = []
                for lt in zcad_conn.doc.Linetypes:
                    lts.append({"name": lt.Name, "description": getattr(lt, 'Description', '')})
                return _ok("获取成功", data=lts)
            elif action == "add":
                fn = props.get("filename", "acad.lin")
                zcad_conn.doc.Linetypes.Load(name, fn)
                return _ok(f"成功加载线型: {name}")
            elif action == "set_active":
                lt = zcad_conn.doc.Linetypes.Item(name)
                zcad_conn.doc.ActiveLinetype = lt
                return _ok(f"成功设置活动线型: {name}")

        elif style_type == "textstyle":
            if action == "list":
                styles = []
                for ts in zcad_conn.doc.TextStyles:
                    info = {"name": ts.Name}
                    for p_name in ['fontFile', 'BigFontFile', 'Height', 'Width', 'ObliqueAngle']:
                        if hasattr(ts, p_name):
                            try: info[p_name.lower()] = getattr(ts, p_name)
                            except Exception: pass
                    styles.append(info)
                return _ok("获取成功", data=styles)
            elif action == "add":
                ts = zcad_conn.doc.TextStyles.Add(name)
                ts.fontFile = props.get("font_file", "txt.shx")
                if props.get("big_font_file") and hasattr(ts, 'BigFontFile'):
                    ts.BigFontFile = props["big_font_file"]
                if "height" in props:
                    ts.Height = props["height"]
                return _ok(f"成功创建文字样式: {name}")
            elif action == "set_active":
                ts = zcad_conn.doc.TextStyles.Item(name)
                zcad_conn.doc.ActiveTextStyle = ts
                return _ok(f"成功设置活动文字样式: {name}")
            elif action == "set_properties":
                ts = zcad_conn.doc.TextStyles.Item(name)
                updated = []
                if "font_file" in props:
                    ts.fontFile = props["font_file"]; updated.append(f"Font={props['font_file']}")
                if "big_font_file" in props and hasattr(ts, 'BigFontFile'):
                    ts.BigFontFile = props["big_font_file"]; updated.append(f"BigFont={props['big_font_file']}")
                if "height" in props:
                    ts.Height = props["height"]; updated.append(f"Height={props['height']}")
                if "width" in props:
                    ts.Width = props["width"]; updated.append(f"Width={props['width']}")
                if "oblique_angle" in props:
                    ts.ObliqueAngle = props["oblique_angle"]; updated.append(f"Oblique={props['oblique_angle']}")
                return _ok(f"成功修改文字样式 '{name}': {', '.join(updated)}")

        elif style_type == "dimstyle":
            if action == "list":
                styles = []
                for ds in zcad_conn.doc.DimStyles:
                    styles.append({"name": ds.Name})
                return _ok("获取成功", data=styles)
            elif action == "add":
                zcad_conn.doc.DimStyles.Add(name)
                return _ok(f"成功创建标注样式: {name}")
            elif action == "set_active":
                ds = zcad_conn.doc.DimStyles.Item(name)
                zcad_conn.doc.ActiveDimStyle = ds
                return _ok(f"成功设置活动标注样式: {name}")

        return _err("样式管理", ValueError(f"不支持的操作: style_type={style_type}, action={action}"))
    except Exception as e:
        return _err(f"样式管理({style_type}.{action})", e)


@mcp.tool
def manage_view(action: str, name: str = None, params: dict = None) -> str:
    """
    管理布局、视图和视口

    参数:
    - action: 操作类型，可选值:
      "list_layouts" - 列出所有布局 (params可含 {include_model:bool})
      "get_active_layout" - 获取当前活动布局
      "add_layout" - 添加布局: 需要name
      "set_active_layout" - 设置活动布局: 需要name
      "list_views" - 列出所有命名视图
      "add_view" - 创建命名视图: 需要name
    - name: 布局/视图名称
    - params: 额外参数
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p = params or {}

        if action == "list_layouts":
            layouts = []
            for layout in zcad_conn.iter_layouts(skip_model=not p.get("include_model", False)):
                layouts.append({"name": layout.Name, "tab_order": layout.TabOrder,
                                "is_model_space": layout.ModelSpace})
            return _ok("获取布局列表成功", data=layouts)

        elif action == "get_active_layout":
            layout = zcad_conn.doc.ActiveLayout
            info = {"name": layout.Name, "tab_order": layout.TabOrder,
                    "is_model_space": layout.ModelSpace}
            return _ok("获取活动布局成功", data=info)

        elif action == "add_layout":
            zcad_conn.doc.Layouts.Add(name)
            return _ok(f"成功添加布局: {name}")

        elif action == "set_active_layout":
            layout = zcad_conn.doc.Layouts.Item(name)
            zcad_conn.doc.ActiveLayout = layout
            return _ok(f"成功设置活动布局: {name}")

        elif action == "list_views":
            views = []
            for v in zcad_conn.doc.Views:
                info = {"name": v.Name}
                if hasattr(v, 'Center'):
                    try: info['center'] = list(v.Center)
                    except Exception: pass
                if hasattr(v, 'Height'):
                    info['height'] = v.Height
                views.append(info)
            return _ok("获取成功", data=views)

        elif action == "add_view":
            zcad_conn.doc.Views.Add(name)
            return _ok(f"成功创建视图: {name}")

        return _err("视图管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"视图管理({action})", e)


@mcp.tool
def manage_document(action: str, params: dict = None) -> str:
    """
    文档管理（新建、保存、关闭、导入导出等）

    参数:
    - action: 操作类型，可选值:
      "new" - 新建空白图纸
      "save" - 保存: params需要 {file_path:str}
      "close" - 关闭当前文档: params可含 {save_changes:bool}（默认True）
      "info" - 获取当前文档信息
      "list" - 列出所有打开的文档
      "activate" - 激活文档: params需要 {name:str}
      "export" - 导出: params需要 {filename:str} (extension可选,默认"DWG")
      "import" - 导入: params需要 {filename:str} (x,y,z,scale_factor可选)
      "plot" - 打印到文件: params需要 {plot_file:str} (plot_config可选)
    - params: 根据操作不同的参数字典
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p = params or {}

        if action == "new":
            new_doc = zcad_conn.app.Documents.Add()
            return _ok(f"成功创建新图纸: {new_doc.Name}", document=new_doc.Name)

        elif action == "save":
            zcad_conn.doc.SaveAs(p["file_path"])
            return _ok(f"图纸已保存至: {p['file_path']}")

        elif action == "close":
            zcad_conn.doc.Close(p.get("save_changes", True))
            return _ok("当前图纸已关闭")

        elif action == "info":
            doc = zcad_conn.doc
            info = {"name": doc.Name, "full_name": doc.FullName,
                    "path": doc.Path, "saved": doc.Saved, "readonly": doc.ReadOnly}
            return _ok("获取文档信息成功", data=info)

        elif action == "list":
            docs = []
            for doc in zcad_conn.app.Documents:
                docs.append({"name": doc.Name,
                             "path": doc.Path if hasattr(doc, 'Path') else "",
                             "saved": doc.Saved if hasattr(doc, 'Saved') else None})
            return _ok("获取成功", data=docs)

        elif action == "activate":
            doc = zcad_conn.app.Documents.Item(p["name"])
            doc.Activate()
            return _ok(f"成功激活文档: {p['name']}")

        elif action == "export":
            sel_set_name = "ExportSelSet"
            try:
                sel = zcad_conn.doc.SelectionSets.Item(sel_set_name)
                sel.Delete()
            except Exception:
                pass
            sel = zcad_conn.doc.SelectionSets.Add(sel_set_name)
            sel.Select(5)
            zcad_conn.doc.Export(p["filename"], p.get("extension", "DWG"), sel)
            try:
                sel.Delete()
            except Exception:
                pass
            return _ok(f"成功导出: {p['filename']}")

        elif action == "import":
            point = APoint(p.get("x", 0), p.get("y", 0), p.get("z", 0))
            zcad_conn.doc.Import(p["filename"], point, p.get("scale_factor", 1.0))
            return _ok(f"成功导入文件: {p['filename']}")

        elif action == "plot":
            zcad_conn.doc.Plot.PlotToFile(p["plot_file"], p.get("plot_config", ""))
            return _ok(f"成功打印到文件: {p['plot_file']}")

        return _err("文档管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"文档管理({action})", e)


@mcp.tool
def manage_table(action: str, params: dict,
                 object_type: str = None, property_name: str = None,
                 property_value: str = None, handle: str = None) -> str:
    """
    操作CAD表格对象

    参数:
    - action: 操作类型，可选值:
      "set_cell" - 设置单元格文本: params需要 {row,col,text}
      "get_cell" - 获取单元格文本: params需要 {row,col}
      "insert_rows" - 插入行: params需要 {row_index} (count,height可选)
      "delete_rows" - 删除行: params需要 {row_index} (count可选)
      "set_column_width" - 设置列宽: params需要 {col,width}
      "set_row_height" - 设置行高: params需要 {row,height}
      "merge_cells" - 合并单元格: params需要 {min_row,max_row,min_col,max_col}
    - params: 操作参数
    - object_type, property_name, property_value, handle: 定位表格
    """
    try:
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type="Table",
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _ok("未找到符合条件的表格", found=False)
        p = params

        if action == "set_cell":
            obj.SetText(p["row"], p["col"], p["text"])
            return _ok(f"成功设置表格[{p['row']},{p['col']}] = '{p['text']}'")
        elif action == "get_cell":
            text = obj.GetText(p["row"], p["col"])
            return _ok("获取成功", row=p["row"], col=p["col"], text=text)
        elif action == "insert_rows":
            obj.InsertRows(p["row_index"], p.get("count", 1), p.get("height", 0))
            return _ok(f"成功在第{p['row_index']}行插入{p.get('count', 1)}行")
        elif action == "delete_rows":
            obj.DeleteRows(p["row_index"], p.get("count", 1))
            return _ok(f"成功从第{p['row_index']}行删除{p.get('count', 1)}行")
        elif action == "set_column_width":
            obj.SetColumnWidth(p["col"], p["width"])
            return _ok(f"成功设置第{p['col']}列宽度={p['width']}")
        elif action == "set_row_height":
            obj.SetRowHeight(p["row"], p["height"])
            return _ok(f"成功设置第{p['row']}行高度={p['height']}")
        elif action == "merge_cells":
            obj.MergeCells(p["min_row"], p["max_row"], p["min_col"], p["max_col"])
            return _ok(f"成功合并单元格: 行{p['min_row']}-{p['max_row']}, 列{p['min_col']}-{p['max_col']}")

        return _err("表格操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"表格操作({action})", e)


def _ensure_selection_set(zcad_conn, name="SS1"):
    try:
        old = zcad_conn.doc.SelectionSets.Item(name)
        old.Delete()
    except Exception:
        pass
    return zcad_conn.doc.SelectionSets.Add(name)


def _selection_set_items(sel, max_items=200):
    items = []
    for i in range(min(sel.Count, max_items)):
        obj = sel.Item(i)
        info = {"object_name": obj.ObjectName}
        if hasattr(obj, 'Handle'):
            info['handle'] = obj.Handle
        if hasattr(obj, 'Layer'):
            info['layer'] = obj.Layer
        items.append(info)
    return items


def _build_filter(filter_criteria):
    if not filter_criteria:
        return None, None
    type_codes = []
    type_values = []
    if "entity_type" in filter_criteria:
        type_codes.append(0)
        type_values.append(filter_criteria["entity_type"])
    if "layer" in filter_criteria:
        type_codes.append(8)
        type_values.append(filter_criteria["layer"])
    if "color" in filter_criteria:
        type_codes.append(62)
        type_values.append(filter_criteria["color"])
    if not type_codes:
        return None, None
    return aInt(type_codes), tuple(type_values)


def _read_pickfirst_selection(zcad_conn, max_items=2000000):
    """读取 CAD 界面中用户当前选中的实体（Pickfirst 选择集）。"""
    try:
        sel = zcad_conn.doc.PickfirstSelectionSet
        count = sel.Count
        items = _selection_set_items(sel, max_items) if count else []
        return count, items
    except Exception:
        return 0, []


@mcp.tool
def select_entities(action: str, params: dict = None) -> str:
    """
    选择集操作

    参数:
    - action: 操作类型，可选值:
      "select" - 选择对象: params需要 {mode}
        mode 0(Window) 或 1(Crossing) 时还需要 {x1,y1,x2,y2}
        mode 2(Previous)、4(Last)、5(All) 时不需要坐标
        可选: {name, filter: {entity_type, layer, color}, return_items: bool}
      "by_polygon" - 多边形选择: params需要 {mode, points}
        mode: 0=Fence, 1=WindowPolygon, 2=CrossingPolygon
        可选: {name, filter: {entity_type, layer, color}, return_items: bool}
      "get_items" - 获取程序化选择集中的实体列表: params可含 {name, max_items}
      "get_picked" - 获取当前 DWG 中用户已选中的实体（界面高亮选择）: params可含 {max_items}
      "list" - 列出所有选择集
      "clear" - 清空选择集: params可含 {name}
      "delete" - 删除选择集: params可含 {name}
    - params: 操作参数
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p = params or {}

        if action == "select":
            mode = p["mode"]
            sel_name = p.get("name", "SS1")
            sel = _ensure_selection_set(zcad_conn, sel_name)

            filter_type, filter_data = _build_filter(p.get("filter"))

            if mode in (0, 1):
                for key in ("x1", "y1", "x2", "y2"):
                    if key not in p:
                        return _err("选择集操作",
                                    ValueError(f"Window/Crossing 模式必须提供 x1,y1,x2,y2，缺少: {key}"))
                p1 = APoint(p["x1"], p["y1"], 0)
                p2 = APoint(p["x2"], p["y2"], 0)
                if filter_type is not None:
                    sel.Select(mode, p1, p2, filter_type, filter_data)
                else:
                    sel.Select(mode, p1, p2)
            else:
                if filter_type is not None:
                    sel.Select(mode, None, None, filter_type, filter_data)
                else:
                    sel.Select(mode)

            result = {"count": sel.Count}
            if p.get("return_items", True):
                result["items"] = _selection_set_items(sel)
            return _ok(
                f"成功选择对象 (模式={mode}), 选择集: {sel_name}, 数量: {sel.Count}",
                **result
            )

        elif action == "by_polygon":
            sel_name = p.get("name", "SS1")
            sel = _ensure_selection_set(zcad_conn, sel_name)
            flat = _flatten_points(p["points"])
            coords = aDouble(*flat)

            filter_type, filter_data = _build_filter(p.get("filter"))
            if filter_type is not None:
                sel.SelectByPolygon(p["mode"], coords, filter_type, filter_data)
            else:
                sel.SelectByPolygon(p["mode"], coords)

            result = {"count": sel.Count}
            if p.get("return_items", True):
                result["items"] = _selection_set_items(sel)
            return _ok(
                f"多边形选择完成, 选择集: {sel_name}, 数量: {sel.Count}",
                **result
            )

        elif action == "get_items":
            sel_name = p.get("name", "SS1")
            try:
                sel = zcad_conn.doc.SelectionSets.Item(sel_name)
            except Exception:
                return _ok(f"选择集 '{sel_name}' 不存在", found=False)
            max_items = p.get("max_items", 200)
            items = _selection_set_items(sel, max_items)
            return _ok("获取成功", count=sel.Count, items=items)

        elif action == "get_picked":
            max_items = p.get("max_items", 200)
            count, items = _read_pickfirst_selection(zcad_conn, max_items)
            if count == 0:
                return _ok("当前没有选中的实体", found=False, count=0, items=[])
            return _ok(f"获取当前选中实体成功, 数量: {count}", count=count, items=items)

        elif action == "list":
            sets = []
            for ss in zcad_conn.doc.SelectionSets:
                sets.append({"name": ss.Name, "count": ss.Count})
            return _ok("获取选择集列表成功", data=sets)

        elif action == "clear":
            sel_name = p.get("name", "SS1")
            try:
                sel = zcad_conn.doc.SelectionSets.Item(sel_name)
                sel.Clear()
                return _ok(f"已清空选择集: {sel_name}")
            except Exception:
                return _ok(f"选择集 '{sel_name}' 不存在", found=False)

        elif action == "delete":
            sel_name = p.get("name", "SS1")
            try:
                sel = zcad_conn.doc.SelectionSets.Item(sel_name)
                sel.Delete()
                return _ok(f"已删除选择集: {sel_name}")
            except Exception:
                return _ok(f"选择集 '{sel_name}' 不存在", found=False)

        return _err("选择集操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"选择集操作({action})", e)


@mcp.tool
def manage_block(action: str, name: str = None, params: dict = None,
                 object_type: str = None, property_name: str = None,
                 property_value: str = None, handle: str = None) -> str:
    """
    图块管理

    参数:
    - action: 操作类型，可选值:
      "list" - 列出所有图块定义
      "info" - 获取图块信息: 需要name
      "create" - 创建图块定义: 需要name, params可含 {x,y,z}
      "get_attributes" - 获取图块引用的属性: 通过handle或property定位
    - name: 图块名称
    - params: 额外参数
    - object_type, property_name, property_value, handle: 定位图块引用（get_attributes时使用）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p = params or {}

        if action == "list":
            blocks = []
            for blk in zcad_conn.doc.Blocks:
                info = {"name": blk.Name, "count": blk.Count,
                        "is_layout": blk.IsLayout, "is_xref": blk.IsXRef}
                if hasattr(blk, 'Origin'):
                    try: info['origin'] = list(blk.Origin)
                    except Exception: pass
                blocks.append(info)
            return _ok("获取成功", data=blocks)

        elif action == "info":
            blk = zcad_conn.doc.Blocks.Item(name)
            info = {"name": blk.Name, "count": blk.Count, "is_layout": blk.IsLayout}
            if hasattr(blk, 'Origin'):
                try: info['origin'] = list(blk.Origin)
                except Exception: pass
            entities = []
            for i in range(blk.Count):
                ent = blk.Item(i)
                entities.append({"index": i, "object_name": ent.ObjectName,
                                 "layer": getattr(ent, 'Layer', 'N/A')})
            info['entities'] = entities
            return _ok("获取成功", data=info)

        elif action == "create":
            point = APoint(p.get("x", 0), p.get("y", 0), p.get("z", 0))
            blk = zcad_conn.doc.Blocks.Add(point, name)
            return _ok(f"成功创建图块定义: {name}", name=name)

        elif action == "get_attributes":
            obj = _find_entity(zcad_conn, object_type="BlockReference",
                               property_name=property_name, property_value=property_value,
                               handle=handle)
            if not obj:
                return _ok("未找到符合条件的图块引用", found=False)
            attrs = obj.GetAttributes()
            result = []
            for attr in attrs:
                result.append({"tag": attr.TagString if hasattr(attr, 'TagString') else "",
                                "text": attr.TextString if hasattr(attr, 'TextString') else ""})
            return _ok("获取成功", data=result)

        return _err("图块管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"图块管理({action})", e)


@mcp.tool
def get_variable(name: str) -> str:
    """
    获取系统变量值

    参数:
    - name: 系统变量名（如 "DIMSCALE", "LTSCALE", "OSMODE" 等）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        value = zcad_conn.doc.GetVariable(name)
        return _ok("获取成功", name=name, value=value)
    except Exception as e:
        return _err("获取系统变量", e)


@mcp.tool
def set_variable(name: str, value) -> str:
    """
    设置系统变量值

    参数:
    - name: 系统变量名
    - value: 变量值
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.SetVariable(name, value)
        return _ok(f"成功设置系统变量: {name} = {value}")
    except Exception as e:
        return _err("设置系统变量", e)


@mcp.tool
def get_application_info() -> str:
    """
    获取 ZWCAD 应用程序信息（版本、路径、窗口状态等）
    """
    try:
        zcad_conn, _ = get_cad_connection()
        app = zcad_conn.app
        info = {}
        for prop in ['Version', 'Name', 'Path', 'FullName', 'Caption',
                      'WindowState', 'Visible', 'WindowLeft', 'WindowTop',
                      'Width', 'Height']:
            if hasattr(app, prop):
                try:
                    info[prop.lower()] = getattr(app, prop)
                except Exception:
                    pass
        return _ok("获取成功", data=info)
    except Exception as e:
        return _err("获取应用信息", e)


# ############################################################
#                   中望机械特有工具（合并后）
# ############################################################


@mcp.tool
def manage_title_block(action: str, params: dict = None) -> str:
    """
    标题栏管理（读取、设置、批量更新）

    参数:
    - action: 操作类型，可选值:
      "get_info" - 获取标题栏所有字段信息
      "set_field" - 设置单个字段: params需要 {field_name, value}
      "update_batch" - 批量更新: params需要 {fields: {字段名:值, ...}}
      "get_field_count" - 获取字段总数
      "get_field_by_index" - 按索引获取字段: params需要 {index}
    - params: 操作参数
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        title = mech_conn.get_title()
        p = params or {}

        if not title:
            return _ok("未找到标题栏对象", found=False)

        if action == "get_info":
            items = []
            count = title.get_item_count()
            for i in range(count):
                label, name, value = title.get_item(i)
                items.append({"index": i, "label": label, "name": name, "value": value})
            return _ok("获取成功", data=items)

        elif action == "set_field":
            title.set_item(p["field_name"], p["value"])
            mech_conn.zwm_db.refresh_title()
            return _ok(f"成功设置标题栏字段 '{p['field_name']}' = '{p['value']}'")

        elif action == "update_batch":
            results = []
            for field_name, value in p["fields"].items():
                title.set_item(field_name, value)
                results.append(f"{field_name}={value}")
            mech_conn.zwm_db.refresh_title()
            return _ok(f"成功批量更新标题栏: {', '.join(results)}")

        elif action == "get_field_count":
            count = title.get_item_count()
            return _ok("获取标题栏字段总数成功", count=count)

        elif action == "get_field_by_index":
            label, name, value = title.get_item(p["index"])
            return _ok("获取成功", data={"index": p["index"], "label": label, "name": name, "value": value})

        return _err("标题栏操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"标题栏操作({action})", e)


@mcp.tool
def manage_frame(action: str, params: dict = None) -> str:
    """
    图框管理（查询、切换、更新属性、刷新）

    参数:
    - action: 操作类型，可选值:
      "list" - 获取所有可用图框列表
      "get_info" - 获取当前图框完整信息
      "get_count" - 获取图框总数
      "get_name_by_index" - 按索引获取图框名: params需要 {index}
      "get_name_by_point" - 按坐标获取图框名: params需要 {x,y} (z可选)
      "get_next_name" - 获取下一个图框名称和信息
      "switch" - 切换当前图框: params需要 {frame_name}
      "update" - 更新图框属性: params可含 {width,height,orientation,scale1,scale2,...}
      "refresh" - 刷新图框显示
    - params: 操作参数
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        p = params or {}

        if action == "list":
            count = mech_conn.zwm_db.get_frame_count()
            frames = [mech_conn.zwm_db.get_frame_name(i) for i in range(count)]
            return _ok("获取图框列表成功", data=frames)

        elif action == "get_info":
            frame = mech_conn.zwm_db.get_frame()
            if not frame:
                return _ok("未找到图框对象", found=False)
            info = {}
            for attr in ['width', 'height', 'std_name', 'frame_size_name', 'frame_style_name',
                          'orientation', 'title_style_name', 'bom_style_name',
                          'dhl_style_name', 'fjl_style_name', 'csl_style_name', 'ggl_style_name',
                          'have_dhl', 'have_fjl', 'have_btl', 'have_csl', 'have_ggl',
                          'scale1', 'scale2']:
                if hasattr(frame, attr):
                    try: info[attr] = getattr(frame, attr)
                    except Exception: pass
            return _ok("获取图框完整信息成功", data=info)

        elif action == "get_count":
            count = mech_conn.zwm_db.get_frame_count()
            return _ok("获取图框总数成功", count=count)

        elif action == "get_name_by_index":
            name = mech_conn.zwm_db.get_frame_name(p["index"])
            return _ok("获取图框名称成功", index=p["index"], name=name)

        elif action == "get_name_by_point":
            point = (p["x"], p["y"], p.get("z", 0))
            name = mech_conn.zwm_db.get_frame_name2(point)
            return _ok("获取图框名称成功", name=name)

        elif action == "get_next_name":
            frame_obj, name = mech_conn.zwm_db.get_next_frm_name()
            result = {"frame_name": name, "has_frame": frame_obj is not None}
            if frame_obj:
                if hasattr(frame_obj, 'width'):
                    result['width'] = frame_obj.width
                if hasattr(frame_obj, 'height'):
                    result['height'] = frame_obj.height
            return _ok("获取成功", data=result)

        elif action == "switch":
            mech_conn.zwm_db.switch_frame(p["frame_name"])
            return _ok(f"成功切换到图框: {p['frame_name']}")

        elif action == "update":
            frame = mech_conn.zwm_db.get_frame()
            if not frame:
                return _ok("未找到图框对象", found=False)
            updated = []
            for attr, val in p.items():
                if val is not None and hasattr(frame, attr):
                    setattr(frame, attr, val)
                    updated.append(f"{attr}={val}")
            mech_conn.zwm_db.refresh_frame()
            return _ok(f"成功更新图框属性: {', '.join(updated)}") if updated else _ok("未提供任何要更新的属性")

        elif action == "refresh":
            mech_conn.zwm_db.refresh_frame()
            return _ok("图框刷新成功")

        return _err("图框操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"图框操作({action})", e)


@mcp.tool
def manage_bom(action: str, params: dict = None) -> str:
    """
    明细表（BOM）管理

    参数:
    - action: 操作类型，可选值:
      "get_row_count" - 获取总行数
      "get_row" - 获取指定行数据: params需要 {row_index}
      "add_row" - 添加新行: params需要 {data:{字段名:值,...}}
      "update_row" - 更新行: params需要 {row_index, data:{字段名:值,...}}
      "insert_row" - 在指定位置插入行: params需要 {index, data:{字段名:值,...}}
      "delete_row" - 删除行: params需要 {index}
      "set_field" - 设置指定行字段: params需要 {row_index, field_key, value}
      "get_field" - 获取指定行字段: params需要 {row_index, field_index}
      "get_field_count" - 获取行字段数: params需要 {row_index}
      "refresh" - 刷新明细表显示
    - params: 操作参数
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        p = params or {}

        if action == "refresh":
            mech_conn.zwm_db.refresh_bom()
            return _ok("明细表刷新成功")

        if not bom:
            return _ok("未找到明细表对象", found=False)

        if action == "get_row_count":
            count = bom.get_item_count()
            return _ok("获取明细表行数成功", count=count)

        elif action == "get_row":
            row = bom.get_item(p["row_index"])
            if not row:
                return _ok(f"未找到索引 {p['row_index']} 的行", found=False)
            fields = []
            field_count = row.get_item_count()
            for i in range(field_count):
                label, name, value = row.get_item(i)
                fields.append({"field_index": i, "label": label, "name": name, "value": value})
            return _ok("获取成功", data={"row_index": p["row_index"], "field_count": field_count, "fields": fields})

        elif action == "add_row":
            new_row = bom.create_bom_row()
            for field_name, value in p["data"].items():
                new_row.set_item(field_name, value)
            bom.add_item(new_row)
            mech_conn.zwm_db.refresh_bom()
            return _ok(f"成功添加明细表行: {p['data']}")

        elif action == "update_row":
            row = bom.get_item(p["row_index"])
            if not row:
                return _ok(f"未找到索引 {p['row_index']} 的行", found=False)
            for field_name, value in p["data"].items():
                row.set_item(field_name, value)
            mech_conn.zwm_db.refresh_bom()
            return _ok(f"成功更新明细表行 {p['row_index']}: {p['data']}")

        elif action == "insert_row":
            new_row = bom.create_bom_row()
            for field_name, value in p["data"].items():
                new_row.set_item(field_name, value)
            bom.insert_item(p["index"], new_row)
            mech_conn.zwm_db.refresh_bom()
            return _ok(f"成功在位置 {p['index']} 插入明细表行")

        elif action == "delete_row":
            bom.delete_item(p["index"])
            mech_conn.zwm_db.refresh_bom()
            return _ok(f"成功删除明细表行 {p['index']}")

        elif action == "set_field":
            row = bom.get_item(p["row_index"])
            if not row:
                return _ok(f"未找到索引 {p['row_index']} 的行", found=False)
            row.set_item(p["field_key"], p["value"])
            mech_conn.zwm_db.refresh_bom()
            return _ok(f"成功设置行 {p['row_index']} 的字段 '{p['field_key']}' = '{p['value']}'")

        elif action == "get_field":
            row = bom.get_item(p["row_index"])
            if not row:
                return _ok(f"未找到索引 {p['row_index']} 的行", found=False)
            label, name, value = row.get_item(p["field_index"])
            return _ok("获取成功", data={"row_index": p["row_index"], "field_index": p["field_index"],
                                         "label": label, "name": name, "value": value})

        elif action == "get_field_count":
            row = bom.get_item(p["row_index"])
            if not row:
                return _ok(f"未找到索引 {p['row_index']} 的行", found=False)
            count = row.get_item_count()
            return _ok("获取明细表字段数量成功", row_index=p["row_index"], count=count)

        return _err("明细表操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"明细表操作({action})", e)


@mcp.tool
def manage_mech_db(action: str, params: dict = None) -> str:
    """
    机械模块数据库操作（打开、保存、关闭）

    参数:
    - action: 操作类型，可选值:
      "open" - 打开机械模块文件: params可含 {file_path}（空或不传表示当前图纸）
      "save" - 保存机械模块数据: params可含 {flag}（默认33）
      "close" - 关闭机械模块连接
    - params: 操作参数
    """
    try:
        _, mech_conn = get_cad_connection()
        p = params or {}

        if action == "open":
            file_path = p.get("file_path", "")
            mech_conn.open_file(file_path)
            return _ok(f"成功打开机械模块文件: {file_path}" if file_path else "成功连接当前活动图纸")

        elif action == "save":
            mech_conn.open_file("")
            mech_conn.zwm_db.save(p.get("flag", 33))
            return _ok("机械模块数据保存成功")

        elif action == "close":
            mech_conn.close()
            return _ok("机械模块连接已关闭")

        return _err("机械数据库操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"机械数据库操作({action})", e)


@mcp.tool
def get_mech_info(info_type: str) -> str:
    """
    获取中望机械模块信息

    参数:
    - info_type: 信息类型，可选值:
      "version" - 机械模块版本
      "cad_path" - CAD安装路径
      "zwm_path" - 机械模块路径
      "style_path" - 样式文件路径
      "about" - 关于信息
    """
    try:
        _, mech_conn = get_cad_connection()
        if info_type == "version":
            return _ok("获取成功", version=mech_conn.zwm_app.get_version())
        elif info_type == "cad_path":
            return _ok("获取成功", path=mech_conn.zwm_app.get_cad_path())
        elif info_type == "zwm_path":
            return _ok("获取成功", path=mech_conn.zwm_app.get_zwm_path())
        elif info_type == "style_path":
            return _ok("获取成功", path=mech_conn.zwm_app.get_style_path())
        elif info_type == "about":
            return _ok("获取成功", about=mech_conn.zwm_app.get_about())
        return _err("获取信息", ValueError(f"不支持的信息类型: {info_type}"))
    except Exception as e:
        return _err(f"获取机械信息({info_type})", e)


@mcp.tool
def mech_doc(action: str, file_path: str, template: str = None) -> str:
    """
    中望机械文档操作

    参数:
    - action: 操作类型 "open"|"new"|"new_named"
      "open" - 打开文档
      "new" - 新建文档
      "new_named" - 基于模板新建: 需要template参数
    - file_path: 文件路径
    - template: 模板名称（new_named时使用）
    """
    try:
        _, mech_conn = get_cad_connection()
        if action == "open":
            mech_conn.zwm_app.open_doc(file_path)
            return _ok(f"成功打开文档: {file_path}")
        elif action == "new":
            mech_conn.zwm_app.new_doc(file_path)
            return _ok(f"成功新建文档: {file_path}")
        elif action == "new_named":
            mech_conn.zwm_app.new_named_doc(file_path, template)
            return _ok(f"成功新建命名文档: {file_path} (模板: {template})")
        return _err("机械文档操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"机械文档操作({action})", e)


@mcp.tool
def cad_environment_init(std_name: str) -> str:
    """
    初始化 CAD 环境（设置标准）

    参数:
    - std_name: 标准名称（如 "GB", "ISO", "DIN" 等）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.cad_environment_init(std_name)
        return _ok(f"CAD 环境初始化成功 (标准: {std_name})", standard=std_name)
    except Exception as e:
        return _err("CAD 环境初始化", e)


@mcp.tool
def get_balloon(text: str = "") -> str:
    """
    获取球标对象（用于零件序号标注）

    参数:
    - text: 气球文本（可选，默认为空）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        balloon = mech_conn.zwm_db.get_balloon(text)
        if balloon:
            return _ok(f"成功获取球标对象: {balloon}")
        else:
            return _ok("未获取到球标对象", found=False)
    except Exception as e:
        return _err("获取球标", e)


@mcp.tool
def create_frame(
    std_name: str = None,
    frame_size_name: str = None,
    orientation: str = "landscape",
    width: float = 0.0,
    height: float = 0.0,
    scale1: float = 1.0,
    scale2: float = 1.0,
    title_style_name: str = None,
    bom_style_name: str = None,
    dhl_style_name: str = "图样代号",
    fjl_style_name: str = "附加栏",
    csl_style_name: str = "包络环面蜗杆",
    ggl_style_name: str = "",
    frame_style_name: str = None,
    have_dhl: bool = False,
    have_fjl: bool = False,
    have_btl: bool = True,
    have_csl: bool = False,
    have_ggl: bool = False
) -> str:
    """
    新建图幅/图框（从XML配置读取默认样式）

    参数:
    - std_name: 标准名 (默认读取系统默认标准)
    - frame_size_name: 图幅尺寸名 (如 "A3", "A4"，默认读取标准默认图幅)
    - orientation: 方向（"landscape"或"portrait"，默认"landscape"）
    - width/height: 宽度/高度（默认0.0）
    - scale1/scale2: 比例 (默认1.0)
    - title_style_name: 标题栏样式名 (默认读取标准默认样式)
    - bom_style_name: 明细表样式名 (默认读取标准默认样式)
    - frame_style_name: 图框样式名 (默认读取标准默认样式)
    - have_dhl/have_fjl/have_btl/have_csl/have_ggl: 各栏开关
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")

        if not std_name:
            std_name = _get_default_standard()
        if not frame_size_name:
            frame_size_name = _get_default_frame_size(std_name)
        if not title_style_name:
            _, title_style_name = _get_title_styles(std_name)
        if not bom_style_name:
            _, bom_style_name = _get_bom_styles(std_name)
        if not frame_style_name:
            frame_style_name = _get_frame_styles(std_name, frame_size_name, orientation)

        frame_obj, name = mech_conn.zwm_db.get_next_frm_name()
        if not name:
            return _ok("获取新图框名称失败", created=False)

        mech_conn.zwm_db.switch_frame(name)
        frame = mech_conn.zwm_db.get_frame()

        if not frame:
            return _ok("获取新图框对象失败", created=False)

        fields = {
            "std_name": std_name, "frame_size_name": frame_size_name,
            "frame_style_name": frame_style_name, "orientation": orientation,
            "width": str(int(width)), "height": str(int(height)),
            "title_style_name": title_style_name, "bom_style_name": bom_style_name,
            "dhl_style_name": dhl_style_name, "fjl_style_name": fjl_style_name,
            "csl_style_name": csl_style_name, "ggl_style_name": ggl_style_name,
            "have_dhl": "1" if have_dhl else "0", "have_fjl": "1" if have_fjl else "0",
            "have_btl": "1" if have_btl else "0", "have_csl": "1" if have_csl else "0",
            "have_ggl": "1" if have_ggl else "0",
            "scale1": str(int(scale1)) if scale1 == int(scale1) else str(scale1),
            "scale2": str(int(scale2)) if scale2 == int(scale2) else str(scale2),
        }

        failed = []
        for key, val_str in fields.items():
            if key in ("width", "height", "have_dhl", "have_fjl", "have_btl", "have_csl", "have_ggl"):
                try:
                    setattr(frame, key, int(val_str))
                except (ValueError, Exception) as e:
                    failed.append({"key": key, "value": val_str, "error": str(e)})
            else:
                try:
                    setattr(frame, key, val_str)
                except Exception as e:
                    failed.append({"key": key, "value": val_str, "error": str(e)})

        mech_conn.zwm_db.build_frame(511)

        return _ok(
            f"成功创建图框: {name} (标准:{std_name}, 图幅:{frame_size_name})",
            frame_name=name, setattr_failures=failed,
        )
    except Exception as e:
        return _err("创建图框", e)


# ============================================================
# 主程序入口
# ============================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ZWCAD Mechanical MCP Server 启动中...")
    logger.info("=" * 60)
    logger.info("服务器已就绪，等待客户端连接...")
    mcp.run(transport="stdio", show_banner=False)

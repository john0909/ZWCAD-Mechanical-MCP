"""
ZWCAD Mechanical MCP Server - 基于 FastMCP 的中望机械CAD自动化服务
提供画直线、画圆、画弧、画椭圆、多段线、样条曲线、标注、图块、图层、
标题栏编辑、图框切换、明细表操作等功能
"""

import json
import math
import sys
import os
import logging
import pythoncom
import xml.etree.ElementTree as ET
from typing import Union, List, Optional, Any, Dict

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

from pydantic import BaseModel, Field
from fastmcp import FastMCP
from pyzwcad import ZwCAD, APoint
from pyzwcad.types import aDouble, aInt

# 按注册表 GUID 预加载 ZwmToolKit 类型库，规避 pyzwcadmech 默认文件系统 glob 在路径不匹配时静默失败
ZWM_TYPELIB_GUID = "{2F671C10-669F-11E7-91B7-BC5FF42AC839}"
try:
    import comtypes.client
    comtypes.client.GetModule((ZWM_TYPELIB_GUID, 1, 0))
    logger.info("预加载 ZwmToolKit 类型库成功 (GUID=%s)", ZWM_TYPELIB_GUID)
except Exception as _tlb_err:
    logger.warning(
        "预加载 ZwmToolKit 类型库失败: %s; 机械模块(标题栏/明细表/图框)可能不可用，"
        "可设置环境变量 PYZWCADMECH_TLB_PATH 指向 ZwmToolKit.tlb 后重启",
        _tlb_err,
    )

from pyzwcadmech import ZwCADMech

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


def _ok(message: str = None, **data) -> dict:
    if message:
        data["msg"] = message
    return data


def _typelib_state():
    """返回 (loaded, source, error)：ZwmToolKit 类型库加载状态。"""
    try:
        from pyzwcadmech import api as _zwm_api
        return _zwm_api.ZWM is not None, _zwm_api.TYPELIB_SOURCE, _zwm_api.TYPELIB_ERROR
    except Exception as exc:
        return False, None, str(exc)


def _err(action: str, e: Exception) -> dict:
    err_str = str(e)
    is_com = "CoInitialize" in err_str or "-2147221008" in err_str
    logger.error("tool_error action=%s error=%s", action, err_str)
    result = {"error": f"{action}失败: {err_str}", "code": "COM_INIT_ERROR" if is_com else "OPERATION_ERROR"}
    hints = []
    if is_com:
        hints.append("确保中望机械2026已启动; 重启ZWCAD和MCP Server; 检查pywin32/comtypes")
    _tlb_loaded, _tlb_src, _tlb_err = _typelib_state()
    if not _tlb_loaded:
        hints.append(
            "检测到 ZwmToolKit 类型库未加载，标题栏/明细表/图框等机械接口将不可用; "
            "可用 mech_diagnose 工具排查，或设置环境变量 PYZWCADMECH_TLB_PATH 指向 ZwmToolKit.tlb 后重启 MCP Server"
        )
    if hints:
        result["hint"] = "; ".join(hints)
    return result


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


def _to_dict(params):
    if hasattr(params, "model_dump"):
        return params.model_dump(exclude_unset=True)
    elif hasattr(params, "dict"):
        return params.dict(exclude_unset=True)
    return params

def _check_params(params: dict, required: list, context: str) -> dict:
    """Return error string if any required key is missing, else None."""
    missing = [k for k in required if k not in params]
    if missing:
        return _err(context, ValueError(f"缺少必需参数: {', '.join(missing)}"))
    return None



# ============================================================
# Pydantic Models for Tools
# ============================================================

class LineParams(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    z1: Optional[float] = 0.0
    z2: Optional[float] = 0.0

class CircleParams(BaseModel):
    center_x: float
    center_y: float
    radius: float
    center_z: Optional[float] = 0.0

class ArcParams(BaseModel):
    center_x: float
    center_y: float
    radius: float
    start_angle: float
    end_angle: float
    center_z: Optional[float] = 0.0

class EllipseParams(BaseModel):
    center_x: float
    center_y: float
    major_axis_x: float
    major_axis_y: float
    radius_ratio: float
    center_z: Optional[float] = 0.0
    major_axis_z: Optional[float] = 0.0

class LwPolylineParams(BaseModel):
    vertices: List[Union[List[float], float]]
    closed: Optional[bool] = False

class PolylineParams(BaseModel):
    vertices: List[Union[List[float], float]]
    closed: Optional[bool] = False

class SplineParams(BaseModel):
    fit_points: List[Union[List[float], float]]
    start_tangent_x: Optional[float] = 0.0
    start_tangent_y: Optional[float] = 0.0
    start_tangent_z: Optional[float] = 0.0
    end_tangent_x: Optional[float] = 0.0
    end_tangent_y: Optional[float] = 0.0
    end_tangent_z: Optional[float] = 0.0

class PointParams(BaseModel):
    x: float
    y: float
    z: Optional[float] = 0.0

class RayParams(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    z1: Optional[float] = 0.0
    z2: Optional[float] = 0.0

class XlineParams(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    z1: Optional[float] = 0.0
    z2: Optional[float] = 0.0

class MlineParams(BaseModel):
    vertices: List[Union[List[float], float]]

class Polyline3DParams(BaseModel):
    vertices: List[Union[List[float], float]]

DrawEntityParams = Union[
    LineParams, CircleParams, ArcParams, EllipseParams,
    LwPolylineParams, PolylineParams, SplineParams, PointParams,
    RayParams, XlineParams, MlineParams, Polyline3DParams,
    Dict[str, Any]
]

class BoxParams(BaseModel):
    origin_x: float
    origin_y: float
    origin_z: float
    length: float
    width: float
    height: float

class CylinderParams(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    radius: float
    height: float

class ConeParams(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    base_radius: float
    height: float

class SphereParams(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    radius: float

class TorusParams(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    torus_radius: float
    tube_radius: float

class WedgeParams(BaseModel):
    center_x: float
    center_y: float
    center_z: float
    length: float
    width: float
    height: float

class Face3DParams(BaseModel):
    x1: float
    y1: float
    z1: float
    x2: float
    y2: float
    z2: float
    x3: float
    y3: float
    z3: float
    x4: Optional[float] = None
    y4: Optional[float] = None
    z4: Optional[float] = None

Draw3DSolidParams = Union[
    BoxParams, CylinderParams, ConeParams, SphereParams, TorusParams, WedgeParams, Face3DParams, Dict[str, Any]
]

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

_DRAW_REQUIRED = {
    "line": ["x1", "y1", "x2", "y2"],
    "circle": ["center_x", "center_y", "radius"],
    "arc": ["center_x", "center_y", "radius", "start_angle", "end_angle"],
    "ellipse": ["center_x", "center_y", "major_axis_x", "major_axis_y", "radius_ratio"],
    "lwpolyline": ["vertices"], "polyline": ["vertices"],
    "spline": ["fit_points"], "point": ["x", "y"],
    "ray": ["x1", "y1", "x2", "y2"], "xline": ["x1", "y1", "x2", "y2"],
    "mline": ["vertices"], "3d_polyline": ["vertices"],
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

_3D_REQUIRED = {
    "3d_face": ["x1", "y1", "z1", "x2", "y2", "z2", "x3", "y3", "z3"],
    "box": ["origin_x", "origin_y", "origin_z", "length", "width", "height"],
    "cylinder": ["center_x", "center_y", "center_z", "radius", "height"],
    "cone": ["center_x", "center_y", "center_z", "base_radius", "height"],
    "sphere": ["center_x", "center_y", "center_z", "radius"],
    "torus": ["center_x", "center_y", "center_z", "torus_radius", "tube_radius"],
    "wedge": ["center_x", "center_y", "center_z", "length", "width", "height"],
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

_DIM_REQUIRED = {
    "aligned": ["x1", "y1", "x2", "y2", "text_x", "text_y"],
    "rotated": ["x1", "y1", "x2", "y2", "text_x", "text_y", "rotation_angle"],
    "diametric": ["chord_x", "chord_y", "far_chord_x", "far_chord_y", "leader_length"],
    "radial": ["center_x", "center_y", "chord_x", "chord_y", "leader_length"],
    "angular": ["vertex_x", "vertex_y", "first_x", "first_y", "second_x", "second_y", "text_x", "text_y"],
    "ordinate": ["def_x", "def_y", "leader_x", "leader_y", "use_x_axis"],
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

_ANNO_REQUIRED = {
    "text": ["text", "x", "y"], "mtext": ["text", "x", "y"],
    "leader": ["points"], "tolerance": ["text", "x", "y"],
    "mleader": ["points"], "hatch": ["pattern_name"],
    "table": ["x", "y", "rows", "cols", "row_height", "col_width"],
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
        cur = obj.Center
        obj.Center = APoint(p.get("center_x", cur[0]), p.get("center_y", cur[1]), p.get("center_z", cur[2]))
        updated.append("Center updated")
    return updated


def _modify_arc_impl(zcad, obj, p):
    updated = []
    if "radius" in p:
        obj.Radius = p["radius"]; updated.append(f"Radius={p['radius']}")
    if "center_x" in p or "center_y" in p or "center_z" in p:
        cur = obj.Center
        obj.Center = APoint(p.get("center_x", cur[0]), p.get("center_y", cur[1]), p.get("center_z", cur[2]))
        updated.append("Center updated")
    if "start_angle" in p:
        obj.StartAngle = p["start_angle"]; updated.append(f"StartAngle={p['start_angle']:.4f}")
    if "end_angle" in p:
        obj.EndAngle = p["end_angle"]; updated.append(f"EndAngle={p['end_angle']:.4f}")
    return updated


def _modify_line_impl(zcad, obj, p):
    updated = []
    if "x1" in p or "y1" in p or "z1" in p:
        cur = obj.StartPoint
        obj.StartPoint = APoint(p.get("x1", cur[0]), p.get("y1", cur[1]), p.get("z1", cur[2]))
        updated.append("StartPoint updated")
    if "x2" in p or "y2" in p or "z2" in p:
        cur = obj.EndPoint
        obj.EndPoint = APoint(p.get("x2", cur[0]), p.get("y2", cur[1]), p.get("z2", cur[2]))
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
    if "x" in p or "y" in p or "z" in p:
        cur = obj.InsertionPoint
        obj.InsertionPoint = APoint(p.get("x", cur[0]), p.get("y", cur[1]), p.get("z", cur[2]))
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
        cur = obj.StartTangent
        obj.StartTangent = APoint(p.get("start_tangent_x", cur[0]), p.get("start_tangent_y", cur[1]), 0)
        updated.append("StartTangent updated")
    if "end_tangent_x" in p or "end_tangent_y" in p:
        cur = obj.EndTangent
        obj.EndTangent = APoint(p.get("end_tangent_x", cur[0]), p.get("end_tangent_y", cur[1]), 0)
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
def draw_entity(entity_type: str, params: DrawEntityParams, layer: str = "0") -> dict:
    """绘制2D实体。entity_type及params([]=可选):
    line:{x1,y1,x2,y2,[z1,z2]} | circle:{center_x,center_y,radius,[center_z]}
    arc:{center_x,center_y,radius,start_angle,end_angle}(弧度)
    ellipse:{center_x,center_y,major_axis_x,major_axis_y,radius_ratio}
    lwpolyline:{vertices:[[x,y],...]，[closed]} | polyline:{vertices:[[x,y,z],...]，[closed]}
    spline:{fit_points:[[x,y,z],...]} | point:{x,y,[z]}
    ray/xline:{x1,y1,x2,y2} | mline/3d_polyline:{vertices:[[x,y,z],...]}"""
    try:
        params = _to_dict(params)
        logger.info("tool_call draw_entity type=%s layer=%s", entity_type, layer)
        zcad_conn, _ = get_cad_connection()
        fn = _DRAW_DISPATCH.get(entity_type)
        if not fn:
            return _err("绘图", ValueError(f"不支持的实体类型: {entity_type}，支持: {', '.join(_DRAW_DISPATCH.keys())}"))
        err = _check_params(params, _DRAW_REQUIRED.get(entity_type, []), f"绘制{entity_type}")
        if err:
            return err
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(msg=desc, handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"绘制{entity_type}", e)


@mcp.tool
def draw_batch(entities: list, layer: str = "0") -> dict:
    """批量绘制多个实体，减少交互轮次。entities为dict列表，每个dict含entity_type和params，可选layer。
    示例: [{"entity_type":"line","params":{"x1":0,"y1":0,"x2":10,"y2":10}},{"entity_type":"circle","params":{"center_x":5,"center_y":5,"radius":3}}]"""
    try:
        logger.info("tool_call draw_batch count=%d", len(entities))
        zcad_conn, _ = get_cad_connection()
        results = []
        for i, e in enumerate(entities):
            et = e.get("entity_type")
            p = e.get("params", {})
            lyr = e.get("layer", layer)
            fn = _DRAW_DISPATCH.get(et) or _3D_DISPATCH.get(et)
            if not fn:
                results.append({"index": i, "error": f"不支持的类型: {et}"})
                continue
            req = _DRAW_REQUIRED.get(et) or _3D_REQUIRED.get(et, [])
            missing = [k for k in req if k not in p]
            if missing:
                results.append({"index": i, "error": f"缺少参数: {','.join(missing)}"})
                continue
            try:
                obj, desc = fn(zcad_conn.model, p, lyr)
                results.append({"index": i, "handle": obj.Handle})
            except Exception as ex:
                results.append({"index": i, "error": str(ex)})
        ok_count = sum(1 for r in results if "handle" in r)
        return _ok(total=len(entities), success=ok_count, results=results)
    except Exception as e:
        return _err("批量绘图", e)


@mcp.tool
def draw_3d_solid(solid_type: str, params: Draw3DSolidParams, layer: str = "0") -> dict:
    """绘制3D实体。solid_type及params([]=可选):
    box:{origin_x,origin_y,origin_z,length,width,height}
    cylinder:{center_x,center_y,center_z,radius,height}
    cone:{center_x,center_y,center_z,base_radius,height}
    sphere:{center_x,center_y,center_z,radius}
    torus:{center_x,center_y,center_z,torus_radius,tube_radius}
    wedge:{center_x,center_y,center_z,length,width,height}
    3d_face:{x1,y1,z1,x2,y2,z2,x3,y3,z3,[x4,y4,z4]}"""
    try:
        params = _to_dict(params)
        zcad_conn, _ = get_cad_connection()
        fn = _3D_DISPATCH.get(solid_type)
        if not fn:
            return _err("3D绘图", ValueError(f"不支持的3D类型: {solid_type}，支持: {', '.join(_3D_DISPATCH.keys())}"))
        err = _check_params(params, _3D_REQUIRED.get(solid_type, []), f"绘制{solid_type}")
        if err:
            return err
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(msg=desc, handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"绘制{solid_type}", e)


@mcp.tool
def add_annotation(annotation_type: str, params: dict, layer: str = "0") -> dict:
    """添加注释对象。annotation_type及params([]=可选):
    text:{text,x,y,[z,height]} | mtext:{text,x,y,[z,width,height]}
    leader:{points:[[x,y,z],...]，[annotation_type:0/1/2]}
    tolerance:{text,x,y,[z,dir_x,dir_y,dir_z]}
    mleader:{points:[[x,y,z],...]，[text,text_height]}
    hatch:{pattern_name,[pattern_type,pattern_scale,pattern_angle]}
    table:{x,y,rows,cols,row_height,col_width}"""
    try:
        zcad_conn, _ = get_cad_connection()
        fn = _ANNO_DISPATCH.get(annotation_type)
        if not fn:
            return _err("添加注释", ValueError(f"不支持的注释类型: {annotation_type}，支持: {', '.join(_ANNO_DISPATCH.keys())}"))
        err = _check_params(params, _ANNO_REQUIRED.get(annotation_type, []), f"添加{annotation_type}")
        if err:
            return err
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(msg=desc, handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"添加{annotation_type}", e)


@mcp.tool
def add_dimension(dim_type: str, params: dict, layer: str = "0") -> dict:
    """添加标注。dim_type及params(z坐标均可选):
    aligned:{x1,y1,x2,y2,text_x,text_y}
    rotated:{x1,y1,x2,y2,text_x,text_y,rotation_angle}
    diametric:{chord_x,chord_y,far_chord_x,far_chord_y,leader_length}
    radial:{center_x,center_y,chord_x,chord_y,leader_length}
    angular:{vertex_x,vertex_y,first_x,first_y,second_x,second_y,text_x,text_y}
    ordinate:{def_x,def_y,leader_x,leader_y,use_x_axis}"""
    try:
        zcad_conn, _ = get_cad_connection()
        fn = _DIM_DISPATCH.get(dim_type)
        if not fn:
            return _err("添加标注", ValueError(f"不支持的标注类型: {dim_type}，支持: {', '.join(_DIM_DISPATCH.keys())}"))
        err = _check_params(params, _DIM_REQUIRED.get(dim_type, []), f"添加{dim_type}标注")
        if err:
            return err
        obj, desc = fn(zcad_conn.model, params, layer)
        return _ok(msg=desc, handle=obj.Handle, layer=layer)
    except Exception as e:
        return _err(f"添加{dim_type}标注", e)


@mcp.tool
def insert_block(block_name: str, x: float, y: float, z: float = 0,
                 x_scale: float = 1.0, y_scale: float = 1.0, z_scale: float = 1.0,
                 rotation: float = 0, layer: str = "0") -> dict:
    """在指定位置插入图块。rotation为弧度。"""
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        ref = zcad_conn.model.InsertBlock(point, block_name, x_scale, y_scale, z_scale, rotation)
        ref.Layer = layer
        return _ok(handle=ref.Handle, block=block_name, layer=layer)
    except Exception as e:
        return _err("插入图块", e)


@mcp.tool
def transform_entity(action: str, params: dict,
                     object_type: str = None, property_name: str = None,
                     property_value: str = None, handle: str = None) -> dict:
    """对实体执行变换操作。通过handle(优先)或object_type+property_name+property_value定位实体。
    action及params([]=可选):
    copy:{from_x,from_y,to_x,to_y,[z]} | move:{from_x,from_y,to_x,to_y,[z]}
    rotate:{base_x,base_y,angle}(弧度) | mirror:{x1,y1,x2,y2}
    scale:{base_x,base_y,factor} | delete:{}
    array_polar:{center_x,center_y,count,[fill_angle]}
    array_rectangular:{num_rows,num_cols,row_spacing,col_spacing}"""
    try:
        logger.info("tool_call transform_entity action=%s handle=%s", action, handle)
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type=object_type,
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _err("变换实体", ValueError("未找到符合条件的对象"))
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
                  property_value: str = None, handle: str = None) -> dict:
    """修改实体几何属性。定位参数同transform_entity。entity_type及params(均可选除特别说明):
    circle:{radius,center_x,center_y,center_z}
    arc:{radius,center_x,center_y,start_angle,end_angle}
    line:{x1,y1,z1,x2,y2,z2} | text:{text,height,rotation,stylename,x,y}
    mtext:{text,height,width,rotation,attachment_point}
    polyline:{closed,constant_width,elevation} | spline:{closed,fit_tolerance,start_tangent_x/y,end_tangent_x/y}
    offset:{distance}(必需) | explode:{}"""
    try:
        logger.info("tool_call modify_entity type=%s handle=%s", entity_type, handle)
        zcad_conn, _ = get_cad_connection()
        if entity_type == "offset":
            obj = _find_entity(zcad_conn, object_type=object_type,
                               property_name=property_name, property_value=property_value,
                               handle=handle)
            if not obj:
                return _err("偏移实体", ValueError("未找到符合条件的对象"))
            if not hasattr(obj, 'Offset'):
                return _ok("此对象不支持偏移操作")
            result = obj.Offset(params["distance"])
            return _ok(f"成功偏移实体, 距离={params['distance']}")

        if entity_type == "explode":
            obj = _find_entity(zcad_conn, object_type=object_type,
                               property_name=property_name, property_value=property_value,
                               handle=handle)
            if not obj:
                return _err("分解实体", ValueError("未找到符合条件的对象"))
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
            return _err(f"修改{entity_type}", ValueError("未找到符合条件的对象"))
        updated = modify_fn(zcad_conn, obj, params)
        if updated and hasattr(obj, 'Update'):
            obj.Update()
        return _ok(f"成功修改{entity_type}: {', '.join(updated)}") if updated else _ok("未提供修改参数")
    except Exception as e:
        return _err(f"修改{entity_type}", e)


@mcp.tool
def get_entity_info(handle: str = None, object_type: str = None,
                    property_name: str = None, property_value: str = None) -> dict:
    """获取实体详细信息（属性、几何数据、边界框）。定位参数同transform_entity。"""
    try:
        logger.info("tool_call get_entity_info handle=%s", handle)
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
            return _err("获取实体信息", ValueError("未找到实体"))

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

        return _ok(data=info)
    except Exception as e:
        return _err("获取实体信息", e)


@mcp.tool
def set_entity_properties(layer: str = None, color: int = None,
                          linetype: str = None, linetype_scale: float = None,
                          lineweight: float = None, visible: bool = None,
                          object_type: str = None, property_name: str = "Layer",
                          property_value: str = "", handle: str = None) -> dict:
    """设置实体通用属性（layer/color/linetype等）。定位参数同transform_entity。"""
    try:
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type=object_type,
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _err("设置实体属性", ValueError("未找到符合条件的对象"))
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
                property_value: str = None, handle: str = None) -> dict:
    """查找符合条件的第一个对象。定位参数同transform_entity。"""
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
            return _ok(found=True, data=obj_info)
        else:
            return _err("查找对象", ValueError("未找到匹配对象"))
    except Exception as e:
        return _err("查找对象", e)


@mcp.tool
def get_objects_in_model(object_type: str = None, limit: int = 500) -> dict:
    """获取模型空间中的对象列表。object_type可选过滤，limit默认500。"""
    try:
        zcad_conn, _ = get_cad_connection()
        objects = []
        count = 0
        for obj in zcad_conn.iter_objects(object_type, limit=limit):
            obj_info = {"object_name": obj.ObjectName}
            if hasattr(obj, 'Handle'):
                obj_info['handle'] = obj.Handle
            if hasattr(obj, 'Layer'):
                obj_info['layer'] = obj.Layer
            objects.append(obj_info)
            count += 1
        truncated = (limit is not None and count >= limit)
        return _ok(total_count=count, truncated=truncated, data=objects)
    except Exception as e:
        return _err("获取对象列表", e)


@mcp.tool
def zoom(mode: str, params: dict = None) -> dict:
    """视图缩放。mode: extents|all|previous(无需params),
    window:{x1,y1,x2,y2}, center:{center_x,center_y,[magnify]},
    scale:{scale,[scale_type:0全图/1当前]}"""
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
                 properties: dict = None) -> dict:
    """管理图层/线型/文字样式/标注样式。style_type: layer|linetype|textstyle|dimstyle
    action: list|add|set_active|set_properties。properties按style_type不同:
    layer: {color,linetype,on,locked,freeze}
    textstyle: {font_file,big_font_file,height,width,oblique_angle}
    linetype add: {filename}(默认acad.lin)"""
    try:
        logger.info("tool_call manage_style type=%s action=%s name=%s", style_type, action, name)
        zcad_conn, _ = get_cad_connection()
        props = properties or {}

        if style_type == "layer":
            if action == "list":
                layers = []
                detail = (properties or {}).get("detail", False)
                for lay in zcad_conn.iter_layers():
                    info = {"name": lay.Name, "color": lay.color}
                    if detail:
                        info.update({"on": lay.LayerOn, "linetype": lay.Linetype,
                                     "locked": lay.Lock, "freeze": lay.Freeze})
                    layers.append(info)
                return _ok(data=layers)
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
                return _ok(data=lts)
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
                return _ok(data=styles)
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
                return _ok(data=styles)
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
def manage_view(action: str, name: str = None, params: dict = None) -> dict:
    """管理布局和视图。action: list_layouts|get_active_layout|add_layout|set_active_layout|list_views|add_view
    |set_active_space|get_active_space。
    add/set_active/需要name参数。
    set_active_space的params:{space:"model"|"paper"}。"""
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
            return _ok(data=views)

        elif action == "add_view":
            zcad_conn.doc.Views.Add(name)
            return _ok(f"成功创建视图: {name}")

        elif action == "set_active_space":
            space = p["space"]
            if space == "model":
                zcad_conn.doc.ActiveSpace = 1
            elif space == "paper":
                zcad_conn.doc.ActiveSpace = 0
            else:
                return _err("视图管理", ValueError(f"不支持的空间类型: {space}，支持: model/paper"))
            return _ok(f"成功切换到{'模型' if space == 'model' else '图纸'}空间")

        elif action == "get_active_space":
            space_val = zcad_conn.doc.ActiveSpace
            space_name = "model" if space_val == 1 else "paper"
            return _ok(data={"space": space_name, "value": space_val})

        return _err("视图管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"视图管理({action})", e)


@mcp.tool
def manage_document(action: str, params: dict = None) -> dict:
    """文档管理。action及params:
    new(无需params) | save:{file_path} | close:{[save_changes]}
    info/list(无需params) | activate:{name}
    export:{filename,[extension]} | import:{filename,[x,y,z,scale_factor]}
    plot:{plot_file,[plot_config]}
    regen:{[scope:0=AllViewports/1=ActiveViewport]}
    start_undo/end_undo(无需params)
    wblock:{file_name,[selection_set_name]}"""
    try:
        logger.info("tool_call manage_document action=%s", action)
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
            return _ok(data=docs)

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
            try:
                zcad_conn.doc.Export(p["filename"], p.get("extension", "DWG"), sel)
            finally:
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

        elif action == "regen":
            scope = p.get("scope", 0)
            zcad_conn.doc.Regen(scope)
            return _ok(f"重生成完成 (scope={scope})")

        elif action == "start_undo":
            zcad_conn.doc.StartUndoMark()
            return _ok("撤消组标记已开始")

        elif action == "end_undo":
            zcad_conn.doc.EndUndoMark()
            return _ok("撤消组标记已结束")

        elif action == "wblock":
            file_name = p["file_name"]
            sel_name = p.get("selection_set_name")
            if sel_name:
                sel = zcad_conn.doc.SelectionSets.Item(sel_name)
                zcad_conn.doc.Wblock(file_name, sel)
            else:
                sel = _ensure_selection_set(zcad_conn, "__wblock_tmp__")
                sel.Select(5)
                try:
                    zcad_conn.doc.Wblock(file_name, sel)
                finally:
                    try:
                        sel.Delete()
                    except Exception:
                        pass
            return _ok(f"成功写块到文件: {file_name}")

        return _err("文档管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"文档管理({action})", e)


@mcp.tool
def manage_table(action: str, params: dict,
                 object_type: str = None, property_name: str = None,
                 property_value: str = None, handle: str = None) -> dict:
    """操作CAD表格对象。定位参数同transform_entity。action及params:
    set_cell:{row,col,text} | get_cell:{row,col}
    insert_rows:{row_index,[count,height]} | delete_rows:{row_index,[count]}
    set_column_width:{col,width} | set_row_height:{row,height}
    merge_cells:{min_row,max_row,min_col,max_col}"""
    try:
        zcad_conn, _ = get_cad_connection()
        obj = _find_entity(zcad_conn, object_type="Table",
                           property_name=property_name, property_value=property_value,
                           handle=handle)
        if not obj:
            return _err("操作表格", ValueError("未找到符合条件的表格"))
        p = params

        if action == "set_cell":
            obj.SetText(p["row"], p["col"], p["text"])
            return _ok(f"成功设置表格[{p['row']},{p['col']}] = '{p['text']}'")
        elif action == "get_cell":
            text = obj.GetText(p["row"], p["col"])
            return _ok(row=p["row"], col=p["col"], text=text)
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


def _read_pickfirst_selection(zcad_conn, max_items=500):
    """读取 CAD 界面中用户当前选中的实体（Pickfirst 选择集）。"""
    try:
        sel = zcad_conn.doc.PickfirstSelectionSet
        count = sel.Count
        items = _selection_set_items(sel, max_items) if count else []
        return count, items
    except Exception:
        return 0, []


@mcp.tool
def select_entities(action: str, params: dict = None) -> dict:
    """选择集操作。action及params:
    select:{mode}(0=Window/1=Crossing需{x1,y1,x2,y2},2=Previous/4=Last/5=All无需坐标,[name,filter:{entity_type,layer,color},return_items])
    by_polygon:{mode(0=Fence/1=WinPoly/2=CrossPoly),points,[name,filter,return_items]}
    get_items:{[name,max_items]} | get_picked:{[max_items]}
    list/clear/delete:{[name]}"""
    try:
        logger.info("tool_call select_entities action=%s", action)
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
                return _err("获取选择集", ValueError(f"选择集 '{sel_name}' 不存在"))
            max_items = p.get("max_items", 200)
            items = _selection_set_items(sel, max_items)
            return _ok(count=sel.Count, items=items)

        elif action == "get_picked":
            max_items = p.get("max_items", 200)
            count, items = _read_pickfirst_selection(zcad_conn, max_items)
            if count == 0:
                return _ok(msg="当前没有选中的实体", count=0, items=[])
            return _ok(count=count, truncated=(count >= max_items), items=items)

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
                return _err("清空选择集", ValueError(f"选择集 '{sel_name}' 不存在"))

        elif action == "delete":
            sel_name = p.get("name", "SS1")
            try:
                sel = zcad_conn.doc.SelectionSets.Item(sel_name)
                sel.Delete()
                return _ok(f"已删除选择集: {sel_name}")
            except Exception:
                return _err("删除选择集", ValueError(f"选择集 '{sel_name}' 不存在"))

        return _err("选择集操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"选择集操作({action})", e)


@mcp.tool
def manage_block(action: str, name: str = None, params: dict = None,
                 object_type: str = None, property_name: str = None,
                 property_value: str = None, handle: str = None) -> dict:
    """图块管理。action: list|info(需name)|create(需name,[x,y,z])|get_attributes(定位参数同transform_entity)。"""
    try:
        zcad_conn, _ = get_cad_connection()
        p = params or {}

        if action == "list":
            blocks = []
            detail = params.get("detail", False) if params else False
            for blk in zcad_conn.doc.Blocks:
                info = {"name": blk.Name, "count": blk.Count}
                if detail:
                    info["is_layout"] = blk.IsLayout
                    info["is_xref"] = blk.IsXRef
                    if hasattr(blk, 'Origin'):
                        try: info['origin'] = list(blk.Origin)
                        except Exception: pass
                blocks.append(info)
            return _ok(data=blocks)

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
            return _ok(data=info)

        elif action == "create":
            point = APoint(p.get("x", 0), p.get("y", 0), p.get("z", 0))
            blk = zcad_conn.doc.Blocks.Add(point, name)
            return _ok(f"成功创建图块定义: {name}", name=name)

        elif action == "get_attributes":
            obj = _find_entity(zcad_conn, object_type="BlockReference",
                               property_name=property_name, property_value=property_value,
                               handle=handle)
            if not obj:
                return _err("获取图块属性", ValueError("未找到符合条件的图块引用"))
            attrs = obj.GetAttributes()
            result = []
            for attr in attrs:
                result.append({"tag": attr.TagString if hasattr(attr, 'TagString') else "",
                                "text": attr.TextString if hasattr(attr, 'TextString') else ""})
            return _ok(data=result)

        return _err("图块管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"图块管理({action})", e)


@mcp.tool
def get_variable(name: str) -> dict:
    """获取系统变量值（如DIMSCALE, LTSCALE, OSMODE等）。"""
    try:
        zcad_conn, _ = get_cad_connection()
        value = zcad_conn.doc.GetVariable(name)
        return _ok(name=name, value=value)
    except Exception as e:
        return _err("获取系统变量", e)


@mcp.tool
def set_variable(name: str, value) -> dict:
    """设置系统变量值。"""
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.SetVariable(name, value)
        return _ok(f"成功设置系统变量: {name} = {value}")
    except Exception as e:
        return _err("设置系统变量", e)


@mcp.tool
def get_app_info(scope: str = "cad") -> dict:
    """获取应用信息。scope: cad(ZWCAD版本/路径/窗口)|mech_version|mech_cad_path|mech_zwm_path|mech_style_path|mech_about"""
    try:
        zcad_conn, mech_conn = get_cad_connection()
        if scope == "cad":
            app = zcad_conn.app
            info = {}
            for prop in ['Version', 'Name', 'Path', 'FullName', 'Caption',
                          'WindowState', 'Visible', 'Width', 'Height']:
                if hasattr(app, prop):
                    try:
                        info[prop.lower()] = getattr(app, prop)
                    except Exception:
                        pass
            return _ok(data=info)
        elif scope == "mech_version":
            return _ok(version=mech_conn.zwm_app.get_version())
        elif scope == "mech_cad_path":
            return _ok(path=mech_conn.zwm_app.get_cad_path())
        elif scope == "mech_zwm_path":
            return _ok(path=mech_conn.zwm_app.get_zwm_path())
        elif scope == "mech_style_path":
            return _ok(path=mech_conn.zwm_app.get_style_path())
        elif scope == "mech_about":
            return _ok(about=mech_conn.zwm_app.get_about())
        return _err("获取信息", ValueError(f"不支持的scope: {scope}"))
    except Exception as e:
        return _err(f"获取应用信息({scope})", e)


@mcp.tool
def mech_diagnose() -> dict:
    """诊断机械模块连接与 ZwmToolKit 类型库加载状态。

    逐项探测：类型库加载、ZWCAD 应用、ZwmApp、ZwmDb、标题栏获取(依赖类型库)，返回各探测项状态与修复建议。
    """
    result = {}

    loaded, source, tlb_err = _typelib_state()
    result["typelib_loaded"] = loaded
    result["typelib_source"] = source
    if tlb_err:
        result["typelib_error"] = str(tlb_err)

    try:
        zcad_conn, mech_conn = get_cad_connection()
    except Exception as e:
        result["cad_connection_ok"] = False
        result["cad_connection_error"] = str(e)
        return _ok("诊断完成(连接建立失败)", **result)

    try:
        _ = mech_conn.app
        result["cad_app_ok"] = True
    except Exception as e:
        result["cad_app_ok"] = False
        result["cad_app_error"] = str(e)

    try:
        _ = mech_conn.zwm_app
        result["zwm_app_ok"] = True
    except Exception as e:
        result["zwm_app_ok"] = False
        result["zwm_app_error"] = str(e)

    try:
        mech_conn.open_file("")
        result["zwm_db_ok"] = True
    except Exception as e:
        result["zwm_db_ok"] = False
        result["zwm_db_error"] = str(e)

    if result.get("zwm_db_ok"):
        try:
            title = mech_conn.get_title()
            result["title_probe_ok"] = title is not None
        except Exception as e:
            result["title_probe_ok"] = False
            result["title_probe_error"] = str(e)

    if not loaded:
        result["hint"] = (
            "ZwmToolKit 类型库未加载，标题栏/明细表/图框等机械接口不可用。"
            "修复方法：1) 确认中望机械已正常安装；"
            "2) 设置环境变量 PYZWCADMECH_TLB_PATH 指向 ZwmToolKit.tlb "
            "(如 C:\\Program Files\\ZWSOFT\\ZWCAD Mechanical 2026 Chs\\Zwcadm\\ZwmToolKit.tlb)；"
            "3) 重启 MCP Server。"
        )
    return _ok("诊断完成", **result)


# ############################################################
#                   中望机械特有工具（合并后）
# ############################################################


@mcp.tool
def manage_title_block(action: str, params: dict = None) -> dict:
    """标题栏管理。action: get_info|get_field_count(无需params),
    set_field:{field_name,value} | update_batch:{fields:{name:val,...}}
    get_field_by_index:{index}"""
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        title = mech_conn.get_title()
        p = params or {}

        if not title:
            return _err("标题栏操作", ValueError("未找到标题栏对象"))

        if action == "get_info":
            items = []
            count = title.get_item_count()
            for i in range(count):
                label, name, value = title.get_item(i)
                item = {"index": i, "label": label, "value": value}
                if name != label:
                    item["name"] = name
                items.append(item)
            return _ok(data=items)

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
            f = {"index": p["index"], "label": label, "value": value}
            if name != label:
                f["name"] = name
            return _ok(data=f)

        return _err("标题栏操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"标题栏操作({action})", e)


@mcp.tool
def manage_frame(action: str, params: dict = None) -> dict:
    """图框管理。action: list|get_info|get_count|get_next_name|refresh(无需params),
    get_name_by_index:{index} | get_name_by_point:{x,y,[z]}
    switch:{frame_name} | update:{width,height,orientation,scale1,scale2,...}"""
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
                return _err("图框操作", ValueError("未找到图框对象"))
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
            return _ok(data=result)

        elif action == "switch":
            mech_conn.zwm_db.switch_frame(p["frame_name"])
            return _ok(f"成功切换到图框: {p['frame_name']}")

        elif action == "update":
            frame = mech_conn.zwm_db.get_frame()
            if not frame:
                return _err("图框操作", ValueError("未找到图框对象"))
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
def manage_bom(action: str, params: dict = None) -> dict:
    """明细表(BOM)管理。action及params:
    get_row_count/refresh(无需params)
    get_row:{row_index} | add_row:{data:{name:val,...}}
    update_row:{row_index,data:{...}} | insert_row:{index,data:{...}}
    delete_row:{index} | set_field:{row_index,field_key,value}
    get_field:{row_index,field_index} | get_field_count:{row_index}"""
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        p = params or {}

        if action == "refresh":
            mech_conn.zwm_db.refresh_bom()
            return _ok("明细表刷新成功")

        if not bom:
            return _err("明细表操作", ValueError("未找到明细表对象"))

        if action == "get_row_count":
            count = bom.get_item_count()
            return _ok("获取明细表行数成功", count=count)

        elif action == "get_row":
            row = bom.get_item(p["row_index"])
            if not row:
                return _err("明细表操作", ValueError(f"未找到索引 {p['row_index']} 的行"))
            fields = []
            field_count = row.get_item_count()
            for i in range(field_count):
                label, name, value = row.get_item(i)
                f = {"field_index": i, "label": label, "value": value}
                if name != label:
                    f["name"] = name
                fields.append(f)
            return _ok(data={"row_index": p["row_index"], "field_count": field_count, "fields": fields})

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
                return _err("明细表操作", ValueError(f"未找到索引 {p['row_index']} 的行"))
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
                return _err("明细表操作", ValueError(f"未找到索引 {p['row_index']} 的行"))
            row.set_item(p["field_key"], p["value"])
            mech_conn.zwm_db.refresh_bom()
            return _ok(f"成功设置行 {p['row_index']} 的字段 '{p['field_key']}' = '{p['value']}'")

        elif action == "get_field":
            row = bom.get_item(p["row_index"])
            if not row:
                return _err("明细表操作", ValueError(f"未找到索引 {p['row_index']} 的行"))
            label, name, value = row.get_item(p["field_index"])
            f = {"row_index": p["row_index"], "field_index": p["field_index"], "label": label, "value": value}
            if name != label:
                f["name"] = name
            return _ok(data=f)

        elif action == "get_field_count":
            row = bom.get_item(p["row_index"])
            if not row:
                return _err("明细表操作", ValueError(f"未找到索引 {p['row_index']} 的行"))
            count = row.get_item_count()
            return _ok("获取明细表字段数量成功", row_index=p["row_index"], count=count)

        return _err("明细表操作", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"明细表操作({action})", e)


@mcp.tool
def manage_mech_db(action: str, params: dict = None) -> dict:
    """机械模块数据库操作。action: open({[file_path]})|save({[flag]})|close。"""
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
def mech_doc(action: str, file_path: str, template: str = None) -> dict:
    """中望机械文档操作。action: open|new|new_named(需template参数)。"""
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
def cad_environment_init(std_name: str) -> dict:
    """初始化CAD环境标准（如GB, ISO, DIN等）。"""
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.cad_environment_init(std_name)
        return _ok(f"CAD 环境初始化成功 (标准: {std_name})", standard=std_name)
    except Exception as e:
        return _err("CAD 环境初始化", e)


@mcp.tool
def get_balloon(text: str = "") -> dict:
    """获取球标对象（用于零件序号标注）。"""
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        balloon = mech_conn.zwm_db.get_balloon(text)
        if balloon:
            return _ok(f"成功获取球标对象: {balloon}")
        else:
            return _err("获取球标", ValueError("未获取到球标对象"))
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
) -> dict:
    """新建图幅/图框。所有参数均可选，默认从XML配置读取。
    orientation: landscape|portrait。have_*: 各栏开关(dhl/fjl/btl/csl/ggl)。"""
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


# ############################################################
#                   字典 / XData / 工具方法
# ############################################################


@mcp.tool
def manage_dictionary(action: str, params: dict = None) -> dict:
    """命名对象字典与XRecord管理。action及params:
    list(无需params) — 列出所有顶层字典
    add:{name} — 创建新字典
    get_items:{name} — 获取字典内所有条目(keyword→ObjectName映射)
    add_object:{dict_name,keyword,object_name} — 向字典添加对象
    get_object:{dict_name,name} — 按名称获取条目
    remove:{dict_name,name} — 删除条目
    rename:{dict_name,old_name,new_name} — 重命名条目
    add_xrecord:{dict_name,keyword} — 在字典中创建XRecord
    get_xrecord:{dict_name,keyword} — 读取XRecord数据(返回types+values数组)
    set_xrecord:{dict_name,keyword,data_types:[],data_values:[]} — 写入XRecord(types为DXF组码)
    get_entity_dict:{handle} — 获取实体的扩展字典
    has_entity_dict:{handle} — 检查实体是否有扩展字典"""
    try:
        logger.info("tool_call manage_dictionary action=%s", action)
        zcad_conn, _ = get_cad_connection()
        p = params or {}
        dicts = zcad_conn.doc.Dictionaries

        if action == "list":
            result = []
            for i in range(dicts.Count):
                d = dicts.Item(i)
                result.append({"name": d.Name, "count": d.Count})
            return _ok(data=result)

        elif action == "add":
            new_dict = dicts.Add(p["name"])
            return _ok(f"成功创建字典: {p['name']}", name=new_dict.Name)

        elif action == "get_items":
            d = dicts.Item(p["name"])
            items = []
            for i in range(d.Count):
                obj = d.Item(i)
                entry = {"index": i, "object_name": obj.ObjectName if hasattr(obj, 'ObjectName') else "Unknown"}
                try:
                    entry["keyword"] = d.GetName(obj)
                except Exception:
                    pass
                if hasattr(obj, 'Handle'):
                    entry["handle"] = obj.Handle
                items.append(entry)
            return _ok(data=items)

        elif action == "add_object":
            d = dicts.Item(p["dict_name"])
            d.AddObject(p["keyword"], p["object_name"])
            return _ok(f"成功向字典 '{p['dict_name']}' 添加对象: {p['keyword']}")

        elif action == "get_object":
            d = dicts.Item(p["dict_name"])
            obj = d.GetObject(p["name"])
            info = {"object_name": obj.ObjectName}
            if hasattr(obj, 'Handle'):
                info["handle"] = obj.Handle
            if hasattr(obj, 'Name'):
                info["name"] = obj.Name
            return _ok(data=info)

        elif action == "remove":
            d = dicts.Item(p["dict_name"])
            d.Remove(p["name"])
            return _ok(f"成功从字典 '{p['dict_name']}' 删除条目: {p['name']}")

        elif action == "rename":
            d = dicts.Item(p["dict_name"])
            d.Rename(p["old_name"], p["new_name"])
            return _ok(f"成功重命名: '{p['old_name']}' → '{p['new_name']}'")

        elif action == "add_xrecord":
            d = dicts.Item(p["dict_name"])
            d.AddXRecord(p["keyword"])
            return _ok(f"成功在字典 '{p['dict_name']}' 中创建 XRecord: {p['keyword']}")

        elif action == "get_xrecord":
            d = dicts.Item(p["dict_name"])
            xr = d.GetObject(p["keyword"])
            types, values = xr.GetXRecordData()
            type_list = list(types) if types else []
            value_list = list(values) if values else []
            return _ok(data={"types": type_list, "values": value_list})

        elif action == "set_xrecord":
            d = dicts.Item(p["dict_name"])
            xr = d.GetObject(p["keyword"])
            types_arr = aInt(p["data_types"])
            values_tuple = tuple(p["data_values"])
            xr.SetXRecordData(types_arr, values_tuple)
            return _ok(f"成功写入 XRecord 数据 ({len(p['data_types'])} 项)")

        elif action == "get_entity_dict":
            obj = zcad_conn.doc.HandleToObject(p["handle"])
            ext_dict = obj.GetExtensionDictionary()
            items = []
            for i in range(ext_dict.Count):
                entry = ext_dict.Item(i)
                item = {"index": i, "object_name": entry.ObjectName if hasattr(entry, 'ObjectName') else "Unknown"}
                try:
                    item["keyword"] = ext_dict.GetName(entry)
                except Exception:
                    pass
                if hasattr(entry, 'Handle'):
                    item["handle"] = entry.Handle
                items.append(item)
            return _ok(data={"handle": p["handle"], "dict_name": ext_dict.Name, "items": items})

        elif action == "has_entity_dict":
            obj = zcad_conn.doc.HandleToObject(p["handle"])
            has_dict = bool(obj.HasExtensionDictionary)
            return _ok(data={"handle": p["handle"], "has_extension_dictionary": has_dict})

        return _err("字典管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"字典管理({action})", e)


@mcp.tool
def manage_xdata(action: str, params: dict = None) -> dict:
    """扩展数据(XData)管理。action及params:
    list_apps(无需params) — 列出所有已注册应用程序名
    register_app:{app_name} — 注册新应用程序名(写XData前必须先注册)
    get_xdata:{handle,app_name} — 读取实体扩展数据(返回types+values)
    set_xdata:{handle,data_types:[],data_values:[]} — 写入扩展数据
      types[0]必须是1001(应用名标识),values[0]是已注册的app_name
      常用类型码: 1000=字符串,1040=实数,1070=整数,1010=3D点
    delete_xdata:{handle,app_name} — 删除实体上指定应用的扩展数据"""
    try:
        logger.info("tool_call manage_xdata action=%s", action)
        zcad_conn, _ = get_cad_connection()
        p = params or {}

        if action == "list_apps":
            apps = []
            for app in zcad_conn.doc.RegisteredApplications:
                apps.append({"name": app.Name})
            return _ok(data=apps)

        elif action == "register_app":
            zcad_conn.doc.RegisteredApplications.Add(p["app_name"])
            return _ok(f"成功注册应用程序: {p['app_name']}", app_name=p["app_name"])

        elif action == "get_xdata":
            obj = zcad_conn.doc.HandleToObject(p["handle"])
            types, values = obj.GetXData(p["app_name"])
            type_list = list(types) if types else []
            value_list = list(values) if values else []
            return _ok(data={"handle": p["handle"], "app_name": p["app_name"],
                             "types": type_list, "values": value_list})

        elif action == "set_xdata":
            obj = zcad_conn.doc.HandleToObject(p["handle"])
            types_arr = aInt(p["data_types"])
            values_tuple = tuple(p["data_values"])
            obj.SetXData(types_arr, values_tuple)
            return _ok(f"成功写入 XData ({len(p['data_types'])} 项)", handle=p["handle"])

        elif action == "delete_xdata":
            obj = zcad_conn.doc.HandleToObject(p["handle"])
            types_arr = aInt([1001])
            values_tuple = (p["app_name"],)
            obj.SetXData(types_arr, values_tuple)
            return _ok(f"成功删除实体上的 XData (app={p['app_name']})", handle=p["handle"])

        return _err("XData管理", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"XData管理({action})", e)


@mcp.tool
def manage_utility(action: str, params: dict = None) -> dict:
    """CAD工具方法(doc.Utility)。action及params:
    translate_coordinates:{point:[x,y,z],from_system:int,to_system:int,[displacement:bool]}
      坐标系: 0=WCS, 1=UCS, 2=DisplayDCS, 3=PaperSpaceDCS
    polar_point:{point:[x,y,z],angle:float,distance:float} — 计算极坐标点
    angle_to_real:{angle_str,unit:int} — 角度字符串转弧度
      unit: 0=度, 1=度分秒, 2=弧度, 3=百分度, 4=勘测单位
    angle_to_string:{angle:float,unit:int,precision:int} — 弧度转角度字符串
    real_to_string:{value:float,unit:int,precision:int} — 实数转字符串
      unit: 1=科学, 2=小数, 3=工程, 4=建筑, 5=分数
    distance_to_real:{distance_str,unit:int} — 距离字符串转实数
    prompt:{message} — 在命令行显示消息
    get_object_id_string:{handle,[hex:bool]} — 获取实体ObjectID"""
    try:
        logger.info("tool_call manage_utility action=%s", action)
        zcad_conn, _ = get_cad_connection()
        p = params or {}
        util = zcad_conn.doc.Utility

        if action == "translate_coordinates":
            pt = APoint(p["point"][0], p["point"][1],
                        p["point"][2] if len(p["point"]) > 2 else 0)
            disp = p.get("displacement", False)
            result = util.TranslateCoordinates(pt, p["from_system"], p["to_system"], disp)
            return _ok(data={"result": list(result)})

        elif action == "polar_point":
            pt = APoint(p["point"][0], p["point"][1],
                        p["point"][2] if len(p["point"]) > 2 else 0)
            result = util.PolarPoint(pt, p["angle"], p["distance"])
            return _ok(data={"result": list(result)})

        elif action == "angle_to_real":
            result = util.AngleToReal(p["angle_str"], p["unit"])
            return _ok(data={"angle_str": p["angle_str"], "radians": result})

        elif action == "angle_to_string":
            result = util.AngleToString(p["angle"], p["unit"], p["precision"])
            return _ok(data={"angle": p["angle"], "string": result})

        elif action == "real_to_string":
            result = util.RealToString(p["value"], p["unit"], p["precision"])
            return _ok(data={"value": p["value"], "string": result})

        elif action == "distance_to_real":
            result = util.DistanceToReal(p["distance_str"], p["unit"])
            return _ok(data={"distance_str": p["distance_str"], "value": result})

        elif action == "prompt":
            util.Prompt(p["message"])
            return _ok(f"消息已发送到命令行: {p['message']}")

        elif action == "get_object_id_string":
            obj = zcad_conn.doc.HandleToObject(p["handle"])
            obj_id = obj.ObjectID
            if p.get("hex", False):
                return _ok(data={"handle": p["handle"], "object_id": hex(obj_id)})
            return _ok(data={"handle": p["handle"], "object_id": str(obj_id)})

        return _err("工具方法", ValueError(f"不支持的操作: {action}"))
    except Exception as e:
        return _err(f"工具方法({action})", e)


# ============================================================
# 主程序入口
# ============================================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ZWCAD Mechanical MCP Server 启动中...")
    logger.info("=" * 60)
    logger.info("服务器已就绪，等待客户端连接...")
    mcp.run(transport="stdio", show_banner=False)

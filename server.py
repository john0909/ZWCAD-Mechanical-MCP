"""
ZWCAD Mechanical MCP Server - 基于 FastMCP 的中望机械CAD自动化服务
提供画直线、画圆、画弧、画椭圆、多段线、样条曲线、标注、图块、图层、
标题栏编辑、图框切换、明细表操作等功能
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

# 将所有日志输出到 stderr，避免污染 MCP STDIO 协议流
# MCP STDIO 传输要求 stdout 只能传输 JSON-RPC 2.0 消息
# 任何非 JSON-RPC 数据写入 stdout 都会导致客户端解析失败和连接超时
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# 强制使用 STA 线程模型以支持 COM 调用
try:
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
except Exception:
    pass

# 创建 MCP Server 实例
mcp = FastMCP(name="ZWCAD Mechanical Drawing Server")

# 默认样式文件路径
STYLES_BASE_PATH = r"C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles"

def _parse_xml_file(file_path):
    """解析 XML 文件"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"XML 文件不存在: {file_path}")
    tree = ET.parse(file_path)
    return tree.getroot()

def _get_default_standard():
    """获取默认标准名称"""
    xml_path = os.path.join(STYLES_BASE_PATH, "standard.xml")
    root = _parse_xml_file(xml_path)
    for standard in root.findall('Standard'):
        if standard.get('Default') == '1':
            return standard.get('Name')
    first = root.find('Standard')
    return first.get('Name') if first is not None else "GB"

def _get_title_styles(standard_name):
    """获取指定标准下的所有标题栏样式"""
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "TitleStyles.xml")
    root = _parse_xml_file(xml_path)
    styles = []
    default_style = None
    # 使用命名空间查找（XML 中可能有命名空间）
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
    """获取指定标准下的所有明细表样式"""
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "BomStyles.xml")
    root = _parse_xml_file(xml_path)
    styles = []
    default_style = None
    # 使用命名空间查找（XML 中可能有命名空间）
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
    """获取指定标准、图幅、方向下的图框样式"""
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "FrameStyles.xml")
    root = _parse_xml_file(xml_path)
    for frame_size_elem in root.findall('.//FrameSize'):
        if frame_size_elem.get('Name') == frame_size:
            for style in frame_size_elem.findall('.//FrameStyle'):
                if style.get('Orientation') == orientation:
                    return style.get('Name')
    return "分区图框"

def _get_default_frame_size(standard_name):
    """获取指定标准下的默认图幅名称（从 FrameStyles.xml 中读取 Default="1"）"""
    xml_path = os.path.join(STYLES_BASE_PATH, standard_name, "FrameStyles.xml")
    root = _parse_xml_file(xml_path)
    for frame_size_elem in root.iter():
        if frame_size_elem.tag.endswith('FrameSize') or frame_size_elem.tag == 'FrameSize':
            if frame_size_elem.get('Default') == '1':
                return frame_size_elem.get('Name')
    # 如果没有找到 Default="1" 的，返回第一个
    for frame_size_elem in root.iter():
        if frame_size_elem.tag.endswith('FrameSize') or frame_size_elem.tag == 'FrameSize':
            return frame_size_elem.get('Name')
    return "A3"  # 最后的默认值




def get_cad_connection():
    """获取或创建 ZWCAD 连接"""
    # 确保当前线程初始化了 COM
    try:
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    except Exception:
        pass
    
    # 每次都重新连接
    zcad_conn = ZwCAD()
    mech_conn = ZwCADMech()
    
    return zcad_conn, mech_conn


def reset_connection():
    """重置 CAD 连接"""
    pass


def _com_error_hint(error_msg: str) -> str:
    """为 COM 初始化错误追加解决方案提示"""
    return error_msg + (
        "\n\n解决方案："
        "\n1. 确保 ZWCAD Mechanical 2027 已启动并运行"
        "\n2. 如果问题仍然存在，请重启 ZWCAD 和 MCP Server"
        "\n3. 检查系统是否正确安装了 pywin32 和 comtypes 库"
    )


def _format_error(action: str, e: Exception) -> str:
    """格式化错误信息，COM 初始化错误附加解决方案"""
    error_msg = f"{action}失败: {str(e)}"
    if "CoInitialize" in str(e) or "-2147221008" in str(e):
        error_msg = _com_error_hint(error_msg)
    return error_msg


# ==========================================
# 基础绘图工具
# ==========================================

@mcp.tool
def draw_line(x1: float, y1: float, z1: float,
              x2: float, y2: float, z2: float,
              layer: str = "0") -> str:
    """
    在 ZWCAD 中绘制一条直线
    
    参数:
    - x1, y1, z1: 起点坐标
    - x2, y2, z2: 终点坐标
    - layer: 图层名称（可选，默认为"0"）
    
    返回: 操作结果信息
    """
    try:
        zcad_conn, mech_conn = get_cad_connection()
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        line = zcad_conn.model.AddLine(p1, p2)
        line.Layer = layer
        return f"成功绘制直线: ({x1},{y1},{z1}) -> ({x2},{y2},{z2})，图层: {layer}"
    except Exception as e:
        return _format_error("绘制直线", e)


@mcp.tool
def draw_circle(center_x: float, center_y: float, center_z: float,
                radius: float, layer: str = "0") -> str:
    """
    在 ZWCAD 中绘制一个圆
    
    参数:
    - center_x, center_y, center_z: 圆心坐标
    - radius: 半径
    - layer: 图层名称（可选，默认为"0"）
    
    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        circle = zcad_conn.model.AddCircle(center, radius)
        circle.Layer = layer
        return f"成功绘制圆: 圆心({center_x},{center_y},{center_z}), 半径={radius}，图层: {layer}"
    except Exception as e:
        return _format_error("绘制圆", e)


@mcp.tool
def add_text(text: str, x: float, y: float, z: float,
             height: float = 2.5) -> str:
    """
    在指定位置添加文本
    
    参数:
    - text: 文本内容
    - x, y, z: 插入点坐标
    - height: 文字高度（可选，默认2.5）
    
    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        text_obj = zcad_conn.model.AddText(text, point, height)
        return f"成功添加文本: '{text}' at ({x},{y},{z})，字高: {height}"
    except Exception as e:
        return _format_error("添加文本", e)


@mcp.tool
def save_drawing(file_path: str) -> str:
    """
    保存当前图纸到指定路径
    
    参数:
    - file_path: 保存路径（如 "C:\\drawings\\test.dwg"）
    
    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.SaveAs(file_path)
        return f"图纸已保存至: {file_path}"
    except Exception as e:
        return f"保存图纸失败: {str(e)}"


@mcp.tool
def close_current_document(save_changes: bool = True) -> str:
    """
    关闭当前活动图纸（与当前打开的 DWG，例如 test.dwg）

    参数:
    - save_changes: 是否在关闭前保存更改（默认 True）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Close(save_changes)
        return "当前图纸已关闭"
    except Exception as e:
        return f"关闭图纸失败: {str(e)}"


@mcp.tool
def new_drawing() -> str:
    """
    创建新的空白图纸
    
    返回: 操作结果信息
    """
    try:
        # 清除缓存强制新建
        reset_connection()

        # 重新建立连接
        zcad_conn, mech_conn = get_cad_connection()

        return f"已连接图纸\n文档: {zcad_conn.doc.Name}"
    except Exception as e:
        return f"连接图纸失败: {str(e)}"


@mcp.tool
def get_document_info() -> str:
    """
    获取当前文档的详细信息
    
    返回: JSON 格式的文档信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        doc = zcad_conn.doc
        
        info = {
            "name": doc.Name,
            "full_name": doc.FullName,
            "path": doc.Path,
            "saved": doc.Saved,
            "readonly": doc.ReadOnly
        }
        
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取文档信息失败: {str(e)}"


@mcp.tool
def get_layouts(include_model: bool = False) -> str:
    """
    获取当前文档的所有布局列表
    
    参数:
    - include_model: 是否包含模型空间（默认False）
    
    返回: JSON 格式的布局列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        
        layouts = []
        for layout in zcad_conn.iter_layouts(skip_model=not include_model):
            layouts.append({
                "name": layout.Name,
                "tab_order": layout.TabOrder,
                "is_model_space": layout.ModelSpace
            })
        
        return json.dumps(layouts, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取布局列表失败: {str(e)}"


@mcp.tool
def get_objects_in_model(object_type: str = None, limit: int = None) -> str:
    """
    获取模型空间中的对象列表
    
    参数:
    - object_type: 对象类型过滤（如 "Line", "Circle", "Text" 等，可选）
    - limit: 最大返回数量（可选，默认全部）
    
    返回: JSON 格式的对象列表
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
            
            # 添加常见属性
            if hasattr(obj, 'Color'):
                obj_info['color'] = obj.Color
            
            objects.append(obj_info)
            count += 1
        
        result = {
            "total_count": count,
            "objects": objects
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取对象列表失败: {str(e)}"


@mcp.tool
def find_object(object_type: str, property_name: str, property_value: str) -> str:
    """
    查找符合条件的第一个对象
    
    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 属性名称（如 "Layer", "Color" 等）
    - property_value: 属性值
    
    返回: JSON 格式的对象信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        
        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False
        
        obj = zcad_conn.find_one(object_type, predicate=predicate)
        
        if obj:
            obj_info = {
                "found": True,
                "object_name": obj.ObjectName,
                "layer": obj.Layer if hasattr(obj, 'Layer') else "N/A"
            }
            return json.dumps(obj_info, ensure_ascii=False, indent=2)
        else:
            return json.dumps({"found": False}, indent=2)
    except Exception as e:
        return f"查找对象失败: {str(e)}"


@mcp.tool
def send_prompt(text: str) -> str:
    """
    在 ZWCAD 命令行和控制台打印文本
    
    参数:
    - text: 要打印的文本内容
    
    返回: 操作结果
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.prompt(text)
        return f"成功发送提示文本: {text}"
    except Exception as e:
        return f"发送提示失败: {str(e)}"


@mcp.tool
def get_active_layout() -> str:
    """
    获取当前激活的布局信息
    
    返回: JSON 格式的布局信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        layout = zcad_conn.doc.ActiveLayout
        
        info = {
            "name": layout.Name,
            "tab_order": layout.TabOrder,
            "is_model_space": layout.ModelSpace
        }
        
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取活动布局失败: {str(e)}"


# ==========================================
# 标题栏工具
# ==========================================

@mcp.tool
def get_title_block_info() -> str:
    """
    获取当前图纸标题栏的所有字段信息
    
    返回: JSON 格式的标题栏字段列表（索引、标签、名称、值）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")  # 连接当前活动图纸
        title = mech_conn.get_title()
        
        if not title:
            return "未找到标题栏对象"
        
        items = []
        count = title.get_item_count()
        for i in range(count):
            label, name, value = title.get_item(i)
            items.append({
                "index": i,
                "label": label,
                "name": name,
                "value": value
            })
        
        return json.dumps(items, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"读取标题栏失败: {str(e)}"


@mcp.tool
def set_title_block_field(field_name: str, value: str) -> str:
    """
    设置标题栏中指定字段的值
    
    参数:
    - field_name: 字段名称（如"设计"、"审核"、"日期"等）
    - value: 要设置的值
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        title = mech_conn.get_title()
        
        if not title:
            return "未找到标题栏对象"
        
        # 设置字段值（使用字段标签或名称）
        title.set_item(field_name, value)
        
        # 刷新标题栏显示
        mech_conn.zwm_db.refresh_title()
        
        return f"成功设置标题栏字段 '{field_name}' = '{value}'"
    except Exception as e:
        return f"设置标题栏字段失败: {str(e)}"


@mcp.tool
def update_title_block_batch(fields: dict) -> str:
    """
    批量更新标题栏多个字段
    
    参数:
    - fields: 字典，键为字段名，值为要设置的内容
      示例: {"设计": "张三", "审核": "李四", "日期": "2026-04-25"}
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        title = mech_conn.get_title()
        
        if not title:
            return "未找到标题栏对象"
        
        results = []
        for field_name, value in fields.items():
            title.set_item(field_name, value)
            results.append(f"{field_name}={value}")
        
        # 刷新标题栏显示
        mech_conn.zwm_db.refresh_title()
        
        return f"成功批量更新标题栏: {', '.join(results)}"
    except Exception as e:
        return f"批量更新标题栏失败: {str(e)}"


@mcp.tool
def get_title_field_count() -> str:
    """
    获取标题栏字段的总数
    
    返回: 字段数量
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        title = mech_conn.get_title()
        
        if not title:
            return "未找到标题栏对象"
        
        count = title.get_item_count()
        return f"标题栏字段总数: {count}"
    except Exception as e:
        return f"获取标题栏字段数量失败: {str(e)}"


@mcp.tool
def get_title_item_by_index(index: int) -> str:
    """
    根据索引获取标题栏的指定字段信息
    
    参数:
    - index: 字段索引（从0开始）
    
    返回: JSON 格式的字段信息（label, name, value）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        title = mech_conn.get_title()
        
        if not title:
            return "未找到标题栏对象"
        
        label, name, value = title.get_item(index)
        
        result = {
            "index": index,
            "label": label,
            "name": name,
            "value": value
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取标题栏字段失败: {str(e)}"


# ==========================================
# 图框工具
# ==========================================



@mcp.tool
def get_available_frames() -> str:
    """
    获取系统中所有可用的图框样式列表
    
    返回: 图框名称列表（JSON 格式）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        
        # 获取图框总数
        count = mech_conn.zwm_db.get_frame_count()
        
        # 获取所有图框名称
        frames = []
        for i in range(count):
            name = mech_conn.zwm_db.get_frame_name(i)
            frames.append(name)
        
        return json.dumps(frames, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取图框列表失败: {str(e)}"


@mcp.tool
def get_frame_full_info() -> str:
    """
    获取当前图框的完整信息（所有属性）
    
    返回: JSON 格式的图框完整属性
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        frame = mech_conn.zwm_db.get_frame()
        
        if not frame:
            return "未找到图框对象"
        
        # 获取所有图框属性
        info = {}
        
        # 基本属性
        if hasattr(frame, 'width'):
            info['width'] = frame.width
        if hasattr(frame, 'height'):
            info['height'] = frame.height
        if hasattr(frame, 'std_name'):
            info['std_name'] = frame.std_name
        if hasattr(frame, 'frame_size_name'):
            info['frame_size_name'] = frame.frame_size_name
        if hasattr(frame, 'frame_style_name'):
            info['frame_style_name'] = frame.frame_style_name
        if hasattr(frame, 'orientation'):
            info['orientation'] = frame.orientation
        
        # 样式属性
        if hasattr(frame, 'title_style_name'):
            info['title_style_name'] = frame.title_style_name
        if hasattr(frame, 'bom_style_name'):
            info['bom_style_name'] = frame.bom_style_name
        if hasattr(frame, 'dhl_style_name'):
            info['dhl_style_name'] = frame.dhl_style_name
        if hasattr(frame, 'fjl_style_name'):
            info['fjl_style_name'] = frame.fjl_style_name
        if hasattr(frame, 'csl_style_name'):
            info['csl_style_name'] = frame.csl_style_name
        if hasattr(frame, 'ggl_style_name'):
            info['ggl_style_name'] = frame.ggl_style_name
        
        # 布尔属性
        if hasattr(frame, 'have_dhl'):
            info['have_dhl'] = frame.have_dhl
        if hasattr(frame, 'have_fjl'):
            info['have_fjl'] = frame.have_fjl
        if hasattr(frame, 'have_btl'):
            info['have_btl'] = frame.have_btl
        if hasattr(frame, 'have_csl'):
            info['have_csl'] = frame.have_csl
        if hasattr(frame, 'have_ggl'):
            info['have_ggl'] = frame.have_ggl
        
        # 比例属性
        if hasattr(frame, 'scale1'):
            info['scale1'] = frame.scale1
        if hasattr(frame, 'scale2'):
            info['scale2'] = frame.scale2
        
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取图框完整信息失败: {str(e)}"


@mcp.tool
def update_frame_properties(
    width: float = None,
    height: float = None,
    orientation: int = None,
    scale1: float = None,
    scale2: float = None,
    have_dhl: bool = None,
    have_fjl: bool = None,
    have_btl: bool = None,
    have_csl: bool = None,
    have_ggl: bool = None,
    title_style_name: str = None,
    bom_style_name: str = None,
    dhl_style_name: str = None,
    fjl_style_name: str = None,
    csl_style_name: str = None,
    ggl_style_name: str = None,
    frame_size_name: str = None,
    frame_style_name: str = None,
    std_name: str = None
) -> str:
    """
    更新图框的多个属性（只更新提供的参数）
    
    参数:
    - width: 宽度
    - height: 高度
    - orientation: 方向（0=横向，1=纵向）
    - scale1: 比例1
    - scale2: 比例2
    - have_dhl: 是否含导航天线
    - have_fjl: 是否含附加栏
    - have_btl: 是否含标题栏
    - have_csl: 是否含参数表
    - have_ggl: 是否含管口表
    - title_style_name: 标题栏样式名
    - bom_style_name: 明细表样式名
    - dhl_style_name: 导航天线样式名
    - fjl_style_name: 附加栏样式名
    - csl_style_name: 参数表样式名
    - ggl_style_name: 管口表样式名
    - frame_size_name: 图框尺寸名
    - frame_style_name: 图框样式名
    - std_name: 标准名
    
    返回: 操作结果
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        frame = mech_conn.zwm_db.get_frame()
        
        if not frame:
            return "未找到图框对象"
        
        updated = []

        _frame_fields = {
            'width': width, 'height': height, 'orientation': orientation,
            'scale1': scale1, 'scale2': scale2,
            'have_dhl': have_dhl, 'have_fjl': have_fjl, 'have_btl': have_btl,
            'have_csl': have_csl, 'have_ggl': have_ggl,
            'title_style_name': title_style_name, 'bom_style_name': bom_style_name,
            'dhl_style_name': dhl_style_name, 'fjl_style_name': fjl_style_name,
            'csl_style_name': csl_style_name, 'ggl_style_name': ggl_style_name,
            'frame_size_name': frame_size_name, 'frame_style_name': frame_style_name,
            'std_name': std_name,
        }

        for attr, val in _frame_fields.items():
            if val is not None and hasattr(frame, attr):
                setattr(frame, attr, val)
                updated.append(f"{attr}={val}")
        
        # 刷新图框
        mech_conn.zwm_db.refresh_frame()
        
        if updated:
            return f"成功更新图框属性: {', '.join(updated)}"
        else:
            return "未提供任何要更新的属性"
            
    except Exception as e:
        return f"更新图框属性失败: {str(e)}"


@mcp.tool
def get_frame_count() -> str:
    """
    获取系统中图框的总数
    
    返回: 图框数量
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        count = mech_conn.zwm_db.get_frame_count()
        return f"图框总数: {count}"
    except Exception as e:
        return f"获取图框数量失败: {str(e)}"


@mcp.tool
def get_frame_name_by_index(index: int) -> str:
    """
    根据索引获取图框名称
    
    参数:
    - index: 图框索引（从0开始）
    
    返回: 图框名称
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        name = mech_conn.zwm_db.get_frame_name(index)
        return f"索引 {index} 的图框名称: {name}"
    except Exception as e:
        return f"获取图框名称失败: {str(e)}"


@mcp.tool
def get_frame_name_by_point(x: float, y: float, z: float = 0) -> str:
    """
    根据坐标点获取图框名称
    
    参数:
    - x, y, z: 坐标点（z可选，默认0）
    
    返回: 图框名称
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        
        # 创建坐标点元组（comtypes需要）
        point = (x, y, z)
        name = mech_conn.zwm_db.get_frame_name2(point)
        return f"坐标 ({x},{y},{z}) 处的图框名称: {name}"
    except Exception as e:
        return f"获取图框名称失败: {str(e)}"


@mcp.tool
def switch_frame(frame_name: str) -> str:
    """
    切换当前活动图框
    
    参数:
    - frame_name: 图框名称
    
    返回: 操作结果
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.switch_frame(frame_name)
        return f"成功切换到图框: {frame_name}"
    except Exception as e:
        return f"切换图框失败: {str(e)}"

@mcp.tool
def refresh_frame() -> str:
    """
    刷新图框显示
    
    返回: 操作结果
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.refresh_frame()
        return "图框刷新成功"
    except Exception as e:
        return f"刷新图框失败: {str(e)}"


# ==========================================
# 明细表（BOM）工具
# ==========================================


@mcp.tool
def add_bom_row(data: dict) -> str:
    """
    向明细表添加新行
    
    参数:
    - data: 字典，包含要添加的字段和值
      示例: {"序号": "1", "名称": "零件A", "材料": "45钢", "数量": "2"}
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        # 创建新行
        new_row = bom.create_bom_row()
        
        # 设置各行列的值
        for field_name, value in data.items():
            new_row.set_item(field_name, value)
        
        # 添加到明细表
        bom.add_item(new_row)
        
        # 刷新明细表显示
        mech_conn.zwm_db.refresh_bom()
        
        return f"成功添加明细表行: {data}"
    except Exception as e:
        return f"添加明细表行失败: {str(e)}"


@mcp.tool
def get_bom_row_count() -> str:
    """
    获取明细表的总行数
    
    返回: 行数
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        count = bom.get_item_count()
        return f"明细表总行数: {count}"
    except Exception as e:
        return f"获取明细表行数失败: {str(e)}"


@mcp.tool
def get_bom_row_data(row_index: int) -> str:
    """
    获取明细表指定行的完整数据
    
    参数:
    - row_index: 行索引（从0开始）
    
    返回: JSON 格式的行数据（包含所有字段）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        row = bom.get_item(row_index)
        if not row:
            return f"未找到索引 {row_index} 的行"
        
        # 获取该行的所有字段
        fields = []
        field_count = row.get_item_count()
        for i in range(field_count):
            label, name, value = row.get_item(i)
            fields.append({
                "field_index": i,
                "label": label,
                "name": name,
                "value": value
            })
        
        result = {
            "row_index": row_index,
            "field_count": field_count,
            "fields": fields
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取明细表行数据失败: {str(e)}"


@mcp.tool
def update_bom_row(row_index: int, data: dict) -> str:
    """
    更新明细表指定行的数据
    
    参数:
    - row_index: 行索引
    - data: 字段字典，键为字段名，值为要设置的内容
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        row = bom.get_item(row_index)
        if not row:
            return f"未找到索引 {row_index} 的行"
        
        # 设置字段值
        for field_name, value in data.items():
            row.set_item(field_name, value)
        
        # 刷新明细表显示
        mech_conn.zwm_db.refresh_bom()
        
        return f"成功更新明细表行 {row_index}: {data}"
    except Exception as e:
        return f"更新明细表行失败: {str(e)}"


@mcp.tool
def insert_bom_row(index: int, data: dict) -> str:
    """
    在明细表指定位置插入新行
    
    参数:
    - index: 插入位置索引
    - data: 行数据字典
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        # 创建新行
        new_row = bom.create_bom_row()
        
        # 设置字段值
        for field_name, value in data.items():
            new_row.set_item(field_name, value)
        
        # 插入到指定位置
        bom.insert_item(index, new_row)
        
        # 刷新明细表显示
        mech_conn.zwm_db.refresh_bom()
        
        return f"成功在位置 {index} 插入明细表行: {data}"
    except Exception as e:
        return f"插入明细表行失败: {str(e)}"


@mcp.tool
def delete_bom_row(index: int) -> str:
    """
    删除明细表指定行
    
    参数:
    - index: 要删除的行索引
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        # 删除行
        bom.delete_item(index)
        
        # 刷新明细表显示
        mech_conn.zwm_db.refresh_bom()
        
        return f"成功删除明细表行 {index}"
    except Exception as e:
        return f"删除明细表行失败: {str(e)}"


@mcp.tool
def get_bom_row_field_count(row_index: int) -> str:
    """
    获取明细表指定行的字段数量
    
    参数:
    - row_index: 行索引
    
    返回: 字段数量
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        row = bom.get_item(row_index)
        if not row:
            return f"未找到索引 {row_index} 的行"
        
        count = row.get_item_count()
        return f"行 {row_index} 的字段数量: {count}"
    except Exception as e:
        return f"获取字段数量失败: {str(e)}"


@mcp.tool
def get_bom_row_field(row_index: int, field_index: int) -> str:
    """
    获取明细表指定行的指定字段信息
    
    参数:
    - row_index: 行索引
    - field_index: 字段索引
    
    返回: JSON 格式的字段信息（label, name, value）
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        row = bom.get_item(row_index)
        if not row:
            return f"未找到索引 {row_index} 的行"
        
        label, name, value = row.get_item(field_index)
        
        result = {
            "row_index": row_index,
            "field_index": field_index,
            "label": label,
            "name": name,
            "value": value
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取字段信息失败: {str(e)}"


@mcp.tool
def set_bom_row_field(row_index: int, field_key: str, value: str) -> str:
    """
    设置明细表指定行的指定字段值
    
    参数:
    - row_index: 行索引
    - field_key: 字段名或索引（字符串）
    - value: 字段值
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        bom = mech_conn.zwm_db.get_bom()
        
        if not bom:
            return "未找到明细表对象"
        
        row = bom.get_item(row_index)
        if not row:
            return f"未找到索引 {row_index} 的行"
        
        # 设置字段值
        row.set_item(field_key, value)
        
        # 刷新明细表显示
        mech_conn.zwm_db.refresh_bom()
        
        return f"成功设置行 {row_index} 的字段 '{field_key}' = '{value}'"
    except Exception as e:
        return f"设置字段值失败: {str(e)}"


@mcp.tool
def refresh_bom() -> str:
    """
    刷新明细表显示
    
    返回: 操作结果
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.refresh_bom()
        return "明细表刷新成功"
    except Exception as e:
        return f"刷新明细表失败: {str(e)}"


# ==========================================
# 数据库操作工具
# ==========================================

@mcp.tool
def open_mech_file(file_path: str = "") -> str:
    """
    打开机械模块文件（空字符串表示当前活动图纸）
    
    参数:
    - file_path: 文件路径（可选，默认为空表示当前图纸）
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file(file_path)
        
        if file_path:
            return f"成功打开机械模块文件: {file_path}"
        else:
            return "成功连接当前活动图纸"
    except Exception as e:
        return f"打开文件失败: {str(e)}"


@mcp.tool
def save_mech_data(flag: int = 33) -> str:
    """
    保存机械模块数据
    
    参数:
    - flag: 保存标志（默认33）
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.save(flag)
        return f"机械模块数据保存成功 (flag={flag})"
    except Exception as e:
        return f"保存机械模块数据失败: {str(e)}"


@mcp.tool
def close_mech() -> str:
    """
    关闭机械模块连接
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.close()
        return "机械模块连接已关闭"
    except Exception as e:
        return f"关闭机械模块失败: {str(e)}"


# ==========================================
# 编辑操作工具
# ==========================================

@mcp.tool
def edit_frame() -> str:
    """
    打开图框编辑对话框/模式
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.frame_edit()
        return "图框编辑模式已启动"
    except Exception as e:
        return f"启动图框编辑失败: {str(e)}"


@mcp.tool
def edit_title() -> str:
    """
    打开标题栏编辑对话框/模式
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.title_edit()
        return "标题栏编辑模式已启动"
    except Exception as e:
        return f"启动标题栏编辑失败: {str(e)}"


@mcp.tool
def edit_csl() -> str:
    """
    打开参数表编辑对话框/模式
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.csl_edit()
        return "参数表编辑模式已启动"
    except Exception as e:
        return f"启动参数表编辑失败: {str(e)}"


@mcp.tool
def edit_fjl() -> str:
    """
    打开附加栏编辑对话框/模式
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.fjl_edit()
        return "附加栏编辑模式已启动"
    except Exception as e:
        return f"启动附加栏编辑失败: {str(e)}"


@mcp.tool
def edit_total_bom() -> str:
    """
    打开汇总明细表编辑对话框/模式
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.total_bom_edit()
        return "汇总明细表编辑模式已启动"
    except Exception as e:
        return f"启动汇总明细表编辑失败: {str(e)}"


# ==========================================
# 应用程序操作工具
# ==========================================

@mcp.tool
def get_mech_version() -> str:
    """
    获取 ZWCAD Mechanical 模块的版本信息
    
    返回: 版本信息字符串
    """
    try:
        _, mech_conn = get_cad_connection()
        version = mech_conn.zwm_app.get_version()
        return f"ZWCAD Mechanical 版本: {version}"
    except Exception as e:
        return f"获取版本信息失败: {str(e)}"


@mcp.tool
def get_cad_path() -> str:
    """
    获取 ZWCAD 的安装路径
    
    返回: CAD 安装路径
    """
    try:
        _, mech_conn = get_cad_connection()
        path = mech_conn.zwm_app.get_cad_path()
        return f"CAD 安装路径: {path}"
    except Exception as e:
        return f"获取 CAD 路径失败: {str(e)}"


@mcp.tool
def get_zwm_path() -> str:
    """
    获取 ZWCAD Mechanical 模块的安装路径
    
    返回: 机械模块路径
    """
    try:
        _, mech_conn = get_cad_connection()
        path = mech_conn.zwm_app.get_zwm_path()
        return f"Mechanical 模块路径: {path}"
    except Exception as e:
        return f"获取 Mechanical 路径失败: {str(e)}"


@mcp.tool
def get_style_path() -> str:
    """
    获取 ZWCAD Mechanical 样式文件的路径
    
    返回: 样式文件路径
    """
    try:
        _, mech_conn = get_cad_connection()
        path = mech_conn.zwm_app.get_style_path()
        return f"样式文件路径: {path}"
    except Exception as e:
        return f"获取样式路径失败: {str(e)}"


@mcp.tool
def get_mech_about() -> str:
    """
    获取 ZWCAD Mechanical 模块的关于信息
    
    返回: 关于信息
    """
    try:
        _, mech_conn = get_cad_connection()
        about = mech_conn.zwm_app.get_about()
        return f"Mechanical 关于信息: {about}"
    except Exception as e:
        return f"获取关于信息失败: {str(e)}"


@mcp.tool
def send_mech_command(cmd: str) -> str:
    """
    向 ZWCAD Mechanical 发送命令
    
    参数:
    - cmd: 命令字符串
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.zwm_app.send_command(cmd)
        return f"命令发送成功: {cmd}"
    except Exception as e:
        return f"发送命令失败: {str(e)}"


@mcp.tool
def open_mech_doc(file_path: str) -> str:
    """
    使用 Mechanical 模块打开文档
    
    参数:
    - file_path: 文件路径
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.zwm_app.open_doc(file_path)
        return f"成功打开文档: {file_path}"
    except Exception as e:
        return f"打开文档失败: {str(e)}"


@mcp.tool
def new_mech_doc(file_path: str) -> str:
    """
    使用 Mechanical 模块新建文档
    
    参数:
    - file_path: 文件路径
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.zwm_app.new_doc(file_path)
        return f"成功新建文档: {file_path}"
    except Exception as e:
        return f"新建文档失败: {str(e)}"


@mcp.tool
def new_named_mech_doc(file_path: str, template: str) -> str:
    """
    使用 Mechanical 模块新建命名文档（基于模板）
    
    参数:
    - file_path: 文件路径
    - template: 模板名称
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.zwm_app.new_named_doc(file_path, template)
        return f"成功新建命名文档: {file_path} (模板: {template})"
    except Exception as e:
        return f"新建命名文档失败: {str(e)}"


# ==========================================
# 其他操作工具
# ==========================================

@mcp.tool
def get_balloon(text: str = "") -> str:
    """
    获取球标对象（用于零件序号标注）
    
    参数:
    - text: 气球文本（可选，默认为空）
    
    返回: 气球对象信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        balloon = mech_conn.zwm_db.get_balloon(text)
        
        if balloon:
            return f"成功获取球标对象: {balloon}"
        else:
            return "未获取到球标对象"
    except Exception as e:
        return f"获取球标失败: {str(e)}"


@mcp.tool
def cad_environment_init(std_name: str) -> str:
    """
    初始化 CAD 环境（设置标准）
    
    参数:
    - std_name: 标准名称（如 "GB", "ISO", "DIN" 等）
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        mech_conn.zwm_db.cad_environment_init(std_name)
        return f"CAD 环境初始化成功 (标准: {std_name})"
    except Exception as e:
        return f"CAD 环境初始化失败: {str(e)}"


@mcp.tool
def get_next_frame_name() -> str:
    """
    获取下一个图框的名称和信息
    
    返回: JSON 格式的图框信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        frame, name = mech_conn.zwm_db.get_next_frm_name()
        
        result = {
            "frame_name": name,
            "has_frame": frame is not None
        }
        
        if frame:
            # 添加图框的基本信息
            if hasattr(frame, 'width'):
                result['width'] = frame.width
            if hasattr(frame, 'height'):
                result['height'] = frame.height
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取下一个图框名称失败: {str(e)}"


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
    新建图幅/图框（从XML配置读取样式）
    
    参数:
    - std_name: 标准名 (默认读取系统默认标准)
    - frame_size_name: 图幅尺寸名 (如 "A3", "A4"，默认读取标准默认图幅)
    - orientation: 方向（"landscape"或"portrait"，默认"landscape"）
    - width: 宽度（默认0.0）
    - height: 高度（默认0.0）
    - scale1: 比例1 (默认1.0)
    - scale2: 比例2 (默认1.0)
    - title_style_name: 标题栏样式名 (默认读取标准默认样式)
    - bom_style_name: 明细表样式名 (默认读取标准默认样式)
    - dhl_style_name: 导航天线样式名 (默认"图样代号")
    - fjl_style_name: 附加栏样式名 (默认"附加栏")
    - csl_style_name: 参数表样式名 (默认"包络环面蜗杆")
    - ggl_style_name: 管口表样式名 (默认"")
    - frame_style_name: 图框样式名 (默认读取标准默认样式)
    - have_dhl: 是否含导航天线 (默认False)
    - have_fjl: 是否含附加栏 (默认False)
    - have_btl: 是否含标题栏 (默认True)
    - have_csl: 是否含参数表 (默认False)
    - have_ggl: 是否含管口表 (默认False)
    
    返回: 操作结果信息
    """
    try:
        _, mech_conn = get_cad_connection()
        mech_conn.open_file("")
        
        # 1. 获取默认值
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
            
        # 2. 获取下一个图框名称并切换
        frame_obj, name = mech_conn.zwm_db.get_next_frm_name()
        if not name:
            return "获取新图框名称失败"
            
        mech_conn.zwm_db.switch_frame(name)
        frame = mech_conn.zwm_db.get_frame()
        
        if not frame:
            return "获取新图框对象失败"
            
        # 3. 设置属性 (参考无界面创建示例)
        fields = {
            "std_name": std_name,
            "frame_size_name": frame_size_name,
            "frame_style_name": frame_style_name,
            "orientation": orientation,
            "width": str(int(width)),
            "height": str(int(height)),
            "title_style_name": title_style_name,
            "bom_style_name": bom_style_name,
            "dhl_style_name": dhl_style_name,
            "fjl_style_name": fjl_style_name,
            "csl_style_name": csl_style_name,
            "ggl_style_name": ggl_style_name,
            "have_dhl": "1" if have_dhl else "0",
            "have_fjl": "1" if have_fjl else "0",
            "have_btl": "1" if have_btl else "0",
            "have_csl": "1" if have_csl else "0",
            "have_ggl": "1" if have_ggl else "0",
            "scale1": str(int(scale1)) if scale1.is_integer() else str(scale1),
            "scale2": str(int(scale2)) if scale2.is_integer() else str(scale2)
        }

        # 将属性值写入图框对象
        for key, val_str in fields.items():
            if key in ["width", "height", "have_dhl", "have_fjl", "have_btl", "have_csl", "have_ggl"]:
                try:
                    setattr(frame, key, int(val_str))
                except ValueError:
                    pass
            else:
                try:
                    setattr(frame, key, val_str)
                except Exception:
                    pass
        
        # 4. 构建图框
        mech_conn.zwm_db.build_frame(511)
        
        return f"成功创建图框: {name} (标准:{std_name}, 图幅:{frame_size_name})"
    except Exception as e:
        return f"创建图框失败: {str(e)}"


# ==========================================
# 扩展绘图工具（来自 zwcad25.tlb COM 接口）
# ==========================================

@mcp.tool
def draw_arc(center_x: float, center_y: float, center_z: float,
             radius: float, start_angle: float, end_angle: float,
             layer: str = "0") -> str:
    """
    在 ZWCAD 中绘制一条圆弧

    参数:
    - center_x, center_y, center_z: 圆心坐标
    - radius: 半径
    - start_angle: 起始角度（弧度）
    - end_angle: 终止角度（弧度）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        arc = zcad_conn.model.AddArc(center, radius, start_angle, end_angle)
        arc.Layer = layer
        return f"成功绘制圆弧: 圆心({center_x},{center_y},{center_z}), 半径={radius}, 角度{start_angle:.4f}~{end_angle:.4f}，图层: {layer}"
    except Exception as e:
        return _format_error("绘制圆弧", e)


@mcp.tool
def draw_ellipse(center_x: float, center_y: float, center_z: float,
                 major_axis_x: float, major_axis_y: float, major_axis_z: float,
                 radius_ratio: float,
                 layer: str = "0") -> str:
    """
    在 ZWCAD 中绘制一个椭圆

    参数:
    - center_x, center_y, center_z: 圆心坐标
    - major_axis_x, major_axis_y, major_axis_z: 主轴方向向量（从圆心到主轴端点）
    - radius_ratio: 短轴与长轴的比值（0~1）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        major_axis = APoint(major_axis_x, major_axis_y, major_axis_z)
        ellipse = zcad_conn.model.AddEllipse(center, major_axis, radius_ratio)
        ellipse.Layer = layer
        return f"成功绘制椭圆: 圆心({center_x},{center_y},{center_z}), 半轴比={radius_ratio}，图层: {layer}"
    except Exception as e:
        return _format_error("绘制椭圆", e)


@mcp.tool
def draw_lwpolyline(vertices: list, layer: str = "0",
                    closed: bool = False) -> str:
    """
    在 ZWCAD 中绘制轻量多段线（LWPolyline）

    参数:
    - vertices: 顶点坐标列表，格式为 [[x1,y1], [x2,y2], ...] 或 [x1,y1,x2,y2,...]
    - layer: 图层名称（可选，默认为"0"）
    - closed: 是否闭合（可选，默认False）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        # 展平顶点列表
        flat = []
        for v in vertices:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        pline = zcad_conn.model.AddLightWeightPolyline(coords)
        pline.Layer = layer
        if closed:
            pline.Closed = True
        return f"成功绘制轻量多段线: {len(flat)//2}个顶点, 闭合={closed}，图层: {layer}"
    except Exception as e:
        return _format_error("绘制轻量多段线", e)


@mcp.tool
def draw_polyline(vertices: list, layer: str = "0",
                  closed: bool = False) -> str:
    """
    在 ZWCAD 中绘制2D多段线（Polyline）

    参数:
    - vertices: 顶点坐标列表，格式为 [[x1,y1,z1], [x2,y2,z2], ...] 或 [x1,y1,x2,y2,...]
    - layer: 图层名称（可选，默认为"0"）
    - closed: 是否闭合（可选，默认False）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        flat = []
        for v in vertices:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        pline = zcad_conn.model.AddPolyline(coords)
        pline.Layer = layer
        if closed:
            pline.Closed = True
        return f"成功绘制2D多段线: {len(flat)//3}个顶点, 闭合={closed}，图层: {layer}"
    except Exception as e:
        return _format_error("绘制2D多段线", e)


@mcp.tool
def draw_spline(fit_points: list,
                start_tangent_x: float = 0, start_tangent_y: float = 0, start_tangent_z: float = 0,
                end_tangent_x: float = 0, end_tangent_y: float = 0, end_tangent_z: float = 0,
                layer: str = "0") -> str:
    """
    在 ZWCAD 中绘制样条曲线

    参数:
    - fit_points: 拟合点列表，格式为 [[x1,y1,z1], [x2,y2,z2], ...] 或 [x1,y1,z1,x2,y2,z2,...]
    - start_tangent_x/y/z: 起点切向向量（可选，默认0）
    - end_tangent_x/y/z: 终点切向向量（可选，默认0）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        flat = []
        for v in fit_points:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        points = aDouble(*flat)
        start_tan = APoint(start_tangent_x, start_tangent_y, start_tangent_z)
        end_tan = APoint(end_tangent_x, end_tangent_y, end_tangent_z)
        spline = zcad_conn.model.AddSpline(points, start_tan, end_tan)
        spline.Layer = layer
        return f"成功绘制样条曲线: {len(flat)//3}个拟合点，图层: {layer}"
    except Exception as e:
        return _format_error("绘制样条曲线", e)


@mcp.tool
def add_point(x: float, y: float, z: float,
              layer: str = "0") -> str:
    """
    在指定位置添加点对象

    参数:
    - x, y, z: 点坐标
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        pt = zcad_conn.model.AddPoint(point)
        pt.Layer = layer
        return f"成功添加点: ({x},{y},{z})，图层: {layer}"
    except Exception as e:
        return _format_error("添加点", e)


@mcp.tool
def add_mtext(text: str, x: float, y: float, z: float,
              width: float = 0, height: float = 2.5,
              rotation: float = 0, layer: str = "0") -> str:
    """
    在指定位置添加多行文本（MText）

    参数:
    - text: 文本内容（支持格式代码）
    - x, y, z: 插入点坐标
    - width: 文本框宽度（可选，0=无限制）
    - height: 文字高度（可选，默认2.5）
    - rotation: 旋转角度（弧度，可选，默认0）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        mtext = zcad_conn.model.AddMText(point, width, text)
        mtext.Height = height
        mtext.Rotation = rotation
        mtext.Layer = layer
        return f"成功添加多行文本: '{text[:50]}' at ({x},{y},{z})，字高: {height}，图层: {layer}"
    except Exception as e:
        return _format_error("添加多行文本", e)


@mcp.tool
def insert_block(block_name: str, x: float, y: float, z: float,
                 x_scale: float = 1.0, y_scale: float = 1.0, z_scale: float = 1.0,
                 rotation: float = 0.0,
                 layer: str = "0") -> str:
    """
    在指定位置插入图块引用

    参数:
    - block_name: 图块名称或DWG文件路径
    - x, y, z: 插入点坐标
    - x_scale, y_scale, z_scale: X/Y/Z方向缩放比例（可选，默认1.0）
    - rotation: 旋转角度（弧度，可选，默认0）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        block_ref = zcad_conn.model.InsertBlock(point, block_name, x_scale, y_scale, z_scale, rotation)
        block_ref.Layer = layer
        return f"成功插入图块: '{block_name}' at ({x},{y},{z})，比例({x_scale},{y_scale},{z_scale})，图层: {layer}"
    except Exception as e:
        return _format_error("插入图块", e)


# ==========================================
# 标注工具（来自 IZcadBlock / IZcadModelSpace COM 接口）
# ==========================================

@mcp.tool
def add_dim_aligned(x1: float, y1: float, z1: float,
                    x2: float, y2: float, z2: float,
                    dim_x: float, dim_y: float, dim_z: float,
                    layer: str = "0",
                    text_override: str = "") -> str:
    """
    添加对齐标注

    参数:
    - x1,y1,z1: 第一条延伸线原点
    - x2,y2,z2: 第二条延伸线原点
    - dim_x,dim_y,dim_z: 标注文字位置
    - layer: 图层名称（可选，默认为"0"）
    - text_override: 标注文字覆盖（可选，默认为空使用自动测量值）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        dim_pt = APoint(dim_x, dim_y, dim_z)
        dim = zcad_conn.model.AddDimAligned(p1, p2, dim_pt)
        dim.Layer = layer
        if text_override:
            dim.TextOverride = text_override
        measurement = dim.Measurement
        return f"成功添加对齐标注: ({x1},{y1})-({x2},{y2}), 测量值={measurement:.4f}，图层: {layer}"
    except Exception as e:
        return _format_error("添加对齐标注", e)


@mcp.tool
def add_dim_rotated(x1: float, y1: float, z1: float,
                    x2: float, y2: float, z2: float,
                    dim_x: float, dim_y: float, dim_z: float,
                    rotation_angle: float,
                    layer: str = "0",
                    text_override: str = "") -> str:
    """
    添加旋转标注

    参数:
    - x1,y1,z1: 第一条延伸线原点
    - x2,y2,z2: 第二条延伸线原点
    - dim_x,dim_y,dim_z: 标注线位置
    - rotation_angle: 标注线旋转角度（弧度）
    - layer: 图层名称（可选，默认为"0"）
    - text_override: 标注文字覆盖（可选，默认为空使用自动测量值）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        dim_pt = APoint(dim_x, dim_y, dim_z)
        dim = zcad_conn.model.AddDimRotated(p1, p2, dim_pt, rotation_angle)
        dim.Layer = layer
        if text_override:
            dim.TextOverride = text_override
        measurement = dim.Measurement
        return f"成功添加旋转标注: 角度={rotation_angle:.4f}, 测量值={measurement:.4f}，图层: {layer}"
    except Exception as e:
        return _format_error("添加旋转标注", e)


@mcp.tool
def add_dim_diametric(chord_x: float, chord_y: float, chord_z: float,
                      far_chord_x: float, far_chord_y: float, far_chord_z: float,
                      leader_length: float = 0,
                      layer: str = "0",
                      text_override: str = "") -> str:
    """
    添加直径标注

    参数:
    - chord_x,chord_y,chord_z: 弦上第一点（圆上一点）
    - far_chord_x,far_chord_y,far_chord_z: 弦上对侧点（圆上对侧点）
    - leader_length: 引线长度（可选，默认0）
    - layer: 图层名称（可选，默认为"0"）
    - text_override: 标注文字覆盖（可选，默认为空使用自动测量值）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        chord = APoint(chord_x, chord_y, chord_z)
        far_chord = APoint(far_chord_x, far_chord_y, far_chord_z)
        dim = zcad_conn.model.AddDimDiametric(chord, far_chord, leader_length)
        dim.Layer = layer
        if text_override:
            dim.TextOverride = text_override
        measurement = dim.Measurement
        return f"成功添加直径标注: 测量值={measurement:.4f}，图层: {layer}"
    except Exception as e:
        return _format_error("添加直径标注", e)


@mcp.tool
def add_dim_radial(center_x: float, center_y: float, center_z: float,
                   chord_x: float, chord_y: float, chord_z: float,
                   leader_length: float = 0,
                   layer: str = "0",
                   text_override: str = "") -> str:
    """
    添加半径标注

    参数:
    - center_x,center_y,center_z: 圆心坐标
    - chord_x,chord_y,chord_z: 圆上一点坐标
    - leader_length: 引线长度（可选，默认0）
    - layer: 图层名称（可选，默认为"0"）
    - text_override: 标注文字覆盖（可选，默认为空使用自动测量值）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        chord = APoint(chord_x, chord_y, chord_z)
        dim = zcad_conn.model.AddDimRadial(center, chord, leader_length)
        dim.Layer = layer
        if text_override:
            dim.TextOverride = text_override
        measurement = dim.Measurement
        return f"成功添加半径标注: 测量值={measurement:.4f}，图层: {layer}"
    except Exception as e:
        return _format_error("添加半径标注", e)


@mcp.tool
def add_dim_angular(vertex_x: float, vertex_y: float, vertex_z: float,
                    first_x: float, first_y: float, first_z: float,
                    second_x: float, second_y: float, second_z: float,
                    text_x: float, text_y: float, text_z: float,
                    layer: str = "0",
                    text_override: str = "") -> str:
    """
    添加角度标注

    参数:
    - vertex_x,vertex_y,vertex_z: 角度顶点
    - first_x,first_y,first_z: 第一条边的端点
    - second_x,second_y,second_z: 第二条边的端点
    - text_x,text_y,text_z: 标注文字位置
    - layer: 图层名称（可选，默认为"0"）
    - text_override: 标注文字覆盖（可选，默认为空使用自动测量值）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        vertex = APoint(vertex_x, vertex_y, vertex_z)
        first = APoint(first_x, first_y, first_z)
        second = APoint(second_x, second_y, second_z)
        text_pt = APoint(text_x, text_y, text_z)
        dim = zcad_conn.model.AddDimAngular(vertex, first, second, text_pt)
        dim.Layer = layer
        if text_override:
            dim.TextOverride = text_override
        measurement = dim.Measurement
        return f"成功添加角度标注: 测量值={measurement:.4f}，图层: {layer}"
    except Exception as e:
        return _format_error("添加角度标注", e)


@mcp.tool
def add_dim_ordinate(def_x: float, def_y: float, def_z: float,
                     leader_x: float, leader_y: float, leader_z: float,
                     use_x_axis: bool = True,
                     layer: str = "0",
                     text_override: str = "") -> str:
    """
    添加坐标标注

    参数:
    - def_x,def_y,def_z: 定义点坐标
    - leader_x,leader_y,leader_z: 引线端点坐标
    - use_x_axis: True=标注X坐标，False=标注Y坐标（默认True）
    - layer: 图层名称（可选，默认为"0"）
    - text_override: 标注文字覆盖（可选，默认为空使用自动测量值）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def_pt = APoint(def_x, def_y, def_z)
        leader_pt = APoint(leader_x, leader_y, leader_z)
        dim = zcad_conn.model.AddDimOrdinate(def_pt, leader_pt, use_x_axis)
        dim.Layer = layer
        if text_override:
            dim.TextOverride = text_override
        axis = "X" if use_x_axis else "Y"
        return f"成功添加坐标标注: {axis}轴，图层: {layer}"
    except Exception as e:
        return _format_error("添加坐标标注", e)


# ==========================================
# 图元操作工具（来自 IZcadEntity COM 接口）
# ==========================================

@mcp.tool
def copy_object(object_type: str, property_name: str, property_value: str,
                to_x: float, to_y: float, to_z: float) -> str:
    """
    复制对象到指定位置（通过偏移移动）

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - to_x, to_y, to_z: 复制到的目标位置坐标

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        # 获取对象位置
        if hasattr(obj, 'InsertionPoint'):
            from_pt = obj.InsertionPoint
        elif hasattr(obj, 'Center'):
            from_pt = obj.Center
        elif hasattr(obj, 'StartPoint'):
            from_pt = obj.StartPoint
        else:
            return "无法确定对象位置，不支持该类型对象的复制"

        to_pt = APoint(to_x, to_y, to_z)
        new_obj = obj.Copy()
        new_obj.Move(from_pt, to_pt)
        return f"成功复制对象到 ({to_x},{to_y},{to_z})"
    except Exception as e:
        return _format_error("复制对象", e)


@mcp.tool
def move_object(object_type: str, property_name: str, property_value: str,
                to_x: float, to_y: float, to_z: float) -> str:
    """
    移动对象到指定位置

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - to_x, to_y, to_z: 目标位置坐标

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        if hasattr(obj, 'InsertionPoint'):
            from_pt = obj.InsertionPoint
        elif hasattr(obj, 'Center'):
            from_pt = obj.Center
        elif hasattr(obj, 'StartPoint'):
            from_pt = obj.StartPoint
        else:
            return "无法确定对象位置"

        to_pt = APoint(to_x, to_y, to_z)
        obj.Move(from_pt, to_pt)
        return f"成功移动对象到 ({to_x},{to_y},{to_z})"
    except Exception as e:
        return _format_error("移动对象", e)


@mcp.tool
def rotate_object(object_type: str, property_name: str, property_value: str,
                  base_x: float, base_y: float, base_z: float,
                  rotation_angle: float) -> str:
    """
    旋转对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - base_x, base_y, base_z: 旋转基点坐标
    - rotation_angle: 旋转角度（弧度）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        base_pt = APoint(base_x, base_y, base_z)
        obj.Rotate(base_pt, rotation_angle)
        return f"成功旋转对象: 基点({base_x},{base_y},{base_z}), 角度={rotation_angle:.4f}弧度"
    except Exception as e:
        return _format_error("旋转对象", e)


@mcp.tool
def mirror_object(object_type: str, property_name: str, property_value: str,
                  x1: float, y1: float, z1: float,
                  x2: float, y2: float, z2: float,
                  delete_original: bool = False) -> str:
    """
    镜像对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - x1,y1,z1: 镜像轴第一点
    - x2,y2,z2: 镜像轴第二点
    - delete_original: 是否删除原对象（可选，默认False保留原对象）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        mirrored = obj.Mirror(p1, p2)
        if delete_original:
            obj.Delete()
        action = "并删除原对象" if delete_original else "保留原对象"
        return f"成功镜像对象{action}: 轴({x1},{y1})-({x2},{y2})"
    except Exception as e:
        return _format_error("镜像对象", e)


@mcp.tool
def scale_object(object_type: str, property_name: str, property_value: str,
                 base_x: float, base_y: float, base_z: float,
                 scale_factor: float) -> str:
    """
    缩放对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - base_x, base_y, base_z: 缩放基点坐标
    - scale_factor: 缩放比例因子

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        base_pt = APoint(base_x, base_y, base_z)
        obj.ScaleEntity(base_pt, scale_factor)
        return f"成功缩放对象: 基点({base_x},{base_y},{base_z}), 比例={scale_factor}"
    except Exception as e:
        return _format_error("缩放对象", e)


@mcp.tool
def delete_object(object_type: str, property_name: str, property_value: str) -> str:
    """
    删除对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        obj.Delete()
        return f"成功删除对象: {object_type}.{property_name}={property_value}"
    except Exception as e:
        return _format_error("删除对象", e)


@mcp.tool
def array_polar(object_type: str, property_name: str, property_value: str,
                center_x: float, center_y: float, center_z: float,
                number_of_objects: int, angle_to_fill: float) -> str:
    """
    极坐标阵列对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - center_x, center_y, center_z: 阵列中心点坐标
    - number_of_objects: 阵列数量（含原对象）
    - angle_to_fill: 填充角度（弧度，正=逆时针）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        center = APoint(center_x, center_y, center_z)
        result = obj.ArrayPolar(number_of_objects, angle_to_fill, center)
        return f"成功极坐标阵列: 数量={number_of_objects}, 填充角度={angle_to_fill:.4f}弧度"
    except Exception as e:
        return _format_error("极坐标阵列", e)


@mcp.tool
def array_rectangular(object_type: str, property_name: str, property_value: str,
                      num_rows: int, num_cols: int, num_levels: int,
                      row_dist: float, col_dist: float, level_dist: float) -> str:
    """
    矩形阵列对象

    参数:
    - object_type: 对象类型（如 "Line", "Circle" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值
    - num_rows: 行数
    - num_cols: 列数
    - num_levels: 层数（3D阵列）
    - row_dist: 行间距
    - col_dist: 列间距
    - level_dist: 层间距

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return f"未找到符合条件的对象: {object_type}.{property_name}={property_value}"

        result = obj.ArrayRectangular(num_rows, num_cols, num_levels,
                                       row_dist, col_dist, level_dist)
        return f"成功矩形阵列: {num_rows}行×{num_cols}列×{num_levels}层"
    except Exception as e:
        return _format_error("矩形阵列", e)


@mcp.tool
def get_object_properties(object_type: str, property_name: str, property_value: str) -> str:
    """
    获取对象的详细属性信息

    参数:
    - object_type: 对象类型（如 "Line", "Circle", "Arc" 等）
    - property_name: 用于定位的属性名（如 "Layer"）
    - property_value: 属性值

    返回: JSON 格式的对象属性信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one(object_type, predicate=predicate)
        if not obj:
            return json.dumps({"found": False}, ensure_ascii=False)

        info = {"found": True, "object_name": obj.ObjectName}

        # 通用属性
        common_props = ['Layer', 'Color', 'Linetype', 'LinetypeScale',
                        'Lineweight', 'Visible', 'EntityName', 'EntityType']
        for prop in common_props:
            if hasattr(obj, prop):
                try:
                    info[prop] = getattr(obj, prop)
                except Exception:
                    pass

        # 几何属性
        geo_props = ['StartPoint', 'EndPoint', 'Center', 'Radius', 'Length',
                     'Area', 'Height', 'Rotation', 'InsertionPoint',
                     'StartAngle', 'EndAngle', 'TotalAngle',
                     'XScaleFactor', 'YScaleFactor', 'ZScaleFactor',
                     'TextString', 'Closed', 'Coordinates']
        for prop in geo_props:
            if hasattr(obj, prop):
                try:
                    val = getattr(obj, prop)
                    # 转换APoint等类型为可序列化格式
                    if hasattr(val, '__iter__'):
                        val = list(val)
                    info[prop] = val
                except Exception:
                    pass

        # 边界框
        try:
            min_pt, max_pt = obj.GetBoundingBox()
            info['bounding_box'] = {
                'min': list(min_pt),
                'max': list(max_pt)
            }
        except Exception:
            pass

        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return f"获取对象属性失败: {str(e)}"


# ==========================================
# 图层管理工具（来自 IZcadLayers / IZcadLayer COM 接口）
# ==========================================

@mcp.tool
def list_layers() -> str:
    """
    获取当前文档的所有图层列表

    返回: JSON 格式的图层列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        layers = []
        for layer in zcad_conn.doc.Layers:
            info = {
                "name": layer.Name,
                "on": layer.LayerOn,
                "frozen": layer.Freeze,
                "locked": layer.Lock,
                "color": layer.color
            }
            if hasattr(layer, 'Linetype'):
                info['linetype'] = layer.Linetype
            if hasattr(layer, 'Description'):
                try:
                    info['description'] = layer.Description
                except Exception:
                    pass
            layers.append(info)
        return json.dumps(layers, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取图层列表失败: {str(e)}"


@mcp.tool
def add_layer(name: str, color: int = 7,
              linetype: str = "Continuous",
              description: str = "") -> str:
    """
    创建新图层

    参数:
    - name: 图层名称
    - color: 颜色索引号（可选，默认7=白色）
    - linetype: 线型名称（可选，默认"Continuous"）
    - description: 图层描述（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        layer = zcad_conn.doc.Layers.Add(name)
        layer.color = color
        layer.Linetype = linetype
        if description and hasattr(layer, 'Description'):
            layer.Description = description
        return f"成功创建图层: '{name}', 颜色={color}, 线型={linetype}"
    except Exception as e:
        return _format_error("创建图层", e)


@mcp.tool
def set_active_layer(name: str) -> str:
    """
    设置当前活动图层

    参数:
    - name: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        layer = zcad_conn.doc.Layers.Item(name)
        zcad_conn.doc.ActiveLayer = layer
        return f"成功设置活动图层: '{name}'"
    except Exception as e:
        return _format_error("设置活动图层", e)


@mcp.tool
def set_layer_properties(name: str,
                         on: bool = None,
                         freeze: bool = None,
                         lock: bool = None,
                         color: int = None,
                         linetype: str = None) -> str:
    """
    设置图层属性

    参数:
    - name: 图层名称
    - on: 图层是否打开（可选）
    - freeze: 图层是否冻结（可选）
    - lock: 图层是否锁定（可选）
    - color: 颜色索引号（可选）
    - linetype: 线型名称（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        layer = zcad_conn.doc.Layers.Item(name)
        updated = []
        if on is not None:
            layer.LayerOn = on
            updated.append(f"on={on}")
        if freeze is not None:
            layer.Freeze = freeze
            updated.append(f"freeze={freeze}")
        if lock is not None:
            layer.Lock = lock
            updated.append(f"lock={lock}")
        if color is not None:
            layer.color = color
            updated.append(f"color={color}")
        if linetype is not None:
            layer.Linetype = linetype
            updated.append(f"linetype={linetype}")
        if updated:
            return f"成功更新图层 '{name}': {', '.join(updated)}"
        return "未提供任何要更新的属性"
    except Exception as e:
        return _format_error("设置图层属性", e)


# ==========================================
# 线型/文字样式/标注样式管理工具
# ==========================================

@mcp.tool
def list_linetypes() -> str:
    """
    获取当前文档的所有线型列表

    返回: JSON 格式的线型列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        linetypes = []
        for lt in zcad_conn.doc.Linetypes:
            info = {"name": lt.Name}
            if hasattr(lt, 'Description'):
                try:
                    info['description'] = lt.Description
                except Exception:
                    pass
            linetypes.append(info)
        return json.dumps(linetypes, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取线型列表失败: {str(e)}"


@mcp.tool
def load_linetype(name: str, filename: str = "acad.lin") -> str:
    """
    从线型文件加载线型

    参数:
    - name: 线型名称
    - filename: 线型文件名（可选，默认"acad.lin"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Linetypes.Load(name, filename)
        return f"成功加载线型: '{name}' (文件: {filename})"
    except Exception as e:
        return _format_error("加载线型", e)


@mcp.tool
def list_textstyles() -> str:
    """
    获取当前文档的所有文字样式列表

    返回: JSON 格式的文字样式列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        styles = []
        for ts in zcad_conn.doc.TextStyles:
            info = {
                "name": ts.Name,
                "font_file": ts.fontFile if hasattr(ts, 'fontFile') else "",
                "height": ts.Height if hasattr(ts, 'Height') else 0,
                "width": ts.Width if hasattr(ts, 'Width') else 1.0,
                "oblique_angle": ts.ObliqueAngle if hasattr(ts, 'ObliqueAngle') else 0
            }
            styles.append(info)
        return json.dumps(styles, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取文字样式列表失败: {str(e)}"


@mcp.tool
def add_textstyle(name: str, font_file: str = "txt.shx",
                  big_font_file: str = "hztxt.shx",
                  height: float = 0) -> str:
    """
    创建新的文字样式

    参数:
    - name: 样式名称
    - font_file: 字体文件名（可选，默认"txt.shx"）
    - big_font_file: 大字体文件名（可选，默认"hztxt.shx"）
    - height: 固定文字高度（可选，0=不固定）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        ts = zcad_conn.doc.TextStyles.Add(name)
        if font_file:
            ts.fontFile = font_file
        if big_font_file and hasattr(ts, 'BigFontFile'):
            ts.BigFontFile = big_font_file
        if height > 0:
            ts.Height = height
        return f"成功创建文字样式: '{name}', 字体={font_file}, 大字体={big_font_file}"
    except Exception as e:
        return _format_error("创建文字样式", e)


@mcp.tool
def list_dimstyles() -> str:
    """
    获取当前文档的所有标注样式列表

    返回: JSON 格式的标注样式列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        styles = []
        for ds in zcad_conn.doc.DimStyles:
            styles.append({"name": ds.Name})
        return json.dumps(styles, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取标注样式列表失败: {str(e)}"


@mcp.tool
def add_dimstyle(name: str) -> str:
    """
    创建新的标注样式

    参数:
    - name: 样式名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.DimStyles.Add(name)
        return f"成功创建标注样式: '{name}'"
    except Exception as e:
        return _format_error("创建标注样式", e)


# ==========================================
# 图块管理工具（来自 IZcadBlocks / IZcadBlock COM 接口）
# ==========================================

@mcp.tool
def list_blocks() -> str:
    """
    获取当前文档的所有图块定义列表

    返回: JSON 格式的图块列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        blocks = []
        for blk in zcad_conn.doc.Blocks:
            info = {
                "name": blk.Name,
                "is_layout": blk.IsLayout if hasattr(blk, 'IsLayout') else False,
                "is_xref": blk.IsXRef if hasattr(blk, 'IsXRef') else False,
                "count": blk.Count if hasattr(blk, 'Count') else 0
            }
            if hasattr(blk, 'Origin'):
                try:
                    origin = blk.Origin
                    info['origin'] = list(origin)
                except Exception:
                    pass
            blocks.append(info)
        return json.dumps(blocks, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取图块列表失败: {str(e)}"


@mcp.tool
def get_block_info(name: str) -> str:
    """
    获取指定图块的详细信息

    参数:
    - name: 图块名称

    返回: JSON 格式的图块信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        blk = zcad_conn.doc.Blocks.Item(name)
        info = {
            "name": blk.Name,
            "count": blk.Count,
            "is_layout": blk.IsLayout if hasattr(blk, 'IsLayout') else False,
            "is_xref": blk.IsXRef if hasattr(blk, 'IsXRef') else False,
            "is_dynamic": blk.IsDynamicBlock if hasattr(blk, 'IsDynamicBlock') else False
        }
        if hasattr(blk, 'Origin'):
            try:
                info['origin'] = list(blk.Origin)
            except Exception:
                pass
        if hasattr(blk, 'Comments'):
            try:
                info['comments'] = blk.Comments
            except Exception:
                pass
        if hasattr(blk, 'Path'):
            try:
                info['path'] = blk.Path
            except Exception:
                pass
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取图块信息失败: {str(e)}"


@mcp.tool
def get_block_attributes(block_name: str, property_name: str, property_value: str) -> str:
    """
    获取图块引用的属性值

    参数:
    - block_name: 图块类型名称
    - property_name: 用于定位图块引用的属性名（如 "Layer"）
    - property_value: 属性值

    返回: JSON 格式的属性列表
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def predicate(obj):
            if hasattr(obj, 'Name') and obj.Name == block_name:
                if hasattr(obj, property_name):
                    return str(getattr(obj, property_name)) == property_value
            return False

        obj = zcad_conn.find_one("BlockReference", predicate=predicate)
        if not obj:
            return f"未找到符合条件的图块引用: {block_name}"

        attrs = obj.GetAttributes()
        result = []
        for attr in attrs:
            result.append({
                "tag": attr.TagString if hasattr(attr, 'TagString') else "",
                "text": attr.TextString if hasattr(attr, 'TextString') else "",
            })
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取图块属性失败: {str(e)}"


# ==========================================
# 文档/应用程序工具（来自 IZcadDocument / IZcadApplication COM 接口）
# ==========================================

@mcp.tool
def zoom_extents() -> str:
    """
    缩放到图形范围（Zoom Extents）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.app.ZoomExtents()
        return "成功执行 Zoom Extents"
    except Exception as e:
        return _format_error("Zoom Extents", e)


@mcp.tool
def zoom_all() -> str:
    """
    缩放显示全部图形（Zoom All）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.app.ZoomAll()
        return "成功执行 Zoom All"
    except Exception as e:
        return _format_error("Zoom All", e)


@mcp.tool
def zoom_window(x1: float, y1: float, x2: float, y2: float) -> str:
    """
    窗口缩放（Zoom Window）

    参数:
    - x1, y1: 窗口左下角坐标
    - x2, y2: 窗口右上角坐标

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        lower_left = APoint(x1, y1, 0)
        upper_right = APoint(x2, y2, 0)
        zcad_conn.app.ZoomWindow(lower_left, upper_right)
        return f"成功执行 Zoom Window: ({x1},{y1})-({x2},{y2})"
    except Exception as e:
        return _format_error("Zoom Window", e)


@mcp.tool
def zoom_center(center_x: float, center_y: float, magnify: float = 1.0) -> str:
    """
    中心缩放（Zoom Center）

    参数:
    - center_x, center_y: 中心点坐标
    - magnify: 放大倍数（可选，默认1.0）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, 0)
        zcad_conn.app.ZoomCenter(center, magnify)
        return f"成功执行 Zoom Center: ({center_x},{center_y}), 倍数={magnify}"
    except Exception as e:
        return _format_error("Zoom Center", e)


@mcp.tool
def get_variable(name: str) -> str:
    """
    获取ZWCAD系统变量的值

    参数:
    - name: 系统变量名称（如 "DIMSCALE", "TEXTSIZE", "LUNITS" 等）

    返回: 变量值
    """
    try:
        zcad_conn, _ = get_cad_connection()
        value = zcad_conn.doc.GetVariable(name)
        return f"系统变量 '{name}' = {value}"
    except Exception as e:
        return f"获取系统变量失败: {str(e)}"


@mcp.tool
def set_variable(name: str, value) -> str:
    """
    设置ZWCAD系统变量的值

    参数:
    - name: 系统变量名称
    - value: 要设置的值（字符串或数字）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.SetVariable(name, value)
        return f"成功设置系统变量 '{name}' = {value}"
    except Exception as e:
        return _format_error("设置系统变量", e)


@mcp.tool
def send_command(command: str) -> str:
    """
    向ZWCAD发送命令行命令（SendCommand）

    参数:
    - command: 命令字符串（如 "._LINE 0,0 100,100 "）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.SendCommand(command)
        return f"命令已发送: {command}"
    except Exception as e:
        return _format_error("发送命令", e)


@mcp.tool
def get_application_info() -> str:
    """
    获取ZWCAD应用程序信息（版本、路径、窗口状态等）

    返回: JSON 格式的应用程序信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        app = zcad_conn.app
        info = {
            "name": app.Name,
            "version": app.Version,
            "full_name": app.FullName,
            "path": app.Path,
            "visible": app.Visible,
            "hwnd": app.HWND if hasattr(app, 'HWND') else None
        }
        if hasattr(app, 'WindowState'):
            info['window_state'] = app.WindowState
        if hasattr(app, 'Caption'):
            info['caption'] = app.Caption
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return f"获取应用程序信息失败: {str(e)}"


@mcp.tool
def plot_to_file(plot_file: str, plot_config: str = "") -> str:
    """
    打印到文件

    参数:
    - plot_file: 输出文件路径（如 "C:\\output\\drawing.pdf"）
    - plot_config: 打印配置名称（可选，使用默认配置）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        plot = zcad_conn.doc.Plot
        if plot_config:
            plot.PlotToFile(plot_file, plot_config)
        else:
            plot.PlotToFile(plot_file)
        return f"成功打印到文件: {plot_file}"
    except Exception as e:
        return _format_error("打印到文件", e)


@mcp.tool
def regen_viewport(which: int = 0) -> str:
    """
    重生成视口显示

    参数:
    - which: 重生成范围（0=活动视口，1=所有视口）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Regen(which)
        return f"成功重生成视口 (which={which})"
    except Exception as e:
        return _format_error("重生成视口", e)


@mcp.tool
def purge_all() -> str:
    """
    清除当前文档中所有未使用的命名对象（图层、图块、样式等）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.PurgeAll()
        return "成功清除所有未使用的命名对象"
    except Exception as e:
        return _format_error("清除命名对象", e)


@mcp.tool
def set_active_textstyle(name: str) -> str:
    """
    设置当前活动文字样式

    参数:
    - name: 文字样式名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        ts = zcad_conn.doc.TextStyles.Item(name)
        zcad_conn.doc.ActiveTextStyle = ts
        return f"成功设置活动文字样式: '{name}'"
    except Exception as e:
        return _format_error("设置活动文字样式", e)


@mcp.tool
def set_active_dimstyle(name: str) -> str:
    """
    设置当前活动标注样式

    参数:
    - name: 标注样式名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        ds = zcad_conn.doc.DimStyles.Item(name)
        zcad_conn.doc.ActiveDimStyle = ds
        return f"成功设置活动标注样式: '{name}'"
    except Exception as e:
        return _format_error("设置活动标注样式", e)


@mcp.tool
def set_active_linetype(name: str) -> str:
    """
    设置当前活动线型

    参数:
    - name: 线型名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        lt = zcad_conn.doc.Linetypes.Item(name)
        zcad_conn.doc.ActiveLinetype = lt
        return f"成功设置活动线型: '{name}'"
    except Exception as e:
        return _format_error("设置活动线型", e)


@mcp.tool
def undo_mark_start() -> str:
    """
    开始撤销标记（StartUndoMark）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.StartUndoMark()
        return "撤销标记已开始"
    except Exception as e:
        return _format_error("开始撤销标记", e)


@mcp.tool
def undo_mark_end() -> str:
    """
    结束撤销标记（EndUndoMark）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.EndUndoMark()
        return "撤销标记已结束"
    except Exception as e:
        return _format_error("结束撤销标记", e)


@mcp.tool
def add_hatch(pattern_type: int, pattern_name: str,
              outer_loop_objects: list,
              associativity: bool = True,
              layer: str = "0",
              pattern_scale: float = 1.0,
              pattern_angle: float = 0) -> str:
    """
    添加填充图案

    参数:
    - pattern_type: 图案类型（0=预定义，1=用户定义，2=自定义）
    - pattern_name: 图案名称（如 "ANSI31", "SOLID" 等）
    - outer_loop_objects: 外边界对象ID列表（需为有效的COM对象数组）
    - associativity: 是否关联（可选，默认True）
    - layer: 图层名称（可选，默认为"0"）
    - pattern_scale: 图案缩放比例（可选，默认1.0）
    - pattern_angle: 图案角度（弧度，可选，默认0）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        hatch = zcad_conn.model.AddHatch(pattern_type, pattern_name, associativity)
        hatch.Layer = layer
        hatch.PatternScale = pattern_scale
        hatch.PatternAngle = pattern_angle

        # 构建外边界环
        if outer_loop_objects:
            obj_array = []
            for obj_id in outer_loop_objects:
                try:
                    obj = zcad_conn.doc.ObjectIdToObject(obj_id)
                    obj_array.append(obj)
                except Exception:
                    pass
            if obj_array:
                hatch.AppendOuterLoop(obj_array)
                hatch.Evaluate()

        return f"成功添加填充: 图案='{pattern_name}', 类型={pattern_type}, 比例={pattern_scale}"
    except Exception as e:
        return _format_error("添加填充", e)


@mcp.tool
def add_leader(points: list, annotation_type: int = 0,
               layer: str = "0") -> str:
    """
    添加引线标注

    参数:
    - points: 引线点列表，格式为 [[x1,y1,z1], [x2,y2,z2], ...] 或 [x1,y1,z1,x2,y2,z2,...]
    - annotation_type: 注释类型（0=无，1=文字，2=图块，3=公差）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        flat = []
        for v in points:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        leader = zcad_conn.model.AddLeader(coords, None, annotation_type)
        leader.Layer = layer
        return f"成功添加引线: {len(flat)//3}个点, 注释类型={annotation_type}，图层: {layer}"
    except Exception as e:
        return _format_error("添加引线", e)


@mcp.tool
def add_tolerance(text: str, x: float, y: float, z: float,
                  dir_x: float = 0, dir_y: float = 0, dir_z: float = 1,
                  layer: str = "0") -> str:
    """
    添加形位公差标注

    参数:
    - text: 公差文本
    - x, y, z: 插入点坐标
    - dir_x, dir_y, dir_z: 方向向量（可选，默认Z方向）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        direction = APoint(dir_x, dir_y, dir_z)
        tol = zcad_conn.model.AddTolerance(text, point, direction)
        tol.Layer = layer
        return f"成功添加形位公差: '{text}' at ({x},{y},{z})，图层: {layer}"
    except Exception as e:
        return _format_error("添加形位公差", e)


@mcp.tool
def add_table(x: float, y: float, z: float,
              rows: int, cols: int,
              row_height: float, col_width: float,
              layer: str = "0") -> str:
    """
    添加表格对象

    参数:
    - x, y, z: 插入点坐标
    - rows: 行数
    - cols: 列数
    - row_height: 行高
    - col_width: 列宽
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        table = zcad_conn.model.AddTable(point, rows, cols, row_height, col_width)
        table.Layer = layer
        return f"成功添加表格: {rows}行×{cols}列 at ({x},{y},{z})，图层: {layer}"
    except Exception as e:
        return _format_error("添加表格", e)


@mcp.tool
def translate_coordinates(x: float, y: float, z: float,
                          from_system: int, to_system: int,
                          displacement: bool = False) -> str:
    """
    坐标系转换

    参数:
    - x, y, z: 要转换的坐标
    - from_system: 源坐标系（0=WCS，1=UCS，2=OCS，3=DSC，4=PCS）
    - to_system: 目标坐标系（0=WCS，1=UCS，2=OCS，3=DSC，4=PCS）
    - displacement: 是否为位移向量（可选，默认False）

    返回: 转换后的坐标
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = aDouble(x, y, z)
        result = zcad_conn.doc.Utility.TranslateCoordinates(
            point, from_system, to_system, displacement
        )
        coords = list(result)
        return json.dumps({"x": coords[0], "y": coords[1], "z": coords[2] if len(coords) > 2 else 0}, indent=2)
    except Exception as e:
        return _format_error("坐标转换", e)


@mcp.tool
def export_drawing(filename: str, extension: str = "DWG") -> str:
    """
    导出当前文档到指定格式

    参数:
    - filename: 导出文件路径
    - extension: 导出格式扩展名（"DWG", "DXF", "BMP", "WMF" 等）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        # 创建选择集用于导出
        sel_set_name = "ExportSelSet"
        try:
            sel = zcad_conn.doc.SelectionSets.Item(sel_set_name)
            sel.Delete()
        except Exception:
            pass
        sel = zcad_conn.doc.SelectionSets.Add(sel_set_name)
        sel.Select(5)  # acSelectionSetAll
        zcad_conn.doc.Export(filename, extension, sel)
        # 清理选择集
        try:
            sel.Delete()
        except Exception:
            pass
        return f"成功导出: {filename} (格式: {extension})"
    except Exception as e:
        return _format_error("导出文档", e)


@mcp.tool
def import_file(filename: str, x: float = 0, y: float = 0, z: float = 0,
                scale_factor: float = 1.0) -> str:
    """
    导入文件到当前文档

    参数:
    - filename: 导入文件路径
    - x, y, z: 插入点坐标（可选，默认原点）
    - scale_factor: 缩放比例（可选，默认1.0）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        zcad_conn.doc.Import(filename, point, scale_factor)
        return f"成功导入文件: {filename} at ({x},{y},{z}), 比例={scale_factor}"
    except Exception as e:
        return _format_error("导入文件", e)


# ==========================================
# 3D实体与曲面绘制工具（来自 IZcadBlock 的 3D 方法）
# ==========================================

@mcp.tool
def draw_3d_face(x1: float, y1: float, z1: float,
                 x2: float, y2: float, z2: float,
                 x3: float, y3: float, z3: float,
                 x4: float = None, y4: float = None, z4: float = None,
                 layer: str = "0") -> str:
    """
    绘制3D面

    参数:
    - x1,y1,z1 ~ x4,y4,z4: 四个角点坐标（若第4点不提供则使用第3点）
    - layer: 图层名称（可选，默认为"0"）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        p3 = APoint(x3, y3, z3)
        if x4 is None:
            x4, y4, z4 = x3, y3, z3
        p4 = APoint(x4, y4, z4)
        face = zcad_conn.model.Add3DFace(p1, p2, p3, p4)
        face.Layer = layer
        return f"成功绘制3D面：图层: {layer}"
    except Exception as e:
        return _format_error("绘制3D面", e)


@mcp.tool
def draw_box(origin_x: float, origin_y: float, origin_z: float,
             length: float, width: float, height: float,
             layer: str = "0") -> str:
    """
    绘制一个3D长方体（Box）

    参数:
    - origin_x, origin_y, origin_z: 原点坐标
    - length: 长度（X方向）
    - width: 宽度（Y方向）
    - height: 高度（Z方向）
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        origin = APoint(origin_x, origin_y, origin_z)
        box = zcad_conn.model.AddBox(origin, length, width, height)
        box.Layer = layer
        return f"成功绘制长方体: ({origin_x},{origin_y},{origin_z}), {length}×{width}×{height}"
    except Exception as e:
        return _format_error("绘制长方体", e)


@mcp.tool
def draw_cylinder(center_x: float, center_y: float, center_z: float,
                  radius: float, height: float,
                  layer: str = "0") -> str:
    """
    绘制一个3D圆柱体

    参数:
    - center_x,center_y,center_z: 底面圆心坐标
    - radius: 半径
    - height: 高度
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        cyl = zcad_conn.model.AddCylinder(center, radius, height)
        cyl.Layer = layer
        return f"成功绘制圆柱体: 圆心({center_x},{center_y},{center_z}), r={radius}, h={height}"
    except Exception as e:
        return _format_error("绘制圆柱体", e)


@mcp.tool
def draw_cone(center_x: float, center_y: float, center_z: float,
              base_radius: float, height: float,
              layer: str = "0") -> str:
    """
    绘制一个3D圆锥体

    参数:
    - center_x,center_y,center_z: 底面圆心坐标
    - base_radius: 底面半径
    - height: 高度
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        cone = zcad_conn.model.AddCone(center, base_radius, height)
        cone.Layer = layer
        return f"成功绘制圆锥体: 底面圆心({center_x},{center_y},{center_z}), r={base_radius}, h={height}"
    except Exception as e:
        return _format_error("绘制圆锥体", e)


@mcp.tool
def draw_sphere(center_x: float, center_y: float, center_z: float,
                radius: float,
                layer: str = "0") -> str:
    """
    绘制一个3D球体

    参数:
    - center_x,center_y,center_z: 球心坐标
    - radius: 半径
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        sphere = zcad_conn.model.AddSphere(center, radius)
        sphere.Layer = layer
        return f"成功绘制球体: 球心({center_x},{center_y},{center_z}), r={radius}"
    except Exception as e:
        return _format_error("绘制球体", e)


@mcp.tool
def draw_torus(center_x: float, center_y: float, center_z: float,
               torus_radius: float, tube_radius: float,
               layer: str = "0") -> str:
    """
    绘制一个3D圆环体

    参数:
    - center_x,center_y,center_z: 圆环中心坐标
    - torus_radius: 圆环半径（中心到管心）
    - tube_radius: 管半径
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        torus = zcad_conn.model.AddTorus(center, torus_radius, tube_radius)
        torus.Layer = layer
        return f"成功绘制圆环体: 中心({center_x},{center_y},{center_z}), R={torus_radius}, r={tube_radius}"
    except Exception as e:
        return _format_error("绘制圆环体", e)


@mcp.tool
def draw_wedge(center_x: float, center_y: float, center_z: float,
               length: float, width: float, height: float,
               layer: str = "0") -> str:
    """
    绘制一个3D楔体

    参数:
    - center_x,center_y,center_z: 原点坐标
    - length: 长度
    - width: 宽度
    - height: 高度
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        center = APoint(center_x, center_y, center_z)
        wedge = zcad_conn.model.AddWedge(center, length, width, height)
        wedge.Layer = layer
        return f"成功绘制楔体: ({center_x},{center_y},{center_z}), {length}×{width}×{height}"
    except Exception as e:
        return _format_error("绘制楔体", e)


@mcp.tool
def draw_3d_polyline(vertices: list, layer: str = "0") -> str:
    """
    绘制3D多段线

    参数:
    - vertices: 三维顶点列表 [[x1,y1,z1],[x2,y2,z2],...]
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        flat = []
        for v in vertices:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        pline = zcad_conn.model.Add3DPoly(coords)
        pline.Layer = layer
        return f"成功绘制3D多段线: {len(flat)//3}个顶点, 图层: {layer}"
    except Exception as e:
        return _format_error("绘制3D多段线", e)


@mcp.tool
def draw_ray(x1: float, y1: float, z1: float,
             x2: float, y2: float, z2: float,
             layer: str = "0") -> str:
    """
    绘制射线（从起点无限延伸）

    参数:
    - x1,y1,z1: 射线起点
    - x2,y2,z2: 射线方向上的一点
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        ray = zcad_conn.model.AddRay(p1, p2)
        ray.Layer = layer
        return f"成功绘制射线: 起点({x1},{y1},{z1}), 图层: {layer}"
    except Exception as e:
        return _format_error("绘制射线", e)


@mcp.tool
def draw_xline(x1: float, y1: float, z1: float,
               x2: float, y2: float, z2: float,
               layer: str = "0") -> str:
    """
    绘制构造线（双向无限延伸）

    参数:
    - x1,y1,z1: 线上第一点
    - x2,y2,z2: 线上第二点
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        xline = zcad_conn.model.AddXline(p1, p2)
        xline.Layer = layer
        return f"成功绘制构造线: ({x1},{y1})-({x2},{y2}), 图层: {layer}"
    except Exception as e:
        return _format_error("绘制构造线", e)


@mcp.tool
def draw_mline(vertices: list, layer: str = "0") -> str:
    """
    绘制多线（MLine）

    参数:
    - vertices: 顶点列表 [[x1,y1,z1],[x2,y2,z2],...]
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        flat = []
        for v in vertices:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        mline = zcad_conn.model.AddMLine(coords)
        mline.Layer = layer
        return f"成功绘制多线: {len(flat)//3}个顶点, 图层: {layer}"
    except Exception as e:
        return _format_error("绘制多线", e)


# ==========================================
# 实体属性设置工具（来自 IZcadEntity 属性 setter）
# ==========================================

def _find_entity(zcad_conn, object_type: str = None,
                 predicate=None):
    """查找实体的辅助函数"""
    if predicate:
        return zcad_conn.find_one(object_type, predicate=predicate)
    return None

@mcp.tool
def set_entity_properties(object_type: str = None,
                          property_name: str = "Layer",
                          property_value: str = "",
                          layer: str = None,
                          color: int = None,
                          linetype: str = None,
                          linetype_scale: float = None,
                          lineweight: float = None,
                          visible: bool = None) -> str:
    """
    设置实体的通用属性

    参数:
    - object_type: 对象类型
    - property_name: 用于定位的属性名
    - property_value: 用于定位的属性值
    - layer: 新图层名（可选）
    - color: 新颜色索引（可选）
    - linetype: 新线型名（可选）
    - linetype_scale: 新线型比例（可选）
    - lineweight: 新线宽（可选）
    - visible: 可见性（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False

        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return json.dumps({"found": False, "message": f"未找到: {object_type}.{property_name}={property_value}"})

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

        return f"成功更新实体属性: {', '.join(updated)}" if updated else "未提供任何属性"
    except Exception as e:
        return _format_error("设置实体属性", e)


@mcp.tool
def explode_entity(object_type: str, property_name: str, property_value: str) -> str:
    """
    分解实体

    参数:
    - object_type: 对象类型
    - property_name: 用于定位的属性名
    - property_value: 用于定位的属性值

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return f"未找到符合条件的对象"
        result = obj.Explode()
        return f"成功分解实体，生成对象数: {len(result)}" if result else "分解成功（未生成对象或空）"
    except Exception as e:
        return _format_error("分解实体", e)


@mcp.tool
def mirror_3d_object(object_type: str, property_name: str, property_value: str,
                     x1: float, y1: float, z1: float,
                     x2: float, y2: float, z2: float,
                     x3: float, y3: float, z3: float) -> str:
    """
    3D镜像对象

    参数:
    - object_type/property_name/property_value: 定位对象
    - x1,y1,z1,x2,y2,z2,x3,y3,z3: 定义镜像平面的三个点

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return f"未找到符合条件的对象"
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        p3 = APoint(x3, y3, z3)
        mirror_obj = obj.Mirror3D(p1, p2, p3)
        return f"成功3D镜像对象"
    except Exception as e:
        return _format_error("3D镜像", e)


@mcp.tool
def rotate_3d_object(object_type: str, property_name: str, property_value: str,
                     x1: float, y1: float, z1: float,
                     x2: float, y2: float, z2: float,
                     rotation_angle: float) -> str:
    """
    3D旋转对象

    参数:
    - object_type/property_name/property_value: 定位对象
    - x1,y1,z1: 旋转轴上第一点
    - x2,y2,z2: 旋转轴上第二点
    - rotation_angle: 旋转角度（弧度）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return f"未找到符合条件的对象"
        p1 = APoint(x1, y1, z1)
        p2 = APoint(x2, y2, z2)
        obj.Rotate3D(p1, p2, rotation_angle)
        return f"成功3D旋转对象, 角度={rotation_angle:.4f}弧度"
    except Exception as e:
        return _format_error("3D旋转", e)


# ==========================================
# 选择集工具（来自 IZcadSelectionSet/IZcadSelectionSets）
# ==========================================

@mcp.tool
def create_selection_set(name: str) -> str:
    """
    创建命名的选择集

    参数:
    - name: 选择集名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        # 删除已存在的同名选择集
        try:
            old = zcad_conn.doc.SelectionSets.Item(name)
            old.Delete()
        except Exception:
            pass
        sel = zcad_conn.doc.SelectionSets.Add(name)
        return f"成功创建选择集: {name}"
    except Exception as e:
        return _format_error("创建选择集", e)


@mcp.tool
def select_objects(mode: int, name: str = "",
                   x1: float = 0, y1: float = 0,
                   x2: float = 0, y2: float = 0) -> str:
    """
    通过窗选/窗交等方式选择对象

    参数:
    - mode: 选择模式
      0=Window（完全包含）, 1=Crossing（相交即选）, 2=Previous, 4=Last, 5=All
    - name: 选择集名称（如为空则使用"SS1"）
    - x1,y1: 第一角点（窗选/窗交使用）
    - x2,y2: 第二角点（窗选/窗交使用）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        sel_name = name or "SS1"
        try:
            old = zcad_conn.doc.SelectionSets.Item(sel_name)
            old.Delete()
        except Exception:
            pass
        sel = zcad_conn.doc.SelectionSets.Add(sel_name)
        p1 = APoint(x1, y1, 0)
        p2 = APoint(x2, y2, 0)
        sel.Select(mode, p1, p2)
        return f"成功选择对象 (模式={mode}), 选择集: {sel_name}, 数量: {sel.Count}"
    except Exception as e:
        return _format_error("选择对象", e)


@mcp.tool
def select_on_screen(name: str = "SS1") -> str:
    """
    交互式屏幕选择对象（需用户在CAD中选择）

    参数:
    - name: 选择集名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        try:
            old = zcad_conn.doc.SelectionSets.Item(name)
            old.Delete()
        except Exception:
            pass
        sel = zcad_conn.doc.SelectionSets.Add(name)
        zcad_conn.prompt("请在屏幕上选择对象，按Enter确认...")
        sel.SelectOnScreen()
        return f"屏幕选择完成，选择集: {name}, 数量: {sel.Count}"
    except Exception as e:
        return _format_error("屏幕选择", e)


@mcp.tool
def select_by_polygon(mode: int, points: list, name: str = "SS1") -> str:
    """
    通过多边形选择对象

    参数:
    - mode: 0=FencePolygon, 1=WindowPolygon, 2=CrossingPolygon
    - points: 多边形顶点列表 [[x1,y1],[x2,y2],...]
    - name: 选择集名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        try:
            old = zcad_conn.doc.SelectionSets.Item(name)
            old.Delete()
        except Exception:
            pass
        sel = zcad_conn.doc.SelectionSets.Add(name)
        flat = []
        for p in points:
            if isinstance(p, (list, tuple)):
                flat.extend(p)
            else:
                flat.append(p)
        coords = aDouble(*flat)
        sel.SelectByPolygon(mode, coords)
        return f"多边形选择完成，选择集: {name}, 数量: {sel.Count}"
    except Exception as e:
        return _format_error("多边形选择", e)


@mcp.tool
def clear_selection_set(name: str = "SS1") -> str:
    """
    清空选择集内容

    参数:
    - name: 选择集名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        sel = zcad_conn.doc.SelectionSets.Item(name)
        sel.Clear()
        return f"已清空选择集: {name}"
    except Exception as e:
        return _format_error("清空选择集", e)


# ==========================================
# 实体几何属性修改工具
# ==========================================

@mcp.tool
def modify_circle(object_type: str, property_name: str, property_value: str,
                  radius: float = None, center_x: float = None,
                  center_y: float = None, center_z: float = None) -> str:
    """
    修改圆的几何属性

    参数:
    - object_type/property_name/property_value: 定位圆对象
    - radius: 新半径（可选）
    - center_x,center_y,center_z: 新圆心坐标（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Circle", predicate=pred)
        if not obj:
            return "未找到符合条件的圆"
        updated = []
        if radius is not None:
            obj.Radius = radius; updated.append(f"Radius={radius}")
        if center_x is not None or center_y is not None or center_z is not None:
            center = APoint(center_x or 0, center_y or 0, center_z or 0)
            obj.Center = center; updated.append(f"Center=({center_x},{center_y},{center_z})")
        return f"成功修改圆: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改圆", e)


@mcp.tool
def modify_arc(object_type: str, property_name: str, property_value: str,
               radius: float = None, center_x: float = None,
               center_y: float = None, center_z: float = None,
               start_angle: float = None, end_angle: float = None) -> str:
    """
    修改圆弧的几何属性

    参数:
    - object_type/property_name/property_value: 定位圆弧对象
    - radius/center_x,y,z/start_angle/end_angle: 新的几何参数

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Arc", predicate=pred)
        if not obj:
            return "未找到符合条件的圆弧"
        updated = []
        if radius is not None:
            obj.Radius = radius; updated.append(f"Radius={radius}")
        if center_x is not None or center_y is not None or center_z is not None:
            obj.Center = APoint(center_x or 0, center_y or 0, center_z or 0)
            updated.append(f"Center=({center_x},{center_y},{center_z})")
        if start_angle is not None:
            obj.StartAngle = start_angle; updated.append(f"StartAngle={start_angle:.4f}")
        if end_angle is not None:
            obj.EndAngle = end_angle; updated.append(f"EndAngle={end_angle:.4f}")
        return f"成功修改圆弧: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改圆弧", e)


@mcp.tool
def modify_line(object_type: str, property_name: str, property_value: str,
                x1: float = None, y1: float = None, z1: float = None,
                x2: float = None, y2: float = None, z2: float = None) -> str:
    """
    修改直线的端点

    参数:
    - object_type/property_name/property_value: 定位直线对象
    - x1,y1,z1: 新起点坐标（可选）
    - x2,y2,z2: 新终点坐标（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Line", predicate=pred)
        if not obj:
            return "未找到符合条件的直线"
        updated = []
        if x1 is not None or y1 is not None or z1 is not None:
            obj.StartPoint = APoint(x1 or 0, y1 or 0, z1 or 0)
            updated.append(f"Start=({x1},{y1},{z1})")
        if x2 is not None or y2 is not None or z2 is not None:
            obj.EndPoint = APoint(x2 or 0, y2 or 0, z2 or 0)
            updated.append(f"End=({x2},{y2},{z2})")
        return f"成功修改直线: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改直线", e)


@mcp.tool
def modify_text(object_type: str, property_name: str, property_value: str,
                text: str = None, height: float = None,
                rotation: float = None, stylename: str = None,
                x: float = None, y: float = None, z: float = None) -> str:
    """
    修改单行文本属性

    参数:
    - object_type/property_name/property_value: 定位文本对象
    - text: 新文本内容（可选）
    - height: 新字高（可选）
    - rotation: 新旋转角（弧度）（可选）
    - stylename: 新文字样式名（可选）
    - x,y,z: 新插入点坐标（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Text", predicate=pred)
        if not obj:
            return "未找到符合条件的文本"
        updated = []
        if text is not None:
            obj.TextString = text; updated.append(f"Text='{text}'")
        if height is not None:
            obj.Height = height; updated.append(f"Height={height}")
        if rotation is not None:
            obj.Rotation = rotation; updated.append(f"Rotation={rotation:.4f}")
        if stylename is not None:
            obj.StyleName = stylename; updated.append(f"Style={stylename}")
        if x is not None or y is not None or z is not None:
            obj.InsertionPoint = APoint(x or 0, y or 0, z or 0)
            updated.append(f"Pos=({x},{y},{z})")
        return f"成功修改文本: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改文本", e)


@mcp.tool
def modify_mtext(object_type: str, property_name: str, property_value: str,
                 text: str = None, height: float = None,
                 width: float = None, rotation: float = None,
                 attachment_point: int = None) -> str:
    """
    修改多行文本属性

    参数:
    - object_type/property_name/property_value: 定位MText对象
    - text: 新文本内容
    - height: 新字高
    - width: 新文本框宽度
    - rotation: 新旋转角（弧度）
    - attachment_point: 对齐点类型

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("MText", predicate=pred)
        if not obj:
            return "未找到符合条件的多行文本"
        updated = []
        if text is not None:
            obj.TextString = text; updated.append("Text updated")
        if height is not None:
            obj.Height = height; updated.append(f"Height={height}")
        if width is not None:
            obj.Width = width; updated.append(f"Width={width}")
        if rotation is not None:
            obj.Rotation = rotation; updated.append(f"Rotation={rotation:.4f}")
        if attachment_point is not None:
            obj.AttachmentPoint = attachment_point; updated.append(f"Attachment={attachment_point}")
        return f"成功修改多行文本: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改多行文本", e)


@mcp.tool
def modify_polyline(object_type: str, property_name: str, property_value: str,
                    closed: bool = None, constant_width: float = None,
                    elevation: float = None) -> str:
    """
    修改多段线属性

    参数:
    - object_type/property_name/property_value: 定位多段线对象
    - closed: 是否闭合
    - constant_width: 等宽值
    - elevation: 高程

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(None, predicate=pred)
        if not obj:
            return "未找到符合条件的多段线"
        updated = []
        if closed is not None and hasattr(obj, 'Closed'):
            obj.Closed = closed; updated.append(f"Closed={closed}")
        if constant_width is not None and hasattr(obj, 'ConstantWidth'):
            obj.ConstantWidth = constant_width; updated.append(f"Width={constant_width}")
        if elevation is not None and hasattr(obj, 'Elevation'):
            obj.Elevation = elevation; updated.append(f"Elevation={elevation}")
        return f"成功修改多段线: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改多段线", e)


@mcp.tool
def modify_spline(object_type: str, property_name: str, property_value: str,
                  closed: bool = None, fit_tolerance: float = None,
                  start_tangent_x: float = None, start_tangent_y: float = None,
                  end_tangent_x: float = None, end_tangent_y: float = None) -> str:
    """
    修改样条曲线属性

    参数:
    - object_type/property_name/property_value: 定位样条曲线对象
    - closed: 是否闭合
    - fit_tolerance: 拟合公差
    - start_tangent_x/y: 起点切向
    - end_tangent_x/y: 终点切向

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Spline", predicate=pred)
        if not obj:
            return "未找到符合条件的样条曲线"
        updated = []
        if closed is not None:
            obj.Closed = closed; updated.append(f"Closed={closed}")
        if fit_tolerance is not None:
            obj.FitTolerance = fit_tolerance; updated.append(f"FitTol={fit_tolerance}")
        if start_tangent_x is not None or start_tangent_y is not None:
            obj.StartTangent = APoint(start_tangent_x or 0, start_tangent_y or 0, 0)
            updated.append("StartTangent updated")
        if end_tangent_x is not None or end_tangent_y is not None:
            obj.EndTangent = APoint(end_tangent_x or 0, end_tangent_y or 0, 0)
            updated.append("EndTangent updated")
        return f"成功修改样条曲线: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改样条曲线", e)


@mcp.tool
def offset_entity(object_type: str, property_name: str, property_value: str,
                  distance: float) -> str:
    """
    偏移实体（线、圆、圆弧、多段线、样条等）

    参数:
    - object_type/property_name/property_value: 定位对象
    - distance: 偏移距离

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return "未找到符合条件的对象"
        if not hasattr(obj, 'Offset'):
            return "此对象不支持偏移操作"
        result = obj.Offset(distance)
        return f"成功偏移实体, 距离={distance}, 生成对象数: {len(result)}" if result else "偏移完成"
    except Exception as e:
        return _format_error("偏移实体", e)


# ==========================================
# 块操作工具（来自 IZcadBlockReference / IZcadBlocks）
# ==========================================

@mcp.tool
def create_block_definition(name: str, x: float = 0, y: float = 0, z: float = 0) -> str:
    """
    创建新的图块定义

    参数:
    - name: 图块名称
    - x,y,z: 图块基点坐标（可选，默认原点）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        blk = zcad_conn.doc.Blocks.Add(point, name)
        return f"成功创建图块定义: {name}, 基点({x},{y},{z})"
    except Exception as e:
        return _format_error("创建图块定义", e)


@mcp.tool
def explode_block_reference(object_type: str, property_name: str, property_value: str) -> str:
    """
    分解图块引用为独立实体

    参数:
    - object_type/property_name/property_value: 定位图块引用对象

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("BlockReference", predicate=pred)
        if not obj:
            return "未找到符合条件的图块引用"
        result = obj.Explode()
        return f"成功分解图块引用, 生成对象数: {len(result)}" if result else "分解成功"
    except Exception as e:
        return _format_error("分解图块引用", e)


@mcp.tool
def get_dynamic_block_properties(object_type: str, property_name: str, property_value: str) -> str:
    """
    获取动态块的属性信息

    参数:
    - object_type/property_name/property_value: 定位动态图块引用

    返回: JSON格式的动态属性列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name) and str(getattr(obj, property_name)) == str(property_value):
                if hasattr(obj, 'IsDynamicBlock'):
                    return obj.IsDynamicBlock
            return False
        obj = zcad_conn.find_one("BlockReference", predicate=pred)
        if not obj or not hasattr(obj, 'IsDynamicBlock') or not obj.IsDynamicBlock:
            return "未找到符合条件的动态图块引用"
        props = obj.GetDynamicBlockProperties()
        result = []
        for p in props:
            result.append({
                "property_name": p.PropertyName if hasattr(p, 'PropertyName') else "",
                "value": p.Value if hasattr(p, 'Value') else "",
                "units_type": p.UnitsType if hasattr(p, 'UnitsType') else "",
            })
        return json.dumps(result, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取动态块属性", e)


@mcp.tool
def get_constant_attributes(object_type: str, property_name: str, property_value: str) -> str:
    """
    获取图块引用的常量属性

    参数:
    - object_type/property_name/property_value: 定位图块引用

    返回: JSON格式的常量属性列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("BlockReference", predicate=pred)
        if not obj:
            return "未找到符合条件的图块引用"
        attrs = obj.GetConstantAttributes()
        result = []
        for attr in attrs:
            result.append({
                "tag": attr.TagString if hasattr(attr, 'TagString') else "",
                "text": attr.TextString if hasattr(attr, 'TextString') else "",
            })
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return _format_error("获取常量属性", e)


# ==========================================
# 表格操作工具（来自 IZcadTable）
# ==========================================

@mcp.tool
def set_cell_text(object_type: str, property_name: str, property_value: str,
                  row: int, col: int, text: str) -> str:
    """
    设置表格单元格文本

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - row, col: 行/列索引（0-based）
    - text: 单元格文本

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        obj.SetText(row, col, text)
        return f"成功设置表格单元格[{row},{col}] = '{text}'"
    except Exception as e:
        return _format_error("设置单元格文本", e)


@mcp.tool
def get_cell_text(object_type: str, property_name: str, property_value: str,
                  row: int, col: int) -> str:
    """
    获取表格单元格文本

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - row, col: 行/列索引

    返回: 单元格文本内容
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        text = obj.GetText(row, col)
        return f"表格[{row},{col}] = '{text}'"
    except Exception as e:
        return _format_error("获取单元格文本", e)


@mcp.tool
def insert_table_rows(object_type: str, property_name: str, property_value: str,
                      row_index: int, count: int = 1, height: float = 0) -> str:
    """
    在表格中插入行

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - row_index: 插入位置的行索引
    - count: 插入行数
    - height: 行高（0=默认）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        obj.InsertRows(row_index, count, height)
        return f"成功在第{row_index}行插入{count}行"
    except Exception as e:
        return _format_error("插入表格行", e)


@mcp.tool
def delete_table_rows(object_type: str, property_name: str, property_value: str,
                      row_index: int, count: int = 1) -> str:
    """
    从表格中删除行

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - row_index: 起始行索引
    - count: 删除行数

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        obj.DeleteRows(row_index, count)
        return f"成功从第{row_index}行删除{count}行"
    except Exception as e:
        return _format_error("删除表格行", e)


@mcp.tool
def set_column_width(object_type: str, property_name: str, property_value: str,
                     col: int, width: float) -> str:
    """
    设置表格列宽

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - col: 列索引
    - width: 新列宽

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        obj.SetColumnWidth(col, width)
        return f"成功设置第{col}列宽度={width}"
    except Exception as e:
        return _format_error("设置列宽", e)


@mcp.tool
def set_row_height(object_type: str, property_name: str, property_value: str,
                   row: int, height: float) -> str:
    """
    设置表格行高

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - row: 行索引
    - height: 新行高

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        obj.SetRowHeight(row, height)
        return f"成功设置第{row}行高度={height}"
    except Exception as e:
        return _format_error("设置行高", e)


@mcp.tool
def merge_cells(object_type: str, property_name: str, property_value: str,
                min_row: int, max_row: int, min_col: int, max_col: int) -> str:
    """
    合并表格单元格

    参数:
    - object_type/property_name/property_value: 定位表格对象
    - min_row, max_row: 行范围（包含）
    - min_col, max_col: 列范围（包含）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Table", predicate=pred)
        if not obj:
            return "未找到符合条件的表格"
        obj.MergeCells(min_row, max_row, min_col, max_col)
        return f"成功合并单元格: 行{min_row}-{max_row}, 列{min_col}-{max_col}"
    except Exception as e:
        return _format_error("合并单元格", e)


# ==========================================
# 多引线工具（来自 IZcadMLeader）
# ==========================================

@mcp.tool
def add_mleader(points: list, text: str = "",
                text_height: float = 2.5, layer: str = "0") -> str:
    """
    添加多重引线（MLeader）

    参数:
    - points: 引线点列表 [[x1,y1,z1],[x2,y2,z2],...]
    - text: 引线文字内容
    - text_height: 文字高度
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        flat = []
        for v in points:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        mleader = zcad_conn.model.AddMLeader(coords)
        mleader.Layer = layer
        if text:
            mleader.TextString = text
            mleader.TextHeight = text_height
        return f"成功添加多重引线: {len(flat)//3}个点, 图层: {layer}"
    except Exception as e:
        return _format_error("添加多重引线", e)


@mcp.tool
def add_mleader_line(object_type: str, property_name: str, property_value: str,
                     points: list) -> str:
    """
    向现有多重引线添加引线

    参数:
    - object_type/property_name/property_value: 定位MLeader对象
    - points: 新引线的点列表 [[x1,y1,z1],[x2,y2,z2],...]

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("MLeader", predicate=pred)
        if not obj:
            return "未找到MLeader对象"
        flat = []
        for v in points:
            if isinstance(v, (list, tuple)):
                flat.extend(v)
            else:
                flat.append(v)
        coords = aDouble(*flat)
        idx = obj.AddLeaderLine(0, coords)
        return f"成功添加引线到MLeader, leaderLineIndex={idx}"
    except Exception as e:
        return _format_error("添加MLeader引线", e)


@mcp.tool
def get_mleader_vertices(object_type: str, property_name: str, property_value: str,
                         leader_line_index: int = 0) -> str:
    """
    获取多重引线的顶点

    参数:
    - object_type/property_name/property_value: 定位MLeader对象
    - leader_line_index: 引线索引

    返回: JSON格式的顶点列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("MLeader", predicate=pred)
        if not obj:
            return "未找到MLeader对象"
        verts = obj.GetLeaderLineVertices(leader_line_index)
        points = list(verts)
        result = [{"x": points[i], "y": points[i+1], "z": points[i+2]}
                  for i in range(0, len(points), 3)]
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return _format_error("获取MLeader顶点", e)


# ==========================================
# 图案填充属性工具（来自 IZcadHatch）
# ==========================================

@mcp.tool
def set_hatch_properties(object_type: str, property_name: str, property_value: str,
                         pattern_name: str = None, pattern_type: int = None,
                         pattern_angle: float = None, pattern_scale: float = None,
                         pattern_double: bool = None) -> str:
    """
    修改填充图案的属性

    参数:
    - object_type/property_name/property_value: 定位填充对象
    - pattern_name: 新图案名称
    - pattern_type: 图案类型（0=预定义，1=用户定义，2=自定义）
    - pattern_angle: 新角度（弧度）
    - pattern_scale: 新比例
    - pattern_double: 是否双线填充

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Hatch", predicate=pred)
        if not obj:
            return "未找到填充对象"
        updated = []
        if pattern_name is not None and pattern_type is not None:
            obj.SetPattern(pattern_type, pattern_name)
            updated.append(f"Pattern={pattern_name}")
        elif pattern_name is not None:
            obj.PatternName = pattern_name; updated.append(f"PatternName={pattern_name}")
        if pattern_type is not None:
            obj.PatternType = pattern_type; updated.append(f"PatternType={pattern_type}")
        if pattern_angle is not None:
            obj.PatternAngle = pattern_angle; updated.append(f"Angle={pattern_angle:.4f}")
        if pattern_scale is not None:
            obj.PatternScale = pattern_scale; updated.append(f"Scale={pattern_scale}")
        if pattern_double is not None:
            obj.PatternDouble = pattern_double; updated.append(f"Double={pattern_double}")
        if updated:
            obj.Evaluate()
        return f"成功修改填充: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改填充属性", e)


@mcp.tool
def add_inner_loop(object_type: str, property_name: str, property_value: str,
                   objects: list) -> str:
    """
    向填充添加内边界（空洞）

    参数:
    - object_type/property_name/property_value: 定位填充对象
    - objects: 内边界对象ID列表（实体ObjectID字符串列表）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Hatch", predicate=pred)
        if not obj:
            return "未找到填充对象"
        obj_array = []
        for oid in objects:
            try:
                obj_array.append(zcad_conn.doc.ObjectIdToObject(oid))
            except Exception:
                pass
        if obj_array:
            obj.AppendInnerLoop(obj_array)
            obj.Evaluate()
        return f"成功添加内边界: {len(obj_array)}个对象"
    except Exception as e:
        return _format_error("添加内边界", e)


# ==========================================
# 实体交集工具
# ==========================================

@mcp.tool
def get_intersection(object_type: str, property_name: str, property_value: str,
                     other_object_type: str, other_property_name: str,
                     other_property_value: str) -> str:
    """
    获取两个实体的交点

    参数:
    - object_type/property_name/property_value: 定位第一个对象
    - other_object_type/other_property_name/other_property_value: 定位第二个对象

    返回: JSON格式的交点列表
    """
    try:
        zcad_conn, _ = get_cad_connection()

        def make_pred(ptype, pname, pval):
            def pred(obj):
                if ptype and obj.ObjectName != "Zcad" + ptype:
                    if not obj.ObjectName.lower().endswith(ptype.lower()):
                        return False
                if hasattr(obj, pname):
                    return str(getattr(obj, pname)) == str(pval)
                return False
            return pred

        from_pred = make_pred(object_type, property_name, property_value)
        to_pred = make_pred(other_object_type, other_property_name, other_property_value)
        obj1 = zcad_conn.find_one(object_type, predicate=from_pred)
        obj2 = zcad_conn.find_one(other_object_type, predicate=to_pred)
        if not obj1 or not obj2:
            return "未找到指定的实体对"
        points = obj1.IntersectWith(obj2, 0)
        pts = list(points)
        result = [{"x": pts[i], "y": pts[i+1], "z": pts[i+2]}
                  for i in range(0, len(pts), 3)]
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return _format_error("获取交点", e)


# ==========================================
# 文档摘要信息工具（来自 IZcadSummaryInfo）
# ==========================================

@mcp.tool
def get_summary_info() -> str:
    """
    获取当前文档的摘要信息（标题、主题、作者等）

    返回: JSON格式的摘要信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        si = zcad_conn.doc.SummaryInfo
        info = {}
        for prop in ['Title', 'Subject', 'Author', 'Keywords', 'Comments',
                     'LastSavedBy', 'RevisionNumber']:
            if hasattr(si, prop):
                try:
                    info[prop.lower()] = getattr(si, prop)
                except Exception:
                    pass
        # 自定义属性
        if hasattr(si, 'NumCustomInfo'):
            try:
                n = si.NumCustomInfo
                custom = {}
                for i in range(n):
                    try:
                        key, val = si.GetCustomByIndex(i)
                        custom[key] = val
                    except Exception:
                        pass
                if custom:
                    info['custom'] = custom
            except Exception:
                pass
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取摘要信息", e)


@mcp.tool
def set_summary_info(title: str = None, subject: str = None,
                     author: str = None, keywords: str = None,
                     comments: str = None) -> str:
    """
    设置文档摘要信息

    参数:
    - title,subject,author,keywords,comments: 要设置的属性（可选）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        si = zcad_conn.doc.SummaryInfo
        updated = []
        if title is not None:
            si.Title = title; updated.append(f"Title='{title}'")
        if subject is not None:
            si.Subject = subject; updated.append(f"Subject='{subject}'")
        if author is not None:
            si.Author = author; updated.append(f"Author='{author}'")
        if keywords is not None:
            si.Keywords = keywords; updated.append(f"Keywords='{keywords}'")
        if comments is not None:
            si.Comments = comments; updated.append(f"Comments='{comments}'")
        return f"成功更新摘要: {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("设置摘要信息", e)


# ==========================================
# 文档集合工具（来自 IZcadDocuments）
# ==========================================

@mcp.tool
def new_document(template_path: str = "") -> str:
    """
    新建文档（基于模板）

    参数:
    - template_path: 模板文件路径（可选，空=默认模板）

    返回: 新建文档的信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        doc = zcad_conn.doc.New(template_path) if template_path else zcad_conn.doc.New("")
        return f"成功新建文档: {doc.Name}"
    except Exception as e:
        return _format_error("新建文档", e)


@mcp.tool
def list_documents() -> str:
    """
    获取所有打开的文档列表

    返回: JSON格式的文档列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        docs = []
        for doc in zcad_conn.app.Documents:
            docs.append({
                "name": doc.Name,
                "path": doc.Path if hasattr(doc, 'Path') else "",
                "saved": doc.Saved if hasattr(doc, 'Saved') else None,
            })
        return json.dumps(docs, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取文档列表失败: {str(e)}"


@mcp.tool
def activate_document(name: str) -> str:
    """
    激活指定文档（切换到前台）

    参数:
    - name: 文档名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        doc = zcad_conn.app.Documents.Item(name)
        doc.Activate()
        return f"成功激活文档: {name}"
    except Exception as e:
        return _format_error("激活文档", e)


# ==========================================
# 布局工具（来自 IZcadLayout/IZcadLayouts）
# ==========================================

@mcp.tool
def add_layout(name: str) -> str:
    """
    添加新布局

    参数:
    - name: 布局名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Layouts.Add(name)
        return f"成功添加布局: {name}"
    except Exception as e:
        return _format_error("添加布局", e)


@mcp.tool
def set_active_layout(name: str) -> str:
    """
    设置活动布局

    参数:
    - name: 布局名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        layout = zcad_conn.doc.Layouts.Item(name)
        zcad_conn.doc.ActiveLayout = layout
        return f"成功设置活动布局: {name}"
    except Exception as e:
        return _format_error("设置活动布局", e)


# ==========================================
# UCS 管理工具（来自 IZcadUCS/IZcadUCSs）
# ==========================================

@mcp.tool
def list_ucs() -> str:
    """
    获取所有UCS列表

    返回: JSON格式的UCS列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        ucss = []
        for ucs in zcad_conn.doc.UserCoordinateSystems:
            info = {"name": ucs.Name}
            if hasattr(ucs, 'Origin'):
                try:
                    info['origin'] = list(ucs.Origin)
                except Exception:
                    pass
            ucss.append(info)
        return json.dumps(ucss, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取UCS列表失败: {str(e)}"


@mcp.tool
def add_ucs(name: str, origin_x: float, origin_y: float, origin_z: float,
            x_axis_x: float, x_axis_y: float, x_axis_z: float,
            y_axis_x: float, y_axis_y: float, y_axis_z: float) -> str:
    """
    创建新的UCS

    参数:
    - name: UCS名称
    - origin_x,origin_y,origin_z: 原点坐标
    - x_axis_x/y/z: X轴方向点
    - y_axis_x/y/z: Y轴方向点

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        origin = APoint(origin_x, origin_y, origin_z)
        x_axis = APoint(x_axis_x, x_axis_y, x_axis_z)
        y_axis = APoint(y_axis_x, y_axis_y, y_axis_z)
        zcad_conn.doc.UserCoordinateSystems.Add(origin, x_axis, y_axis, name)
        return f"成功创建UCS: {name}"
    except Exception as e:
        return _format_error("创建UCS", e)


@mcp.tool
def set_active_ucs(name: str) -> str:
    """
    设置活动UCS

    参数:
    - name: UCS名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        ucs = zcad_conn.doc.UserCoordinateSystems.Item(name)
        zcad_conn.doc.ActiveUCS = ucs
        return f"成功设置活动UCS: {name}"
    except Exception as e:
        return _format_error("设置活动UCS", e)


# ==========================================
# 编组工具（来自 IZcadGroup/IZcadGroups）
# ==========================================

@mcp.tool
def list_groups() -> str:
    """
    获取所有编组列表

    返回: JSON格式的编组列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        groups = []
        for g in zcad_conn.doc.Groups:
            groups.append({"name": g.Name, "count": g.Count})
        return json.dumps(groups, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取编组列表失败: {str(e)}"


@mcp.tool
def create_group(name: str) -> str:
    """
    创建编组

    参数:
    - name: 编组名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Groups.Add(name)
        return f"成功创建编组: {name}"
    except Exception as e:
        return _format_error("创建编组", e)


@mcp.tool
def append_to_group(group_name: str,
                    object_type: str, property_name: str, property_value: str) -> str:
    """
    将对象添加到编组

    参数:
    - group_name: 编组名称
    - object_type/property_name/property_value: 定位要添加的对象

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        group = zcad_conn.doc.Groups.Item(group_name)
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return "未找到要添加的对象"
        group.AppendItems([obj])
        return f"成功将对象添加到编组 '{group_name}'"
    except Exception as e:
        return _format_error("添加到编组", e)


# ==========================================
# 视图/视口工具（来自 IZcadView/IZcadViews/IZcadViewport/IZcadPViewport）
# ==========================================

@mcp.tool
def list_views() -> str:
    """
    获取所有命名视图列表

    返回: JSON格式的视图列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        views = []
        for v in zcad_conn.doc.Views:
            info = {"name": v.Name}
            if hasattr(v, 'Center'):
                try:
                    info['center'] = list(v.Center)
                except Exception:
                    pass
            if hasattr(v, 'Height'):
                info['height'] = v.Height
            if hasattr(v, 'Width'):
                info['width'] = v.Width
            views.append(info)
        return json.dumps(views, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取视图列表失败: {str(e)}"


@mcp.tool
def add_view(name: str) -> str:
    """
    创建命名视图

    参数:
    - name: 视图名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Views.Add(name)
        return f"成功创建视图: {name}"
    except Exception as e:
        return _format_error("创建视图", e)


@mcp.tool
def set_view(object_type: str, property_name: str, property_value: str,
             view_name: str) -> str:
    """
    设置视口显式视图

    参数:
    - object_type/property_name/property_value: 定位PViewport对象
    - view_name: 命名视图名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        vp = zcad_conn.find_one("PViewport", predicate=pred)
        if not vp:
            return "未找到PViewport对象"
        view = zcad_conn.doc.Views.Item(view_name)
        vp.SetView(view)
        return f"成功设置视口视图: {view_name}"
    except Exception as e:
        return _format_error("设置视口视图", e)


@mcp.tool
def lock_viewport(object_type: str, property_name: str, property_value: str,
                  locked: bool = True) -> str:
    """
    锁定/解锁图纸空间视口

    参数:
    - object_type/property_name/property_value: 定位PViewport对象
    - locked: True=锁定, False=解锁

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        vp = zcad_conn.find_one("PViewport", predicate=pred)
        if not vp:
            return "未找到PViewport对象"
        vp.DisplayLocked = locked
        return f"成功{'锁定' if locked else '解锁'}视口"
    except Exception as e:
        return _format_error("锁定视口", e)


# ==========================================
# 图层状态管理工具（来自 IZcadLayerStateManager）
# ==========================================

@mcp.tool
def save_layer_state(name: str) -> str:
    """
    保存当前图层状态

    参数:
    - name: 图层状态名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        lsm = zcad_conn.doc.Layers.LayerStateManager \
            if hasattr(zcad_conn.doc.Layers, 'LayerStateManager') else None
        if lsm is None:
            # Fallback via Database
            lsm = zcad_conn.doc.Database.Layers.LayerStateManager \
                if hasattr(zcad_conn.doc.Database.Layers, 'LayerStateManager') else None
        if lsm is None:
            return "图层状态管理器不可用"
        lsm.Save(name, 255)
        return f"成功保存图层状态: {name}"
    except Exception as e:
        return _format_error("保存图层状态", e)


@mcp.tool
def restore_layer_state(name: str) -> str:
    """
    恢复图层状态

    参数:
    - name: 图层状态名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        lsm = zcad_conn.doc.Layers.LayerStateManager
        lsm.Restore(name)
        return f"成功恢复图层状态: {name}"
    except Exception as e:
        return _format_error("恢复图层状态", e)


# ==========================================
# 绘制顺序工具
# ==========================================

@mcp.tool
def move_entity_to_top(object_type: str, property_name: str, property_value: str) -> str:
    """
    将实体移动到绘制顺序的顶部

    参数:
    - object_type/property_name/property_value: 定位对象

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return "未找到对象"
        st = zcad_conn.doc.Database.SortentsTable \
            if hasattr(zcad_conn.doc.Database, 'SortentsTable') else None
        if st is None:
            return "绘制顺序表不可用（此文文件内可能使用了DrawOrderTable）"
        st.MoveToTop([obj])
        return "成功移动实体到顶部"
    except Exception as e:
        return _format_error("绘制顺序", e)


# ==========================================
# 扩展应用程序操作工具
# ==========================================

@mcp.tool
def zoom_scaled(scale: float = 1.0, scale_type: int = 0) -> str:
    """
    按比例缩放视图

    参数:
    - scale: 缩放比例
    - scale_type: 缩放类型（0=相对于全图，1=相对于当前视图）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.app.ZoomScaled(scale, scale_type)
        return f"成功执行 ZoomScaled: scale={scale}, type={scale_type}"
    except Exception as e:
        return _format_error("ZoomScaled", e)


@mcp.tool
def zoom_previous() -> str:
    """
    缩放到前一个视图

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.app.ZoomPrevious()
        return "成功执行 ZoomPrevious"
    except Exception as e:
        return _format_error("ZoomPrevious", e)


@mcp.tool
def eval_lisp(expression: str) -> str:
    """
    执行LISP表达式

    参数:
    - expression: LISP表达式字符串

    返回: 执行结果
    """
    try:
        zcad_conn, _ = get_cad_connection()
        result = zcad_conn.app.Eval(expression)
        return f"LISP执行结果: {result}"
    except Exception as e:
        return _format_error("执行LISP", e)


@mcp.tool
def get_zcad_state() -> str:
    """
    获取ZWCAD应用程序状态（是否静默）

    返回: 状态信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        state = zcad_conn.app.GetZcadState()
        info = {}
        if hasattr(state, 'IsQuiescent'):
            info['is_quiescent'] = state.IsQuiescent
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取状态", e)


# ==========================================
# Q3D实体属性工具
# ==========================================

@mcp.tool
def get_solid_properties(object_type: str, property_name: str, property_value: str) -> str:
    """
    获取3D实体的属性（体积、质心等）

    参数:
    - object_type/property_name/property_value: 定位3D实体

    返回: JSON格式的实体属性
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return "未找到3D实体"
        info = {}
        for prop in ['Volume', 'SolidType']:
            if hasattr(obj, prop):
                try:
                    info[prop.lower()] = getattr(obj, prop)
                except Exception:
                    pass
        if hasattr(obj, 'Centroid'):
            try:
                info['centroid'] = list(obj.Centroid)
            except Exception:
                pass
        if hasattr(obj, 'MomentOfInertia'):
            try:
                info['moment_of_inertia'] = list(obj.MomentOfInertia)
            except Exception:
                pass
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取3D实体属性", e)


# ==========================================
# 区域对象工具（来自 IZcadRegion）
# ==========================================

@mcp.tool
def get_region_properties(object_type: str, property_name: str, property_value: str) -> str:
    """
    获取区域对象的属性（面积、周长、质心等）

    参数:
    - object_type/property_name/property_value: 定位区域对象

    返回: JSON格式的区域属性
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("Region", predicate=pred)
        if not obj:
            return "未找到区域对象"
        info = {}
        for prop in ['Area', 'Perimeter']:
            if hasattr(obj, prop):
                try:
                    info[prop.lower()] = getattr(obj, prop)
                except Exception:
                    pass
        if hasattr(obj, 'Centroid'):
            try:
                info['centroid'] = list(obj.Centroid)
            except Exception:
                pass
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取区域属性", e)


# ==========================================
# 外部参照工具
# ==========================================

@mcp.tool
def attach_xref(path_name: str, name: str,
                x: float = 0, y: float = 0, z: float = 0,
                x_scale: float = 1, y_scale: float = 1, z_scale: float = 1,
                rotation: float = 0, overlay: bool = False,
                layer: str = "0") -> str:
    """
    附着外部参照

    参数:
    - path_name: DWG文件路径
    - name: 参照名称
    - x,y,z: 插入点
    - x_scale,y_scale,z_scale: 缩放比例
    - rotation: 旋转角度（弧度）
    - overlay: 是否为覆盖型参照
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        xref = zcad_conn.model.AttachExternalReference(
            path_name, name, point, x_scale, y_scale, z_scale, rotation, overlay
        )
        xref.Layer = layer
        return f"成功附着外部参照: '{name}' ({path_name})"
    except Exception as e:
        return _format_error("附着外部参照", e)


@mcp.tool
def bind_xref(object_type: str, property_name: str, property_value: str,
              prefix_name: bool = True) -> str:
    """
    绑定外部参照到当前文档

    参数:
    - object_type/property_name/property_value: 定位外部参照对象
    - prefix_name: 是否保留名称前缀

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one("ExternalReference", predicate=pred)
        if not obj:
            return "未找到外部参照"
        obj.Bind(prefix_name)
        return "成功绑定外部参照"
    except Exception as e:
        return _format_error("绑定外部参照", e)


# ==========================================
# 光栅图像工具
# ==========================================

@mcp.tool
def add_raster(image_path: str, x: float = 0, y: float = 0, z: float = 0,
               scale_factor: float = 1.0, rotation: float = 0.0,
               layer: str = "0") -> str:
    """
    添加光栅图像

    参数:
    - image_path: 图像文件路径
    - x,y,z: 插入点
    - scale_factor: 缩放比例
    - rotation: 旋转角度（弧度）
    - layer: 图层名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        point = APoint(x, y, z)
        raster = zcad_conn.model.AddRaster(image_path, point, scale_factor, rotation)
        raster.Layer = layer
        return f"成功添加光栅图像: {image_path}"
    except Exception as e:
        return _format_error("添加光栅图像", e)


# ==========================================
# 文字样式属性工具
# ==========================================

@mcp.tool
def set_textstyle_properties(name: str,
                             font_file: str = None,
                             big_font_file: str = None,
                             height: float = None,
                             width: float = None,
                             oblique_angle: float = None) -> str:
    """
    修改现有文字样式的属性

    参数:
    - name: 文字样式名称
    - font_file: 新字体文件
    - big_font_file: 新大字体文件
    - height: 新固定高度
    - width: 新宽度因子
    - oblique_angle: 新倾斜角度

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        ts = zcad_conn.doc.TextStyles.Item(name)
        updated = []
        if font_file is not None:
            ts.fontFile = font_file; updated.append(f"Font={font_file}")
        if big_font_file is not None and hasattr(ts, 'BigFontFile'):
            ts.BigFontFile = big_font_file; updated.append(f"BigFont={big_font_file}")
        if height is not None:
            ts.Height = height; updated.append(f"Height={height}")
        if width is not None:
            ts.Width = width; updated.append(f"Width={width}")
        if oblique_angle is not None:
            ts.ObliqueAngle = oblique_angle; updated.append(f"Oblique={oblique_angle}")
        return f"成功修改文字样式 '{name}': {', '.join(updated)}" if updated else "未提供修改参数"
    except Exception as e:
        return _format_error("修改文字样式", e)


# ==========================================
# 实体 XData 工具
# ==========================================

@mcp.tool
def get_entity_objectid(object_type: str, property_name: str, property_value: str) -> str:
    """
    获取实体的Handle和ObjectID

    参数:
    - object_type/property_name/property_value: 定位实体

    返回: JSON格式的实体标识信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return "未找到实体"
        info = {"object_name": obj.ObjectName}
        if hasattr(obj, 'Handle'):
            info['handle'] = obj.Handle
        if hasattr(obj, 'ObjectID'):
            info['object_id'] = str(obj.ObjectID)
        if hasattr(obj, 'OwnerID'):
            info['owner_id'] = str(obj.OwnerID)
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取实体标识", e)


@mcp.tool
def get_object_by_handle(handle: str) -> str:
    """
    通过句柄获取实体对象信息

    参数:
    - handle: 实体句柄字符串（如 "1A2B"）

    返回: JSON格式的实体信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        obj = zcad_conn.doc.Database.HandleToObject(handle)
        if not obj:
            return f"未找到句柄 {handle} 对应的实体"
        info = {"found": True, "object_name": obj.ObjectName, "handle": handle}
        common_props = ['Layer', 'Color', 'Linetype', 'LinetypeScale',
                        'Lineweight', 'Visible']
        for prop in common_props:
            if hasattr(obj, prop):
                try:
                    info[prop] = getattr(obj, prop)
                except Exception:
                    pass
        try:
            min_pt, max_pt = obj.GetBoundingBox()
            info['bounding_box'] = {'min': list(min_pt), 'max': list(max_pt)}
        except Exception:
            pass
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("句柄查找实体", e)


# ==========================================
# 字典/XRecord/XData 工具（自定义数据存储）
# ==========================================

@mcp.tool
def list_dictionaries() -> str:
    """
    列出文档中的所有命名对象字典

    返回: JSON格式的字典列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        dicts = []
        for d in zcad_conn.doc.Dictionaries:
            dicts.append({"name": d.Name, "count": d.Count})
        return json.dumps(dicts, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取字典列表失败: {str(e)}"


@mcp.tool
def add_dictionary(name: str) -> str:
    """
    创建新的命名对象字典

    参数:
    - name: 字典名称

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        zcad_conn.doc.Dictionaries.Add(name)
        return f"成功创建字典: {name}"
    except Exception as e:
        return _format_error("创建字典", e)


@mcp.tool
def add_xrecord(dict_name: str, xrecord_name: str,
                data_type: int, data_value) -> str:
    """
    向字典添加XRecord（扩展记录）

    参数:
    - dict_name: 字典名称
    - xrecord_name: XRecord名称
    - data_type: 数据类型码（1=字符串，10=双精度，70=整数等）
    - data_value: 数据值

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        d = zcad_conn.doc.Dictionaries.Item(dict_name)
        xrec = d.AddXRecord(xrecord_name)
        xrec.SetXRecordData(data_type, data_value)
        return f"成功添加XRecord: '{xrecord_name}' 到字典 '{dict_name}'"
    except Exception as e:
        return _format_error("添加XRecord", e)


# ==========================================
# 应用首选项工具
# ==========================================

@mcp.tool
def get_preferences() -> str:
    """
    获取所有应用首选项的摘要信息

    返回: JSON格式的首选项摘要
    """
    try:
        zcad_conn, _ = get_cad_connection()
        prefs = zcad_conn.app.Preferences
        info = {
            "display": {},
            "drafting": {},
            "open_save": {},
            "selection": {},
            "system": {},
            "user": {},
        }
        # Display
        if hasattr(prefs, 'Display'):
            dp = prefs.Display
            for p in ['DisplayScrollBars', 'LayoutDisplayMargins',
                      'LayoutDisplayPaper', 'LayoutCreateViewport']:
                if hasattr(dp, p):
                    try: info['display'][p.lower()] = getattr(dp, p)
                    except Exception: pass
        # Drafting
        if hasattr(prefs, 'Drafting'):
            dr = prefs.Drafting
            for p in ['AutoSnapMarker', 'AutoSnapMagnet', 'AutoSnapTooltip',
                      'AutoSnapApertureSize', 'AutoSnapMarkerSize']:
                if hasattr(dr, p):
                    try: info['drafting'][p.lower()] = getattr(dr, p)
                    except Exception: pass
        # OpenSave
        if hasattr(prefs, 'OpenSave'):
            os_ = prefs.OpenSave
            for p in ['AutoSaveInterval', 'CreateBackup', 'SavePreviewThumbnail',
                      'FullCRCValidation']:
                if hasattr(os_, p):
                    try: info['open_save'][p.lower()] = getattr(os_, p)
                    except Exception: pass
        # Selection
        if hasattr(prefs, 'Selection'):
            sp = prefs.Selection
            for p in ['PickFirst', 'PickAdd', 'PickDrag', 'PickAuto',
                      'PickBoxSize', 'DisplayGrips']:
                if hasattr(sp, p):
                    try: info['selection'][p.lower()] = getattr(sp, p)
                    except Exception: pass
        # System
        if hasattr(prefs, 'System'):
            sy = prefs.System
            for p in ['SingleDocumentMode', 'BeepOnError']:
                if hasattr(sy, p):
                    try: info['system'][p.lower()] = getattr(sy, p)
                    except Exception: pass
        # User
        if hasattr(prefs, 'User'):
            up = prefs.User
            for p in ['KeyboardAccelerator', 'SCMDefaultMode']:
                if hasattr(up, p):
                    try: info['user'][p.lower()] = getattr(up, p)
                    except Exception: pass
        return json.dumps(info, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return _format_error("获取首选项", e)


@mcp.tool
def set_preference(category: str, name: str, value) -> str:
    """
    设置应用首选项

    参数:
    - category: 类别名（"Display"/"Drafting"/"OpenSave"/"Selection"/"System"/"User"/"Files"/"Output"）
    - name: 属性名（如 "AutoSnapMarker", "PickFirst", "AutoSaveInterval"）
    - value: 新值（整数、布尔值或字符串）

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        prefs = zcad_conn.app.Preferences
        cat_obj = getattr(prefs, category)
        if not cat_obj:
            return f"未找到首选项类别: {category}"
        setattr(cat_obj, name, value)
        return f"成功设置首选项: {category}.{name} = {value}"
    except Exception as e:
        return _format_error("设置首选项", e)


# ==========================================
# 材质工具（来自 IZcadMaterial/IZcadMaterials）
# ==========================================

@mcp.tool
def list_materials() -> str:
    """
    列出文档中的所有材质

    返回: JSON格式的材质列表
    """
    try:
        zcad_conn, _ = get_cad_connection()
        mats = []
        for m in zcad_conn.doc.Materials:
            info = {"name": m.Name}
            if hasattr(m, 'Description'):
                try: info['description'] = m.Description
                except Exception: pass
            mats.append(info)
        return json.dumps(mats, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"获取材质列表失败: {str(e)}"


@mcp.tool
def add_material(name: str, description: str = "") -> str:
    """
    创建新材质

    参数:
    - name: 材质名称
    - description: 描述

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        mat = zcad_conn.doc.Materials.Add(name)
        if description:
            mat.Description = description
        return f"成功创建材质: {name}"
    except Exception as e:
        return _format_error("创建材质", e)


# ==========================================
# 超链接工具（来自 IZcadHyperlinks/IZcadHyperlink）
# ==========================================

@mcp.tool
def add_hyperlink(object_type: str, property_name: str, property_value: str,
                  url: str, description: str = "") -> str:
    """
    向实体添加超链接

    参数:
    - object_type/property_name/property_value: 定位实体
    - url: 超链接URL
    - description: 链接描述文字

    返回: 操作结果信息
    """
    try:
        zcad_conn, _ = get_cad_connection()
        def pred(obj):
            if hasattr(obj, property_name):
                return str(getattr(obj, property_name)) == str(property_value)
            return False
        obj = zcad_conn.find_one(object_type, predicate=pred)
        if not obj:
            return "未找到实体"
        hl = obj.Hyperlinks.Add(url)
        if description and hasattr(hl, 'URLDescription'):
            hl.URLDescription = description
        return f"成功添加超链接: {url}"
    except Exception as e:
        return _format_error("添加超链接", e)


# ==========================================
# 主程序入口
# ==========================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ZWCAD Mechanical MCP Server 启动中...")
    logger.info("=" * 60)
    logger.info("服务器已就绪，等待客户端连接...")
    mcp.run()

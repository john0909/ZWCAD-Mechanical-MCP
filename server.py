"""  
ZWCAD Mechanical MCP Server - 基于 FastMCP 的中望机械CAD自动化服务
提供画直线、画圆、标题栏编辑、图框切换、明细表操作等功能
"""

from fastmcp import FastMCP
from pyzwcad import ZwCAD, APoint
from pyzwcadmech import ZwCADMech
import json
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
# 主程序入口
# ==========================================

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("ZWCAD Mechanical MCP Server 启动中...")
    logger.info("=" * 60)
    logger.info("服务器已就绪，等待客户端连接...")
    mcp.run()

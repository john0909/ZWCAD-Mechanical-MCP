# ZWCAD机械版 MCP Server

[中文](#zwcad-mechanical-mcp-server) | [English](#english)

---

基于 [FastMCP](https://github.com/jlowin/fastmcp) 框架的中望机械CAD自动化 MCP 服务，让 AI 模型（如 DeepSeek, Qwen, GLM, Kimi 等）可以通过 MCP 协议直接操控中望机械CAD完成绘图、编辑标题栏、管理图框和明细表等操作。

## 演示视频

https://github.com/user-attachments/assets/827604ac-3e79-47f8-8655-71bd306c33cb

## 功能概览

| 分类 | 工具数 | 说明 |
|------|--------|------|
| 基础绘图 | 10 | 直线、圆、圆弧、椭圆、多段线、样条曲线、点、文本等 |
| 3D绘图 | 8 | 长方体、圆柱、圆锥、球体、圆环、楔体、3D面/多段线 |
| 辅助线 | 3 | 射线、构造线、多线 |
| 标注 | 6 | 对齐/旋转/直径/半径/角度/坐标标注 |
| 引线与公差 | 5 | 引线、形位公差、多重引线 |
| 填充 | 3 | 图案填充、修改填充、内边界 |
| 图块 | 8 | 图块列表/信息/属性、插入/创建/分解图块、动态块 |
| 表格 | 8 | 创建表格、单元格读写、行列增删、合并 |
| 对象变换 | 11 | 复制、移动、旋转、镜像、缩放、删除、阵列、偏移等 |
| 对象修改 | 10 | 修改圆/弧/线/文本/多段线/样条曲线属性、实体属性设置 |
| 图层 | 6 | 图层列表/创建/激活/属性设置/状态保存/恢复 |
| 样式 | 10 | 线型/文字样式/标注样式管理 |
| 文档与布局 | 14 | 新建/打开/保存/关闭文档、布局管理、对象查找 |
| 标题栏 | 5 | 读取/修改/批量修改标题栏字段 |
| 图框 | 10 | 获取图框信息、切换/创建/刷新图框等 |
| 明细表 | 10 | 增删改查明细表行及字段 |
| 数据库 | 3 | 打开/保存/关闭机械模块数据 |
| 编辑对话框 | 5 | 图框/标题栏/参数表/附加栏/汇总明细表编辑 |
| 视图与缩放 | 11 | 缩放、命名视图、视口锁定/重生成 |
| 选择集 | 5 | 创建/选择/清空选择集 |
| UCS与坐标 | 4 | UCS管理、坐标转换 |
| 编组 | 3 | 编组列表/创建/追加 |
| 应用程序 | 12 | 版本/路径/命令、LISP执行、文档操作 |
| 系统 | 5 | 系统变量、首选项、应用状态 |
| 文件I/O | 5 | 打印/导出/导入/外部参照 |
| 其他 | 20 | 球标、环境初始化、超链接、对象查询、撤销、字典、材质、摘要信息等 |

**共计 200 个工具**

## 系统要求

- **操作系统**: Windows 10/11
- **CAD 软件**: [中望机械CAD 2027](https://www.zwsoft.com/product/zwcad/mfg) 已安装并运行
- **Python**: 3.9+

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动中望机械CAD

确保中望机械CAD 2027 已启动并打开了一个 DWG 文件。

### 3. 启动 MCP Server

```bash
python server.py
```

或使用一键启动脚本：

```bash
start.bat
```

### 4. 配置 MCP 客户端

#### Cursor

在项目根目录创建 `.cursor/mcp.json`，或编辑全局配置：

```json
{
  "mcpServers": {
    "zwcadmech": {
      "command": "python",
      "args": ["path/to/zwcad-mechanical-mcp-server/server.py"]
    }
  }
}
```

#### Claude Desktop

编辑 `~/AppData/Roaming/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "zwcadmech": {
      "command": "python",
      "args": ["path/to/zwcad-mechanical-mcp-server/server.py"]
    }
  }
}
```

#### Qoder

参考 `mcp-config.json` 进行配置。

## 工具详细说明

### 基础绘图

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `draw_line` | 绘制直线 | 起点终点坐标, 图层 |
| `draw_circle` | 绘制圆 | 圆心坐标, 半径, 图层 |
| `draw_arc` | 绘制圆弧 | 圆心, 半径, 起止角度 |
| `draw_ellipse` | 绘制椭圆 | 圆心, 主轴向量, 半径比 |
| `draw_lwpolyline` | 绘制轻量多段线 | 顶点列表, 是否闭合 |
| `draw_polyline` | 绘制2D多段线 | 顶点列表, 是否闭合 |
| `draw_spline` | 绘制样条曲线 | 拟合点列表, 起止切向 |
| `add_point` | 添加点对象 | 坐标 |
| `add_text` | 添加单行文本 | 文本内容, 位置, 字高 |
| `add_mtext` | 添加多行文本 | 文本内容, 位置, 宽度, 字高 |

### 3D绘图

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `draw_3d_face` | 绘制3D面 | 四角点坐标 |
| `draw_3d_polyline` | 绘制3D多段线 | 三维顶点列表 |
| `draw_box` | 绘制长方体 | 原点, 长/宽/高 |
| `draw_cylinder` | 绘制圆柱体 | 底面圆心, 半径, 高度 |
| `draw_cone` | 绘制圆锥体 | 底面圆心, 半径, 高度 |
| `draw_sphere` | 绘制球体 | 球心, 半径 |
| `draw_torus` | 绘制圆环体 | 中心, 圆环半径, 管半径 |
| `draw_wedge` | 绘制楔体 | 原点, 长/宽/高 |

### 辅助线

| 工具 | 说明 |
|------|------|
| `draw_ray` | 绘制射线（单向无限延伸） |
| `draw_xline` | 绘制构造线（双向无限延伸） |
| `draw_mline` | 绘制多线 |

### 标注

| 工具 | 说明 | 关键参数 |
|------|------|----------|
| `add_dim_aligned` | 对齐标注 | 两条延伸线原点, 文字位置 |
| `add_dim_rotated` | 旋转标注 | 原点, 文字位置, 旋转角度 |
| `add_dim_diametric` | 直径标注 | 弦上两点, 引线长度 |
| `add_dim_radial` | 半径标注 | 圆心, 圆上一点 |
| `add_dim_angular` | 角度标注 | 顶点, 两条边端点 |
| `add_dim_ordinate` | 坐标标注 | 定义点, 引线端点 |

### 引线与公差

| 工具 | 说明 |
|------|------|
| `add_leader` | 添加引线标注 |
| `add_tolerance` | 添加形位公差标注 |
| `add_mleader` | 添加多重引线 |
| `add_mleader_line` | 向多重引线添加引线 |
| `get_mleader_vertices` | 获取多重引线顶点 |

### 填充

| 工具 | 说明 |
|------|------|
| `add_hatch` | 添加图案填充 |
| `set_hatch_properties` | 修改填充图案属性 |
| `add_inner_loop` | 向填充添加内边界（空洞） |

### 图块

| 工具 | 说明 |
|------|------|
| `list_blocks` | 获取所有图块定义列表 |
| `get_block_info` | 获取图块详细信息 |
| `get_block_attributes` | 获取图块引用属性值 |
| `insert_block` | 插入图块引用 |
| `create_block_definition` | 创建新图块定义 |
| `explode_block_reference` | 分解图块引用 |
| `get_dynamic_block_properties` | 获取动态块属性 |
| `get_constant_attributes` | 获取图块常量属性 |

### 表格

| 工具 | 说明 |
|------|------|
| `add_table` | 添加表格对象 |
| `set_cell_text` | 设置单元格文本 |
| `get_cell_text` | 获取单元格文本 |
| `insert_table_rows` | 插入行 |
| `delete_table_rows` | 删除行 |
| `set_column_width` | 设置列宽 |
| `set_row_height` | 设置行高 |
| `merge_cells` | 合并单元格 |

### 对象变换

| 工具 | 说明 |
|------|------|
| `copy_object` | 复制对象 |
| `move_object` | 移动对象 |
| `rotate_object` | 旋转对象 |
| `mirror_object` | 镜像对象 |
| `scale_object` | 缩放对象 |
| `delete_object` | 删除对象 |
| `array_polar` | 极坐标阵列 |
| `array_rectangular` | 矩形阵列 |
| `mirror_3d_object` | 3D镜像 |
| `rotate_3d_object` | 3D旋转 |
| `move_entity_to_top` | 移至绘制顺序顶部 |

### 对象修改

| 工具 | 说明 |
|------|------|
| `modify_circle` | 修改圆的几何属性 |
| `modify_arc` | 修改圆弧的几何属性 |
| `modify_line` | 修改直线端点 |
| `modify_text` | 修改单行文本属性 |
| `modify_mtext` | 修改多行文本属性 |
| `modify_polyline` | 修改多段线属性 |
| `modify_spline` | 修改样条曲线属性 |
| `offset_entity` | 偏移实体 |
| `explode_entity` | 分解实体 |
| `set_entity_properties` | 设置实体通用属性（图层/颜色/线型等） |

### 图层

| 工具 | 说明 |
|------|------|
| `list_layers` | 获取所有图层列表 |
| `add_layer` | 创建新图层 |
| `set_active_layer` | 设置当前活动图层 |
| `set_layer_properties` | 设置图层属性（开关/冻结/锁定/颜色/线型） |
| `save_layer_state` | 保存当前图层状态 |
| `restore_layer_state` | 恢复图层状态 |

### 样式

| 工具 | 说明 |
|------|------|
| `list_linetypes` | 获取线型列表 |
| `load_linetype` | 加载线型 |
| `set_active_linetype` | 设置当前线型 |
| `list_textstyles` | 获取文字样式列表 |
| `add_textstyle` | 创建文字样式 |
| `set_active_textstyle` | 设置当前文字样式 |
| `set_textstyle_properties` | 修改文字样式属性 |
| `list_dimstyles` | 获取标注样式列表 |
| `add_dimstyle` | 创建标注样式 |
| `set_active_dimstyle` | 设置当前标注样式 |

### 文档与布局

| 工具 | 说明 |
|------|------|
| `new_drawing` | 新建空白图纸 |
| `new_document` | 新建文档（基于模板） |
| `get_document_info` | 获取文档详细信息 |
| `get_layouts` | 获取布局列表 |
| `get_objects_in_model` | 获取模型空间对象列表 |
| `find_object` | 查找符合条件的对象 |
| `send_prompt` | 在命令行打印文本 |
| `get_active_layout` | 获取当前激活布局 |
| `list_documents` | 获取所有打开的文档 |
| `activate_document` | 激活指定文档 |
| `add_layout` | 添加新布局 |
| `set_active_layout` | 设置活动布局 |
| `close_current_document` | 关闭当前文档 |
| `save_drawing` | 保存图纸 |

### 标题栏操作

| 工具 | 说明 |
|------|------|
| `get_title_block_info` | 获取标题栏所有字段（索引/标签/名称/值） |
| `set_title_block_field` | 设置单个字段值（如"设计"、"审核"） |
| `update_title_block_batch` | 批量设置多个字段 `{"设计": "张三", "审核": "李四"}` |
| `get_title_field_count` | 获取字段总数 |
| `get_title_item_by_index` | 按索引获取字段详情 |

### 图框操作

| 工具 | 说明 |
|------|------|
| `create_frame` | 新建图幅（自动读取 XML 默认样式配置） |
| `get_available_frames` | 获取当前图纸所有图框名称 |
| `get_frame_full_info` | 获取当前图框完整属性 |
| `update_frame_properties` | 更新图框属性（尺寸/样式/比例等） |
| `switch_frame` | 切换活动图框 |
| `refresh_frame` | 刷新图框显示 |
| `get_frame_count` | 获取图框总数 |
| `get_frame_name_by_index` | 按索引获取图框名 |
| `get_frame_name_by_point` | 按坐标获取图框名 |
| `get_next_frame_name` | 获取下一个图框名称 |

### 明细表（BOM）操作

| 工具 | 说明 |
|------|------|
| `add_bom_row` | 添加行 `{"序号": "1", "名称": "零件A"}` |
| `get_bom_row_count` | 获取总行数 |
| `get_bom_row_data` | 获取指定行全部字段 |
| `update_bom_row` | 更新指定行数据 |
| `insert_bom_row` | 在指定位置插入行 |
| `delete_bom_row` | 删除指定行 |
| `get_bom_row_field_count` | 获取行字段数 |
| `get_bom_row_field` | 获取行指定字段 |
| `set_bom_row_field` | 设置行指定字段值 |
| `refresh_bom` | 刷新明细表显示 |

### 数据库操作

| 工具 | 说明 |
|------|------|
| `open_mech_file` | 打开机械模块文件 |
| `save_mech_data` | 保存机械模块数据 |
| `close_mech` | 关闭机械模块连接 |

### 编辑对话框

| 工具 | 说明 |
|------|------|
| `edit_frame` | 打开图框编辑对话框 |
| `edit_title` | 打开标题栏编辑对话框 |
| `edit_csl` | 打开参数表编辑对话框 |
| `edit_fjl` | 打开附加栏编辑对话框 |
| `edit_total_bom` | 打开汇总明细表编辑对话框 |

### 视图与缩放

| 工具 | 说明 |
|------|------|
| `zoom_extents` | 缩放到图形范围 |
| `zoom_all` | 缩放显示全部图形 |
| `zoom_window` | 窗口缩放 |
| `zoom_center` | 中心缩放 |
| `zoom_scaled` | 按比例缩放 |
| `zoom_previous` | 缩放到前一个视图 |
| `list_views` | 获取命名视图列表 |
| `add_view` | 创建命名视图 |
| `set_view` | 设置视口视图 |
| `lock_viewport` | 锁定/解锁视口 |
| `regen_viewport` | 重生成视口显示 |

### 选择集

| 工具 | 说明 |
|------|------|
| `create_selection_set` | 创建命名选择集 |
| `select_objects` | 窗选/窗交选择对象 |
| `select_on_screen` | 交互式屏幕选择 |
| `select_by_polygon` | 多边形选择对象 |
| `clear_selection_set` | 清空选择集 |

### UCS与坐标

| 工具 | 说明 |
|------|------|
| `list_ucs` | 获取UCS列表 |
| `add_ucs` | 创建新UCS |
| `set_active_ucs` | 设置活动UCS |
| `translate_coordinates` | 坐标系转换 |

### 编组

| 工具 | 说明 |
|------|------|
| `list_groups` | 获取编组列表 |
| `create_group` | 创建编组 |
| `append_to_group` | 将对象添加到编组 |

### 应用程序

| 工具 | 说明 |
|------|------|
| `get_mech_version` | 获取机械模块版本 |
| `get_cad_path` | 获取CAD安装路径 |
| `get_zwm_path` | 获取机械模块路径 |
| `get_style_path` | 获取样式文件路径 |
| `get_mech_about` | 获取机械模块关于信息 |
| `send_mech_command` | 发送机械模块命令 |
| `open_mech_doc` | 使用机械模块打开文档 |
| `new_mech_doc` | 使用机械模块新建文档 |
| `new_named_mech_doc` | 使用机械模块新建命名文档 |
| `get_application_info` | 获取应用程序信息 |
| `send_command` | 发送命令行命令 |
| `eval_lisp` | 执行LISP表达式 |

### 系统

| 工具 | 说明 |
|------|------|
| `get_variable` | 获取系统变量值 |
| `set_variable` | 设置系统变量值 |
| `get_zcad_state` | 获取应用状态（是否静默） |
| `get_preferences` | 获取应用首选项摘要 |
| `set_preference` | 设置应用首选项 |

### 文件I/O

| 工具 | 说明 |
|------|------|
| `plot_to_file` | 打印到文件 |
| `export_drawing` | 导出图纸（DWG/DXF/BMP/WMF等） |
| `import_file` | 导入文件 |
| `attach_xref` | 附着外部参照 |
| `bind_xref` | 绑定外部参照 |

### 其他

| 工具 | 说明 |
|------|------|
| `get_balloon` | 获取球标对象 |
| `cad_environment_init` | 初始化CAD环境 |
| `add_hyperlink` | 向实体添加超链接 |
| `add_raster` | 添加光栅图像 |
| `purge_all` | 清除未使用的命名对象 |
| `get_intersection` | 获取两实体交点 |
| `get_object_properties` | 获取对象详细属性 |
| `get_object_by_handle` | 通过句柄获取实体信息 |
| `get_entity_objectid` | 获取实体的Handle和ObjectID |
| `get_solid_properties` | 获取3D实体属性（体积/质心） |
| `get_region_properties` | 获取区域属性（面积/周长/质心） |
| `undo_mark_start` | 开始撤销标记 |
| `undo_mark_end` | 结束撤销标记 |
| `list_dictionaries` | 列出命名对象字典 |
| `add_dictionary` | 创建命名对象字典 |
| `add_xrecord` | 向字典添加扩展记录 |
| `list_materials` | 列出所有材质 |
| `add_material` | 创建新材质 |
| `get_summary_info` | 获取文档摘要信息 |
| `set_summary_info` | 设置文档摘要信息 |

## 示例：通过 AI 创建图框

在 Cursor / Claude Code 中对 AI 说：

> "帮我创建一个 A3 横向图框，标准为 GB，包含标题栏和附加栏"

AI 会自动调用 `create_frame` 工具：

```python
create_frame(
    frame_size_name="A3",
    orientation="landscape",
    std_name="GB",
    have_btl=True,
    have_fjl=True
)
```

## 项目结构

```
zwcad-mechanical-mcp-server/
├── server.py                 # MCP Server 主程序（200个工具）
├── requirements.txt          # Python 依赖
├── mcp-config.json           # MCP 客户端配置示例
├── start.bat                 # Windows 一键启动
├── .gitignore
├── LICENSE
└── README.md
```

## 技术架构

```
AI 客户端 (Cursor/Claude/Qoder)
        │
        │ MCP 协议 (STDIO)
        ▼
   FastMCP Server
        │
        ├── pyzwcad ──────► ZWCAD COM API (基础绘图)
        │
        └── pyzwcadmech ──► ZwmToolKit COM API (机械专业功能)
                                ├── ZwmApp (应用程序)
                                ├── ZwmDb  (数据库)
                                ├── ZwmTitle (标题栏)
                                ├── ZwmBom   (明细表)
                                └── ZwmFrame (图框)
```

## 注意事项

1. **ZWCAD 必须运行**: 所有工具调用都需要中望机械CAD已启动并打开 DWG 文件。

2. **样式文件路径**: `create_frame` 工具从中望机械CAD安装目录的 XML 配置文件中读取默认样式，路径为 `C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles`。

## 依赖项目

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD/AutoCAD Python COM 封装
- [pyzwcadmech](https://github.com/john0909/pyzwcadmech) - 中望机械CAD Python COM 封装
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP 协议服务端框架

## 许可证

MIT License - 详见 [LICENSE](LICENSE)

---

<a id="english"></a>

# ZWCAD Mechanical MCP Server

[中文](#zwcad-mechanical-mcp-server) | English

A ZWCAD Mechanical automation MCP server built with [FastMCP](https://github.com/jlowin/fastmcp), enabling AI models (Claude, GPT, Cursor, etc.) to control ZWCAD Mechanical directly via the MCP protocol for drawing, title block editing, frame management, BOM operations, and more.

## Demo Video

https://github.com/user-attachments/assets/827604ac-3e79-47f8-8655-71bd306c33cb

## Feature Overview

| Category | Tools | Description |
|----------|-------|-------------|
| Basic Drawing | 10 | Line, circle, arc, ellipse, polyline, spline, point, text |
| 3D Drawing | 8 | Box, cylinder, cone, sphere, torus, wedge, 3D face/polyline |
| Construction Lines | 3 | Ray, xline, mline |
| Dimensioning | 6 | Aligned/rotated/diametric/radial/angular/ordinate |
| Leaders & Tolerance | 5 | Leader, tolerance, mleader |
| Hatch | 3 | Pattern hatch, hatch properties, inner loop |
| Block | 8 | Block list/info/attributes, insert/create/explode, dynamic block |
| Table | 8 | Create table, cell read/write, row/col insert/delete, merge |
| Object Transform | 11 | Copy, move, rotate, mirror, scale, delete, array, offset |
| Object Modify | 10 | Modify circle/arc/line/text/polyline/spline, entity properties |
| Layer | 6 | Layer list/create/activate/properties, state save/restore |
| Style | 10 | Linetype/text style/dim style management |
| Document & Layout | 14 | New/open/save/close doc, layouts, find objects |
| Title Block | 5 | Read/modify/batch update title block fields |
| Frame | 10 | Frame info, switch/create/refresh frames |
| BOM (Bill of Materials) | 10 | CRUD operations on BOM rows and fields |
| Database | 3 | Open/save/close mechanical data |
| Edit Dialogs | 5 | Frame/title/CSL/FJL/total BOM editing dialogs |
| View & Zoom | 11 | Zoom, named views, viewport lock/regen |
| Selection Set | 5 | Create/select/clear selection sets |
| UCS & Coordinates | 4 | UCS management, coordinate translation |
| Group | 3 | Group list/create/append |
| Application | 12 | Version, paths, commands, LISP, document ops |
| System | 5 | System variables, preferences, app state |
| File I/O | 5 | Plot, export, import, xref |
| Other | 20 | Balloon, environment init, hyperlink, object query, undo, dictionary, material, etc. |

**Total: 200 tools**

## Requirements

- **OS**: Windows 10/11
- **CAD Software**: [ZWCAD Mechanical 2026](https://www.zwsoft.com/product/zwcad/mfg) installed and running
- **Python**: 3.9+

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Launch ZWCAD Mechanical

Make sure ZWCAD Mechanical 2026 is running with a DWG file open.

### 3. Start the MCP Server

```bash
python server.py
```

Or use the one-click launcher:

```bash
start.bat
```

### 4. Configure your MCP client

#### Cursor

Create `.cursor/mcp.json` in your project root or edit the global config:

```json
{
  "mcpServers": {
    "zwcadmech": {
      "command": "python",
      "args": ["path/to/zwcad-mechanical-mcp-server/server.py"]
    }
  }
}
```

#### Claude Desktop

Edit `~/AppData/Roaming/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "zwcadmech": {
      "command": "python",
      "args": ["path/to/zwcad-mechanical-mcp-server/server.py"]
    }
  }
}
```

#### Qoder

Refer to `mcp-config.json` for configuration.

## Tool Reference

### Basic Drawing

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `draw_line` | Draw a line | Start/end coordinates, layer |
| `draw_circle` | Draw a circle | Center, radius, layer |
| `draw_arc` | Draw an arc | Center, radius, start/end angle |
| `draw_ellipse` | Draw an ellipse | Center, major axis, radius ratio |
| `draw_lwpolyline` | Draw lightweight polyline | Vertex list, closed |
| `draw_polyline` | Draw 2D polyline | Vertex list, closed |
| `draw_spline` | Draw spline curve | Fit points, start/end tangent |
| `add_point` | Add point | Coordinates |
| `add_text` | Add single-line text | Text, position, height |
| `add_mtext` | Add multi-line text | Text, position, width, height |

### 3D Drawing

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `draw_3d_face` | Draw 3D face | Four corner points |
| `draw_3d_polyline` | Draw 3D polyline | 3D vertex list |
| `draw_box` | Draw a box | Origin, length/width/height |
| `draw_cylinder` | Draw a cylinder | Base center, radius, height |
| `draw_cone` | Draw a cone | Base center, radius, height |
| `draw_sphere` | Draw a sphere | Center, radius |
| `draw_torus` | Draw a torus | Center, torus radius, tube radius |
| `draw_wedge` | Draw a wedge | Origin, length/width/height |

### Construction Lines

| Tool | Description |
|------|-------------|
| `draw_ray` | Draw a ray (one-way infinite) |
| `draw_xline` | Draw a construction line (two-way infinite) |
| `draw_mline` | Draw a multiline |

### Dimensioning

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `add_dim_aligned` | Aligned dimension | Two origin points, text position |
| `add_dim_rotated` | Rotated dimension | Points, rotation angle |
| `add_dim_diametric` | Diametric dimension | Two chord points |
| `add_dim_radial` | Radial dimension | Center, point on circle |
| `add_dim_angular` | Angular dimension | Vertex, two edge endpoints |
| `add_dim_ordinate` | Ordinate dimension | Definition point, leader endpoint |

### Leaders & Tolerance

| Tool | Description |
|------|-------------|
| `add_leader` | Add leader annotation |
| `add_tolerance` | Add geometric tolerance |
| `add_mleader` | Add multiline leader |
| `add_mleader_line` | Add leader line to mleader |
| `get_mleader_vertices` | Get mleader vertices |

### Hatch

| Tool | Description |
|------|-------------|
| `add_hatch` | Add pattern hatch |
| `set_hatch_properties` | Modify hatch pattern properties |
| `add_inner_loop` | Add inner boundary (hole) to hatch |

### Block

| Tool | Description |
|------|-------------|
| `list_blocks` | List all block definitions |
| `get_block_info` | Get block details |
| `get_block_attributes` | Get block reference attributes |
| `insert_block` | Insert block reference |
| `create_block_definition` | Create new block definition |
| `explode_block_reference` | Explode block reference |
| `get_dynamic_block_properties` | Get dynamic block properties |
| `get_constant_attributes` | Get block constant attributes |

### Table

| Tool | Description |
|------|-------------|
| `add_table` | Add table object |
| `set_cell_text` | Set cell text |
| `get_cell_text` | Get cell text |
| `insert_table_rows` | Insert rows |
| `delete_table_rows` | Delete rows |
| `set_column_width` | Set column width |
| `set_row_height` | Set row height |
| `merge_cells` | Merge cells |

### Object Transform

| Tool | Description |
|------|-------------|
| `copy_object` | Copy object |
| `move_object` | Move object |
| `rotate_object` | Rotate object |
| `mirror_object` | Mirror object |
| `scale_object` | Scale object |
| `delete_object` | Delete object |
| `array_polar` | Polar array |
| `array_rectangular` | Rectangular array |
| `mirror_3d_object` | 3D mirror |
| `rotate_3d_object` | 3D rotate |
| `move_entity_to_top` | Move to draw order top |

### Object Modify

| Tool | Description |
|------|-------------|
| `modify_circle` | Modify circle geometry |
| `modify_arc` | Modify arc geometry |
| `modify_line` | Modify line endpoints |
| `modify_text` | Modify single-line text properties |
| `modify_mtext` | Modify multi-line text properties |
| `modify_polyline` | Modify polyline properties |
| `modify_spline` | Modify spline properties |
| `offset_entity` | Offset entity |
| `explode_entity` | Explode entity |
| `set_entity_properties` | Set entity properties (layer/color/linetype etc.) |

### Layer

| Tool | Description |
|------|-------------|
| `list_layers` | List all layers |
| `add_layer` | Create new layer |
| `set_active_layer` | Set active layer |
| `set_layer_properties` | Set layer properties (on/freeze/lock/color/linetype) |
| `save_layer_state` | Save layer state |
| `restore_layer_state` | Restore layer state |

### Style

| Tool | Description |
|------|-------------|
| `list_linetypes` | List linetypes |
| `load_linetype` | Load linetype |
| `set_active_linetype` | Set active linetype |
| `list_textstyles` | List text styles |
| `add_textstyle` | Create text style |
| `set_active_textstyle` | Set active text style |
| `set_textstyle_properties` | Modify text style properties |
| `list_dimstyles` | List dimension styles |
| `add_dimstyle` | Create dimension style |
| `set_active_dimstyle` | Set active dimension style |

### Document & Layout

| Tool | Description |
|------|-------------|
| `new_drawing` | New blank drawing |
| `new_document` | New document (from template) |
| `get_document_info` | Get document info |
| `get_layouts` | Get layout list |
| `get_objects_in_model` | Get model space objects |
| `find_object` | Find object by property |
| `send_prompt` | Print text to command line |
| `get_active_layout` | Get active layout |
| `list_documents` | List all open documents |
| `activate_document` | Activate a document |
| `add_layout` | Add new layout |
| `set_active_layout` | Set active layout |
| `close_current_document` | Close current document |
| `save_drawing` | Save drawing |

### Title Block

| Tool | Description |
|------|-------------|
| `get_title_block_info` | Get all title block fields (index/label/name/value) |
| `set_title_block_field` | Set a single field value (e.g. "Designer", "Reviewer") |
| `update_title_block_batch` | Batch update multiple fields `{"Designer": "Zhang", "Reviewer": "Li"}` |
| `get_title_field_count` | Get total field count |
| `get_title_item_by_index` | Get field details by index |

### Frame

| Tool | Description |
|------|-------------|
| `create_frame` | Create a new frame (auto-reads XML default style config) |
| `get_available_frames` | Get all frame names in current drawing |
| `get_frame_full_info` | Get complete frame properties |
| `update_frame_properties` | Update frame properties (size/style/scale, etc.) |
| `switch_frame` | Switch active frame |
| `refresh_frame` | Refresh frame display |
| `get_frame_count` | Get total frame count |
| `get_frame_name_by_index` | Get frame name by index |
| `get_frame_name_by_point` | Get frame name by coordinate point |
| `get_next_frame_name` | Get next frame name |

### BOM (Bill of Materials)

| Tool | Description |
|------|-------------|
| `add_bom_row` | Add a row `{"No.": "1", "Name": "Part A"}` |
| `get_bom_row_count` | Get total row count |
| `get_bom_row_data` | Get all fields of a specific row |
| `update_bom_row` | Update a specific row |
| `insert_bom_row` | Insert a row at a specific position |
| `delete_bom_row` | Delete a specific row |
| `get_bom_row_field_count` | Get field count of a row |
| `get_bom_row_field` | Get a specific field of a row |
| `set_bom_row_field` | Set a specific field value of a row |
| `refresh_bom` | Refresh BOM display |

### Database

| Tool | Description |
|------|-------------|
| `open_mech_file` | Open mechanical file |
| `save_mech_data` | Save mechanical data |
| `close_mech` | Close mechanical connection |

### Edit Dialogs

| Tool | Description |
|------|-------------|
| `edit_frame` | Open frame edit dialog |
| `edit_title` | Open title block edit dialog |
| `edit_csl` | Open parameter table edit dialog |
| `edit_fjl` | Open additional block edit dialog |
| `edit_total_bom` | Open total BOM edit dialog |

### View & Zoom

| Tool | Description |
|------|-------------|
| `zoom_extents` | Zoom to drawing extents |
| `zoom_all` | Zoom to show all |
| `zoom_window` | Window zoom |
| `zoom_center` | Center zoom |
| `zoom_scaled` | Scaled zoom |
| `zoom_previous` | Zoom to previous view |
| `list_views` | List named views |
| `add_view` | Create named view |
| `set_view` | Set viewport view |
| `lock_viewport` | Lock/unlock viewport |
| `regen_viewport` | Regenerate viewport |

### Selection Set

| Tool | Description |
|------|-------------|
| `create_selection_set` | Create named selection set |
| `select_objects` | Window/crossing selection |
| `select_on_screen` | Interactive screen selection |
| `select_by_polygon` | Polygon selection |
| `clear_selection_set` | Clear selection set |

### UCS & Coordinates

| Tool | Description |
|------|-------------|
| `list_ucs` | List UCS |
| `add_ucs` | Create new UCS |
| `set_active_ucs` | Set active UCS |
| `translate_coordinates` | Coordinate system translation |

### Group

| Tool | Description |
|------|-------------|
| `list_groups` | List groups |
| `create_group` | Create group |
| `append_to_group` | Append object to group |

### Application

| Tool | Description |
|------|-------------|
| `get_mech_version` | Get mechanical module version |
| `get_cad_path` | Get CAD installation path |
| `get_zwm_path` | Get mechanical module path |
| `get_style_path` | Get style file path |
| `get_mech_about` | Get mechanical module about info |
| `send_mech_command` | Send mechanical command |
| `open_mech_doc` | Open doc with mechanical module |
| `new_mech_doc` | New doc with mechanical module |
| `new_named_mech_doc` | New named doc with mechanical module |
| `get_application_info` | Get application info |
| `send_command` | Send command line command |
| `eval_lisp` | Evaluate LISP expression |

### System

| Tool | Description |
|------|-------------|
| `get_variable` | Get system variable value |
| `set_variable` | Set system variable value |
| `get_zcad_state` | Get app state (silent mode) |
| `get_preferences` | Get preferences summary |
| `set_preference` | Set preference |

### File I/O

| Tool | Description |
|------|-------------|
| `plot_to_file` | Plot to file |
| `export_drawing` | Export drawing (DWG/DXF/BMP/WMF etc.) |
| `import_file` | Import file |
| `attach_xref` | Attach external reference |
| `bind_xref` | Bind external reference |

### Other

| Tool | Description |
|------|-------------|
| `get_balloon` | Get balloon object |
| `cad_environment_init` | Initialize CAD environment |
| `add_hyperlink` | Add hyperlink to entity |
| `add_raster` | Add raster image |
| `purge_all` | Purge unused named objects |
| `get_intersection` | Get intersection of two entities |
| `get_object_properties` | Get object detailed properties |
| `get_object_by_handle` | Get entity info by handle |
| `get_entity_objectid` | Get entity Handle and ObjectID |
| `get_solid_properties` | Get 3D solid properties (volume/centroid) |
| `get_region_properties` | Get region properties (area/perimeter/centroid) |
| `undo_mark_start` | Start undo mark |
| `undo_mark_end` | End undo mark |
| `list_dictionaries` | List named object dictionaries |
| `add_dictionary` | Create named object dictionary |
| `add_xrecord` | Add XRecord to dictionary |
| `list_materials` | List all materials |
| `add_material` | Create new material |
| `get_summary_info` | Get document summary info |
| `set_summary_info` | Set document summary info |

## Example: Creating a Frame via AI

In Cursor / Claude Code, tell the AI:

> "Create an A3 landscape frame with GB standard, including title block and additional block"

The AI will automatically call the `create_frame` tool:

```python
create_frame(
    frame_size_name="A3",
    orientation="landscape",
    std_name="GB",
    have_btl=True,
    have_fjl=True
)
```

## Project Structure

```
zwcad-mechanical-mcp-server/
├── server.py                 # MCP Server main program (200 tools)
├── requirements.txt          # Python dependencies
├── mcp-config.json           # MCP client configuration example
├── start.bat                 # Windows one-click launcher
├── .gitignore
├── LICENSE
└── README.md
```

## Architecture

```
AI Client (Cursor/Claude/Qoder)
        │
        │ MCP Protocol (STDIO)
        ▼
   FastMCP Server
        │
        ├── pyzwcad ──────► ZWCAD COM API (basic drawing)
        │
        └── pyzwcadmech ──► ZwmToolKit COM API (mechanical features)
                                ├── ZwmApp (application)
                                ├── ZwmDb  (database)
                                ├── ZwmTitle (title block)
                                ├── ZwmBom   (BOM)
                                └── ZwmFrame (frame)
```

## Important Notes

1. **ZWCAD Must Be Running**: All tool calls require ZWCAD Mechanical to be running with a DWG file open.

2. **Style File Path**: The `create_frame` tool reads default styles from XML config files in the ZWCAD MFG installation directory: `C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles`.

## Dependencies

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD/AutoCAD Python COM wrapper
- [pyzwcadmech](https://github.com/john0909/pyzwcadmech) - ZWCAD MFG Python COM wrapper
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP protocol server framework

## License

MIT License - See [LICENSE](LICENSE)

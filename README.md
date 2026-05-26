# ZWCAD机械版 MCP Server

[中文](#zwcad-mechanical-mcp-server) | [English](#english)

---

中望机械CAD自动化 MCP 服务，让大模型MCP 协议直接操控中望机械CAD完成绘图、编辑标题栏、管理图框和明细表等操作。

## 演示视频

https://github.com/user-attachments/assets/827604ac-3e79-47f8-8655-71bd306c33cb

绘制渐开线直齿圆柱齿轮示例

https://github.com/user-attachments/assets/489ec032-c238-4d7f-8d69-bb894ef1b40b

## 功能概览

| 分类 | 工具数 | 说明 |
|------|--------|------|
| 绘图 | 2 | `draw_entity`（2D）、`draw_3d_solid`（3D）|
| 注释与标注 | 3 | `add_annotation`、`add_dimension`、`insert_block` |
| 实体操作 | 4 | `transform_entity`、`modify_entity`、`get_entity_info`、`set_entity_properties` |
| 对象查询 | 2 | `find_object`、`get_objects_in_model` |
| 样式管理 | 1 | `manage_style`（图层/线型/文字/标注样式 CRUD）|
| 视图与布局 | 2 | `manage_view`、`zoom` |
| 文档管理 | 1 | `manage_document` |
| 表格操作 | 1 | `manage_table` |
| 选择集 | 1 | `select_entities` |
| 图块管理 | 1 | `manage_block` |
| 系统工具 | 5 | `send_command`、`send_prompt`、`get_variable`、`set_variable`、`get_application_info` |
| 标题栏 | 1 | `manage_title_block` |
| 图框 | 2 | `manage_frame`、`create_frame` |
| 明细表 | 1 | `manage_bom` |
| 机械数据库 | 1 | `manage_mech_db` |
| 机械应用 | 5 | `get_mech_info`、`mech_doc`、`cad_environment_init`、`get_balloon` |

**共计 30 个工具**（由 100 个原子工具通过 dispatch 模式合并优化，减少 67% LLM 上下文占用）

## 系统要求

- **操作系统**: Windows 10/11
- **CAD 软件**: [中望机械CAD 2026](https://www.zwsoft.com/product/zwcad/mfg) 已安装并运行
- **Python**: 3.9+

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动中望机械CAD

确保中望机械CAD 2026 已启动并打开了一个 DWG 文件。

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

### 绘图工具

| 工具 | 说明 | entity_type / solid_type |
|------|------|--------------------------|
| `draw_entity` | 绘制2D实体 | `line`, `circle`, `arc`, `ellipse`, `lwpolyline`, `polyline`, `spline`, `point`, `ray`, `xline`, `mline`, `3d_polyline` |
| `draw_3d_solid` | 绘制3D实体 | `box`, `cylinder`, `cone`, `sphere`, `torus`, `wedge`, `3d_face` |

### 注释与标注

| 工具 | 说明 | annotation_type / dim_type |
|------|------|---------------------------|
| `add_annotation` | 添加注释对象 | `text`, `mtext`, `leader`, `tolerance`, `mleader`, `hatch`, `table` |
| `add_dimension` | 添加标注 | `aligned`, `rotated`, `diametric`, `radial`, `angular`, `ordinate` |
| `insert_block` | 在指定位置插入图块 | — |

### 实体操作

| 工具 | 说明 | action / entity_type |
|------|------|----------------------|
| `transform_entity` | 实体变换 | `copy`, `move`, `rotate`, `mirror`, `scale`, `delete`, `array_polar`, `array_rectangular` |
| `modify_entity` | 修改实体几何属性 | `circle`, `arc`, `line`, `text`, `mtext`, `polyline`, `spline`, `offset`, `explode` |
| `get_entity_info` | 获取实体详细信息 | — |
| `set_entity_properties` | 设置实体通用属性（图层/颜色/线型等） | — |

### 对象查询

| 工具 | 说明 |
|------|------|
| `find_object` | 按类型/属性/句柄查找对象 |
| `get_objects_in_model` | 获取模型空间对象列表 |

### 样式管理

| 工具 | 说明 | style_type × action |
|------|------|---------------------|
| `manage_style` | 图层/线型/文字/标注样式 CRUD | style_type: `layer`, `linetype`, `textstyle`, `dimstyle`; action: `list`, `add`, `set_active`, `set_properties` |

### 视图、布局与缩放

| 工具 | 说明 | action / mode |
|------|------|---------------|
| `manage_view` | 布局/视图管理 | `list_layouts`, `get_active_layout`, `add_layout`, `set_active_layout`, `list_views`, `add_view` |
| `zoom` | 视图缩放 | `extents`, `all`, `window`, `center`, `scale`, `previous` |

### 文档管理

| 工具 | 说明 | action |
|------|------|--------|
| `manage_document` | 文档新建/保存/关闭/导入/导出 | `new`, `save`, `close`, `info`, `list`, `activate`, `export`, `import`, `plot` |

### 表格操作

| 工具 | 说明 | action |
|------|------|--------|
| `manage_table` | CAD表格对象操作 | `set_cell`, `get_cell`, `insert_rows`, `delete_rows`, `set_column_width`, `set_row_height`, `merge_cells` |

### 选择集

| 工具 | 说明 | action |
|------|------|--------|
| `select_entities` | 选择集操作 | `select`, `on_screen`, `by_polygon`, `clear` |

### 图块管理

| 工具 | 说明 | action |
|------|------|--------|
| `manage_block` | 图块定义/信息/属性管理 | `list`, `info`, `create`, `get_attributes` |

### 系统工具

| 工具 | 说明 |
|------|------|
| `send_command` | 发送命令行命令（通用万能接口，低频操作均可通过此工具实现） |
| `send_prompt` | 在命令行显示提示文本 |
| `get_variable` | 获取系统变量值 |
| `set_variable` | 设置系统变量值 |
| `get_application_info` | 获取应用程序信息 |

### 标题栏操作

| 工具 | 说明 | action |
|------|------|--------|
| `manage_title_block` | 标题栏读取/设置/批量更新 | `get_info`, `set_field`, `update_batch`, `get_field_count`, `get_field_by_index` |

### 图框操作

| 工具 | 说明 | action |
|------|------|--------|
| `manage_frame` | 图框查询/切换/更新/刷新 | `list`, `get_info`, `get_count`, `get_name_by_index`, `get_name_by_point`, `get_next_name`, `switch`, `update`, `refresh` |
| `create_frame` | 新建图幅（自动读取 XML 默认样式配置） | — |

### 明细表（BOM）操作

| 工具 | 说明 | action |
|------|------|--------|
| `manage_bom` | 明细表增删改查 | `get_row_count`, `get_row`, `add_row`, `update_row`, `insert_row`, `delete_row`, `set_field`, `get_field`, `get_field_count`, `refresh` |

### 机械数据库

| 工具 | 说明 | action |
|------|------|--------|
| `manage_mech_db` | 机械模块数据库操作 | `open`, `save`, `close` |

### 机械应用

| 工具 | 说明 |
|------|------|
| `get_mech_info` | 获取机械模块信息（info_type: `version`, `cad_path`, `zwm_path`, `style_path`, `about`） |
| `mech_doc` | 机械文档操作（action: `open`, `new`, `new_named`） |
| `cad_environment_init` | 初始化CAD环境标准 |
| `get_balloon` | 获取球标对象 |


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
├── server.py                 # MCP Server 主程序（33个合并工具）
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
   FastMCP Server (33 tools, dispatch pattern)
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

create 3d solid
https://github.com/user-attachments/assets/489ec032-c238-4d7f-8d69-bb894ef1b40b

## Feature Overview

| Category | Tools | Description |
|----------|-------|-------------|
| Drawing | 2 | `draw_entity` (2D), `draw_3d_solid` (3D) |
| Annotation & Dimension | 3 | `add_annotation`, `add_dimension`, `insert_block` |
| Entity Operation | 4 | `transform_entity`, `modify_entity`, `get_entity_info`, `set_entity_properties` |
| Object Query | 2 | `find_object`, `get_objects_in_model` |
| Style Management | 1 | `manage_style` (layer/linetype/textstyle/dimstyle CRUD) |
| View & Layout | 2 | `manage_view`, `zoom` |
| Document Management | 1 | `manage_document` |
| Table | 1 | `manage_table` |
| Selection Set | 1 | `select_entities` |
| Block Management | 1 | `manage_block` |
| System | 5 | `send_command`, `send_prompt`, `get_variable`, `set_variable`, `get_application_info` |
| Title Block | 1 | `manage_title_block` |
| Frame | 2 | `manage_frame`, `create_frame` |
| BOM | 1 | `manage_bom` |
| Mech Database | 1 | `manage_mech_db` |
| Mech Application | 5 | `get_mech_info`,  `mech_doc`, `cad_environment_init`, `get_balloon` |

**Total: 30 tools** (consolidated from 100 atomic tools via dispatch pattern, reducing LLM context usage by 67%)

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

### Drawing

| Tool | Description | entity_type / solid_type |
|------|-------------|--------------------------|
| `draw_entity` | Draw 2D entity | `line`, `circle`, `arc`, `ellipse`, `lwpolyline`, `polyline`, `spline`, `point`, `ray`, `xline`, `mline`, `3d_polyline` |
| `draw_3d_solid` | Draw 3D solid | `box`, `cylinder`, `cone`, `sphere`, `torus`, `wedge`, `3d_face` |

### Annotation & Dimension

| Tool | Description | Type parameter |
|------|-------------|----------------|
| `add_annotation` | Add annotation objects | `text`, `mtext`, `leader`, `tolerance`, `mleader`, `hatch`, `table` |
| `add_dimension` | Add dimensions | `aligned`, `rotated`, `diametric`, `radial`, `angular`, `ordinate` |
| `insert_block` | Insert block reference | — |

### Entity Operations

| Tool | Description | action / entity_type |
|------|-------------|----------------------|
| `transform_entity` | Transform entity | `copy`, `move`, `rotate`, `mirror`, `scale`, `delete`, `array_polar`, `array_rectangular` |
| `modify_entity` | Modify entity geometry | `circle`, `arc`, `line`, `text`, `mtext`, `polyline`, `spline`, `offset`, `explode` |
| `get_entity_info` | Get entity details (properties, geometry, bounding box) | — |
| `set_entity_properties` | Set entity properties (layer/color/linetype etc.) | — |

### Object Query

| Tool | Description |
|------|-------------|
| `find_object` | Find object by type/property/handle |
| `get_objects_in_model` | List model space objects |

### Style Management

| Tool | Description | Parameters |
|------|-------------|------------|
| `manage_style` | Layer/linetype/text style/dim style CRUD | style_type: `layer`\|`linetype`\|`textstyle`\|`dimstyle`; action: `list`\|`add`\|`set_active`\|`set_properties` |

### View, Layout & Zoom

| Tool | Description | action / mode |
|------|-------------|---------------|
| `manage_view` | Layout and view management | `list_layouts`, `get_active_layout`, `add_layout`, `set_active_layout`, `list_views`, `add_view` |
| `zoom` | View zoom control | `extents`, `all`, `window`, `center`, `scale`, `previous` |

### Document Management

| Tool | Description | action |
|------|-------------|--------|
| `manage_document` | Document new/save/close/import/export | `new`, `save`, `close`, `info`, `list`, `activate`, `export`, `import`, `plot` |

### Table, Selection, Block

| Tool | Description |
|------|-------------|
| `manage_table` | Table cell/row/column operations |
| `select_entities` | Selection set operations |
| `manage_block` | Block definition/info/attributes management |

### System

| Tool | Description |
|------|-------------|
| `send_command` | Send command string to ZWCAD (universal fallback for any operation) |
| `send_prompt` | Display text in ZWCAD command line |
| `get_variable` / `set_variable` | Read/write system variables |
| `get_application_info` | Get ZWCAD version, path, window info |

### Title Block

| Tool | Description | action |
|------|-------------|--------|
| `manage_title_block` | Title block read/set/batch update | `get_info`, `set_field`, `update_batch`, `get_field_count`, `get_field_by_index` |

### Frame

| Tool | Description |
|------|-------------|
| `manage_frame` | Frame query/switch/update/refresh (actions: `list`, `get_info`, `switch`, `update`, `refresh`, etc.) |
| `create_frame` | Create a new frame (auto-reads XML default style config) |

### BOM (Bill of Materials)

| Tool | Description | action |
|------|-------------|--------|
| `manage_bom` | BOM CRUD operations | `get_row_count`, `get_row`, `add_row`, `update_row`, `insert_row`, `delete_row`, `set_field`, `get_field`, `refresh` |

### Mechanical Module

| Tool | Description |
|------|-------------|
| `manage_mech_db` | Mechanical database open/save/close |
| `get_mech_info` | Get mech module info (version, paths, about) |
| `mech_doc` | Mechanical document open/new operations |
| `cad_environment_init` | Initialize CAD standard environment |
| `get_balloon` | Get balloon object for part numbering |

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
├── server.py                 # MCP Server main program (33 consolidated tools)
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
   FastMCP Server (33 tools, dispatch pattern)
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







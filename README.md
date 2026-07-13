﻿# ZWCAD机械版 MCP Server

[中文](#zwcad-mechanical-mcp-server) | [English](#english)

---

中望机械CAD自动化 MCP 服务，让大模型通过 MCP 协议直接操控中望机械CAD完成绘图、编辑标题栏、管理图框和明细表等操作。

## 演示视频

https://github.com/user-attachments/assets/827604ac-3e79-47f8-8655-71bd306c33cb

绘制渐开线直齿圆柱齿轮示例

https://github.com/user-attachments/assets/489ec032-c238-4d7f-8d69-bb894ef1b40b

## 功能概览

| 分类 | 工具数 | 说明 |
|------|--------|------|
| 绘图 | 3 | `draw_entity`（2D）、`draw_batch`（批量）、`draw_3d_solid`（3D）|
| 注释与标注 | 3 | `add_annotation`、`add_dimension`、`insert_block` |
| 实体操作 | 4 | `transform_entity`、`modify_entity`、`get_entity_info`、`set_entity_properties` |
| 对象查询 | 2 | `find_object`、`get_objects_in_model` |
| 样式管理 | 1 | `manage_style`（图层/线型/文字/标注样式 CRUD）|
| 视图与布局 | 2 | `manage_view`、`zoom` |
| 文档管理 | 1 | `manage_document` |
| 表格操作 | 1 | `manage_table` |
| 选择集 | 1 | `select_entities` |
| 图块管理 | 1 | `manage_block` |
| 系统工具 | 3 | `get_variable`、`set_variable`、`get_app_info` |
| 诊断工具 | 1 | `mech_diagnose`（机械模块连接与类型库诊断）|
| 标题栏 | 1 | `manage_title_block` |
| 图框 | 2 | `manage_frame`、`create_frame` |
| 明细表 | 1 | `manage_bom` |
| 机械数据库 | 1 | `manage_mech_db` |
| 机械应用 | 3 | `mech_doc`、`cad_environment_init`、`get_balloon` |
| 扩展数据 | 3 | `manage_dictionary`、`manage_xdata`、`manage_utility` |

**共计 34 个工具**

## 系统要求

- **操作系统**: Windows 10/11
- **CAD 软件**: [中望机械CAD 2026](https://www.zwsoft.com/product/zwcad/mfg) 已安装并运行
- **Python**: 3.9+

## 快速开始

最简单的安装MCP方法：打开Agent，在里面输入:安装上此MCP服务: https://github.com/john0909/ZWCAD-Mechanical-MCP

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
| `draw_batch` | 批量绘制多种实体 | 支持上述2D实体与3D实体的混合批量绘制 |
| `draw_3d_solid` | 绘制3D实体 | `box`, `cylinder`, `cone`, `sphere`, `torus`, `wedge`, `3d_face` |

### 注释与标注

| 工具 | 说明 | annotation_type / dim_type |
|------|------|---------------------------|
| `add_annotation` | 添加注释对象 | `text`, `mtext`, `leader`, `tolerance`, `mleader`, `hatch`, `table` |
| `add_dimension` | 添加标注 | `aligned`, `rotated`, `diametric`, `radial`, `angular`, `ordinate` |
| `insert_block` | 在指定位置插入图块 | - |

### 实体操作

| 工具 | 说明 | action / entity_type |
|------|------|----------------------|
| `transform_entity` | 实体变换 | `copy`, `move`, `rotate`, `mirror`, `scale`, `delete`, `array_polar`, `array_rectangular` |
| `modify_entity` | 修改实体几何属性 | `circle`, `arc`, `line`, `text`, `mtext`, `polyline`, `spline`, `offset`, `explode` |
| `get_entity_info` | 获取实体详细信息 | - |
| `set_entity_properties` | 设置实体通用属性（图层/颜色/线型等） | - |

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
| `manage_document` | 文档新建/保存/关闭/导入/导出/打印 | `new`, `save`, `close`, `info`, `list`, `activate`, `export`, `import`, `plot` |

### 表格、选择集与图块

| 工具 | 说明 |
|------|------|
| `manage_table` | 表格单元格/行/列操作 |
| `select_entities` | 选择集操作（窗口/交叉/多边形/过滤器选择） |
| `manage_block` | 图块定义/信息/属性管理 |

### 系统工具

| 工具 | 说明 |
|------|------|
| `get_variable` / `set_variable` | 读写系统变量 |
| `get_app_info` | 获取应用信息。scope: `cad`（ZWCAD版本/路径）、`mech_version`、`mech_cad_path`、`mech_zwm_path`、`mech_style_path`、`mech_about` |

### 诊断工具

| 工具 | 说明 |
|------|------|
| `mech_diagnose` | 诊断机械模块连接与 ZwmToolKit 类型库加载状态。逐项探测：类型库加载、ZWCAD 应用、ZwmApp、ZwmDb、标题栏获取，返回各探测项状态与修复建议。每次调用自动重置连接缓存以获取最新状态。 |

### 标题栏

| 工具 | 说明 | action |
|------|------|--------|
| `manage_title_block` | 标题栏读取/设置/批量更新 | `get_info`, `set_field`, `update_batch`, `get_field_count`, `get_field_by_index` |

> ⚠️ 此工具依赖 ZwmToolKit 类型库，类型库未加载时将快速返回 `TYPELIB_NOT_LOADED` 错误。

### 图框

| 工具 | 说明 | action |
|------|------|--------|
| `manage_frame` | 图框查询/切换/更新/刷新 | `list`, `get_info`, `get_count`, `get_name_by_index`, `get_name_by_point`, `get_next_name`, `switch`, `update`, `refresh` |
| `create_frame` | 新建图框（自动从XML配置读取默认样式） | - |

> ⚠️ `create_frame` 以及 `manage_frame` 的 `get_info`/`update` 操作依赖类型库。`list`/`get_count`/`switch`/`refresh` 等操作不依赖类型库，在类型库未加载时仍可使用。

### 明细表（BOM）

| 工具 | 说明 | action |
|------|------|--------|
| `manage_bom` | 明细表增删改查 | `get_row_count`, `get_row`, `add_row`, `update_row`, `insert_row`, `delete_row`, `set_field`, `get_field`, `get_field_count`, `refresh` |

> ⚠️ 除 `refresh` 外的所有操作依赖类型库。`refresh` 不依赖类型库，在类型库未加载时仍可使用。

### 机械模块

| 工具 | 说明 |
|------|------|
| `manage_mech_db` | 机械数据库操作。action: `open`/`save`/`close` |
| `mech_doc` | 机械文档操作。action: `open`/`new`/`new_named` |
| `cad_environment_init` | 初始化CAD标准环境（GB, ISO, DIN等） |
| `get_balloon` | 获取球标对象用于零件编号标注 |

> 以上工具不依赖类型库，在类型库未加载时仍可通过 late binding 正常工作。

### 扩展数据

| 工具 | 说明 | action |
|------|------|--------|
| `manage_dictionary` | 命名对象字典与XRecord管理 | `list`, `add`, `get_items`, `add_object`, `get_object`, `remove`, `rename` |
| `manage_xdata` | 实体扩展数据(XData)读写 | `get`, `set`, `list_apps`, `add_app` |
| `manage_utility` | CAD工具方法（坐标转换/距离/角度计算/关键字输入等） | `distance`, `angle`, `polar`, `translate_coords`, `get_real`, `get_keyword` |

## ZwmToolKit 类型库加载机制

机械模块（标题栏/明细表/图框等）依赖 `ZwmToolKit.tlb` 类型库。`pyzwcadmech.api` 采用 **5 级回退策略** 加载类型库，确保在各种安装环境下都能成功加载：

| 优先级 | 策略 | 说明 |
|--------|------|------|
| 1 | 文件系统 glob | 在 `C:\Program Files\ZWSOFT\ZWCAD Mechanical*\Zwcadm\` 下搜索 `ZwmToolKit*.tlb`，按版本年份排序优先选最新 |
| 2 | 环境变量 | 读取 `PYZWCADMECH_TLB_PATH` 环境变量指向的 `.tlb` 文件 |
| 3 | 本地路径 | 搜索当前工作目录和包目录下的 `ZwmToolKit.tlb` |
| 4 | 预生成模块 | 复用已生成的 `comtypes.gen.ZwmToolKitLib` 模块（如 server.py 预加载生成的） |
| 5 | GUID 注册表 | 按类型库 GUID `{2F671C10-669F-11E7-91B7-BC5FF42AC839}` 从 Windows 注册表加载 |

### server.py 预加载

`server.py` 在导入 `pyzwcadmech` 之前，会先按 GUID 预加载类型库，提前生成 `comtypes.gen.ZwmToolKitLib` 模块。即使后续 `pyzwcadmech.api` 的文件搜索失败，也能通过策略 4 复用该预生成模块。

### 运行时重试

如果类型库在 import 时加载失败（例如 ZWCAD 尚未启动），`ZwCADMech.zwm_app` 属性在首次访问时会自动调用 `reload_typelib()` 重试加载。也可通过 `mech_diagnose` 工具触发重新诊断。

### 环境变量配置

如果类型库无法自动加载（如自定义安装路径），可设置环境变量：

```json
{
  "mcpServers": {
    "zwcadmech": {
      "command": "python",
      "args": ["server.py"],
      "env": {
        "PYZWCADMECH_TLB_PATH": "C:\\Program Files\\ZWSOFT\\ZWCAD Mechanical 2026 Chs\\Zwcadm\\ZwmToolKit.tlb"
      }
    }
  }
}
```

### 类型库依赖矩阵

| 工具 | 类型库未加载时 | 说明 |
|------|--------------|------|
| `manage_title_block` | ❌ 不可用 | 返回 `TYPELIB_NOT_LOADED` 错误 |
| `create_frame` | ❌ 不可用 | 返回 `TYPELIB_NOT_LOADED` 错误 |
| `manage_bom`（除 refresh） | ❌ 不可用 | 返回错误并附带修复提示 |
| `manage_frame`（get_info/update） | ❌ 不可用 | 返回错误并附带修复提示 |
| `manage_bom`（refresh） | ✅ 可用 | 通过 late binding 工作 |
| `manage_frame`（list/switch/refresh 等） | ✅ 可用 | 通过 late binding 工作 |
| `manage_mech_db` / `mech_doc` / `cad_environment_init` / `get_balloon` | ✅ 可用 | 通过 late binding 工作 |
| `get_app_info`（mech_* scope） | ✅ 可用 | 通过 late binding 工作 |
| 所有 pyzwcad 基础工具（绘图/标注/变换/查询等） | ✅ 可用 | 完全不依赖类型库 |

## 示例：通过 AI 创建图框

在 Cursor / Claude Code 中，告诉 AI：

> "创建一个A3横向图框，GB标准，包含标题栏和附加栏"

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
├── server.py                 # MCP Server 主程序（34个工具）
├── requirements.txt          # Python 依赖
├── mcp-config.json           # MCP 客户端配置示例
├── start.bat                 # Windows 一键启动脚本
├── install.cmd               # 安装脚本
├── .gitignore
├── LICENSE
└── README.md
```

## 架构

```
AI Client (Cursor/Claude/Qoder)
        │
        │ MCP Protocol (STDIO)
        ▼
   FastMCP Server (server.py, 34 tools)
        │
        ├── pyzwcad ──────► ZWCAD.Application COM API (基础绘图/标注/变换/查询)
        │                   └── 不依赖类型库，始终可用
        │
        └── pyzwcadmech ──► ZwmToolKit COM API (机械功能)
                │
                ├── 类型库加载 (5级回退策略)
                │   ├── 1. 文件 glob (版本感知排序)
                │   ├── 2. PYZWCADMECH_TLB_PATH 环境变量
                │   ├── 3. 本地路径
                │   ├── 4. 预生成 comtypes.gen 模块
                │   └── 5. GUID 注册表加载
                │
                ├── ZwmApp ──── 应用层 (版本/路径/文档操作) ── 不依赖类型库
                ├── ZwmDb ──── 数据库层 (打开/保存/图框管理)
                │   ├── open_file/save/close/switch_frame ── 不依赖类型库
                │   ├── get_title() ──► ZwmTitle ── 依赖类型库
                │   ├── get_bom() ────► ZwmBom ─── 依赖类型库
                │   └── get_frame() ──► ZwmFrame ─ 依赖类型库
                │
                └── 运行时重试: zwm_app 属性在 ZWM=None 时自动调用 reload_typelib()

   连接缓存: get_cad_connection() 缓存 (ZwCAD, ZwCADMech) 实例
   诊断工具: mech_diagnose() 每次调用自动重置连接缓存，逐项探测
```

## 重要说明

1. **ZWCAD 必须运行**：所有工具调用都要求中望机械CAD 已启动并打开了 DWG 文件。

2. **样式文件路径**：`create_frame` 工具从 XML 配置文件读取默认样式：`C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles`

3. **类型库加载**：机械模块（标题栏/明细表/图框）依赖 ZwmToolKit 类型库。正常安装环境下会自动加载；如遇加载失败，可使用 `mech_diagnose` 工具诊断，或设置 `PYZWCADMECH_TLB_PATH` 环境变量指向 `ZwmToolKit.tlb` 文件。

4. **连接缓存**：MCP Server 会缓存 CAD 连接实例以提高性能。`mech_diagnose` 工具每次调用会自动重置缓存以获取最新状态。

## 依赖

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD/AutoCAD Python COM 封装
- [pyzwcadmech](https://github.com/john0909/pyzwcadmech) - 中望机械 Python COM 封装
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP 协议服务框架
- [comtypes](https://github.com/enthought/comtypes) - COM 类型库加载与接口调用
- [pywin32](https://github.com/mhammond/pywin32) - Windows COM 初始化支持

## License

MIT License - See [LICENSE](LICENSE)

---

# English

# ZWCAD Mechanical MCP Server

A ZWCAD Mechanical CAD automation MCP service that allows AI models to directly control ZWCAD Mechanical via the MCP protocol for drawing, title block editing, frame management, BOM operations, and more.

## Feature Overview

| Category | Tools | Description |
|----------|-------|-------------|
| Drawing | 3 | `draw_entity` (2D), `draw_batch` (batch), `draw_3d_solid` (3D) |
| Annotation | 3 | `add_annotation`, `add_dimension`, `insert_block` |
| Entity Ops | 4 | `transform_entity`, `modify_entity`, `get_entity_info`, `set_entity_properties` |
| Object Query | 2 | `find_object`, `get_objects_in_model` |
| Style Mgmt | 1 | `manage_style` (layer/linetype/text/dim style CRUD) |
| View & Layout | 2 | `manage_view`, `zoom` |
| Document | 1 | `manage_document` |
| Table | 1 | `manage_table` |
| Selection | 1 | `select_entities` |
| Block | 1 | `manage_block` |
| System | 3 | `get_variable`, `set_variable`, `get_app_info` |
| Diagnostics | 1 | `mech_diagnose` (mechanical module & typelib diagnostics) |
| Title Block | 1 | `manage_title_block` |
| Frame | 2 | `manage_frame`, `create_frame` |
| BOM | 1 | `manage_bom` |
| Mech Database | 1 | `manage_mech_db` |
| Mech App | 3 | `mech_doc`, `cad_environment_init`, `get_balloon` |
| Extended Data | 3 | `manage_dictionary`, `manage_xdata`, `manage_utility` |

**Total: 34 tools**

## System Requirements

- **OS**: Windows 10/11
- **CAD Software**: [ZWCAD Mechanical 2026](https://www.zwsoft.com/product/zwcad/mfg) installed and running
- **Python**: 3.9+

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start ZWCAD Mechanical

Ensure ZWCAD Mechanical 2026 is running with a DWG file open.

### 3. Start MCP Server

```bash
python server.py
```

Or use the launcher:

```bash
start.bat
```

### 4. Configure MCP Client

#### Cursor

Create `.cursor/mcp.json` in the project root:

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
| `draw_entity` | Draw 2D entities | `line`, `circle`, `arc`, `ellipse`, `lwpolyline`, `polyline`, `spline`, `point`, `ray`, `xline`, `mline`, `3d_polyline` |
| `draw_batch` | Batch draw multiple entity types | Supports mixed 2D and 3D entities |
| `draw_3d_solid` | Draw 3D solids | `box`, `cylinder`, `cone`, `sphere`, `torus`, `wedge`, `3d_face` |

### Annotation & Dimension

| Tool | Description | type |
|------|-------------|------|
| `add_annotation` | Add annotation objects | `text`, `mtext`, `leader`, `tolerance`, `mleader`, `hatch`, `table` |
| `add_dimension` | Add dimensions | `aligned`, `rotated`, `diametric`, `radial`, `angular`, `ordinate` |
| `insert_block` | Insert block at specified position | - |

### Entity Operations

| Tool | Description | action / entity_type |
|------|-------------|----------------------|
| `transform_entity` | Entity transform | `copy`, `move`, `rotate`, `mirror`, `scale`, `delete`, `array_polar`, `array_rectangular` |
| `modify_entity` | Modify entity geometry | `circle`, `arc`, `line`, `text`, `mtext`, `polyline`, `spline`, `offset`, `explode` |
| `get_entity_info` | Get entity details (properties, geometry, bounding box) | - |
| `set_entity_properties` | Set entity properties (layer/color/linetype etc.) | - |

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
| `select_entities` | Selection set operations (window/crossing/polygon/filter) |
| `manage_block` | Block definition/info/attributes management |

### System

| Tool | Description |
|------|-------------|
| `get_variable` / `set_variable` | Read/write system variables |
| `get_app_info` | Get app info. scope: `cad` (version/path), `mech_version`, `mech_cad_path`, `mech_zwm_path`, `mech_style_path`, `mech_about` |

### Diagnostics

| Tool | Description |
|------|-------------|
| `mech_diagnose` | Diagnose mechanical module connection and ZwmToolKit type library loading status. Probes: typelib loading, ZWCAD app, ZwmApp, ZwmDb, title block retrieval. Auto-resets connection cache on each call. |

### Title Block

| Tool | Description | action |
|------|-------------|--------|
| `manage_title_block` | Title block read/set/batch update | `get_info`, `set_field`, `update_batch`, `get_field_count`, `get_field_by_index` |

> ⚠️ Requires ZwmToolKit type library. Returns `TYPELIB_NOT_LOADED` error if not loaded.

### Frame

| Tool | Description | action |
|------|-------------|--------|
| `manage_frame` | Frame query/switch/update/refresh | `list`, `get_info`, `get_count`, `get_name_by_index`, `get_name_by_point`, `get_next_name`, `switch`, `update`, `refresh` |
| `create_frame` | Create a new frame (auto-reads XML default style config) | - |

> ⚠️ `create_frame` and `manage_frame` `get_info`/`update` require type library. `list`/`get_count`/`switch`/`refresh` work without it.

### BOM (Bill of Materials)

| Tool | Description | action |
|------|-------------|--------|
| `manage_bom` | BOM CRUD operations | `get_row_count`, `get_row`, `add_row`, `update_row`, `insert_row`, `delete_row`, `set_field`, `get_field`, `get_field_count`, `refresh` |

> ⚠️ All actions except `refresh` require type library. `refresh` works without it.

### Mechanical Module

| Tool | Description |
|------|-------------|
| `manage_mech_db` | Mechanical database operations. action: `open`/`save`/`close` |
| `mech_doc` | Mechanical document operations. action: `open`/`new`/`new_named` |
| `cad_environment_init` | Initialize CAD standard environment (GB, ISO, DIN, etc.) |
| `get_balloon` | Get balloon object for part numbering |

> These tools work without type library via late binding.

### Extended Data

| Tool | Description | action |
|------|-------------|--------|
| `manage_dictionary` | Named object dictionary & XRecord management | `list`, `add`, `get_items`, `add_object`, `get_object`, `remove`, `rename` |
| `manage_xdata` | Entity extended data (XData) read/write | `get`, `set`, `list_apps`, `add_app` |
| `manage_utility` | CAD utility methods (coordinate conversion/distance/angle/keyword input) | `distance`, `angle`, `polar`, `translate_coords`, `get_real`, `get_keyword` |

## ZwmToolKit Type Library Loading

The mechanical module (title block / BOM / frame) depends on the `ZwmToolKit.tlb` type library. `pyzwcadmech.api` uses a **5-strategy fallback** to load it:

| Priority | Strategy | Description |
|----------|----------|-------------|
| 1 | File glob | Search `ZwmToolKit*.tlb` in `C:\Program Files\ZWSOFT\ZWCAD Mechanical*\Zwcadm\`, sort by version year (newest first) |
| 2 | Env variable | Read `PYZWCADMECH_TLB_PATH` environment variable |
| 3 | Local path | Search current working directory and package directory |
| 4 | Pre-generated module | Reuse existing `comtypes.gen.ZwmToolKitLib` module |
| 5 | GUID registry | Load by type library GUID from Windows registry |

### Runtime Retry

If the type library fails to load at import time (e.g., ZWCAD not yet started), the `ZwCADMech.zwm_app` property automatically calls `reload_typelib()` on first access. The `mech_diagnose` tool can also trigger re-diagnosis.

### Environment Variable

If automatic loading fails (e.g., custom install path), set the environment variable:

```json
{
  "mcpServers": {
    "zwcadmech": {
      "command": "python",
      "args": ["server.py"],
      "env": {
        "PYZWCADMECH_TLB_PATH": "C:\\Program Files\\ZWSOFT\\ZWCAD Mechanical 2026 Chs\\Zwcadm\\ZwmToolKit.tlb"
      }
    }
  }
}
```

### Type Library Dependency Matrix

| Tool | When type library not loaded | Notes |
|------|------------------------------|-------|
| `manage_title_block` | ❌ Unavailable | Returns `TYPELIB_NOT_LOADED` error |
| `create_frame` | ❌ Unavailable | Returns `TYPELIB_NOT_LOADED` error |
| `manage_bom` (except refresh) | ❌ Unavailable | Returns error with fix hint |
| `manage_frame` (get_info/update) | ❌ Unavailable | Returns error with fix hint |
| `manage_bom` (refresh) | ✅ Available | Works via late binding |
| `manage_frame` (list/switch/refresh etc.) | ✅ Available | Works via late binding |
| `manage_mech_db` / `mech_doc` / `cad_environment_init` / `get_balloon` | ✅ Available | Works via late binding |
| `get_app_info` (mech_* scope) | ✅ Available | Works via late binding |
| All pyzwcad basic tools (drawing/annotation/transform/query etc.) | ✅ Available | No type library dependency |

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
├── server.py                 # MCP Server main program (34 tools)
├── requirements.txt          # Python dependencies
├── mcp-config.json           # MCP client configuration example
├── start.bat                 # Windows one-click launcher
├── install.cmd               # Installation script
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
   FastMCP Server (server.py, 34 tools)
        │
        ├── pyzwcad ──────► ZWCAD.Application COM API (basic drawing)
        │                   └── No type library dependency, always available
        │
        └── pyzwcadmech ──► ZwmToolKit COM API (mechanical features)
                │
                ├── Type library loading (5-strategy fallback)
                │   ├── 1. File glob (version-aware sorting)
                │   ├── 2. PYZWCADMECH_TLB_PATH env variable
                │   ├── 3. Local path
                │   ├── 4. Pre-generated comtypes.gen module
                │   └── 5. GUID registry loading
                │
                ├── ZwmApp ──── Application layer ── No type library dependency
                ├── ZwmDb ──── Database layer
                │   ├── open_file/save/close/switch_frame ── No dependency
                │   ├── get_title() ──► ZwmTitle ── Requires type library
                │   ├── get_bom() ────► ZwmBom ─── Requires type library
                │   └── get_frame() ──► ZwmFrame ─ Requires type library
                │
                └── Runtime retry: zwm_app auto-calls reload_typelib() when ZWM=None

   Connection cache: get_cad_connection() caches (ZwCAD, ZwCADMech) instances
   Diagnostics: mech_diagnose() auto-resets cache, probes each component
```

## Important Notes

1. **ZWCAD Must Be Running**: All tool calls require ZWCAD Mechanical to be running with a DWG file open.

2. **Style File Path**: The `create_frame` tool reads default styles from XML config files: `C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles`

3. **Type Library Loading**: The mechanical module (title block / BOM / frame) depends on the ZwmToolKit type library. It loads automatically in normal installations. If loading fails, use the `mech_diagnose` tool to diagnose, or set the `PYZWCADMECH_TLB_PATH` environment variable to point to `ZwmToolKit.tlb`.

4. **Connection Cache**: The MCP Server caches CAD connection instances for performance. The `mech_diagnose` tool automatically resets the cache on each call for fresh diagnostics.

## Dependencies

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD/AutoCAD Python COM wrapper
- [pyzwcadmech](https://github.com/john0909/pyzwcadmech) - ZWCAD MFG Python COM wrapper
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP protocol server framework
- [comtypes](https://github.com/enthought/comtypes) - COM type library loading and interface invocation
- [pywin32](https://github.com/mhammond/pywin32) - Windows COM initialization support

## License

MIT License - See [LICENSE](LICENSE)

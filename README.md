# ZWCAD MFG MCP Server

[中文](#zwcad-mechanical-mcp-server) | [English](#english)

---

基于 [FastMCP](https://github.com/jlowin/fastmcp) 框架的中望机械CAD自动化 MCP 服务，让 AI 模型（如 DeepSeek, Qwen,GLM,Kimi等）可以通过 MCP 协议直接操控中望机械CAD完成绘图、编辑标题栏、管理图框和明细表等操作。

## 功能概览

| 分类 | 工具数 | 说明 |
|------|--------|------|
| 基础绘图 | 5 | 画直线、画圆、添加文本、保存图纸、新建图纸 |
| 文档与布局 | 6 | 获取文档信息、布局列表、模型对象、查找对象等 |
| 标题栏操作 | 5 | 读取/修改/批量修改标题栏字段 |
| 图框操作 | 10 | 获取图框信息、切换/创建/刷新图框等 |
| 明细表操作 | 10 | 增删改查明细表行及字段 |
| 数据库操作 | 3 | 打开/保存/关闭机械模块数据 |
| 编辑操作 | 5 | 图框/标题栏/参数表/附加栏/汇总明细表编辑 |
| 应用程序操作 | 9 | 版本信息、路径查询、命令发送、文档操作 |
| 其他 | 2 | 球标、环境初始化 |

**共计 55 个工具**

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
| `add_text` | 添加文本 | 文本内容, 位置, 字高 |
| `save_drawing` | 保存图纸 | 文件路径 |
| `new_drawing` | 新建图纸 | - |

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
├── server.py                 # MCP Server 主程序（55个工具）
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

##演示视频
https://github.com/john0909/ZWCAD-Mechanical-MCP/blob/main/ZWCADMechMCPSample.mp4

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

## Feature Overview

| Category | Tools | Description |
|----------|-------|-------------|
| Basic Drawing | 5 | Line, circle, text, save, new drawing |
| Document & Layout | 6 | Document info, layouts, model objects, find, prompt |
| Title Block | 5 | Read/modify/batch update title block fields |
| Frame | 10 | Frame info, switch/create/refresh frames |
| BOM (Bill of Materials) | 10 | CRUD operations on BOM rows and fields |
| Database | 3 | Open/save/close mechanical data |
| Edit Operations | 5 | Frame/title/CSL/FJL/total BOM editing dialogs |
| Application | 9 | Version, paths, commands, document operations |
| Other | 2 | Balloon, environment init |

**Total: 55 tools**

## Requirements

- **OS**: Windows 10/11
- **CAD Software**: [ZWCAD Mechanical 2027](https://www.zwsoft.com/product/zwcad/mfg) installed and running
- **Python**: 3.9+

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Launch ZWCAD Mechanical

Make sure ZWCAD Mechanical 2027 is running with a DWG file open.

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
| `draw_circle` | Draw a circle | Center coordinates, radius, layer |
| `add_text` | Add text | Text content, position, height |
| `save_drawing` | Save drawing | File path |
| `new_drawing` | New drawing | - |

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
├── server.py                 # MCP Server main program (55 tools)
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

1. **COM Threading**: The server initializes STA (Single-Threaded Apartment) model at startup for ZWCAD COM compatibility. Do not remove the `pythoncom.CoInitializeEx` call.

2. **stdout Pollution**: The MCP STDIO transport requires stdout for JSON-RPC messages only. All logging is redirected to stderr. Never use `print()` to write to stdout.

3. **ZWCAD MFG Must Be Running**: All tool calls require ZWCAD MFG to be running with a DWG file open.

4. **Style File Path**: The `create_frame` tool reads default styles from XML config files in the ZWCAD MFG installation directory: `C:\Users\Public\Documents\ZWSoft\zwcadm\2026\zh-CN\styles`.

## Dependencies

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD/AutoCAD Python COM wrapper
- [pyzwcadmech](https://github.com/john0909/pyzwcadmech) - ZWCAD MFG Python COM wrapper
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP protocol server framework

## License

MIT License - See [LICENSE](LICENSE)

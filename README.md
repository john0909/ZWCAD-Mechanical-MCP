# ZWCAD机械版 MCP Server

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
| 对象查询 | 3 | `find_object`、`get_objects_in_model`、`query_dimensions` |
| 样式管理 | 1 | `manage_style`（图层/线型/文字/标注样式 CRUD）|
| 视图与布局 | 2 | `manage_view`、`zoom` |
| 文档管理 | 1 | `manage_document` |
| 表格操作 | 1 | `manage_table` |
| 选择集 | 1 | `select_entities` |
| 图块管理 | 1 | `manage_block` |
| 系统工具 | 3 | `get_variable`、`set_variable`、`get_app_info` |
| 诊断工具 | 1 | `mech_diagnose`（机械后端、ZRX 桥接与连接诊断）|
| 标题栏 | 1 | `manage_title_block` |
| 图框 | 2 | `manage_frame`、`create_frame` |
| 明细表 | 2 | `manage_bom`、`create_partlist` |
| 机械数据库 | 1 | `manage_mech_db` |
| 机械应用 | 4 | `mech_doc`、`cad_environment_init`、`get_balloon`、`insert_balloon` |
| 机械符号标注 | 6 | `manage_surf_sym`、`manage_fc_frame`、`manage_datum_id`、`manage_note`、`manage_welding`、`manage_bubble` |
| 扩展数据 | 3 | `manage_dictionary`、`manage_xdata`、`manage_utility` |

**共计 43 个工具**

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

默认 `ZWMECH_USE_ZRX=0`，机械功能优先使用 `pyzwcadmech`；如果 ZwmToolKit COM 接口不可用，服务会通过活动 ZWCAD 的 `Application.LoadZrx()` 自动加载 `ZWMechMCP.zrx` 并回退到本机桥接。将 `ZWMECH_USE_ZRX` 设为 `1`（也接受 `true/on/yes`）可强制所有机械功能直接走 ZRX。

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
| `add_dimension` | 添加标注（支持公差/配合代号） | `aligned`, `rotated`, `diametric`, `radial`, `angular`, `ordinate` |
| `insert_block` | 在指定位置插入图块 | - |

**标注公差与配合**（`add_dimension` 与 `modify_entity(entity_type="dimension")` 通用，均放在 `params` 中，可选）：

| 参数 | 说明 |
|------|------|
| `tolerance_display` | 公差显示方式：`none`\|`symmetrical`(对称)\|`deviation`(偏差)\|`limits`(极限)\|`basic`(基本)，或 0-4 |
| `upper_deviation` / `lower_deviation` | 上/下偏差（带符号，如 `0.021` / `-0.05`） |
| `tolerance_precision` | 公差小数位数 0-8 |
| `tolerance_height_scale` | 公差字高系数（GB 常用 0.7） |
| `fit_symbol` | 配合代号，如 `"H7"`、`"H7/g6"`（含 `/` 或 `^` 时默认堆叠为分数显示） |
| `fit_stacked` / `fit_height_scale` | 配合代号是否堆叠（默认 `True`）/ 字高系数（默认 0.7） |
| `text_prefix` / `text_suffix` / `text_override` | 标注文字前缀/后缀/替代（`<>` 表示测量值） |

示例：直径50H7孔 → `add_dimension(dim_type="diametric", params={..., "fit_symbol": "H7"})`；
50(+0.021/0)偏差 → `params={..., "tolerance_display": "deviation", "upper_deviation": 0.021, "lower_deviation": 0}`；
已有标注补公差 → `modify_entity(entity_type="dimension", handle="A3F", params={"tolerance_display": "limits", ...})`。

### 实体操作

| 工具 | 说明 | action / entity_type |
|------|------|----------------------|
| `transform_entity` | 实体变换 | `copy`, `move`, `rotate`, `mirror`, `scale`, `delete`, `array_polar`, `array_rectangular` |
| `modify_entity` | 修改实体几何属性（含标注公差/配合） | `circle`, `arc`, `line`, `text`, `mtext`, `polyline`, `spline`, `dimension`, `offset`, `explode` |
| `get_entity_info` | 获取实体详细信息 | - |
| `set_entity_properties` | 设置实体通用属性（图层/颜色/线型等） | - |

### 对象查询

| 工具 | 说明 |
|------|------|
| `find_object` | 按类型/属性/句柄查找对象 |
| `get_objects_in_model` | 获取模型空间对象列表 |
| `query_dimensions` | 快速查询所有标注（尺寸值/公差/文字覆盖等）；原生 DXF 过滤，远快于逐个迭代；`detail=summary\|full`，可按 `layer` 过滤 |

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
| `mech_diagnose` | 诊断当前机械后端、`pyzwcadmech` 启动探测、ZRX 路径与桥接插件/版本/PID，并读取 ZWCAD、ZwmApp、ZwmDb、标题栏等状态。每次调用自动重置当前线程连接缓存。 |

### 标题栏

| 工具 | 说明 | action |
|------|------|--------|
| `manage_title_block` | 标题栏读取/设置/批量更新 | `get_info`, `set_field`, `update_batch`, `get_field_count`, `get_field_by_index` |

> 默认 `auto` 模式会先使用 `pyzwcadmech`，探测失败后自动切换到 ZRX；只有两条路径都不可用时才返回机械后端错误。

### 图框

| 工具 | 说明 | action |
|------|------|--------|
| `manage_frame` | 图框查询/切换/更新/刷新 | `list`, `get_info`, `get_count`, `get_name_by_index`, `get_name_by_point`, `get_next_name`, `switch`, `update`, `refresh` |
| `create_frame` | 新建图框（自动从XML配置读取默认样式） | - |

> 图框操作使用当前选定的机械后端。默认优先 `pyzwcadmech`，故障时自动切换到 ZRX 桥接。

### 明细表（BOM）

| 工具 | 说明 | action |
|------|------|--------|
| `manage_bom` | 明细表增删改查 | `get_row_count`, `get_row`, `add_row`, `update_row`, `insert_row`, `delete_row`, `set_field`, `get_field`, `get_field_count`, `batch_update`, `refresh` |
| `create_partlist` | 创建明细表实体 | 发送 `_.ZwmPartlist` 命令 |

> BOM 操作使用当前选定的机械后端；默认模式下无需预先加载 ZRX。ZRX 缺失、端口被占用或 PID 不匹配时，错误详情可在 `mech_diagnose` 中查看。
>
> 💡 **BOM 持久化说明**：修改 BOM 数据后，`update_row`/`set_field`/`batch_update` 等操作会自动调用 `refresh_bom()` 将更改写入 DWG 图纸。请勿在 BOM 修改后调用 `manage_mech_db` 的 `save` 操作，`save` 会从图纸重载数据导致修改丢失。

### 机械模块

| 工具 | 说明 |
|------|------|
| `manage_mech_db` | 机械数据库操作。action: `open`/`save`/`close` |
| `mech_doc` | 机械文档操作。action: `open`/`new`/`new_named` |
| `cad_environment_init` | 初始化CAD标准环境（GB, ISO, DIN等） |
| `get_balloon` | 获取球标对象用于零件编号标注 |
| `insert_balloon` | 插入球标（零件序号标注），通过 LISP 命令 Zwm_BalloonInsert 实现。参数: 箭头位置/符号位置/文字/序号类型(0-6)/是否带引线 |

### 机械符号标注（ZwmToolKit LISP）

以下工具通过 `lisp_bridge.py` 向 ZWCAD 发送 `Zwm_*` AutoLISP（Get/Set 经命名字典 `ZWM_MCP` 临时 XRECORD 回传；Insert 以 ModelSpace 新增实体句柄为准）。插入前建议先 `cad_environment_init("GB")`。详细 LISP 槽位见 [ZwmToolKit符号标注LISP接口说明.md](ZwmToolKit符号标注LISP接口说明.md)。

| 工具 | 说明 | action |
|------|------|--------|
| `manage_surf_sym` | 表面粗糙度 `ZwmSurfSym` | `insert` / `get` / `set` |
| `manage_fc_frame` | 形位公差框 `ZwmFCFrame` | `insert` / `get` / `set` |
| `manage_datum_id` | 基准代号 `ZwmDatumId` | `insert` / `get` / `set` |
| `manage_note` | 机械引线注释 `ZwmNote` | `insert` / `get` / `set` |
| `manage_welding` | 焊接符号 `ZwmWelding` | `insert` / `get` / `set` |
| `manage_bubble` | 检验气泡图（非零件序号球标） | `auto` / `fill_all` / `fill_picked` / `manu` / `manu_list` / `get_substd` |

> 以上机械模块与符号工具使用当前选定的机械后端。ZRX 回退覆盖当前 MCP 暴露的调用面，不承诺覆盖 `pyzwcadmech` 未被 MCP 使用的全部公开 API。

### 扩展数据

| 工具 | 说明 | action |
|------|------|--------|
| `manage_dictionary` | 命名对象字典与XRecord管理 | `list`, `add`, `get_items`, `add_object`, `get_object`, `remove`, `rename` |
| `manage_xdata` | 实体扩展数据(XData)读写 | `get`, `set`, `list_apps`, `add_app` |
| `manage_utility` | CAD工具方法（坐标转换/距离/角度计算/关键字输入等） | `distance`, `angle`, `polar`, `translate_coords`, `get_real`, `get_keyword` |

## 机械后端自动回退

`mechanical_backend.py` 在 MCP 开始接受请求前选择机械后端。`ZWMECH_BACKEND` 支持以下模式：

| 模式 | 行为 | 用途 |
|------|------|------|
| `auto`（默认） | 独立子进程探测 `pyzwcadmech`；失败后自动 `LoadZrx()` 并验证桥接。 | 日常使用 |
| `pyzwcadmech` | 只使用 Python COM 路径；探测失败时机械功能降级。 | 主路径排查 |
| `zrx` | 跳过 Python COM 探测，直接加载/验证 ZRX。 | 桥接验收 |

启动探测为只读操作，检查类型库、机械版本、当前机械 DB、标题栏、BOM 和图框；没有相应图纸对象属于正常结果，调用异常才判定失败。探测放在带超时的子进程中，避免异常 COM 阻塞 MCP 启动。

ZRX 回退流程如下：

1. 将 `ZWMECH_ZRX_PATH` 按项目目录解析相对路径；默认使用 `zrx\ZWMechMCP.zrx`。也支持填写绝对路径覆盖默认值。
2. 通过活动 `ZWCAD.Application.LoadZrx()` 加载插件。
3. 轮询 `ZWMECH_BRIDGE_HOST:ZWMECH_BRIDGE_PORT` 的 `ping`。
4. 校验插件标识 `ZWMechMCP`、版本和 `process_id`；PID 必须与 `Application.HWND` 所属 ZWCAD 进程一致。

运行期只从 `pyzwcadmech` 单向切换到 ZRX。只读操作切换成功后自动重试一次；写操作不会盲目重放，返回 `MECHANICAL_BACKEND_SWITCHED_RETRY_REQUIRED`，确认图纸状态后重新调用。参数错误、对象不存在和业务错误不会触发切换。两条路径均失败时服务仍启动，机械工具返回 `MECHANICAL_BACKEND_UNAVAILABLE`，基础 CAD 工具保持可用。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ZWMECH_USE_ZRX` | `0` | 设为 `1`、`true`、`on` 或 `yes` 时强制所有机械功能使用 ZRX；默认优先使用 `pyzwcadmech`。 |
| `ZWMECH_BACKEND` | `auto` | `auto`、`pyzwcadmech` 或 `zrx`。 |
| `ZWMECH_ZRX_PATH` | `zrx\\ZWMechMCP.zrx` | ZRX 回退插件路径；相对路径以当前项目目录为基准，也支持绝对路径。 |
| `ZWMECH_BRIDGE_HOST` | `127.0.0.1` | 本机桥接地址，建议保持回环地址。 |
| `ZWMECH_BRIDGE_PORT` | `17890` | ZRX HTTP/JSON 桥接端口。插件和 MCP 必须使用相同端口。 |

PowerShell 中可临时强制一路径：

```powershell
$env:ZWMECH_BACKEND = "zrx"
python server.py
```

默认 `auto` 不要求预先手工加载插件。若需恢复或调试，可在 ZWCAD 中执行 `ZRXLOAD`/`APPLOAD`，然后执行 `ZWMMECHSTATUS`。使用 `mech_diagnose` 可查看当前后端、探测步骤、切换原因、ZRX 路径、桥接信息以及两条路径的错误。

调试两条路线时，建议分别使用 `ZWMECH_USE_ZRX=0`（默认，优先 COM）和 `ZWMECH_USE_ZRX=1`（强制 ZRX）。`ZWMECH_BACKEND` 仍可用于兼容旧配置或启用 `auto`、`pyzwcadmech`、`zrx` 模式。

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
├── server.py                 # MCP Server 主程序（43个工具）
├── lisp_bridge.py            # AutoLISP SendCommand 与 XRECORD 回传
├── mech_symbols.py           # 机械符号 LISP 编排（manage_* 符号工具）
├── mechanical_backend.py     # 机械探测、选路与运行期回退
├── mech_bridge.py            # ZRX HTTP/JSON 兼容层
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
   FastMCP Server (server.py, 43 tools)
        │
        ├── pyzwcad ──────► ZWCAD.Application COM API (基础绘图/标注/变换/查询)
        │                   └── 不依赖类型库，始终可用
        │
        ├── lisp_bridge.py ─► Zwm_* LISP（符号 Get/Set 经 ZWM_MCP XRECORD）
        │
        └── mechanical_backend.py ──► 机械后端自动选路
                ├── pyzwcadmech ──► ZwmToolKit COM（默认主路径）
                └── mech_bridge.py ──► HTTP/JSON ──► ZWMechMCP.zrx
                                             LoadZrx 自动回退，插件/版本/PID 校验
                                             ZWCAD 进程内调用 ZwmToolKit

   连接缓存: CAD/机械 COM 代理按工作线程缓存，后端切换后按代次重建
   诊断工具: mech_diagnose() 自动重置当前线程缓存并报告两条路径状态
```

## 重要说明

1. **ZWCAD 必须运行**：所有工具调用都要求中望机械CAD 已启动并打开了 DWG 文件。

2. **样式文件路径**：`create_frame` 工具从 ZWCAD 的 XML 配置目录读取默认样式；实际目录随安装位置和语言版本变化。

3. **机械后端**：默认先探测 `pyzwcadmech`，失败后自动对活动 ZWCAD 调用 `LoadZrx()`。手工 `ZRXLOAD`/`APPLOAD` 和 `ZWMMECHSTATUS` 仍可用于恢复、调试或强制 `ZWMECH_BACKEND=zrx` 验收。

4. **连接缓存**：连接按 MCP 工作线程隔离，避免跨 STA 复用 COM 代理。`mech_diagnose` 会重置当前线程缓存以获取最新状态。

## 依赖

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD Python COM 封装
- [pyzwcadmech](https://pypi.org/project/pyzwcadmech/) >=0.3.0 - 中望机械 Python COM 封装（含 BOM 读写修复）
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
| Object Query | 3 | `find_object`, `get_objects_in_model`, `query_dimensions` |
| Style Mgmt | 1 | `manage_style` (layer/linetype/text/dim style CRUD) |
| View & Layout | 2 | `manage_view`, `zoom` |
| Document | 1 | `manage_document` |
| Table | 1 | `manage_table` |
| Selection | 1 | `select_entities` |
| Block | 1 | `manage_block` |
| System | 3 | `get_variable`, `set_variable`, `get_app_info` |
| Diagnostics | 1 | `mech_diagnose` (mechanical backend, ZRX bridge, and connection diagnostics) |
| Title Block | 1 | `manage_title_block` |
| Frame | 2 | `manage_frame`, `create_frame` |
| BOM | 2 | `manage_bom`, `create_partlist` |
| Mech Database | 1 | `manage_mech_db` |
| Mech App | 4 | `mech_doc`, `cad_environment_init`, `get_balloon`, `insert_balloon` |
| Mech Symbols | 6 | `manage_surf_sym`, `manage_fc_frame`, `manage_datum_id`, `manage_note`, `manage_welding`, `manage_bubble` |
| Extended Data | 3 | `manage_dictionary`, `manage_xdata`, `manage_utility` |

**Total: 43 tools**

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

In the default `ZWMECH_BACKEND=auto` mode, MCP probes `pyzwcadmech` at startup. If the ZwmToolKit COM interfaces are unavailable, it calls `Application.LoadZrx()` on the active ZWCAD instance and uses the local ZRX bridge for mechanical operations; preloading the plugin is normally unnecessary.

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
| `add_dimension` | Add dimensions (with tolerance/fit support) | `aligned`, `rotated`, `diametric`, `radial`, `angular`, `ordinate` |
| `insert_block` | Insert block at specified position | - |

**Dimension tolerance & fit** (optional keys in `params` of `add_dimension`, or `modify_entity` with `entity_type="dimension"`):

| Parameter | Description |
|-----------|-------------|
| `tolerance_display` | Tolerance style: `none`\|`symmetrical`\|`deviation`\|`limits`\|`basic`, or 0-4 |
| `upper_deviation` / `lower_deviation` | Upper/lower deviation (signed, e.g. `0.021` / `-0.05`) |
| `tolerance_precision` | Tolerance decimal places 0-8 |
| `tolerance_height_scale` | Tolerance text height factor (GB commonly 0.7) |
| `fit_symbol` | Fit designation, e.g. `"H7"`, `"H7/g6"` (stacked as fraction by default when containing `/` or `^`) |
| `fit_stacked` / `fit_height_scale` | Stack fit designation (default `True`) / height factor (default 0.7) |
| `text_prefix` / `text_suffix` / `text_override` | Dimension text prefix/suffix/override (`<>` keeps measured value) |

Examples: a ø50H7 hole (diametric) -> `add_dimension(dim_type="diametric", params={..., "fit_symbol": "H7"})`;
50(+0.021/0) deviation -> `params={..., "tolerance_display": "deviation", "upper_deviation": 0.021, "lower_deviation": 0}`;
add tolerance to an existing dimension -> `modify_entity(entity_type="dimension", handle="A3F", params={"tolerance_display": "limits", ...})`.

### Entity Operations

| Tool | Description | action / entity_type |
|------|-------------|----------------------|
| `transform_entity` | Entity transform | `copy`, `move`, `rotate`, `mirror`, `scale`, `delete`, `array_polar`, `array_rectangular` |
| `modify_entity` | Modify entity geometry (incl. dimension tolerance/fit) | `circle`, `arc`, `line`, `text`, `mtext`, `polyline`, `spline`, `dimension`, `offset`, `explode` |
| `get_entity_info` | Get entity details (properties, geometry, bounding box) | - |
| `set_entity_properties` | Set entity properties (layer/color/linetype etc.) | - |

### Object Query

| Tool | Description |
|------|-------------|
| `find_object` | Find object by type/property/handle |
| `get_objects_in_model` | List model space objects |
| `query_dimensions` | Fast query all dimensions (measurement/tolerance/text override); native DXF filter; `detail=summary\|full`, optional `layer` filter |

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
| `mech_diagnose` | Reports the selected mechanical backend, `pyzwcadmech` startup probe, ZRX path, bridge plugin/version/PID, fallback reason, and ZWCAD/ZwmApp/ZwmDb/title block state. Resets the current worker connection cache on each call. |

### Title Block

| Tool | Description | action |
|------|-------------|--------|
| `manage_title_block` | Title block read/set/batch update | `get_info`, `set_field`, `update_batch`, `get_field_count`, `get_field_by_index` |

> In default `auto` mode this first uses `pyzwcadmech` and then falls back to ZRX after a failed probe. A mechanical backend error is returned only when both routes are unavailable.

### Frame

| Tool | Description | action |
|------|-------------|--------|
| `manage_frame` | Frame query/switch/update/refresh | `list`, `get_info`, `get_count`, `get_name_by_index`, `get_name_by_point`, `get_next_name`, `switch`, `update`, `refresh` |
| `create_frame` | Create a new frame (auto-reads XML default style config) | - |

> Frame actions use the selected mechanical backend: `pyzwcadmech` by default, then the ZRX bridge after a qualifying failure.

### BOM (Bill of Materials)

| Tool | Description | action |
|------|-------------|--------|
| `manage_bom` | BOM CRUD operations | `get_row_count`, `get_row`, `add_row`, `update_row`, `insert_row`, `delete_row`, `set_field`, `get_field`, `get_field_count`, `batch_update`, `refresh` |
| `create_partlist` | Create parts list entity | Sends `_.ZwmPartlist` command |

> BOM actions use the selected mechanical backend. The default mode does not require preloading ZRX; missing artifacts, occupied ports, or PID mismatches are reported by `mech_diagnose`.
>
> 💡 **BOM Persistence**: After modifying BOM data, `update_row`/`set_field`/`batch_update` automatically call `refresh_bom()` to write changes to the DWG. Do NOT call `manage_mech_db`'s `save` after BOM modifications, as `save` reloads data from the drawing and discards changes.

### Mechanical Module

| Tool | Description |
|------|-------------|
| `manage_mech_db` | Mechanical database operations. action: `open`/`save`/`close` |
| `mech_doc` | Mechanical document operations. action: `open`/`new`/`new_named` |
| `cad_environment_init` | Initialize CAD standard environment (GB, ISO, DIN, etc.) |
| `get_balloon` | Get balloon object for part numbering |
| `insert_balloon` | Insert balloon (part number annotation) via LISP command Zwm_BalloonInsert. Params: arrow point/symbol point/text/seq type(0-6)/leader |

### Mechanical symbol annotation (ZwmToolKit LISP)

These tools send `Zwm_*` AutoLISP through `lisp_bridge.py` (Get/Set round-trip via temporary XRECORD in named dictionary `ZWM_MCP`; Insert resolves new entity handles from ModelSpace). Call `cad_environment_init("GB")` before insert when possible. See [ZwmToolKit符号标注LISP接口说明.md](ZwmToolKit符号标注LISP接口说明.md) for LISP slot details.

| Tool | Description | action |
|------|-------------|--------|
| `manage_surf_sym` | Surface roughness `ZwmSurfSym` | `insert` / `get` / `set` |
| `manage_fc_frame` | Feature control frame `ZwmFCFrame` | `insert` / `get` / `set` |
| `manage_datum_id` | Datum identifier `ZwmDatumId` | `insert` / `get` / `set` |
| `manage_note` | Mechanical leader note `ZwmNote` | `insert` / `get` / `set` |
| `manage_welding` | Welding symbol `ZwmWelding` | `insert` / `get` / `set` |
| `manage_bubble` | Inspection bubble (not part balloon) | `auto` / `fill_all` / `fill_picked` / `manu` / `manu_list` / `get_substd` |

> Mechanical module and symbol tools use the selected mechanical backend. The ZRX fallback covers the MCP call surface, not every public API exposed by `pyzwcadmech`.

### Extended Data

| Tool | Description | action |
|------|-------------|--------|
| `manage_dictionary` | Named object dictionary & XRecord management | `list`, `add`, `get_items`, `add_object`, `get_object`, `remove`, `rename` |
| `manage_xdata` | Entity extended data (XData) read/write | `get`, `set`, `list_apps`, `add_app` |
| `manage_utility` | CAD utility methods (coordinate conversion/distance/angle/keyword input) | `distance`, `angle`, `polar`, `translate_coords`, `get_real`, `get_keyword` |

## Automatic Mechanical Backend Fallback

Before accepting MCP requests, `mechanical_backend.py` selects one process-wide mechanical backend. `ZWMECH_BACKEND` supports:

| Mode | Behavior | Use |
|------|----------|-----|
| `auto` (default) | Run a bounded child-process probe of `pyzwcadmech`; on failure call `LoadZrx()` and validate the bridge. | Normal operation |
| `pyzwcadmech` | Use only the Python COM path; mechanical tools degrade if the probe fails. | Primary-route diagnosis |
| `zrx` | Skip the Python COM probe and load/validate ZRX directly. | Bridge acceptance |

The startup probe is read-only and checks the type library, mechanical version, current mechanical database, title block, BOM, and frame. Missing objects in the drawing are valid results; call exceptions are failures. Running the probe in a subprocess with a timeout prevents a stuck COM server from blocking MCP startup.

ZRX fallback:

1. Resolve `ZWMECH_ZRX_PATH` relative to the project directory; the default is `zrx\\ZWMechMCP.zrx`. An absolute path may also be supplied to override it.
2. Call `Application.LoadZrx()` on the active `ZWCAD.Application` instance.
3. Poll `ZWMECH_BRIDGE_HOST:ZWMECH_BRIDGE_PORT` for `ping`.
4. Validate plugin `ZWMechMCP`, version, and `process_id`; the bridge PID must match the PID resolved from `Application.HWND`.

Runtime switching is one-way from `pyzwcadmech` to ZRX. Read-only operations retry once after a successful switch. Writes are not replayed and return `MECHANICAL_BACKEND_SWITCHED_RETRY_REQUIRED`; inspect the drawing before deliberately retrying. Parameter, missing-object, and ordinary business errors do not trigger a switch. If both routes fail, MCP still starts, mechanical tools return `MECHANICAL_BACKEND_UNAVAILABLE`, and basic CAD tools remain available.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ZWMECH_USE_ZRX` | `0` | Set to `1`, `true`, `on`, or `yes` to force all mechanical tools through ZRX; default prefers `pyzwcadmech`. |
| `ZWMECH_BACKEND` | `auto` | `auto`, `pyzwcadmech`, or `zrx`. |
| `ZWMECH_ZRX_PATH` | `zrx\\ZWMechMCP.zrx` | Fallback ZRX path; relative values are based on the project directory, and absolute values are also supported. |
| `ZWMECH_BRIDGE_HOST` | `127.0.0.1` | Local bridge address; keep it loopback-only. |
| `ZWMECH_BRIDGE_PORT` | `17890` | Local HTTP/JSON bridge port. The plugin and MCP must use the same value. |

PowerShell example:

```powershell
$env:ZWMECH_BACKEND = "zrx"
python server.py
```

In `auto` mode, preloading the plugin is normally unnecessary. For recovery or debugging, run `ZRXLOAD`/`APPLOAD` in ZWCAD and then `ZWMMECHSTATUS`. `mech_diagnose` reports the active backend, probe steps, fallback reason, ZRX path, bridge metadata, and errors from both routes.

For route comparison, use `ZWMECH_USE_ZRX=0` (default, prefer COM) and `ZWMECH_USE_ZRX=1` (force ZRX). `ZWMECH_BACKEND` remains available for legacy configuration and explicit `auto`, `pyzwcadmech`, or `zrx` modes.

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
├── server.py                 # MCP Server main program (43 tools)
├── lisp_bridge.py            # AutoLISP SendCommand and XRECORD round-trip
├── mech_symbols.py           # Mechanical symbol LISP dispatch (manage_* tools)
├── mechanical_backend.py     # probe, route selection, and runtime fallback
├── mech_bridge.py            # ZRX HTTP/JSON compatibility client
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
   FastMCP Server (server.py, 43 tools)
        │
        ├── pyzwcad ──────► ZWCAD.Application COM API (basic drawing)
        │                   └── No type library dependency, always available
        │
        ├── lisp_bridge.py ─► Zwm_* LISP (symbol Get/Set via ZWM_MCP XRECORD)
        │
        └── mechanical_backend.py ──► mechanical backend selection
                ├── pyzwcadmech ──► ZwmToolKit COM (default primary route)
                └── mech_bridge.py ──► HTTP/JSON ──► ZWMechMCP.zrx
                                             LoadZrx fallback, plugin/version/PID validation
                                             in-process ZwmToolKit calls

   Connection cache: CAD/mechanical COM proxies are per-worker and rebuilt after switching
   Diagnostics: mech_diagnose() resets the current worker cache and reports both routes
```

## Important Notes

1. **ZWCAD Must Be Running**: All tool calls require ZWCAD Mechanical to be running with a DWG file open.

2. **Style File Path**: The `create_frame` tool reads default styles from the ZWCAD XML configuration directory; the actual location depends on the installation and language.

3. **Mechanical backend**: The default flow probes `pyzwcadmech` first, then calls `LoadZrx()` on the active ZWCAD instance if the probe fails. Manual `ZRXLOAD`/`APPLOAD` and `ZWMMECHSTATUS` remain available for recovery, debugging, or forced `ZWMECH_BACKEND=zrx` validation.

4. **Connection Cache**: Connections are isolated per MCP worker to avoid cross-STA COM reuse. `mech_diagnose` resets the current worker cache for fresh diagnostics.

## Dependencies

- [pyzwcad](https://pypi.org/project/pyzwcad/) - ZWCAD Python COM wrapper
- [pyzwcadmech](https://pypi.org/project/pyzwcadmech/) >=0.3.0 - ZWCAD MFG Python COM wrapper (includes BOM read/write fixes)
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP protocol server framework
- [comtypes](https://github.com/enthought/comtypes) - COM type library loading and interface invocation
- [pywin32](https://github.com/mhammond/pywin32) - Windows COM initialization support

## License

MIT License - See [LICENSE](LICENSE)

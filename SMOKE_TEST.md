# MCP 最小冒烟验证清单

> 前置条件：ZWCAD Mechanical 2027 已启动并打开一个图纸文件。
> 验证方式：逐组调用工具，检查返回的 JSON 中 `ok` 字段。

---

## 1. 连接与环境

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 1.1 | `get_document_info` | (无) | `ok:true`，返回文档名 |
| 1.2 | `get_application_info` | (无) | `ok:true`，返回版本信息 |
| 1.3 | `get_mech_version` | (无) | `ok:true`，返回 Mechanical 版本 |
| 1.4 | `get_zcad_state` | (无) | `ok:true`，返回窗口状态 |

## 2. 基础绘图 → 修改 → 删除链路

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 2.1 | `draw_line` | `x1=0,y1=0,z1=0,x2=100,y2=100,z2=0` | `ok:true`，返回 `handle` |
| 2.2 | `draw_circle` | `center_x=50,center_y=50,center_z=0,radius=25` | `ok:true`，返回 `handle` |
| 2.3 | `add_text` | `text="Test",x=10,y=10,z=0` | `ok:true`，返回 `handle` |
| 2.4 | `get_objects_in_model` | `object_type="Line",limit=5` | `ok:true`，`total_count>=1` |
| 2.5 | `get_object_by_handle` | `handle=<2.1返回的handle>` | `ok:true`，返回实体属性 |
| 2.6 | `modify_line` | `handle=<2.1的handle>,color=1` | `ok:true` |
| 2.7 | `delete_object` | `handle=<2.1的handle>` | `ok:true` |
| 2.8 | `delete_object` | `handle=<2.2的handle>` | `ok:true` |
| 2.9 | `delete_object` | `handle=<2.3的handle>` | `ok:true` |

## 3. 文档操作

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 3.1 | `new_drawing` | (无) | `ok:true`，新文档名非空 |
| 3.2 | `get_document_info` | (无) | `ok:true`，文档名与 3.1 匹配 |
| 3.3 | `save_drawing` | `file_path="C:\\temp\\smoke_test.dwg"` | `ok:true` |
| 3.4 | `close_current_document` | `save_changes=False` | `ok:true` |

## 4. 图层 & 样式

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 4.1 | `list_layers` | (无) | `ok:true`，至少含 "0" 图层 |
| 4.2 | `add_layer` | `name="SmokeTestLayer"` | `ok:true` |
| 4.3 | `set_active_layer` | `name="SmokeTestLayer"` | `ok:true` |
| 4.4 | `list_linetypes` | (无) | `ok:true` |
| 4.5 | `list_textstyles` | (无) | `ok:true` |
| 4.6 | `list_dimstyles` | (无) | `ok:true` |

## 5. 命令发送

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 5.1 | `send_command` | `command="._REGEN"` | `ok:true`（自动追加 `\n`） |
| 5.2 | `send_mech_command` | `cmd="._REGEN"` | `ok:true`（自动追加 `\n`） |

## 6. 机械模块 — 图框

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 6.1 | `open_mech_file` | `file_path=""` | `ok:true` |
| 6.2 | `get_frame_count` | (无) | `ok:true`，`count>=1` |
| 6.3 | `get_frame_full_info` | (无) | `ok:true`，含 `std_name` |
| 6.4 | `get_available_frames` | (无) | `ok:true`，返回图框列表 |

## 7. 机械模块 — 标题栏

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 7.1 | `get_title_block_info` | (无) | `ok:true`，返回字段列表 |
| 7.2 | `get_title_field_count` | (无) | `ok:true`，`count>0` |
| 7.3 | `set_title_block_field` | `field_name="设计",value="SmokeTest"` | `ok:true` |
| 7.4 | `get_title_block_info` | (无) | 验证"设计"字段已更新 |
| 7.5 | `set_title_block_field` | `field_name="设计",value=""` | `ok:true`（清理） |

## 8. 机械模块 — 明细表

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 8.1 | `get_bom_row_count` | (无) | `ok:true`，记录初始行数 N |
| 8.2 | `add_bom_row` | `data={"序号":"99","名称":"SmokeTest"}` | `ok:true` |
| 8.3 | `get_bom_row_count` | (无) | `ok:true`，`count == N+1` |
| 8.4 | `get_bom_row_data` | `row_index=N` | `ok:true`，含 "SmokeTest" |
| 8.5 | `delete_bom_row` | `index=N` | `ok:true` |
| 8.6 | `get_bom_row_count` | (无) | `ok:true`，`count == N` |

## 9. Handle 精确定位

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 9.1 | `draw_circle` | `center_x=200,center_y=200,center_z=0,radius=10` | `ok:true`，记录 handle H |
| 9.2 | `modify_circle` | `handle=H,radius=20` | `ok:true` |
| 9.3 | `get_object_properties` | `handle=H` | `ok:true`，Radius==20 |
| 9.4 | `copy_object` | `handle=H,dx=50,dy=0,dz=0` | `ok:true` |
| 9.5 | `delete_object` | `handle=H` | `ok:true` |

## 10. 错误处理

| # | 工具 | 参数 | 预期 |
|---|---|---|---|
| 10.1 | `get_object_by_handle` | `handle="INVALID"` | `ok:false` 或 `found:false` |
| 10.2 | `modify_circle` | `handle="INVALID",radius=10` | `ok:true,found:false` |
| 10.3 | `delete_bom_row` | `index=9999` | `ok:false`，含错误描述 |

---

## 执行说明

1. 按组顺序执行，每组测试前确保 ZWCAD 正常响应
2. 检查每个返回值的 `ok` 字段
3. 使用 `handle` 参数的测试需要传递前序步骤返回的实际句柄值
4. 测试完成后建议执行 `purge_all` 清理测试数据

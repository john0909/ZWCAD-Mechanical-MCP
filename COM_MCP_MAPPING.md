# COM → MCP 工具映射矩阵

> 记录 `zwcad25.tlb` / `ZwmToolKit.lib` 的 COM 接口与 `server.py` MCP 工具之间的对应关系。
> 状态说明：✅ 已封装 | ⚠️ 语义重构（函数名/参数与 COM 不完全对应）| ❌ 未封装

---

## 统一协议说明

所有 MCP 工具返回值遵循统一 JSON 协议：

```json
// 成功
{"ok": true, "message": "...", ...data}

// 失败
{"ok": false, "error": "xxx失败: ...", "error_code": "OPERATION_ERROR|COM_INIT_ERROR"}
```

实体操作工具均支持可选 `handle` 参数用于精确定位，优先于 `property_name`/`property_value` 遍历查找。

---

## 1. IZcadApplication（应用程序）

| COM 方法/属性 | MCP 工具 | 状态 |
|---|---|---|
| `Application.Documents.Add` | `new_drawing` | ✅ 真正调用 Documents.Add |
| `Application.Documents.Open` | `new_document` | ✅ |
| `Application.ActiveDocument` | `get_document_info` | ✅ |
| `Application.Documents` (遍历) | `list_documents` | ✅ |
| `Application.Name/Version/FullName` | `get_application_info` | ✅ |
| `Application.Preferences` | `get_preferences` / `set_preference` | ✅ |
| `Application.Eval` (LISP) | `eval_lisp` | ✅ |
| `Application.GetVariable` / `SetVariable` | `get_variable` / `set_variable` | ✅ |
| `Application.ZoomExtents` | `zoom_extents` | ✅ |
| `Application.ZoomAll` | `zoom_all` | ✅ |
| `Application.ZoomWindow` | `zoom_window` | ✅ |
| `Application.ZoomCenter` | `zoom_center` | ✅ |
| `Application.ZoomScaled` | `zoom_scaled` | ✅ |
| `Application.ZoomPrevious` | `zoom_previous` | ✅ |
| `Application.WindowState` 等 | `get_zcad_state` | ✅ |

## 2. IZcadDocument（文档）

| COM 方法/属性 | MCP 工具 | 状态 |
|---|---|---|
| `Document.SaveAs` | `save_drawing` | ✅ |
| `Document.Close` | `close_current_document` | ✅ |
| `Document.SendCommand` | `send_command` | ✅ 自动追加 `\n` |
| `Document.Name/FullName/Path/Saved/ReadOnly` | `get_document_info` | ✅ |
| `Document.ActiveLayout` | `get_active_layout` | ✅ |
| `Document.Layouts` (遍历) | `get_layouts` | ✅ |
| `Document.Layers` | `list_layers` / `add_layer` / `set_active_layer` / `set_layer_properties` | ✅ |
| `Document.Linetypes` | `list_linetypes` / `load_linetype` | ✅ |
| `Document.TextStyles` | `list_textstyles` / `add_textstyle` / `set_textstyle_properties` | ✅ |
| `Document.DimStyles` | `list_dimstyles` / `add_dimstyle` | ✅ |
| `Document.Blocks` | `list_blocks` / `get_block_info` / `create_block_definition` | ✅ |
| `Document.Groups` | `list_groups` / `create_group` / `append_to_group` | ✅ |
| `Document.Views` | `list_views` / `add_view` / `set_view` | ✅ |
| `Document.UserCoordinateSystems` | `list_ucs` / `add_ucs` / `set_active_ucs` | ✅ |
| `Document.Dictionaries` | `list_dictionaries` / `add_dictionary` / `add_xrecord` | ✅ |
| `Document.Materials` | `list_materials` / `add_material` | ✅ |
| `Document.Database.HandleToObject` | `get_object_by_handle` | ✅ |
| `Document.SelectionSets` | `create_selection_set` / `select_objects` / `select_on_screen` / `select_by_polygon` / `clear_selection_set` | ✅ |
| `Document.Activate` | `activate_document` | ✅ |
| `Document.Export` | `export_drawing` | ✅ |
| `Document.Import` | `import_file` | ✅ |
| `Document.Plot` | `plot_to_file` | ✅ |
| `Document.PurgeAll` | `purge_all` | ✅ |
| `Document.Regen` | `regen_viewport` | ✅ |
| `Document.SummaryInfo` | `get_summary_info` / `set_summary_info` | ✅ |
| `Document.StartUndoMark/EndUndoMark` | `undo_mark_start` / `undo_mark_end` | ✅ |
| `Document.Prompt` | `send_prompt` | ✅ |

## 3. IZcadModelSpace / IZcadBlock（绘图）

| COM 方法 | MCP 工具 | 状态 |
|---|---|---|
| `AddLine` | `draw_line` | ✅ 返回 handle |
| `AddCircle` | `draw_circle` | ✅ 返回 handle |
| `AddArc` | `draw_arc` | ✅ 返回 handle |
| `AddEllipse` | `draw_ellipse` | ✅ 返回 handle |
| `AddText` | `add_text` | ✅ 返回 handle |
| `AddMText` | `add_mtext` | ✅ 返回 handle |
| `AddPoint` | `add_point` | ✅ 返回 handle |
| `AddLightWeightPolyline` | `draw_lwpolyline` | ✅ 返回 handle |
| `AddPolyline` | `draw_polyline` | ✅ 返回 handle |
| `AddSpline` | `draw_spline` | ✅ 返回 handle |
| `Add3DPolyline` | `draw_3d_polyline` | ✅ 返回 handle |
| `AddRay` | `draw_ray` | ✅ 返回 handle |
| `AddXline` | `draw_xline` | ✅ 返回 handle |
| `AddMLine` | `draw_mline` | ✅ 返回 handle |
| `InsertBlock` | `insert_block` | ✅ 返回 handle |
| `AddDimAligned` | `add_dim_aligned` | ✅ 返回 handle |
| `AddDimRotated` | `add_dim_rotated` | ✅ 返回 handle |
| `AddDim3PointAngular` | `add_dim_angular` | ✅ 返回 handle |
| `AddDimDiametric` | `add_dim_diametric` | ✅ 返回 handle |
| `AddDimRadial` | `add_dim_radial` | ✅ 返回 handle |
| `AddDimOrdinate` | `add_dim_ordinate` | ✅ 返回 handle |
| `AddHatch` | `add_hatch` | ✅ 返回 handle |
| `AddLeader` | `add_leader` | ✅ 返回 handle |
| `AddMLeader` | `add_mleader` | ✅ 返回 handle |
| `AddTable` | `add_table` | ✅ 返回 handle |
| `AddTolerance` | `add_tolerance` | ✅ 返回 handle |
| `Add3DFace` | `draw_3d_face` | ✅ 返回 handle |
| `AddBox` | `draw_box` | ✅ 返回 handle |
| `AddCylinder` | `draw_cylinder` | ✅ 返回 handle |
| `AddCone` | `draw_cone` | ✅ 返回 handle |
| `AddSphere` | `draw_sphere` | ✅ 返回 handle |
| `AddTorus` | `draw_torus` | ✅ 返回 handle |
| `AddWedge` | `draw_wedge` | ✅ 返回 handle |
| `AddRaster` | `add_raster` | ✅ 返回 handle |
| `AttachExternalReference` | `attach_xref` | ✅ 返回 handle |
| `AddLayout` | `add_layout` | ✅ |
| `AddRegion` | — | ❌ |
| `AddRevolvedSolid` | — | ❌ |
| `AddExtrudedSolid` | — | ❌ |
| `AddExtrudedSolidAlongPath` | — | ❌ |

## 4. IZcadEntity（实体操作）

| COM 方法 | MCP 工具 | 状态 |
|---|---|---|
| `Entity.Copy` | `copy_object` | ✅ 支持 handle 定位 |
| `Entity.Move` | `move_object` | ✅ 支持 handle 定位 |
| `Entity.Rotate` | `rotate_object` | ✅ 支持 handle 定位 |
| `Entity.Mirror` | `mirror_object` | ✅ 支持 handle 定位 |
| `Entity.ScaleEntity` | `scale_object` | ✅ 支持 handle 定位 |
| `Entity.Delete` | `delete_object` | ✅ 支持 handle 定位 |
| `Entity.Offset` | `offset_entity` | ✅ 支持 handle 定位 |
| `Entity.ArrayPolar` | `array_polar` | ✅ 支持 handle 定位 |
| `Entity.ArrayRectangular` | `array_rectangular` | ✅ 支持 handle 定位 |
| `Entity.Mirror3D` | `mirror_3d_object` | ✅ 支持 handle 定位 |
| `Entity.Rotate3D` | `rotate_3d_object` | ✅ 支持 handle 定位 |
| `Entity.Explode` | `explode_entity` | ✅ 支持 handle 定位 |
| `Entity.Layer/Color/Linetype/...` | `set_entity_properties` / `get_object_properties` | ✅ 支持 handle 定位 |
| `Entity.GetBoundingBox` | `get_object_by_handle` (内含) | ✅ |
| `Entity.Handle/ObjectID` | `get_entity_objectid` / `get_object_by_handle` | ✅ |
| `Entity.IntersectWith` | `get_intersection` | ✅ 支持 handle1/handle2 |
| `Entity.Hyperlinks.Add` | `add_hyperlink` | ✅ 支持 handle 定位 |
| `Entity.TransformBy` | — | ❌ |
| `Entity.Update` | — | ❌ |

## 5. 特定实体修改

| 操作 | MCP 工具 | 状态 |
|---|---|---|
| Circle 属性修改 | `modify_circle` | ✅ 支持 handle 定位 |
| Arc 属性修改 | `modify_arc` | ✅ 支持 handle 定位 |
| Line 属性修改 | `modify_line` | ✅ 支持 handle 定位 |
| Text 属性修改 | `modify_text` | ✅ 支持 handle 定位 |
| MText 属性修改 | `modify_mtext` | ✅ 支持 handle 定位 |
| Polyline 属性修改 | `modify_polyline` | ✅ 支持 handle 定位 |
| Spline 属性修改 | `modify_spline` | ✅ 支持 handle 定位 |
| Hatch 属性修改 | `set_hatch_properties` / `add_inner_loop` | ✅ 支持 handle 定位 |
| Table 操作 | `set_cell_text` / `get_cell_text` / `insert_table_rows` / `delete_table_rows` / `set_column_width` / `set_row_height` / `merge_cells` | ✅ 支持 handle 定位 |
| MLeader 操作 | `add_mleader_line` / `get_mleader_vertices` | ✅ 支持 handle 定位 |
| BlockReference 操作 | `explode_block_reference` / `get_dynamic_block_properties` / `get_constant_attributes` / `get_block_attributes` | ✅ 支持 handle 定位 |

## 6. IZcadSelectionSet（选择集）

| COM 方法 | MCP 工具 | 状态 |
|---|---|---|
| `SelectionSets.Add` | `create_selection_set` | ✅ |
| `SelectionSet.Select` | `select_objects` | ✅ |
| `SelectionSet.SelectOnScreen` | `select_on_screen` | ✅ |
| `SelectionSet.SelectByPolygon` | `select_by_polygon` | ✅ |
| `SelectionSet.Clear` | `clear_selection_set` | ✅ |

## 7. IZcadUtility（工具）

| COM 方法 | MCP 工具 | 状态 |
|---|---|---|
| `Utility.TranslateCoordinates` | `translate_coordinates` | ✅ |
| `Utility.GetEntity` | — | ❌ |
| `Utility.GetPoint` | — | ❌ |
| `Utility.GetDistance` | — | ❌ |
| `Utility.GetAngle` | — | ❌ |
| `Utility.GetString` | — | ❌ |
| `Utility.GetInput` | — | ❌ |
| `Utility.Prompt` | `send_prompt` | ✅ |

> 注：`Utility.Get*` 系列为交互式输入方法，MCP STDIO 模式下无法直接使用。

## 8. pyzwcadmech（机械模块 — ZwmToolKit.lib）

### ZwmApp（应用）

| 方法 | MCP 工具 | 状态 |
|---|---|---|
| `get_version` | `get_mech_version` | ✅ |
| `get_cad_path` | `get_cad_path` | ✅ |
| `get_zwm_path` | `get_zwm_path` | ✅ |
| `get_style_path` | `get_style_path` | ✅ |
| `get_about` | `get_mech_about` | ✅ |
| `send_command` | `send_mech_command` | ✅ 自动追加 `\n` |
| `open_doc` | `open_mech_doc` | ✅ |
| `new_doc` | `new_mech_doc` | ✅ |
| `new_named_doc` | `new_named_mech_doc` | ✅ |

### ZwmDb（数据库）

| 方法 | MCP 工具 | 状态 |
|---|---|---|
| `open_file` | `open_mech_file` | ✅ |
| `save` | `save_mech_data` | ✅ |
| `close` | `close_mech` | ✅ |
| `get_frame` | `get_frame_full_info` | ✅ |
| `get_frame_count` | `get_frame_count` | ✅ |
| `get_frame_name` | `get_frame_name_by_index` | ✅ |
| `get_frame_name2` | `get_frame_name_by_point` | ✅ |
| `switch_frame` | `switch_frame` | ✅ |
| `refresh_frame` | `refresh_frame` | ✅ |
| `build_frame` | `create_frame` | ✅ 显式报告字段赋值结果 |
| `get_next_frm_name` | `get_next_frame_name` | ✅ |
| `frame_edit` | `edit_frame` | ✅ |
| `get_title` | `get_title_block_info` / `set_title_block_field` / `update_title_block_batch` | ✅ |
| `refresh_title` | (内部调用，在 set_title_block_field 内自动触发) | ✅ |
| `title_edit` | `edit_title` | ✅ |
| `get_bom` | `add_bom_row` / `get_bom_row_count` / `get_bom_row_data` / `update_bom_row` / `insert_bom_row` / `delete_bom_row` | ✅ |
| `refresh_bom` | `refresh_bom` | ✅ |
| `total_bom_edit` | `edit_total_bom` | ✅ |
| `csl_edit` | `edit_csl` | ✅ |
| `fjl_edit` | `edit_fjl` | ✅ |
| `get_balloon` | `get_balloon` | ✅ |
| `cad_environment_init` | `cad_environment_init` | ✅ |

---

## 未封装 COM 能力（候选后续工具）

| COM 接口 / 方法 | 说明 |
|---|---|
| `AddRegion` | 创建面域 |
| `AddRevolvedSolid` | 旋转实体 |
| `AddExtrudedSolid` | 拉伸实体 |
| `AddExtrudedSolidAlongPath` | 沿路径拉伸 |
| `Entity.TransformBy` | 通用矩阵变换 |
| `Entity.Update` | 强制更新实体显示 |
| `Utility.GetEntity/GetPoint/...` | 交互式输入（STDIO 不兼容） |
| `SectionManager` | 剖面管理 |
| `MLeaderStyle` | 多重引线样式管理 |
| `TableStyle` | 表格样式管理 |

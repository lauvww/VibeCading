# AGENTS.md

本文件约束 `D:\VibeCading` 项目内的后续 AI agent、Codex、IDE 助手和开发者工作方式。它的目标不是描述一次临时任务，而是让后续协作者持续理解这个项目的最终方向、阶段路线和工程质量底线。

## 1. 项目最终目标

VibeCading 的最终目标是做一个面向机械 CAD 的本地 AI 自动化工作台：

```text
用户自然语言对话
-> AI Agent 理解工程意图、补齐关键参数、拆解建模步骤
-> 生成结构化 CAD 任务 / Feature DSL / 工程计划
-> MCP 工具层安全执行
-> CAD 软件完成建模、装配、出图、导出和验证
-> 返回模型文件、工程图、导出文件、预览图和执行摘要
```

最终体验应该接近：用户像和工程师沟通一样描述需求，AI agent 能完成工程师的一部分 CAD 建模工作。

但项目原则不是“一句话生成任意复杂 CAD”，也不是“AI 直接随意控制 CAD”。正确路线是：

```text
AI 负责理解、规划、补参、拆解和检查
MCP / 工具层负责按受控参数执行 CAD 操作
CAD 软件负责真实建模、出图和导出
验证逻辑负责判断结果是否可信
```

所有复杂能力都应该逐步沉淀为可组合、可验证、可复用的结构化工具，而不是生成一大段不可控宏。

## 2. 当前优先路线

当前开发和测试优先使用 SolidWorks：

- Windows 本地运行。
- Python 作为 MCP / 工具层主要语言。
- SolidWorks 自动化通过 `pywin32` 调用 `SldWorks.Application` COM。
- 项目专用环境优先使用 `D:\VibeCading\.conda\VibeCading`。
- SolidWorks 模板放在项目内 `mcp-server\SW模板`。
- 输出文件放在 `outputs\jobs\<job-id>\`。

后续可以适配其他 CAD 软件，但不要因此破坏当前 SolidWorks-first 的主线。

## 2.1 语言、编码和中文命名

- 默认用中文理解用户自然语言需求，并默认用中文回复用户。
- 用户没有特别要求时，示例任务、零件名称、工程名称、特征名称、命名面、基准面和输出文件名都可以使用中文。
- 项目文件统一按 UTF-8 读写。JSON、summary、SVG、Skill 文档和 AGENTS.md 都应保持 UTF-8。
- 不要把中文 job_id、part name 或 operation id 强行改成英文；只过滤 Windows / SolidWorks 明显不安全的字符，例如 `<>:"/\|?*` 和控制字符。
- 如果在 Windows PowerShell 里直接 `Get-Content` 看到中文乱码，优先用 `Get-Content -Encoding UTF8` 检查，不要先假设文件已经损坏。
- PDF 报告应尽量使用能显示中文的编码和字体配置；如果某个 PDF 查看器缺少中文字体支持，要在结果里说明这是报告显示限制，不代表 CAD 模型或 JSON 命名损坏。

未来可能适配：

- FreeCAD / CadQuery / build123d：用于开源建模、无 SolidWorks 环境原型验证。
- AutoCAD / ezdxf：用于二维图纸、批量标注、图框和 DXF。
- 其他 CAD：通过新的 adapter 接入，不要把 SolidWorks 逻辑硬编码进核心 DSL。

## 3. 产品定位

VibeCading 不是通用聊天机器人，也不是简单宏集合。它应该是：

```text
面向机械 CAD 的本地 AI Agent + MCP 工具系统
```

第一阶段重点不是全能 CAD Copilot，而是把高频、确定、可验证的机械设计动作产品化。

优先覆盖：

- 安装板
- L 型支架
- 法兰
- 轴
- 垫片
- 简单箱体
- 简单装配体
- 工程图
- STEP / STL / DXF / PDF 导出

## 4. 分阶段路线

后续开发应该分阶段、分模块推进，不要一次性追求复杂完整系统。

### 阶段 1：零件建模

目标：让 agent 能生成可维护的参数化零件。

优先能力：

- 受约束草图
- 拉伸
- 切除
- 旋转
- 孔
- 圆角
- 倒角
- 阵列
- 镜像
- 筋
- 壳
- 旋转
- 简单扫掠 / 放样
- 材质和属性
- SLDPRT / STEP / STL 导出

质量要求：

- 草图必须尽量完全定义。
- 草图约束优先使用尺寸和几何关系；`fixed` 只允许作为少量原点、基准点、构造参考的稳定锚点，不要用来锁定生产几何或阵列副本。
- 特征树要清晰。
- 尺寸应可修改。
- 建模失败要返回具体失败步骤。
- 不允许把明显欠约束的模型当作成功结果交付。

### 阶段 2：装配体装配

目标：让 agent 能把多个零件组合成简单装配体。

优先能力：

- 创建装配体
- 插入零件
- 基准面 / 坐标系对齐
- 配合关系
- 阵列零件
- 干涉检查
- BOM 基础信息
- SLDASM / STEP 导出

质量要求：

- 配合关系要明确。
- 零件位置不能靠偶然拖拽结果。
- 装配失败时要报告哪个零件、哪个配合失败。

### 阶段 3：二维零件图

目标：从零件生成基础工程图。

优先能力：

- 三视图
- 等轴测图
- 标题栏
- 主要尺寸
- 孔尺寸
- 材料 / 比例 / 图号
- PDF / DXF 导出

质量要求：

- 不要自动编造公差、表面粗糙度、热处理、GD&T 或制造标准。
- 关键制造语义缺失时必须让 agent 提醒或追问。

### 阶段 4：二维装配图

目标：从装配体生成基础装配图。

优先能力：

- 装配视图
- 爆炸图
- 明细表
- 序号球标
- 装配尺寸
- PDF 导出

质量要求：

- BOM 和序号要与装配体一致。
- 不要把装配图当作零件制造图处理。

### 阶段 5：二维图纸逆向建模

目标：让 agent 根据二维图纸辅助重建三维模型。

这是后续高级能力，不能过早假装完整实现。

优先拆分：

- 读取图纸图像 / PDF / DXF
- 识别视图、比例、轮廓、孔、尺寸和标注
- 生成候选三维建模计划
- 向用户确认歧义
- 执行受控建模
- 对比生成模型和原图尺寸

质量要求：

- 图纸逆向存在歧义时必须说明，不要伪装成确定结果。
- 缺少视图、尺寸冲突、比例不明时必须追问或标记风险。

## 5. 架构原则

核心架构应保持为：

```text
Natural Language
-> Agent Planning
-> Feature Plan
-> Primitive DSL / CAD JSON
-> MCP Tools
-> CAD Adapter
-> SolidWorks / FreeCAD / AutoCAD / other CAD
-> Validation / Export / Summary
```

各层职责：

- Agent：理解需求、补齐参数、拆解特征、决定是否追问。
- Feature Plan：表达自然语言解析后的主形体、工程语义上下文、功能特征、建模方法、草图策略、关键参数、引用基准、缺失能力和待确认问题。
- DSL：表达确定的 CAD 意图，不包含随意脚本。
- MCP / tools：提供受控操作入口。
- Adapter：处理具体 CAD 软件 API。
- Validators：提前检查尺寸、参数、格式和约束策略。
- Outputs：保存模型、导出文件、预览和摘要。

不要把所有逻辑塞进一个 SolidWorks 宏里。

### 5.1 产品架构：工程语义驱动，不做模板库

VibeCading 的长期产品架构不是“越做越多的零件模板库”，也不是让用户说出具体 CAD 命令后再执行。正确方向是让 Agent 像工程师一样先理解零件为什么存在、在哪里工作、和什么配合，再决定如何建模。

自然语言建模应走下面这条主线：

```text
用户自然语言
-> 提取零件功能、使用场景、装配/配合关系、制造约束
-> 拆成工程特征：基体、安装界面、定位界面、配合孔/轴、密封槽、加强筋、避让、导向、过渡等
-> 针对每个特征选择建模方法：拉伸、切除、旋转、扫描、放样、阵列、镜像、面引用、草图处理等
-> 针对每个建模方法选择草图策略：轮廓、轴线、路径、截面、导向线、引用边、等距线、约束和尺寸
-> 生成 Feature Plan
-> 编译为 Primitive DSL
-> SolidWorks 执行、验证、导出
```

模板只能作为上层示例、回归样件或常见任务入口，不能成为主要扩展方式。后续不要通过不断新增 `shaft_generator`、`flange_generator`、`special_part_generator` 这类专用模板来覆盖复杂零件。复杂零件应通过“功能特征 + 建模策略 + 草图策略”的组合来表达。

Feature Plan 应逐步记录这些工程语义；当前自然语言草案已经开始输出其中的基础字段：

- `part_roles`：零件在机构中的作用，例如支撑、定位、连接、密封、传动、防护、导向、安装。
- `working_context`：使用场景和受力/运动/空间约束，例如固定底座、轴承座、管路过渡、钣金支架、密封端盖。
- `mating_interfaces`：与其他零件配合的面、孔、轴、槽、台阶、基准和装配关系。
- `feature_intents`：每个特征的功能作用，例如安装孔、定位销孔、轴承孔、退刀槽、密封槽、加强筋、减重孔、避让槽。
- `modeling_method`：Agent 选择的建模命令及原因。
- `sketch_strategy`：该特征应如何画草图、如何约束、哪些尺寸是驱动尺寸、是否需要引用已有面/边。
- `questions`：当功能、配合、受力、制造语义不清楚时需要向用户确认的问题。

Agent 应该自己判断建模指令，不能要求用户必须说“用拉伸”“用旋转”“用放样”。用户可以这样描述：

```text
做一个用于固定电机的小支架，底部四个安装孔，竖板上有两个长圆孔用于调节张紧。
```

Agent 应该从“固定”“安装孔”“调节张紧”“长圆孔”推断基体、安装界面、可调连接界面和对应的建模/草图策略，而不是等待用户命名 CAD 命令。

当 Agent 无法判断功能或使用场景时，必须先和用户对齐工程语义。典型需要追问的情况包括：

- 这个孔是安装孔、定位孔、轴承孔、减重孔还是走线孔。
- 这个槽是密封槽、退刀槽、避让槽、导向槽还是调节长孔。
- 某个圆角/倒角是制造去锐边、装配导向、应力优化还是外观处理。
- 某个面是装配基准、加工基准、密封面、承载面还是外观面。
- 用户描述的特征既可以拉伸切除，也可以旋转切除、扫描切除或放样切除，且不同选择会影响制造和后续修改。

## 6. DSL 和工具设计规则

优先使用结构化 JSON / DSL 表达 CAD 任务。

好的方向：

```json
{
  "version": "feature_plan.v1",
  "dominant_geometry": "prismatic",
  "engineering_context": {
    "part_roles": ["mounting_support"],
    "working_context": ["fixed_mounting"],
    "mating_interfaces": ["mounting_face", "four_corner_fastener_pattern"],
    "manufacturing_intent": ["milled_or_plate_like"],
    "semantic_assumptions": ["units_mm"]
  },
  "features": [
    {
      "id": "base_plate",
      "kind": "base_body",
      "method": "extrude",
      "functional_role": "mounting_plate_body",
      "feature_intent": "provide the primary mounting body and flat mounting faces",
      "mating_interfaces": ["mounting_face"],
      "modeling_method": {
        "command": "extrude",
        "reason": "Plate geometry is clearest as one constrained closed profile extruded to thickness."
      },
      "sketch_strategy": {
        "type": "centered_closed_rectangle",
        "driving_dimensions": ["length", "width", "thickness"]
      },
      "parameters": {
        "length": 120,
        "width": 80,
        "thickness": 8
      }
    },
    {
      "id": "fastener_hole_pattern",
      "kind": "hole_pattern",
      "method": "cut_extrude",
      "functional_role": "fastener_hole_pattern",
      "feature_intent": "provide bolt or screw clearance pattern for mounting",
      "mating_interfaces": ["fastener_or_clearance_hole"],
      "modeling_method": {
        "command": "cut_extrude",
        "reason": "Same-plane through holes are stable as one constrained hole sketch followed by through cut."
      },
      "sketch_strategy": {
        "type": "same_plane_circle_layout",
        "driving_dimensions": ["hole_diameter", "hole_centers", "edge_margin_or_pitch"]
      },
      "parameters": {
        "through": true,
        "holes": []
      }
    }
  ],
  "missing_capabilities": []
}
```

不好的方向：

```text
AI 生成一大段不可审计、不可拆解、不可验证的 SolidWorks 宏
```

新增功能时优先增加：

- 可复用的 Feature Plan feature kind
- Feature Plan 到 Primitive DSL 的编译规则
- 功能语义字段，例如 `functional_role`、`mating_interface`、`modeling_method`、`sketch_strategy`
- 明确的 operation type
- 明确的参数
- 参数校验
- SolidWorks 执行逻辑
- preview fallback
- 测试
- summary 元数据

## 7. 工程质量底线

机械 CAD 不是只要“看起来像”就算完成。

必须优先保证：

- 草图尽量完全约束。
- 完全约束应主要来自尺寸、水平/垂直、重合、相切、镜像、穿透等工程关系；少用 `fixed`，避免把本该可修改的草图几何直接固定死。
- `fully_define_sketch` 只能作为尺寸和几何关系之后的残余自由度补全工具，尤其用于样条曲线手柄/曲率等 SolidWorks 内部自由度；不要用它掩盖缺少设计意图的草图。
- 草图尺寸应表达工程师真正会修改的驱动尺寸，不要为了完全定义而把每个端点都从原点标尺寸。矩形用中心/长宽，孔用中心/直径，槽用中心/长宽/间距，回转截面用轴向位置/半径，样条用关键控制点和相切/曲率关系；SolidWorks 显示为灰色的从动尺寸过多时，优先改 primitive 的关系和驱动尺寸策略。
- 关键尺寸来自参数，不要靠手动画出来的偶然几何。
- 特征树可读、可维护。
- 输出文件真实存在且非空。
- STEP / PDF / DXF 等导出不能伪造成功。
- 失败时返回具体失败步骤。
- 不要绕过 SolidWorks 的错误，只为了让任务显示成功。

如果 SolidWorks 报告草图欠定义、特征失败、导出失败，应该让任务失败或带明确 warning，而不是静默继续。

## 8. 当前已验证能力

当前项目已经验证过：

- `mounting_plate`：安装板建模。
- SolidWorks COM 连接。
- 项目内 SolidWorks 零件模板识别。
- 受约束安装板草图。
- `feature_part` 基础 DSL。
- `l_profile_extrude`：L 型支架基础特征。
- `primitive_part`：多特征零件建模。
- 拉伸、拉伸切除、旋转、旋转切除、扫描、扫描切除、放样、放样切除。
- 草图级圆角、倒角轮廓、镜像圆孔、线性圆孔阵列。
- 转换实体引用 / 面 loop 投影、等距实体，并用它们完成上表面等距浅槽切除。
- 草图剪裁 `trim_entities` 已经有 SolidWorks 真机样件通过；稳定路径是用显式 `trim_point` / `pick_points` 表达工程师点击位置，不要只给实体 id。边界剪裁优先使用 `boundary_entities` + `trim_targets`，`inside` / `outside` 都已有真机样件通过；`power` 剪裁可接受 `entity_point_fallback` 降级，只要 SolidWorks 输出成功。
- 草图删除 `delete_entities` 已经有 SolidWorks 真机样件通过；用于删除临时线、辅助线或不应进入后续特征的多余草图段，不要依赖后续特征自动忽略这些几何。
- 开口槽 / 边缘缺口工作流已经有 SolidWorks 真机样件通过；稳定路径是先在生成面上转换/等距引用轮廓作为定位参考，需要时用 `trim_entities` / `delete_entities` 清理参考草图，再创建最终切除轮廓并做完全定义检查，最后执行 `cut_extrude`。
- 圆弧扫描路径和恒定扭转扫描。
- 导向线 / 变截面扫描已经有 SolidWorks 真机样件通过；关键是 profile sketch 里必须用 `pierce` 关系明确连接 path 和 guide curve。
- 多截面放样已经有 SolidWorks 真机样件通过；稳定路径是从原始基准面创建偏置基准面，在每个基准面上建立完全定义的截面草图，再用 ordered `profiles` 调用 `loft`。
- 多截面放样切除已经有 SolidWorks 真机样件通过；稳定路径是先创建实体基体，再建立多个完全定义的切除截面草图，用 ordered `profiles` 调用 `cut_loft`。
- 草图优化样件已经有 SolidWorks 真机样件通过；稳定路径是草图内完成圆角、倒角轮廓、镜像孔和孔阵列，减少后续建模特征数量。
- 生成面选择、命名面、偏置基准面。
- 中文 job、零件、特征、命名面、基准面和输出文件名。
- SLDPRT / STEP / SVG / PDF 输出。
- summary 中记录约束状态、导出状态和错误信息。
- 自然语言建模策略规划 `plan-strategy`，用于在生成 Primitive DSL 前选择建模方式、列出推荐 primitive 和提示缺失参数。
- 自然语言到 `feature_plan.v1` 草案生成 `plan-features`，用于记录 dominant geometry、engineering_context、features、functional_role、feature_intent、modeling_method、sketch_strategy、parameters、references、questions 和 missing capabilities。
- 常见工程特征能进入 Feature Plan planned feature；如果尺寸、目标面或工程语义不足，必须带 `questions` / `missing_capabilities`，不能被静默忽略。
- Feature Plan 到 `primitive_part` 草案编译 `draft-job`，以及自然语言直接执行 `run-nl`。当前真机验证范围包括中文阶梯轴 + 贯穿中心孔、中文安装板 + 四角孔、中文电机安装板 + 两个调节长圆孔、轴类环形槽 / 密封槽 / 退刀槽、沉孔、带拔模角锥形沉头孔、螺纹孔攻丝底孔、居中口袋、居中避让槽、凸台、简单拉伸加强筋：Agent 选择旋转或棱柱策略，生成 revolve / cut_revolve 或 extrude / cut_extrude primitive；长圆孔通过 `add_straight_slot` + `cut_extrude` 生成，沉头孔通过带 `draft_angle` 的 `cut_extrude` 生成锥形座，螺纹孔当前生成 tap-drill 底孔并记录 thread metadata，SolidWorks 输出 SLDPRT / STEP / SVG / PDF，并记录草图 fully constrained。
- 螺纹孔当前还不是完整 SolidWorks Hole Wizard / cosmetic thread 特征；后续如果要用于正式工程图螺纹标注，应继续补 Hole Wizard 或 cosmetic thread executor。

后续修改时，不要破坏这些已验证能力。

## 9. 开发和测试命令

优先使用项目 conda 环境：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe
```

验证 JSON：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\basic\mounting_plate.json
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py validate .\examples\basic\l_bracket.json
```

运行预览后端：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\basic\mounting_plate.json --backend preview
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\basic\l_bracket.json --backend preview
```

自然语言建模策略规划：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py plan-strategy "做一个带中心孔和环形槽的阶梯轴，直径40，长度120"
```

自然语言生成 Feature Plan：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py plan-features "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝"
```

自然语言生成 Primitive JSON 草案：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py draft-job "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢"
```

自然语言直接执行建模：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run-nl "做一个阶梯轴，总长120，最大直径40，左段直径30长度40，右段直径20长度30，中心孔直径10贯穿，材料45钢" --backend solidworks
```

自然语言安装板直接执行建模：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run-nl "做一个安装板，长120宽80厚8，四角孔孔径8，孔边距15，材料6061铝" --backend solidworks
```

检查 SolidWorks：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py sw-check
```

运行 SolidWorks 后端：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\basic\mounting_plate.json --backend solidworks
D:\VibeCading\.conda\VibeCading\python.exe .\mcp-server\server.py run .\examples\basic\l_bracket.json --backend solidworks
```

运行测试：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe -m unittest discover .\mcp-server\tests
```

编译检查：

```powershell
D:\VibeCading\.conda\VibeCading\python.exe -m compileall .\mcp-server
```

## 10. SolidWorks 开发注意事项

SolidWorks COM 状态可能受以下因素影响：

- 软件是否已经启动。
- 是否存在残留活动草图。
- 是否有未关闭的模态窗口。
- 模板路径是否正确。
- 当前活动文档状态。
- 同名文件是否已经被 SolidWorks 打开。

开发时要注意：

- 尽量显式新建文档，不依赖当前活动文档。
- 使用项目模板，不依赖用户系统默认模板。
- 保存前考虑同名文件被占用的情况。
- 不要默认强制关闭 SolidWorks，除非用户确认。
- 如果 COM 进入不稳定状态，先诊断，再请求用户允许重启 SolidWorks。

## 11. 适配其他 CAD 的规则

后续适配 FreeCAD、AutoCAD 或其他软件时：

- 新增 adapter，不要污染核心 DSL。
- 尽量复用 validators。
- 输出 summary 结构保持一致。
- 后端能力不足时明确 warning，不要假装支持。
- 不同 CAD 的实现差异应封装在 adapter 内。

## 12. Agent 对话策略

Agent 面对自然语言 CAD 需求时，应该：

1. 判断任务属于零件、装配、出图、逆向建模还是导出。
2. 先理解零件功能、使用场景、受力/运动/空间约束、装配关系和配合类型。
3. 再提取明确尺寸、孔、材料、数量、导出格式等参数。
4. 把零件拆成有工程意图的特征，而不是只拆成几何形状。
5. 为每个特征选择建模方法和草图策略，并记录为什么这样选。
6. 对缺失的工程关键参数追问。
7. 能合理默认的非关键参数可以自行默认，并在 summary 里记录。
8. 生成结构化 Feature Plan / CAD JSON，而不是自由宏。
9. 执行后检查约束、导出和文件状态。
10. 给用户返回完成结果、产物路径、验证状态和风险。

自然语言转建模时，先判断建模策略，再生成 Feature Plan，最后编译为 primitive：

- 建模策略必须由 Agent 基于功能和工程语义判断，不应要求用户命名 CAD 指令。
- 先判断每个特征的作用：承载、安装、定位、连接、密封、传动、导向、避让、减重、加强、外观或制造处理。
- 再判断该特征与其他零件的配合关系：间隙配合、过盈配合、螺栓连接、销定位、轴承座、密封面、滑动导向、焊接/钣金折弯等。
- 最后选择建模方法和草图策略。建模方法决定草图怎么画，草图不能脱离后续特征命令独立设计。
- 板、块、凸台、筋、槽、口袋类几何优先用拉伸 / 拉伸切除。
- 如果圆角、倒角、对称孔、等距孔阵列可以在草图阶段稳定表达，优先使用草图级 primitive，而不是额外增加实体圆角、倒角、镜像或阵列特征。
- 草图圆角和倒角的默认工程流程是先画基础草图并完成尺寸/几何约束，再调用 SolidWorks 的草图圆角或草图倒角命令；不要默认直接画一个已倒角的固定轮廓。
- 当用户描述“沿已有边线”“从面边界内缩”“密封槽”“边缘浅槽”“轮廓等距”时，优先考虑 `convert_entities` + `offset_entities`，再做完全定义检查和切除/拉伸。
- 当用户描述“开口槽”“边缘缺口”“U 形槽”“从边上切进去的槽”时，优先在目标面上引用外轮廓/等距参考确定位置，清理临时引用后再建立受尺寸约束的切除轮廓并执行 `cut_extrude`，不要把一组未清理的辅助线直接留给后续特征碰运气。
- 轴、套筒、垫圈、旋钮、圆锥、皮带轮、车削类几何优先用旋转。
- 中心孔、环形槽、退刀槽、沉头类旋转减料特征优先用旋转切除。
- 管路、把手、导轨、线缆、沿路径变化的筋位优先用扫描 primitive。
- 曲线孔、弯曲槽、油路、线槽、空心管内孔优先用扫描切除 primitive。
- 导向线和变截面扫描必须显式建立 path/profile/guide 的 `pierce` 关系；preview 通过不等于 SolidWorks 真机建模通过。
- 多截面过渡、异形管、风道、外壳过渡优先用放样 `loft` primitive。截面顺序、截面基准面、是否需要导向线或连接点会直接影响结果，缺失时应让 agent 追问或使用清晰默认值。
- 变径孔、渐缩槽、异形贯穿减料、进出口不同形状的内部通道优先用放样切除 `cut_loft` primitive。切除截面必须落在已有实体的合理范围内，截面顺序不能随意调换。

草图策略必须服务于选定的建模方法：

- 拉伸 / 拉伸切除：使用闭合轮廓，优先用中心矩形、圆、槽、多边形、等距轮廓等可尺寸驱动草图。
- 旋转 / 旋转切除：使用半剖轮廓和明确旋转轴，轴线、台阶、孔、槽的尺寸要符合车削类设计意图。
- 扫描 / 扫描切除：拆成路径草图和截面草图，必须处理 profile 与 path 的穿透/重合关系，导向线扫描还要处理 guide curve。
- 放样 / 放样切除：使用有序截面草图和明确基准/偏置平面，截面顺序、连接方向和尺寸要可解释。
- 面派生特征：当特征依赖已有实体边界时，优先用 `convert_entities` / `offset_entities`，再剪裁或删除临时引用，保留干净的最终轮廓。
- 阵列 / 镜像：如果重复关系本身属于同一草图意图，优先在草图中表达；如果是装配或独立特征语义，再使用特征级阵列/镜像。

不要让 AI 因为用户用了自然语言就直接生成自由宏。AI 应该先把语义拆成主形体、功能特征、草图、基准、路径、截面、约束、尺寸和引用关系，写入 Feature Plan，再由受控编译器生成 primitive。

需要追问的典型情况：

- 关键尺寸缺失。
- 孔位置不明确。
- 孔、槽、面、圆角、倒角等特征的功能作用不明确。
- 使用场景、载荷方向、运动关系、配合类型会影响建模方案。
- 装配基准不明确。
- 出图标准、公差、材料等制造语义不明确。
- 二维图纸逆向存在多种可能三维解释。

不需要为了每个小默认值都追问。优先推进可验证结果。

## 13. 必须记住的两类后续工作流问题

后续继续开发 VibeCading 时，必须持续记住下面两类真实工程场景。它们不是一次性功能点，而是 CAD Agent 能否接近工程师工作方式的核心问题。

### 13.1 不要靠无限增加默认判断来处理复杂建模

实际工程建模中，同一个零件往往有多种建模方式。工程师会根据零件功能、使用场景、装配关系、配合类型、制造方式和后续修改需求，选择最简洁、最稳定、最容易修改的建模方案，而不是机械地套用固定规则。

因此，Skill 里写入的默认判断只能作为第一批工程经验样例，不能变成无限增长的 `if this part name then do that` 规则库。

当遇到不在当前默认判断里的零件，或者复杂的多步骤、多特征零件时，Agent 应该先做建模策略规划，再生成 Feature Plan，最后由编译器生成 primitive：

```text
用户自然语言需求
-> 提取零件功能、使用场景、装配/配合关系、关键尺寸、制造语义
-> 判断 dominant geometry：板类、轴类、壳体、管路、过渡体、装配体等
-> 拆解为有工程意图的功能特征：安装、定位、配合、密封、承载、导向、避让、减重、加强等
-> 为每个功能特征选择建模方法：拉伸、切除、旋转、扫描、放样、阵列、镜像、面引用等
-> 为每个建模方法选择对应草图策略：闭合轮廓、半剖轮廓、路径+截面、有序截面、引用边/等距边等
-> 比较 2-3 个候选建模方案
-> 按工程标准选择最简洁、最可维护、最稳定的方案
-> 生成 Feature Plan
-> 编译为 Primitive DSL / CAD JSON
-> 执行、验证、导出
```

选择“最简洁建模方式”时，不能只看操作数量少不少。应综合判断：

- 特征树是否清晰、可读、可维护。
- 草图是否容易完全定义。
- 关键尺寸是否方便后续修改。
- 特征拆分是否反映零件的功能作用和配合关系。
- 草图策略是否和选定的建模命令匹配。
- 是否符合真实工程建模习惯和制造语义。
- 是否减少脆弱引用和偶然几何。
- 是否能被当前 SolidWorks executor 稳定执行。
- 是否能清楚解释为什么这样建模。

当前已经有轻量级 `strategy_planner` / `modeling_strategy` 元数据层，以及 `feature_plan.v1` 中间层。后续自然语言零件建模应先经过策略选择和 Feature Plan，再编译成 Primitive DSL；不要继续把更多零件名称判断堆进 Skill，也不要新增“某某零件生成器”作为主要扩展方式。正确扩展方向是增加可复用 feature kind 和 Feature Plan compiler 规则。

后续优化重点不是让用户说出 CAD 命令，而是让 Agent 通过功能语义选择命令。只有当功能、使用场景或配合语义不足以判断建模方式时，Agent 才应该追问用户，例如“这个槽是密封槽还是避让槽”“这个孔是定位销孔还是螺栓安装孔”“这个圆角是去锐边还是应力过渡”。

### 13.2 必须支持已有零件的增量修改建模

真实工程师通常不能一次完成建模。零件建好后，经常还要改尺寸、加孔、改槽、替换特征、抑制特征、增加倒角，甚至局部重建。

所以 VibeCading 不能只支持“从零生成一个新零件”。后续必须支持基于已有模型和建模历史的增量修改：

```text
用户提出修改需求
-> Agent 判断修改类型
-> 读取原始 job_spec / summary / SLDPRT / 特征树
-> 找到相关 operation_id、feature_id、sketch_id、dimension_id、named_face 或 reference_plane
-> 生成增量修改计划
-> 修改参数、追加特征、替换特征、抑制特征或必要时重建局部
-> SolidWorks rebuild
-> 验证草图约束、关键尺寸、导出文件和 summary
-> 生成新版本，不默认覆盖旧版本
```

修改已有零件时，应按下面优先级处理：

1. 优先修改已有参数或尺寸。
2. 其次追加独立特征。
3. 再考虑替换局部特征。
4. 必要时抑制或删除特征。
5. 最后才考虑整体重建。

如果零件是 VibeCading 自己生成的，应该优先依赖 `job_spec.json`、`summary.json`、operation id、feature id、命名面和基准面进行可追踪修改。

如果零件是人工在 SolidWorks 中创建的，或者缺少 VibeCading 的结构化历史，Agent 只能先读取特征树、草图、尺寸、面、边和 bounding box，并且必须在关键设计意图不明确时询问用户，不能直接假装理解原始工程意图。

后续推荐增加一种 `edit_part` DSL，用于表达：

- 修改某个尺寸。
- 在某个特征后追加操作。
- 替换某个局部特征。
- 抑制或恢复某个特征。
- 从旧版本生成新版本。

默认规则：修改模型时不要直接覆盖原始结果，应生成 revision，保留旧版本以便回滚和对比。

## 14. 不要做的事

- 不要把“能生成一个外形”误判成“工程建模完成”。
- 不要接受明显欠约束草图。
- 不要生成不可控长宏作为主要实现。
- 不要绕过参数校验。
- 不要伪造 STEP、PDF、DXF 或模型文件生成成功。
- 不要在没有用户确认时关闭用户可能正在使用的 SolidWorks 文档。
- 不要为了支持未来 CAD 软件而破坏当前 SolidWorks-first 主线。
- 不要过早承诺完整二维图纸逆向能力。

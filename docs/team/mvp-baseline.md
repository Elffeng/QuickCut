# 现有 MVP 基线：可以复用什么，还没有实现什么

审计日期：2026-11-06。代码基线：`6cb978d`（`Add Chinese magnetic male narration summary video`）。本文描述该提交的真实实现；团队指南中的多素材、外部空镜库、逐级精剪和剪映工程属于下一阶段目标。

本文供 A–F 六位同事确定起点、复用边界和迁移顺序。代码是事实来源；此前聊天中的旧视频、测试数量或音色描述不应覆盖当前源码和可追溯的成片记录。

## 1. 当前产品实际上能做什么

现有 QuickCut 是一个本地、单源视频的可运行原型。输入一个视频和一个文本要求，可以缓存视频索引，检索若干来源明确的片段，形成 5–60 秒时间线，再由 FFmpeg 输出视频。它已经包含 ASR、可选 CLIP、可选本地 Qwen 规划、基础时间线编辑、逐句本地 TTS、字幕与音频验证。

更完整的中文故事样例通过专用脚本完成：先审阅素材并确定三幕候选范围，再让 Qwen 在每幕中选取镜头，校验选片与排序；旁白经过画面对照修订，逐句生成配音，最后验证视频、字幕与原声。这个样例证明关键技术能够协作，但仍有显式人工编辑配置，不代表任意输入都能全自动得到同等结果。

| 能力 | 当前状态 | 事实依据与限制 |
|---|---|---|
| 一个长视频的索引、检索、剪辑 | 已实现 | `IndexManifest` 和 `Timeline` 都只有一个 `source_video` |
| 多个短视频、多个长视频共同编排 | 待实现 | 当前 `asset_id` 在多数路径中实际保存单源 `shot_id`，缺少全项目素材注册表 |
| 固定窗口粗分段 | 已实现 | 默认 3 秒窗口、3 秒步长，中点抽一帧；不是场景或动作边界检测 |
| 真实关键帧缓存 | 已实现 | 缓存复用前检查 PNG，VLM 输入前进一步解码验证；抽帧失败报错 |
| Whisper 原声转录 | 已实现、可选 | 默认库接口不开启；显式选择 `faster-whisper` 时失败会暴露 |
| CLIP 图文语义检索 | 已有可选适配器 | 默认和已审阅中文样例使用颜色直方图，不能把样例效果归因于 CLIP |
| 外部空镜库与联合召回 | 待实现 | `external` 仅存在于来源枚举；没有外部库导入、索引、检索和混合渲染闭环 |
| Qwen 真实看图选择镜头 | 已实现、可选 | 候选关键帧带 ID/源时间；严格校验来源、数量、预算和三幕关系 |
| 逐级事件→镜头→边界精剪 | 待实现 | 通用路径仍以固定窗口和规则补齐为主，没有完整层级式细化 |
| 逐句中文配音与字幕定时 | 已实现 | macOS `say`，中文默认 Reed，逐句 WAV 测量和时间适配 |
| replace / trim / reorder | 已实现基础操作 | 不会自动重建故事、旁白、字幕或刷新所有派生结果 |
| 剪映可编辑草稿导出 | 未实现 | MP4 和 SRT 是媒体产物，不等价于剪映多轨工程 |
| 通用任务队列、断点续跑、模型调度 | 待实现 | FastAPI/Uvicorn 是入口层；当前重任务主要在请求或脚本中同步执行 |

主要依据：[数据结构](../../quickcut/types.py)、[核心索引与剪辑](../../quickcut/core.py)、[故事规划](../../quickcut/story.py)、[中文样例说明](../chinese-summary.md)。

## 2. 两条现有处理路径必须区分

### 路径 A：通用 API / CLI / Gradio 原型

```text
单个源视频
  → build_index：固定窗口 + 关键帧 + 可选 ASR + 向量缓存
  → localize：视觉匹配 + transcript 关键词匹配
  → Timeline
  → 可选 basic 故事规划
  → trim / replace / reorder
  → render 或 render-story
```

- CLI 的 `basic` 和 API `/basic` 调用 `build_basic_vlog`；`planner=ollama` 才会显式使用本地 Qwen。默认 planner 是 `deterministic`。`auto` 遇到模型不可用或非法响应可降级，不能将降级输出统计为一次成功的 Qwen 决策。
- Gradio 的 **Index + localize** 调用的是 `build_index → localize`，没有调用 `build_basic_vlog`。勾选 **Local narration** 只控制渲染已有旁白，不能代替故事生成。
- 通用故事构建器仍保留按源时间修复顺序、填充邻近窗口、重新分配三幕和模板补文的代码。即便 `plan_with_ollama` 已严格校验原始响应，后续构建器仍可能调整它。因此不能笼统声称通用成片顺序完全来自 Qwen。
- `localize` 低分时返回 `coverage=abstain`，但 `basic` 可以继续使用规则回退镜头。团队下一阶段应把“拒绝、降级、需要更多素材”作为明确状态。

入口：[CLI](../../quickcut/cli.py)、[API](../../quickcut/api.py)、[Gradio](../../quickcut/ui.py)。

### 路径 B：已审阅的中文故事样例

```text
重新索引真实素材
  → 审阅候选区间、三幕和关键因果镜头
  → 每幕一张编号接触表，分别调用 Qwen
  → 校验选片；必要时让 Qwen 自己修正遗漏和顺序
  → 保存模型原文、图片哈希和纠正过程
  → 对照画面编写/修订中文句子与时间区间
  → 逐句 TTS，保存实测定时后的时间线
  → 原声参考、字幕烧录、配音混音、成片验证
```

这里的三幕配置与旁白不是自动生成后未经审阅就交付。`act_config.json` 明确规定候选区间、每幕数量和必选关键窗口；`editorial_cues.json` 明确保存画面对照后的中文文案与字幕区间。重新运行模型可能选择不同镜头，因此必须重新审阅 cue 是否仍匹配，不能把旧 cue 无条件套到新选择上。

仓库记录的样例为：源素材 212 个真实关键帧，39 个候选窗口，三幕选择数 6 / 8 / 6，共 20 个窗口，成片 58.5 秒。三幕配置共指定 9 个必选关键窗口。它使用 `fallback-color-histogram` 索引；ASR 没有识别到可用源对白。模型看图和人为故事约束才是这个样例叙事组织的主要依据。

该路径拒绝非法、重复、越界或遗漏关键事件的选择，保留模型的纠正记录；没有通过静默补片来伪装成完整模型方案。它是下一阶段 C/D/F 最值得复用的可追溯实现。

文件：[样例工作流](../../scripts/chinese_summary.py)、[分幕模型规划](../../scripts/plan_summary_acts.py)、[三幕配置](../../examples/chinese_summary/act_config.json)、[审阅后的旁白](../../examples/chinese_summary/editorial_cues.json)、[保存的模型选择记录](../../examples/chinese_summary/qwen_selection.json)。

## 3. 真实技术选型与默认值

下表记录源码中当前配置，不是对未来模型效果的承诺。新增模型时应保留旧适配器供回归比较。

| 模块 | 当前技术 | 默认 / 样例参数 | 负责同事 |
|---|---|---|---|
| Python 包 | setuptools、dataclass | 声明 `Python >= 3.10`，包版本 `0.1.0` | 全员；D 管理协议迁移 |
| 媒体处理 | FFmpeg；可回退到 `imageio-ffmpeg` 自带二进制 | 关键帧宽 256；渲染 H.264、yuv420p | A / F |
| 默认视觉特征 | Python 颜色直方图 | 64 个 RGB bins + 8 个亮度 bins | B |
| 可选语义视觉编码 | OpenCLIP + PyTorch | `MobileCLIP-S2`，pretrained=`datacompdr` | B |
| 原声 ASR | faster-whisper | `tiny`、`cpu`、`int8`、beam 1、VAD 开启 | A |
| 本地 VLM | Ollama HTTP 接口 | `qwen2.5vl:3b`，默认 `http://127.0.0.1:11434` | C |
| VLM 视觉输入 | Pillow 接触表 / 单帧 | 通用接触表默认 12 格；专用分幕每次 1 张，最多 24 格 | C |
| 输出约束 | JSON Schema + Python 二次校验 | 允许的 shot IDs、数量、预算、三幕分区 | C / D |
| 本地 TTS | macOS `say`，无 say 时尝试 `espeak` | 中文逐句默认 `Reed (中文（中国大陆）)`、rate 145 | E |
| 字幕 | SRT + FFmpeg libass | 当前中文样例使用 PingFang SC | E / F |
| 音频中间格式 | PCM WAV / MKV | 48 kHz；配音单声道、原声参考立体声 | E / F |
| 最终音频 | AAC | 48 kHz、双声道、192 kbps | F |
| 服务入口 | FastAPI + Uvicorn | 本地 HTTP API | D |
| 工作台 | Gradio | 单视频、基础编辑和渲染 | D |
| 配音覆盖检查 | 本地 faster-whisper | 样例使用 `small`、中文、词时间戳 | E / F |

OpenCLIP 适配器使用归一化图像/文本向量和余弦相似度；当前代码没有显式 GPU 迁移或向量数据库。`auto` 可以回退为直方图。颜色词典主要是英文，无已知颜色词时 fallback 给固定低分，不能将中文输入支持理解为中文语义检索已完成。

当前融合分数是：

```text
score = visual_score + 0.35 × query_token_overlap_with_transcript
```

transcript 项是词面交集，不是文本语义模型，也没有专门中文分词。`threshold=0.22` 是现有默认参数，不能未经验证直接跨模型复用。

VLM 读取关键帧，不是完整连续视频；对动作方向、角色关系、因果结果仍可能判断错误。格式校验通过只能证明返回数据可执行，不能证明叙述正确。

来源：[依赖声明](../../pyproject.toml)、[视觉编码](../../quickcut/encoder.py)、[ASR](../../quickcut/asr.py)、[VLM](../../quickcut/vlm.py)、[声音处理](../../quickcut/voice.py)。

## 4. 逐句配音与原声处理的可复用能力

当前 `synthesize_timed_narration` 已经能将每句 TTS 合成独立 WAV，去除首尾静音，测量真实时长，再用保持音高的 `atempo` 适配目标区间。默认句末停顿为 0.18 秒。每句的原始时长、tempo、实际放置区间与 speech end 写入故事元数据。

若字幕文本拼接后与旁白完全一致，函数保留这些显式 cue 的视觉时间安排；否则按每句语音的实测长度分配总时长。不能把这一步理解为已自动理解动作并完成语义对齐：显式 cue 仍需要 C/D 的故事板依据。

当前混音保留原声，固定增益 0.30；旁白归一化到 −18 LUFS，再与原声混合并限幅。片段中间音频使用 PCM，减少每个剪辑点引入 AAC priming 的问题。剪辑、拼接、字幕和混音阶段都统一处理时间戳。

下一阶段 E 应把音色、时长、音频和字幕作为独立 `VoicePackage` 输出；D 决定成片时间，F 执行混音和导出。当前函数直接修改 `Timeline.captions` 和 `Timeline.story` 的副作用需要在迁移时明确处理。

当前没有配音节奏异常的完整业务决策，例如超长句子应改文案还是延长镜头；也没有独立角色声线、对白口型同步、音乐自动选曲或复杂音效设计模块。

## 5. 文件到六人职责的映射

“主责”表示建议的下一阶段维护归属，不意味着现在应由多人同时编辑同一个文件。

| 现有文件 | 可复用内容 | 建议主责 | 迁移时注意 |
|---|---|---|---|
| [core.py](../../quickcut/core.py) 的 probe / index | 探测、抽帧、缓存、转录关联 | A | 从单文件拆成素材注册与项目聚合；代理素材另建引用 |
| [asr.py](../../quickcut/asr.py) | 本地 ASR、sidecar、时间关联 | A | 输出语言、模型版本、失败状态；与媒体缓存分开失效 |
| [encoder.py](../../quickcut/encoder.py) | 直方图、OpenCLIP 适配器、向量归一化 | B | 同一索引必须使用一致编码器指纹；评估中文召回 |
| [core.py](../../quickcut/core.py) 的 localize | 基础召回和排序 | B | 增加联合素材池、外部空镜、结构化检索需求 |
| [vlm.py](../../quickcut/vlm.py) | 视觉 payload、约束生成、模型证据、严格校验 | C | 保留原始响应与模型决策；区分人工规则与模型输出 |
| [story.py](../../quickcut/story.py) | 通用故事构建原型 | C / D，先拆接口再分别维护 | 规则排序、补段、文案模板属于历史实现，不作为新架构默认行为 |
| [plan_summary_acts.py](../../scripts/plan_summary_acts.py) | 分幕看图与模型自纠正 | C | 将硬编码三幕/本地字体/模型参数改为配置；保留证据 |
| [types.py](../../quickcut/types.py) | 当前数据类 | D | 新协议版本与旧 JSON 适配，不能直接改变字段含义 |
| [ui.py](../../quickcut/ui.py)、[api.py](../../quickcut/api.py)、[cli.py](../../quickcut/cli.py) | 基础入口与编辑交互 | D | 接入新编排服务；编辑后重新计算受影响派生物 |
| [voice.py](../../quickcut/voice.py) 的 TTS / timing | 本地逐句语音、WAV 时长、字幕 | E | 合成结果独立交付，明确语速过度调整状态 |
| [core.py](../../quickcut/core.py) 的 render、[voice.py](../../quickcut/voice.py) 的 burn / mix | 画面编码、原声保留、字幕烧录、混音 | F | 每个片段按 asset_id 解析源文件，支持多源规格归一化 |
| [verify_chinese_summary.py](../../scripts/verify_chinese_summary.py) | 流信息、解码、字幕、原声回归验证 | F | 扩展多素材、草稿导入/重定位验证 |
| [check_narration_coverage.py](../../scripts/check_narration_coverage.py) | 已知末句与词时间戳检查 | E / F | 不把 Whisper 幻觉尾句作为覆盖成功 |

## 6. 新同事的最小启动顺序

以下命令在仓库根目录执行。优先沿用团队已有虚拟环境；新机器可自行创建 `.venv`。依赖文件目前主要使用版本下限，没有完整锁文件；第一次成功安装后应记录解释器、库版本、FFmpeg build 和模型版本，供其他同事复现。

### 6.1 先跑不依赖模型权重的链路

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[server,runtime,ui,dev]'
QUICKCUT_ASR=none python scripts/smoke_demo.py
python -m pytest -q
```

`smoke_demo.py` 自己生成简单颜色视频，验证“索引—检索—改剪辑点—渲染—不支持请求”链路；它不能验证真实语义、故事质量和中文声音。模型响应的单元测试主要通过 mock 验证接口与约束；真实模型质量需另外验收。媒体测试依赖相应本地二进制和 Python 库，实际执行结果以测试输出为准。

启动现有界面或 API：

```bash
python -m quickcut.ui
uvicorn quickcut.api:app --host 127.0.0.1 --port 8000
```

两条服务命令分别在终端运行。Gradio 当前仍是单源检索工作台；API 提供 `/index`、`/localize`、`/basic`、`/edit`、`/render` 和 `/render-story`。

### 6.2 启用 ASR、真实 VLM 和可选 CLIP

```bash
python -m pip install -e '.[asr]' 'pillow>=10' numpy
ollama pull qwen2.5vl:3b
```

先确保 Ollama 本地服务可访问；安装和拉取权重需要网络，完成后推理可以本地执行。Whisper 首次运行也可能下载权重。离线模式只适用于模型已缓存的机器。

基础真实素材命令（先把自己的视频放到 `inputs/source.mp4`）：

```bash
quickcut index inputs/source.mp4 --cache-dir cache --encoder fallback --asr faster-whisper
quickcut basic inputs/source.mp4 'a complete forest journey 45 seconds' \
  --cache-dir cache --encoder fallback --asr faster-whisper \
  --planner ollama --duration 45 --timeline outputs/basic.json \
  --render --output outputs/basic.mp4
```

这条通用命令可能因严格模型校验失败而报错，应该查看真实响应或缩小候选，不应为了“演示成功”静默编造镜头。中文故事的受控复现请按[中文样例说明](../chinese-summary.md)运行。

需要测试 CLIP 的同事另外安装并显式选择编码器：

```bash
python -m pip install -e '.[ml]'
quickcut index inputs/source.mp4 --cache-dir cache-openclip \
  --encoder openclip --asr faster-whisper --force
```

不同模型配置暂时使用独立缓存目录；不要用 fallback 索引直接执行 OpenCLIP 检索。实际权重名或平台兼容性有问题时，应记录失败并调整配置，不得悄悄把 fallback 成绩当成 CLIP 成绩。

### 6.3 环境与平台限制

- `pyproject.toml` 声明 Python 3.10 以上；当前开发机的 `.venv` 使用 Python 3.14，不代表所有可选依赖在所有 Python 版本都已测试。新同事应以团队跑通的环境矩阵为准。
- Python 依赖由 extras 安装；Ollama、FFmpeg/ffprobe、macOS 语音与系统字体不由 `pip install` 一并提供。`all` extra 不包含 `dev` 测试依赖。
- 基础 FFmpeg 可以来自 `imageio-ffmpeg`；字幕烧录必须有 libass `subtitles` filter。严格验证脚本需要真正可执行的 `ffprobe`，不能只依赖媒体时长正则解析。
- Reed 中文男声属于 macOS；Windows/Linux 路径会尝试 espeak，但声音效果不能自动视为等价。下一阶段 E 必须明确支持的平台与替代本地 TTS。
- 已审阅分幕脚本使用 macOS Arial 字体路径，字幕样例使用 PingFang SC；迁移平台时需要配置字体。该脚本尚未实现完整跨平台封装。
- `inputs/`、`outputs/`、`cache/`、`tmp/` 和视频文件受 `.gitignore` 排除。仓库克隆得到代码与样例配置，不会自动获得原视频、模型、缓存或此前成片。

## 7. 当前缓存、时间线和编辑中的迁移陷阱

1. **单源 ID 不能直接当全局素材 ID。** 当前所有片段都从 `Timeline.source_video` 截取，渲染器不根据每个 item 的 asset_id 寻找不同文件。需要素材注册表后才能支持多源；先合并视频再冒充一份源会损失独立来源与精修能力。
2. **缓存指纹不够完整。** 现有 index_id 包括路径、大小、mtime、窗口/步长、encoder 名和 ASR backend 名，但没有完整 CLIP checkpoint、ASR model、语言或预处理版本。换模型/参数时应显式重建；A/B 应新增完整算法指纹。
3. **时间单位与轨道结构是旧约定。** 现在是浮点秒、顺序列表，duration 为各 item 长度之和；还没有独立轨道、输出位置、转场重叠或素材映射。新协议的整数时间和多轨结构需版本化转换，不能对旧字段直接换单位。
4. **精剪后派生物会过期。** `update_timeline` 修改 items，但不更新 story、narration、captions。D 应建立 revision 和局部失效机制，E/F 拒绝使用旧 revision 的结果。
5. **通用 CLI 保存时间过早。** `basic` 在 `render_story_timeline` 前写出 JSON；TTS 会在渲染期间更新字幕与音频时序元数据，因此该 JSON 未必包含最终语音时序。专用中文 render 脚本在逐句合成后保存，后者应成为新版的交付方式。
6. **模板补文不等于故事完整。** 通用 `_complete_narration` 仍有文案长度和模板填充逻辑，可能生成“开场交代环境”这样的制作说明。C 的新故事板应直接围绕画面与用户意图写脚本，E 应允许时长反馈，不靠无信息句子撑满一分钟。
7. **片尾过滤目前不是分类模型。** 通用路径使用 `max(总时长×80%, 总时长−120s)` 的尾段规则；专用样例使用审阅过的 494 秒边界。这不能直接迁移为任意素材的片尾事实。
8. **画面和语音覆盖需要分别验证。** `PTS=0` 证明时间起点一致；音频流存在不证明原声还在；Whisper 最后一个时间戳不保证最后一句真实存在。F 要保留原声参考与独立旁白，E/F 检查已知末句，C/D 检查画面语义。
9. **JSON Schema 约束不是理解能力。** 模型可以合法返回 ID 却误认角色或遗漏因果。VLM 的原文、实际输入图片、人工约束和后续修订都应可追溯。
10. **当前在线入口还是原型。** API 上传与渲染主要同步处理，尚无任务状态、取消、容量控制或用户隔离；不能仅因使用 FastAPI/Uvicorn 就称为生产级推理平台。

## 8. 下一阶段的复用建议

保留旧链路作为回归基线，将现有函数封装为新模块适配器，再迁移数据协议。优先复用关键帧校验、ASR、视觉编码适配、Qwen 证据记录、逐句配音和音频验证；重点重构多素材注册、层级分段、结构化需求检索、时间线编排以及可编辑工程输出。

先让一份人工编写的多源故事板能够通过 D/E/F 输出可编辑工程，再把 C 的模型结果替换进去，能让“模型效果”和“工程是否可执行”分别被验收。B 的空镜库同样应先以可追溯的静态候选接入，再逐步提高自动召回质量。

本次基线文档没有重新运行模型或修改运行时代码。历史样例的 82 项测试与音视频指标来自[已保存样例说明](../chinese-summary.md)；本轮指南发布时的实际测试结果由主文档的验证记录另行说明。

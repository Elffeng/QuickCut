# 团队接口黄金样例（设计契约 0.1.0）

这套文件让 A–F 六位同事在上游实现完成之前，使用同一份输入输出开发模块。它是下一阶段的**数据协议提案和离线测试夹具**，不是当前 `quickcut` CLI/API 已支持的格式，也不是可导入剪映的真实草稿。

`bundle.json` 封装八份相互引用的文档：`Brief`、`AssetManifest`、`RetrievalRequest`、`CandidateSet`、`StoryPlan`、`VoicePackage`、`EditTimeline` 和 `ExportManifest`。统一 `schema_version: "0.1.0"`、项目 ID、整数微秒和版本引用。设计说明见 [接口协议](../../docs/team/contracts.md)。

样例讲述“离开城市，到林间散步，最后坐下休息”，包含 3 个短视频、1 个长视频、2 个外部空镜的元数据。最终时间线长 18 秒，包含主素材、空镜、独立原声轨、逐句配音轨和可编辑字幕轨。未使用的素材也保留在素材清单中。

## 检查样例

从仓库根目录运行，Python 3.10+ 标准库即可，无需下载模型：

```bash
python examples/team_contracts/validate.py
python examples/team_contracts/validate.py examples/team_contracts/bundle.json
python examples/team_contracts/validate.py --self-test
```

成功时输出 `PASS: contract fixture ...`。检查内容包括必需文档、版本引用、ID、整数时间区间、素材范围、候选与故事引用、时间线时长、单轨重叠、配音与字幕文本/时序一致、包内路径等。它**不是完整 JSON Schema 验证器**，不检查实际画面语义、文件编解码、TTS 质量或剪映导入能力。

`--self-test` 还会构造五个错误副本，确认过期引用、越界路径、越界源时间、字幕不一致和虚假导出成功声明被拒绝，不会改写样例文件。

## 占位媒体与证据边界

- 顶层和每份文档的 `fixtures_only` 均为 `true`；`media/...` 文件均为占位路径，仓库没有附带这些素材。
- 文件摘要使用 `fixture:` 前缀，不能当作真实内容哈希。
- 配音时长是为了说明对接关系而构造的样例数据，不是一次真实 TTS 测量记录。
- `ExportManifest.status` 是 `not_exported`，`target_app.version` 是 `UNVERIFIED`，没有宣称导出或导入成功。

A 或 E 接入真实媒体后，应使用实际文件和哈希替换占位数据；F 只有完成目标版本的真实导入验收，才能将导出状态写成 `verified_import`。生产数据验证应拒绝 `fixtures_only: true`。

## 每位同事如何使用

| 同事 | 开发时使用 | 首轮输出 |
|---|---|---|
| A | 清单中的六个媒体槽位；自备对应合法素材 | 真实 `AssetManifest`、关键帧与 transcript |
| B | `AssetManifest` 和 `RetrievalRequest` | `CandidateSet`；保留来源及空结果 |
| C | `Brief` 和 `CandidateSet` | `StoryPlan`；事件证据与空镜职责可追溯 |
| D | `StoryPlan` 和 `VoicePackage` | `EditTimeline`；负责全局时间和轨道安排 |
| E | `StoryPlan.narration_cues` | 逐句 WAV、实测时长、局部字幕及 `needs_retime` 状态 |
| F | `EditTimeline`、两个媒体清单 | 实际预览、工程包和真实导入结果 |

不要把样例中的镜头选择、固定时长或声音指标直接当作业务规则。联调时可以换素材、故事和节奏，但必须保留协议所表达的来源、时序与版本关系。

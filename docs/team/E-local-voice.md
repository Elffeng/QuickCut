# E：本地配音与字幕交付说明

## 本次解决的问题与接收方

E 将 C 批准的逐句文本转换为独立 WAV、实测时长、局部字幕和超时反馈。D 接收 VoicePackage 并统一编排时间；F 根据 D 冻结的时间线解析生成音频并独立混音。E 不修改故事、镜头、原声或全局时间线。

本次覆盖任务书全部 P0；P1 的神经 TTS、声音克隆、多角色和情绪控制未列入本次实现。旧 `voice.py` 保持兼容，新入口显式返回 VoicePackage，不调用会修改旧 Timeline 的 `synthesize_timed_narration`。

## 协议与入口

- 输入：StoryPlan，`schema_version: "0.1.0"`；也可读取黄金 bundle 中的 StoryPlan。
- 输出：VoicePackage，`schema_version: "0.1.0"`，`owner: "E"`，`timing_authority: "D"`。
- Python 接口：`quickcut.voice_package.build_voice_package(story, project_root, ...)`，返回新字典，不修改输入。
- CLI：`python -m quickcut.voice_package`。只依赖 Python 3.10+；真实模式另需 FFmpeg 和系统 `say` 或 espeak/espeak-ng。`--capabilities` 列出本机实际可用音色、语言和参数。
- macOS 已验证：Reed（中国大陆中文），145 语速，48 kHz 单声道 PCM16。espeak 适配接口已实现，尚未做该平台的真实媒体试听验收。
- 本地合成不使用云端推理。可选 Whisper 核验首次使用需要下载模型，之后可离线运行。

运行目录所有媒体 URI 均相对于 `--root`，使用 `/`，无个人绝对路径。资产 ID 使用项目、句子和合成配置的哈希，前缀为 `generated-voice-`；D/F 需与 A 的清单合并并检查 ID 唯一性。

## 从仓库根目录复现

协议模式使用测试音，不是配音，所有产物 `fixtures_only: true`：

```bash
python scripts/demo_voice_package.py --fixture --root outputs/e-fixture
```

真实模式产生三条中文 WAV、单句改稿版本、指定区间适配版本与验证结果：

```bash
python scripts/demo_voice_package.py --root outputs/e-real
```

单次调用：

```bash
python -m quickcut.voice_package --capabilities
python -m quickcut.voice_package --story examples/voice_package/story.json \
  --config examples/voice_package/config.json --root outputs/e-once \
  --mode measure --revision 1
```

此样例第三句故意超时，所以单次命令退出码 **2** 是预期结果，音频和 JSON 仍完整写出；demo 会检查该预期后返回 0。`ready` 返回 0；需要重定时、部分成功、失败均返回 2，消费方必须同时检查 JSON。默认输出 `voice_package-r1.json`，已有文档禁止覆盖，下一轮使用新 revision 或新的输出名。旧 WAV 内容寻址保存，不覆盖旧版媒体。

指定区间适配请求：

```bash
python -m quickcut.voice_package --story examples/voice_package/story.json \
  --config examples/voice_package/config.json --request examples/voice_package/fit-request.json \
  --root outputs/e-fit --mode fit --revision 3
```

原样回显请求的 `project_id`、`story_plan` 精确引用、`timeline` 精确引用、`cue_ranges` 和 `iteration`。第一次测量不需要 EditTimeline。适配轮次必须为 1 或 2，第三轮拒绝，交 D/C 处理。D 必须核对回复中的时间线引用与当前未完成请求完全一致；E 无法从一个旧请求得知 D 在另一台机器上是否又产生了新版。

局部重生成：更新 StoryPlan revision 后，将旧 VoicePackage 通过 `--previous` 传入，并增加 `--revision`。同一 `--root` 下逐句按批准文本、引擎/系统版本、实际音色、语言、语速及静音处理版本复用缓存；文件哈希不一致则重新生成。`cue_overrides` 可单独更改某句 voice/rate。

## 音频处理和时长语义

- 从真实 PCM 样本数测量整数微秒时长，不使用字数估计。
- `engine_duration_us` 为引擎转换出的完整 WAV 时长；`raw_duration_us` 为仅移除边界静音后的语音时长。
- 仅在音频两端移除约 -50 dBFS 以下的静音，保留 40 ms 保护边界，句内停顿不裁切。全静音返回 `NO_SPEECH`；引擎错误返回 `TTS_FAILED`，不会用静音占位伪装成功。
- 默认追加 180000 微秒句末留白，可设为 0；`duration_us` 是最终完整 WAV（含留白）的实测时长，`speech_end_us` 不含追加留白。
- `measure` 完全不变速，只报告是否符合预算；`fit` 仅在需要时使用保音高 atempo。默认允许 1–1.15 倍速，配置硬上限 1.25；不为填满空白而减速。适配后的真实文件重新测量，仍超时则返回 `needs_retime`，不截去末词、不用 atrim 强行凑时长。
- `duration_budget_us` 是当前预算或 D 指定区间的长度；超预算时也保存完整 WAV。D 先延长合法画面/空镜，仍不足则由 C 改稿。
- `local_subtitles[].range_us` 是相对该句音频起点的半开区间；字幕采用批准的原文，覆盖实际处理后的语音，不包含追加句末留白。每句另附局部 SRT。D 负责映射到成片，F 保留可编辑文字轨，不能将多条局部 SRT 直接拼成全局 SRT。
- 时长由 48 kHz 样本量化，微秒舍入最多约半个样本；SRT 仅用于毫秒精度预览，JSON 微秒记录是交接依据。

## 状态、错误与版本失效

包状态：全部可用且符合预算为 `ready`，存在超时为 `needs_retime`，部分合成失败为 `partial`，全部合成失败为 `failed`。空旁白列表产生空 `ready` 包。每句保留独立的 `fit_status`，失败句没有伪造音频资产。

错误信封包含 `stage: voice`、项目 ID、受影响 cue ID、错误码、说明及下一步负责人。输入过期为 `STALE_INPUT_REVISION`，未知音色为 `UNSUPPORTED_VOICE`，不支持的情绪控制为 `UNSUPPORTED_PARAMETER`，非法合同为 `INVALID_INPUT`，输出已存在为 `OUTPUT_EXISTS`。超时返回 `VOICE_NEEDS_RETIME` 给 D；合成失败由 E 处理。

改变文本、音色或适配配置会改变该句生成资产；`invalidated_cue_ids` 列出改变/删除/失败的句子，`alignment_invalidated` 提醒 D 重新对齐。即使其他句 WAV 可以复用，旧版 VoicePackage 仍不能冒充新版脚本的结果；新包重新引用批准的 StoryPlan revision，音频和字幕记录包含同一脚本引用。

## 对现有契约的兼容说明

核心字段、时间单位、局部字幕及引用结构沿用黄金样例。新增可选字段包括 request、mode、script_input、srt_uri、cache_key/cache_hit、speech_end_us、sentence_pause_us、engine_duration_us、quality、errors、invalidated_cue_ids、alignment_invalidated；消费者可忽略诊断字段，但必须识别失败与 needs_retime。

黄金 `examples/team_contracts/validate.py` 验证的是已完成编排的固定成功 bundle，其“每句必须小于预算”检查不能用来否定 E 正常返回的超时反馈。本次不修改共享协议或固定成功夹具。E 的独立验证器支持真实超时包，并检查实测文件、哈希、字幕和脚本引用：

```bash
python scripts/verify_voice_package.py --story examples/voice_package/story.json \
  --package examples/voice_package/real/voice_package.json \
  --root examples/voice_package/real
python examples/team_contracts/validate.py --self-test
```

接口未改变共享核心字段；请 D/F 审核上述可选扩展，并在其集成中阻止 failed/partial/needs_retime 包进入最终导出。跨模块版本接受规则仍由 D 执行。

## 交付样例与证据

`examples/voice_package/` 包含原始手写脚本、配置、实际 WAV/局部 SRT、测量包、改稿包、适配请求及回复、fixture 包与验证日志。手写脚本是 TTS 测试，不声称已经验证对应画面事件；真实合成包与纯测试音包分开标记。

真实初始结果：cue-01 为 904021 微秒，cue-02 为 2862729 微秒，cue-03 为 11782479 微秒；第三句预算 1000000 微秒，明确 needs_retime。适配示例第一句 tempo 约 1.08063，完整 WAV 为 841667 微秒，符合 850000 微秒区间。修改第一句后仅 cue-01 改变，另外两句缓存命中。

自动化测试覆盖边界静音与句内停顿、超时保留完整声音、有限变速、版本/项目/请求检查、改稿与单句换声、缓存损坏、部分失败、全失败、静音、路径越界与输出不可覆盖。全仓库结果及测试环境见 `evidence/pytest.txt`、`evidence/requirements-tested.txt`。运行：

```bash
python -m pip install -e '.[dev,runtime,server]' pillow
python -m pytest -q
```

可选本地 ASR 核验保留原始识别结果，绝不回写字幕：

```bash
python -m pip install 'faster-whisper==1.2.1'
python scripts/check_voice_package_asr.py --model small \
  --root examples/voice_package/real --package examples/voice_package/real/voice_package.json \
  --report outputs/asr-small.json
```

Whisper base/small 的原始响应均已保存：长句 small 相似度约 0.977、末尾文字检出；短句及正常句存在识别错误和繁体字输出，未将它们标成逐字 ASR 通过，也没有据此替换批准字幕。当前样例峰值未削波，文件与局部字幕检查通过；声音自然度、发音的最终确认仍需实际试听，ASR 不等于自然度验收。未完成 D 的真实编排联调、F 的原声混音和剪映实机验收，这些属于后续消费者与全组验收，不能以 E 的独立成功样例代替。

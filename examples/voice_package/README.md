# E 模块交付样例

使用与交接说明见 [E-local-voice.md](../../docs/team/E-local-voice.md)。

- `story.json`：三句手写中文，第三句故意只有 1 秒预算。
- `config.json`：真实测试音色及适配配置。
- `real/voice_package.json`：真实中文初始测量；`real/audio/narration/` 内是独立可播放 WAV。
- `real/voice_package-r2.json` 与 `story-r2.json`：只改第一句，其余 WAV 复用。
- `fit-request.json` 与 `real/voice_package-fit.json`：精确引用 D 的请求和保留末词的温和适配结果。
- `fixture/`：测试音输出，`fixtures_only: true`，不代表中文语音。
- `evidence/`：媒体哈希与时序校验、测试日志、本地 ASR 原始响应及环境记录。

所有 URI 相对于对应的 `real/` 或 `fixture/` 项目根目录。真实数据约几 MB，媒体已随本目录提供，不需要访问某位成员的个人素材目录。运行时自动建立的缓存 WAV 是仅处理边界静音后的原始配音（遵循仓库规则不纳入 Git）；随交付提供的 narration WAV 是加上句末留白及可选温和变速后的交接音频。首次在新机器运行会建立缓存，后续单句修改才可命中本机缓存。

复现成功、超时、改稿、适配和故意失败：

```bash
python scripts/demo_voice_package.py --fixture --root outputs/e-fixture
python scripts/demo_voice_package.py --root outputs/e-real
```

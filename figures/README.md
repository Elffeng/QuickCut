# QuickCut 团队架构图

这些图描述下一阶段的目标架构，不表示所有模块已经实现。完整说明见[项目指南](../docs/PROJECT_GUIDE.zh-CN.md)。

| 图 | 可预览 Markdown | Mermaid 源码 | 已渲染图片 |
| --- | --- | --- | --- |
| 由粗到细的总体工作流 | [说明与图](quickcut-coarse-to-fine.md) | [.mmd](quickcut-coarse-to-fine.mmd) | [PNG](quickcut-coarse-to-fine.png) |
| 六人交付关系 | [说明与图](quickcut-team-handoffs.md) | [.mmd](quickcut-team-handoffs.mmd) | [PNG](quickcut-team-handoffs.png) |
| 配音与画面定时反馈 | [说明与图](quickcut-voice-retiming.md) | [.mmd](quickcut-voice-retiming.mmd) | [PNG](quickcut-voice-retiming.png) |

GitHub 可以预览 `.md` 内的 Mermaid，PNG 可直接用于文档或汇报。修改时同步更新 `.mmd` 与对应 `.md` 中的代码块，再重新渲染 PNG。主指南引用 PNG，不需要读者安装渲染工具。

本次使用 Mermaid CLI `12.2.0` 进行语法与渲染检查。通用重绘命令：

```bash
npx -y @mermaid-js/mermaid-cli@12.2.0 \
  -i figures/quickcut-coarse-to-fine.mmd \
  -o figures/quickcut-coarse-to-fine.png \
  -b white --size 1800 -s 1.5
```

Mermaid CLI 需要本地可用的浏览器运行时；已有 Chrome 时可通过 `-p` 指定 Puppeteer 配置，避免额外下载。字体使用本机中文字体，跨平台重绘时应确认中文字形正常。语法依据：[Mermaid 官方流程图说明](https://mermaid.js.org/syntax/flowchart.html)。

校验与人工可视检查记录见[图形检查报告](verification.md)。

# 第 16 章：方法论

一次性能调查要能复查、复现并顺利交接，至少需要交代清楚四件事：现象如何定义、现有证据能证明什么、App、系统与测试环境各自影响哪一段，以及修复后如何验证。

前面的章节分别讲解了系统机制与分析工具；本章则把问题定义、责任归因、指标体系、对照实验、线上监控、源码阅读和团队协作整合进同一套调查流程。最后的 16.8 节专门介绍 AI 编码能力评测，梳理它的任务集、验证器与统计口径——这部分衡量的是编码代理完成工程任务的能力，与 App 运行时性能实测面向不同的目标。

<!-- gracker-diagram: ch16-readme-01-investigation-evidence-loop -->
![从问题定义走到发布验证](../../assets/diagrams/ch16/ch16-readme-01-investigation-evidence-loop.png)

图：先明确现象和指标，再结合现场与源码检验归因，最后通过对照实验与发布监控验证修复。设备分级策略按具体场景验证；AI 编码评测采用独立的任务与验证协议，与 App 性能实测分属不同维度。

## 内容索引


- [16.1 Android 性能优化原则、实证与治理](01-performance-principles-evidence-governance.md)
- [16.2 如何区分系统问题和 App 问题](02-system-vs-app.md)
- [16.3 性能指标体系与线上监控](03-performance-metrics-online-monitoring.md)
- [16.4 设备分级性能策略实战](04-device-tier-performance-strategy.md)
- [16.5 性能测试最佳实践](05-testing-best-practices.md)
- [16.6 竞品分析方法](06-competitive-analysis.md)
- [16.7 AOSP 代码阅读](07-aosp-reading.md)
- [16.8 Google Android Bench：AI 编码能力评测方法论](08-google-android-bench-ai-coding-evaluation-methodology.md)

## 阅读建议

- 第一次建立性能分析流程：按 `16.1` → `16.2` → `16.3` 阅读，先统一问题、证据与指标口径，再检验归因。
- 设计可比较的实验：阅读 `16.6` 和 `16.5`；前者偏竞品对照，后者偏回归测试。
- 处理线上问题并推动修复：先用 `16.3` 定义监控信号和指标，再用 `16.1` 的治理方法跟到发布验收。
- 从证据继续追源码或研究数据：阅读 `16.7` 和 `16.1`。评估 AI 修改 Android 代码的能力时，再阅读 `16.8`。
- 制定跨启动、渲染、内存和媒体的设备差异化策略：阅读 `16.4`，并回到对应机制章验证每项预算。


<!-- gracker-diagram: ch16-readme-02-question-driven-reading -->
![按问题选择方法论章节](../../assets/diagrams/ch16/ch16-readme-02-question-driven-reading.png)

图：按当前任务选择对应的方法论入口，再结合相关机制章节核对验证对象。这些分组按阅读目的划分，彼此可交叉参考；其中 16.8 节评估编码能力，不能用榜单分数推断平台或 App 的运行性能。
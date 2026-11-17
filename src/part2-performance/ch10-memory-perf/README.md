# 第 10 章：内存性能

内存问题影响体验的方式很多：OOM（内存不足）、频繁 GC、帧丢失、前后台恢复变慢、系统换页、缓存进程（cached process）重启，以及业务运行越久越迟缓。本章从应用性能视角组织诊断方法，重点回答三个问题：

1. 增长发生在哪类内存中；
2. 谁持有对象或资源；
3. 这项变化怎样影响 GC、调度、I/O 和用户可感知延迟。

<!-- gracker-diagram: ch10-index-01-three-questions -->
![从增长、持有到体验影响](../../assets/diagrams/ch10/ch10-index-01-three-questions.png)

图：三个问题互相补充：分类指标定位增长范围，所有权证据说明谁仍持有资源，同一业务窗口的时间线检验体验影响。

> 源码基线：Android 17 / API 37 / AOSP `android-17.0.0_r1`；涉及 PSI（资源压力导致任务停顿的时间）、cgroup v2（控制组机制）、回收与内核内存统计时，内核核对版本为 `android17-6.18-2026-06_r6`；旧版本差异会在对应专题中保留说明，平台机制的结论适用范围以 Android 17 为上限。

## 内容索引

- [10.1 App 内存分析与案例](01-app-memory-analysis-cases.md)
- [10.2 低内存对系统性能的影响](02-low-memory-impact.md)
- [10.3 内存抖动与频繁 GC](03-memory-churn.md)
- [10.4 GPU 与图形内存统计、归因与诊断](04-gpu-graphics-memory-tracking.md)

<!-- gracker-diagram: ch10-index-02-topic-navigation -->
![四篇专题按现场问题选读](../../assets/diagrams/ch10/ch10-index-02-topic-navigation.png)

图：10.1 提供 App 排障主线；按低内存、分配抖动或图形资源线索进入 10.2–10.4。专题之间可以交叉取证，不是固定执行顺序。

## 按现象选择入口

| 现场现象 | 建议入口 |
| --- | --- |
| 不清楚 Java、Native、PSS、RSS、SwapPss、Graphics 的区别 | [10.1 App 内存分析与案例](01-app-memory-analysis-cases.md) |
| 页面退出后 Activity、View、callback 或资源仍被持有 | [23.2 内存泄漏检测与治理](../../part5-app/ch23-memory-practice/02-memory-leak-governance.md) |
| 多轮业务操作后内存持续增长 | [10.1 App 内存分析与案例](01-app-memory-analysis-cases.md) |
| PSI、换页、lmkd、后台重启或整机卡顿 | [10.2 低内存对系统性能的影响](02-low-memory-impact.md) |
| 需要查看从症状到证据的完整案例 | [10.1 App 内存分析与案例](01-app-memory-analysis-cases.md) |
| live set（仍存活的对象集合）稳定，但短命分配和 GC 很频繁 | [10.3 内存抖动与频繁 GC](03-memory-churn.md) |
| Graphics、DMA-BUF（跨设备共享的缓冲区）或 GPU private memory（GPU 私有内存）增长 | [10.4 GPU 与图形内存统计、归因与诊断](04-gpu-graphics-memory-tracking.md) |
| SQLite/Room 查询、CursorWindow 或分页造成峰值 | [24.2 数据库与序列化性能](../../part5-app/ch24-io-network/02-database-serialization-performance.md) |
| ART region、CMC（并发标记压缩）、LOS（大对象空间）或 compaction（内存压缩整理）引起疑问 | [4.2 ART Heap、GC 与后台维护调度](../../part1-fundamentals/ch04-memory/02-art-heap-gc-maintenance.md) |

## 分析顺序

拿到一个内存问题，我们按固定的顺序推进：先定义业务窗口，再确定内存域，然后区分 live set、churn 与峰值，最后通过单变量对照实验验证改动效果。

### 1. 定义业务窗口

先把要排查的问题整理成一段可重复执行的操作序列，并记录现场条件：设备、构建指纹（build fingerprint）、ART Mainline（可独立更新的 ART 系统模块）版本、应用版本、ABI（应用二进制接口）、构建类型、数据集、前后台状态以及采样时钟。

<!-- gracker-diagram: ch10-index-03-business-window -->
![先固定现场条件，再对齐阶段](../../assets/diagrams/ch10/ch10-index-03-business-window.png)

图：先定义可重复操作与等待区间，保存设备、构建、ART 模块、应用、ABI、负载和前后台状态。轨道仅示意按共同时间基准对齐；不同统计值不因此变成同一计量口径。

### 2. 确定内存域

窗口固定后，接下来要确定内存增长落在哪个域。调查时至少需要覆盖以下六个视角；它们彼此交叉，统计时应按域分别记录与比较。其中线程和文件描述符属于资源线索，而 PSI 衡量资源压力导致的任务停顿，属于时间维度的压力信号（见 [PSI 官方说明](https://docs.kernel.org/accounting/psi.html)）：

- ART managed heap（由 ART 管理的 Java/Kotlin 对象堆）；
- Native heap；
- 匿名映射（没有文件作为后备存储）与文件映射；
- Graphics、DMA-BUF 与 GPU private memory；
- Stack（线程栈）、Code（代码映射）、线程和文件描述符；
- Swap/ZRAM（交换区与压缩内存）和系统 PSI。

<!-- gracker-diagram: ch10-index-04-investigation-views -->
![容量、资源与压力分别解释](../../assets/diagrams/ch10/ch10-index-04-investigation-views.png)

图：这些是交叉的调查视角：ART 与 Native 堆可由匿名映射承载，图形资源也可能进入其他统计；线程数、FD 数和 PSI 不是另一套堆字节数。

确定内存域之后，还要弄清各自的回收责任。GC 主要负责回收 managed heap 中不可达对象占用的堆空间。部分与 Java 对象关联的 Native 分配通过 `NativeAllocationRegistry` 登记，对象不可达后由清理机制调用登记的释放函数（见 [固定 r1 源码](https://android.googlesource.com/platform/libcore/+/refs/tags/android-17.0.0_r1/luni/src/main/java/libcore/util/NativeAllocationRegistry.java)）。这条清理路径只覆盖登记过的分配，其余的 Native 内存、Surface、编解码器（codec）、GPU 或内核资源，仍要逐类核对持有者（owner）、关闭责任、共享引用以及异步工作的完成条件。

<!-- gracker-diagram: ch10-index-05-gc-native-boundary -->
![Java 可达性可以关联已登记 Native 清理](../../assets/diagrams/ch10/ch10-index-05-gc-native-boundary.png)

图：部分 Native 分配登记了与 Java 对象关联的释放函数；对象不可达后可经清理机制触发释放。图中不承诺执行时机，也不表示所有 Native 或 GPU backing 已同步回收。

### 3. 区分 live set、churn 与峰值

确定内存域之后，再用对应工具区分当前问题属于长期存活的 live set、短命对象的频繁分配与回收（churn），还是瞬时峰值：

- heap dump（堆转储）用于分析转储中的对象与引用链；采集时需记录工具是否先触发 GC 及其对象过滤策略，同时注意转储操作本身也会扰动进程内存（见 [官方工具说明](https://developer.android.com/studio/profile/capture-heap-dump)）；
- ART allocation profile（分配剖析）用于分析托管对象的分配调用栈与分配速率；
- Native heap profile 用于分析 `malloc`/`free` 调用栈；
- Perfetto 用于在同一时间线上对齐 GC、调度、帧（frame）、缺页（fault）、PSI 与业务阶段；
- `dumpsys meminfo` 和 smaps（进程内存映射明细）用于确定统计分类与映射归属；
- DMA-BUF、memtrack 和 GpuService 分别提供图形对象、分类统计或驱动上报证据；使用前先确认设备支持、权限、覆盖范围与采集完整性，缺失的数据按未知处理，不能直接计成 0。

工具分类能把调查范围缩小到具体的内存域和分配路径；但要制定出可验证的修复方案，还必须拿到资源持有者、对象生命周期或完整调用栈。

<!-- gracker-diagram: ch10-index-06-tool-evidence -->
![按问题选择工具，区分创建与持有](../../assets/diagrams/ch10/ch10-index-06-tool-evidence.png)

图：heap dump 查对象引用；分配剖析查创建热点和速率；时间线检验体验相关性；映射与图形统计限定增长范围。工具提供的证据不同，创建栈不能代替保留引用图。

### 4. 做单变量对照实验

调整策略后，通过单变量对照实验检验效果：每次只改变一个变量，例如缓存容量、图片目标尺寸、任务并发数、解析批次或缓冲区（buffer）规格。比较内存指标时，应同步观察 CPU、I/O、GC、帧超期（frame deadline miss）、缓存命中率和业务尾延迟（少数最慢请求的耗时）。

如果内存降下来了，但重建成本、I/O 或卡顿明显增加，说明方案还没有达到平衡，仍需继续调整。

<!-- gracker-diagram: ch10-index-07-single-variable -->
![单变量实验同时观察收益与代价](../../assets/diagrams/ch10/ch10-index-07-single-variable.png)

图：保留同一负载和现场条件，一次调整一个变量；同时比较内存、CPU、I/O、GC、帧超期、命中率与尾延迟。根据证据选择保留或继续调整，不预设缓存越小越好。

## 阅读建议

前面的入口表按现场现象做了分流，这里再补充几条跨专题的阅读配合方式：

- App 侧排障建议从 10.1 入手，再按排查出的内存域进入对应小节。
- 遇到 OOM、GC 抖动和前后台恢复问题，建议与第 4 章中的 ART、lmkd、MemoryLimiter 及内核回收章节对照阅读。
- 图形与渲染相关问题要把 10.4 和渲染专题放在同一时间线上分析，避免只盯着 Java heap。
- 进行平台或设备厂商（OEM）调试时，还应保存现场的 cgroup、PSI、低内存终止守护进程（lmkd）、MemoryLimiter 与 ART 配置——API 级别只标明框架版本，设备的实际状态仍以这些现场配置为准。

## 证据边界

在分析内存问题与复核本章结论时，需要守住以下几条口径：

- 数据结论应有源码路径、官方文档或可复现实验支撑。
- PSS、RSS、Java heap、Native allocated 和 GPU memory 各自维护独立的统计范围，汇总前先核对口径。
- `System.gc()`、`WeakReference`、对象池、WebP、SparseArray 与异步线程的使用都依赖具体场景，是否适用要看前提条件。
- 证明内存泄漏需要通过重复操作验证，单次快照不够；确认资源已经释放，一次 GC 之后仍需继续观察。
- 评估或引用性能收益时，必须同时注明设备、构建版本、负载、指标口径与对照条件。


<!-- gracker-diagram: ch10-index-08-evidence-boundaries -->
![结论保留口径、重复性与对照条件](../../assets/diagrams/ch10/ch10-index-08-evidence-boundaries.png)

图：快照、GC 和工具标签都只是一段证据。泄漏与释放结论需结合重复业务、持有关系及资源生命周期；性能收益需保存可复查的现场条件。

---
title: Perfetto UI、状态轨道与版本边界
chapter: '14.2'
section: '14.2'
section_title: Perfetto View 解读
status: finalized
applicable_versions: Android 9 (API 28) - Android 17 (API 37)
last_verified: '2026-11-16'
last_verified_against: AOSP android-17.0.0_r1（external/perfetto ece66975738007dd0978b911d8a2077e49b8f31e、frameworks/native ae266dcb706d083868578cfedce381ef44488a07）+ android17-6.18-2026-06_r6；2026-10-24 官方 UI 文档与 v58.2 交互源码；v57.2 C++ SDK 发布归档、v57.2/v58.2 主机 Trace Processor；C API 按 v57.2/v58.2 发布头文件编译核对，Java 按对应 tag 公共源码核对；2026-11-16 抽检官方 UI、FrameTimeline、调度文档及 Android 17 CHANGELOG/TrackEvent/self_dur、v57.2 state 解析源码，最新稳定发布核对到 v59.1；既有 SDK 编译与主机行为实测未重跑
last_source_verified_at: '2026-11-16'
last_idle_audit_at: '2026-11-16T10:39:07+08:00'
confidence: high
sources:
- type: internal-reference
  path: 当 Perfetto 显示 Running 时,Android 程序到底在做什么? .md
  role: Running、Runnable 与线程状态解释边界
- type: internal-reference
  path: 2026-07-13-android17-surfaceflinger-perfetto-trace.md
  role: Android 17 SurfaceFlinger trace 入口与调用阶段
- type: internal-reference
  path: 2026-05-06-binder-transaction-trace-perfetto-analysis.md
  role: Binder transaction、线程状态与跨进程关联
- type: official
  path: https://perfetto.dev/docs/visualization/perfetto-ui
  role: 当前 UI 的加载、导航、选区、过滤、Pin 与快捷键
- type: official
  path: https://perfetto.dev/docs/visualization/ui-automation
  role: 命令面板、启动命令与宏
- type: official
  path: https://perfetto.dev/docs/analysis/debug-tracks
  role: SQL 模式与 Debug Track
- type: official
  path: https://perfetto.dev/docs/data-sources/cpu-scheduling
  role: CPU 调度轨道、waker 与 end_state 定义
- type: official
  path: https://perfetto.dev/docs/data-sources/frametimeline
  role: FrameTimeline Expected/Actual、颜色、字段与 Flow
- type: official
  path: https://perfetto.dev/docs/instrumentation/track-events
  role: Flow Event 与 Counter 的数据语义
- type: official
  path: https://perfetto.dev/docs/analysis/sql-tables
  role: slice、sched 与 thread_state 表字段
- type: official
  path: https://perfetto.dev/docs/analysis/stdlib-docs
  role: slices.self_dur 与 Android Binder 标准库
- type: official
  path: https://perfetto.dev/docs/analysis/common-queries
  role: Uninterruptible Sleep 与 blocked_function 分析
- type: official
  path: https://perfetto.dev/docs/visualization/large-traces
  role: 大型 trace 的本机 Trace Processor 后端
- type: official
  path: https://developer.android.com/studio/profile/cpu-profiler
  role: Android Studio System Trace 的系统级视图
- type: upstream
  path: https://github.com/google/perfetto/blob/v58.2/ui/src/plugins/dev.perfetto.Sched/common.ts
  role: v58.2 colorForThreadState 配色实现；具体颜色不作为稳定分析接口
- type: aosp
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/types/task_state.cc
  role: Android 17 Trace Processor 的内核 task state 解码
- type: aosp
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/slices/self_dur.sql
  role: Android 17 slice_self_dur 实现
- type: aosp
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/android/binder.sql
  role: Android 17 Binder transaction 关联
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/Scheduler/Scheduler.cpp
  role: Android 17 onFrameSignal、commit 与 composite 调度
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/SurfaceFlinger.cpp
  role: Android 17 SurfaceFlinger commit/composite 实现
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/CompositionEngine/src/Output.cpp
  role: Android 17 Output present 与 release 阶段
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/Scheduler/FrameTimeline.cpp
  role: Android 17 FrameTimeline 分类与 trace 输出
- type: kernel
  path: https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/linux/sched.h
  role: Android 17 common kernel 线程状态位定义
- type: official
  path: https://github.com/google/perfetto/releases/tag/v57.1
- type: official
  path: https://github.com/google/perfetto/releases/tag/v59.1
  role: 2026-11-16 最新稳定发布核对；不改变本文 v57.2/v58.2 的验证基线
- type: aosp
  path: protos/perfetto/trace/track_event/track_event.proto (v57.1 tag)
- type: aosp
  path: protos/perfetto/trace/track_event/state_descriptor.proto (v57.1 tag)
tags:
  - perfetto
  - trace-view
  - frame-timeline
  - binder
  - thread-state
  - cpu-scheduling
  - trackevent
  - 状态追踪
related_chapters:
- '14.1'
- '2.9'
- '15.2'
- '15.3'
- '14.7'
- '14.11'
- '14.12'
- '14.6'
last_consolidated_at: '2026-08-24'
consolidated_from:
- src/part3-tools/ch14-perfetto/03-perfetto-view.md
- src/part3-tools/ch14-perfetto/21-perfetto-v57-state-tracks.md
---

# Perfetto UI、状态轨道与版本边界

打开一份 trace，最先看到的是一排排 track、slice、counter 和 flow，它们把线程、进程与系统组件在一段时间内的离散状态直接摊在时间轴上。同一个位置上的轨道，语义会随着版本和数据源发生变化，因此读图应先确认语义，颜色只用来辅助快速定位。

## 轨道、切片、计数器与因果连接

### 一轮分析的读图顺序

Perfetto UI 把多个 data source（产生某类 trace 数据的采集组件）产生的事件摆在同一条时间轴上。如果录制时没有启用调度事件、FrameTimeline、Binder 或应用标记，UI 自己无法补回这些数据，因果链条仍需沿既有事件逐层追查。读图时，最好把“轨道上发生了什么”和“为什么发生”拆成两步来问。

一轮可靠的读图调查可以按以下顺序推进：

1. 在 Info/Stats 中确认 trace 时间范围、目标进程和数据完整性；Stats 会列出解析错误与丢包等诊断信息。
2. 用 Area Selection 圈出复现动作对应的时间窗，避免在整份 trace 中漫无目的地浏览。
3. 借助 FrameTimeline、启动标记、ANR、输入事件或业务 Slice 锁定异常事件。
4. 回到相关线程，区分 Running、Runnable、Sleeping 与 Uninterruptible Sleep。
5. 沿着 Binder、Flow、waker 或帧 token 检查跨线程、跨进程和显示下游。
6. 需要批量对比时，将 UI 上的观察转化为 PerfettoSQL 查询。


> 源码基线：平台结论固定到 Android 17 / API 37 / `android-17.0.0_r1`，内核 `android17-6.18-2026-06_r6`。交互说明按 2026-10-24 官方文档及上游 v58.2 源码核对；state track 的历史行为另按 v57.2 发布 SDK 和 v57.2/v58.2 主机分析器验证。网页 UI、主机工具和设备组件分别记录版本；这些主机核查不代表 Android 真机采集。

### 打开并整理 Trace

#### 加载方式与大文件

[Perfetto UI](https://ui.perfetto.dev/) 可以通过侧边栏的“Open trace file”或直接拖放来加载本地 trace。一次选择多个文件时，UI 会进入合并配置流程，将它们放到共享时间轴上；合并前必须确认各份文件的时钟来源与对齐依据。

浏览器能够流畅处理多大的 trace，取决于 trace 内容、主机内存、浏览器限制与查询复杂度，没有一成不变的体积门槛。当加载或交互开始卡顿时，可以切换后端：运行 `./trace_processor server http <trace>`，让本机原生 Trace Processor 作为 UI 后端，或者直接用 `trace_processor_shell` 查询（具体流程见 §14.1）。把二进制 trace 全量转成文本通常会先让体积膨胀，同时失去 UI 的索引优势，因此大文件默认应保留二进制形态。


#### 时间轴、选择与详情抽屉

当前 UI 的常用交互操作如下：

| 目的 | 操作 | 结果 |
| --- | --- | --- |
| 缩放与平移 | `W` / `S`、`A` / `D`；也可用 `Ctrl` + 滚轮和 `Shift` + 拖动 | 改变可见时间窗 |
| 聚焦事件 | 选中事件后按 `F` | 通过 Focus current selection 聚焦选区；具体缩放按该 UI 构建实现 |
| 相邻事件 | `,` / `.` | 在同一轨道切换前一个或后一个事件 |
| 时间选区 | 在时间轴或轨道区域拖动 | 创建 Area Selection，其中包含起止时间和被选轨道集合 |
| 事件转选区 | 选中事件后按 `R` | 用事件边界创建 Area Selection |
| 详情抽屉 | `Q` | 显示或隐藏 Tab Drawer（选中事件、查询结果等详情所在的底部面板） |
| 命令面板 | `Ctrl+Shift+P`；macOS 用 `Cmd+Shift+P` | 搜索并执行 UI 命令 |
| 当前快捷键 | `?` | 查看该 UI 构建实际注册的快捷键 |

Area Selection 除了起止时间之外，还包含被选中的轨道集合。修改 track shell（轨道左侧的名称和控制区域）上的勾选项会直接改变选区统计范围；因此分享截图或结论时，最好把时间选区与轨道集合一并写明。


#### 找轨道、过滤和 Pin

面对包含成百上千条轨道的长 trace，提高排查效率的关键是减少同时可见的轨道数量：

- Track Finder 可按名称模糊查找轨道。
- Timeline 工具栏的过滤器可按轨道名、进程或线程缩小显示范围；清除过滤后数据仍在。
- 轨道外壳的 Pin 按钮可将关键轨道固定到工作区顶部。

分析一帧卡顿时，常用的 Pin 组合包括 App 主线程、RenderThread、FrameTimeline、`surfaceflinger` 主线程和相关 CPU；分析同步 Binder 时，则可以把客户端线程与服务端 Binder 线程钉在一起。Pin 只调整显示顺序，不改变数据本身和时间对齐。


Omnibox 是页面顶部的统一搜索和命令输入框，输入 `:` 即可进入 SQL 模式。查询结果能否生成 Debug Track 取决于列的语义：Slice Track 至少需要选定名称、非空时间戳和 duration 列，Counter Track 至少需要选定时间戳和数值列；列名可以在创建界面中手动映射，`name`、`ts`、`dur` 或 `value` 只是常见的默认列名。复杂查询将在 §14.7 展开，这里先把它看作“把 SQL 查询结果放回时间轴”的入口。

<!-- gracker-diagram: ch14-02-05-sql-debug-tracks -->
![查询结果返回时间轴](../../assets/diagrams/ch14/ch14-02-05-sql-debug-tracks.png)

图：先让结果列具有明确语义，再映射成 Debug Track。列名可以映射，但纳秒时间戳与区间或数值语义必须正确。

### 轨道描述的是哪一层

#### CPU Scheduling、Frequency 与 Idle

CPU Scheduling 轨道来自内核调度事件，每个 Slice 表示某条线程在某颗 CPU 上连续运行的区间；详情中的 `priority`、线程身份和 `end_state`（线程被切出 CPU 后进入的调度状态）可以帮助解释这段运行是如何结束的。这条轨道回答“哪条线程在何时占用哪颗 CPU”，至于线程此时执行了哪一行代码，仍要依靠应用 Slice、调用栈采样或方法跟踪来回答。

CPU Frequency 轨道来自设备上报的频率事件，能够反映记录到的频点变化，但频率数字本身不足以证明某段代码变慢：CPU 微架构、单核处理能力、热限制、空闲状态、调度放置和内存等待都会影响最终完成时间。判断线程迁移到另一颗 CPU 是否带来负面影响，还要结合 Runnable 延迟、各 CPU 的并发负载与设备拓扑；主线程也无需始终固定在某颗“大核”上。

CPU Idle 轨道描述 CPU 核心的空闲状态。线程处于 Sleeping 或 D 状态时本就无资格参与调度，此时看到部分 CPU 进入 idle 属于正常现象；只有当线程已经处于 Runnable，且在 affinity（线程允许运行的 CPU 集合）和 cpuset（系统为一组任务限定的 CPU 集合）等约束下存在可用 CPU，却迟迟没有进入 Running 时，才需要继续排查优先级、系统负载和调度策略。


#### 进程、线程、Slice 与线程状态

进程分组把同一进程的线程、Counter 与相关轨道收拢在一起。线程轨道上通常会同时出现两类数据：

- **Slice**：应用或平台标记的命名区间，例如 `Choreographer#doFrame`、`performTraversals`、`DrawFrame`。Slice 说明某个逻辑区间尚未结束，并不保证线程在这段时间内全程占用 CPU。
- **Thread State**：Trace Processor 根据 `sched_switch`、`sched_waking` 等事件重建出的调度状态，用来说明线程究竟在 CPU 上运行、排队等待 CPU，还是在等待某个唤醒条件。

App 主线程承担 Looper 消息、输入分发、组件生命周期与 View/Compose 工作，其中 `Choreographer#doFrame` 是传统 View/HWUI 帧的重要入口；RenderThread 则负责 HWUI 渲染工作的记录、准备与图形提交，其中可能交织着 CPU 执行、GPU 工作排队以及 fence（表示前序图形工作何时完成的同步对象）等待。需要注意，名称相同的 Slice 在不同 Android 版本、渲染后端和厂商实现中可能涵盖不同的子阶段，排查时应结合子 Slice 与对应源码核对。


Binder 线程名可以帮助定位服务端的执行线程；至于服务端具体在执行哪个方法，仍取决于平台或业务是否在服务端路径上添加了 ATrace / Track Event 标记，Binder transaction 本身不保证携带 Java 方法名。

#### Counter Track

Counter 由一组“时间戳 + 数值”样本组成，常见如 CPU 频率、RSS（进程驻留在物理内存中的页量）、堆大小、BufferQueue 积压量或自定义队列深度。UI 会把离散样本连成折线或阶梯图；Counter 的来源、单位和采样间隔由数据源决定，图形上升本身尚不足以证明存在内存泄漏或性能退化。

观察到内存 Counter 持续上升时，需综合区分采样区间、GC、缓存上限、映射文件、共享内存和进程生命周期；GPU Counter 是否存在以及字段含义，也受 GPU 数据源与厂商支持限制。分析报告中应写明 Counter 名称、单位、数据源与比较窗口。


### Slice 的三种时间

#### Wall Duration

`slice.dur` 是 Slice 从起点到终点的墙上时长，直接对应时间轴上的色块宽度。在这段时间里线程可能处于运行、等待 CPU、休眠或阻塞等任意状态，因此较长的 Slice 只能说明该命名区间跨度较大，不足以直接判定为 CPU 计算繁重。

#### Thread Duration / CPU 时间

`slice.thread_dur` 只有在数据源记录了可用的线程时间时才有意义，例如 Track Event 的线程时间计数器，或 JSON Trace Event 中的 `tts` / `tdur`（适用范围同样不限于 Track Event）。Android ATrace 的普通 Slice 经常缺失这一字段；对于缺失或尚未确定的线程时间，应保留为未知，而不能用 0 替代。

需要精确计算某个线程 Slice 内的 on-CPU 时间时，应把该 Slice 的半开区间 `[ts, ts + dur)` 与 `thread_state.state = 'Running'` 求交（半开表示包含起点、不包含终点）。只有当调度数据覆盖完整时，墙上时间才能被拆解为 Running、Runnable、Sleeping、D 等互斥状态；trace 边界、丢包和未知区间仍需单独列出。

<!-- gracker-diagram: ch14-02-09-running-intersection -->
![CPU 估计使用半开区间求交](../../assets/diagrams/ch14/ch14-02-09-running-intersection.png)

图：把目标 Slice 与同一线程的 Running 区间求交。未知、丢失和边界不完整区间不能自动补成零或已知状态。图中时序条长与间隔仅为示意，非设备实测。

#### Self Duration

Self Duration 是轨道嵌套视角下的时间口径，即完整、正确嵌套的父 Slice 扣除直接子 Slice 墙上时长后的剩余部分。Android 17 与 v57.2 固定的 `slices.self_dur` 实现直接计算 `slice.dur - SUM(直接子 Slice 的 dur)`，任意重叠区间的并集并不在这套计算范围内，因此使用前应先排查开放区间、错误嵌套或事件丢失。这一结果依然属于墙上时间，既不等同于函数自身的 CPU 时间，也不会自动扣除其他线程上的异步工作。

<!-- gracker-diagram: ch14-02-10-three-durations -->
![墙上、线程和自身墙上时间](../../assets/diagrams/ch14/ch14-02-10-three-durations.png)

图：三种时长需要分别解释，不能相互替代。`slices.self_dur` 按父 `dur` 减直接子 `dur` 之和计算，要求区间完整且正确嵌套。图中时序条长与间隔仅为示意，非设备实测。

下面的查询用于对比 `doFrame` 的墙上时长、自身墙上时长与可选线程时长：

```sql
INCLUDE PERFETTO MODULE slices.self_dur;

SELECT
  s.id,
  s.name,
  s.dur / 1e6 AS wall_ms,
  sd.self_dur / 1e6 AS self_wall_ms,
  CASE WHEN s.thread_dur >= 0 THEN s.thread_dur / 1e6 END AS thread_ms
FROM slice AS s
JOIN slice_self_dur AS sd USING (id)
WHERE s.name GLOB 'Choreographer#doFrame*'
  AND s.dur >= 0
  AND sd.self_dur BETWEEN 0 AND s.dur
ORDER BY s.dur DESC
LIMIT 20;
```

查询结果中 `thread_ms` 为 `NULL` 表示缺失或未确定的线程时间，CPU 消耗需结合其他证据确认。该查询只保留完整父区间且数值在合理范围内的 self duration，属于初步筛选；子事件是否完整、等待原因是什么，仍要回到 `thread_state` 补齐。

### 线程状态与颜色编码

#### 从内核状态到 UI 颜色

Android 17 Trace Processor 会按内核 `prev_state` 解码调度状态，其中 `android17-6.18-2026-06_r6/include/linux/sched.h` 定义了 `TASK_RUNNING`、`TASK_INTERRUPTIBLE`、`TASK_UNINTERRUPTIBLE` 等状态位。UI 上的颜色主要用于辅助快速浏览，不同主题、轨道类型和 UI 版本都可能调整配色，因此正式结论应记录状态名或 SQL 值，“绿色段”“橙色段”这类口头描述只在看图定位时使用即可。

| UI / SQL 状态 | 内核或处理器含义 | 可以确认 | 仍需补证据 |
| --- | --- | --- | --- |
| `Running` | 线程正在某颗 CPU 上运行 | 该区间获得了 CPU | 执行哪段代码、是否受缓存或内存延迟影响 |
| `R` / Runnable | 已具备运行资格，等待调度 | 该区间没有获得 CPU | 是负载、优先级、affinity、cpuset 还是调度策略 |
| `R+` | Runnable，并由抢占结束上一段运行 | 线程被抢占后等待 | 抢占者、优先级和 CPU 负载 |
| `S` / Sleeping | 可中断睡眠，等待显式唤醒 | 线程不在运行队列 | Binder、futex（用户态锁进入内核等待时使用的机制）、条件变量、定时器或其他等待对象 |
| `D` / Uninterruptible Sleep | 不可中断睡眠 | 线程等待内核条件 | 是否为 I/O、具体 `blocked_function`、设备驱动或内存回收 |

当前稳定版 UI 通常使用不同深浅的绿色区分 Running 与 Runnable，将 Sleeping/Idle 显示为低对比度色块，D 状态则采用暖色。具体色值随主题和 UI 实现变化，不宜当作稳定的数据接口；此外，FrameTimeline 的绿、浅绿、红、黄、蓝属于另一套帧结果编码，阅读时应与线程状态分开。结论中只需记录状态值和详情字段即可。


#### D 状态的常见来源

`TASK_UNINTERRUPTIBLE` 表示线程所等待的条件不会被普通信号打断，磁盘 I/O 只是其中的常见来源之一，驱动等待、页回收、文件系统、块设备以及其他内核等待路径同样可能引发 D 状态。

当采集了 `sched/sched_blocked_reason` 时，`thread_state` 可以提供 `blocked_function`，部分 trace 还会给出 `io_wait`。缺少这些字段时，只能得出“Uninterruptible Sleep，原因未由本次 trace 识别”的结论；要坐实磁盘瓶颈，仍需这些字段提供支撑。

<!-- gracker-diagram: ch14-02-12-d-state-evidence -->
![D 状态的原因需要具体证据](../../assets/diagrams/ch14/ch14-02-12-d-state-evidence.png)

图：D 表示不可中断等待，具体条件需要本次 trace 的证据。缺少 `blocked_function` 或 I/O 证据时应保留原因未知。

#### 红色锁竞争标记的来源

`Lock contention on a monitor lock` 等红色 Slice 来自 ART 或平台层的锁竞争埋点（monitor lock 即 Java 对象监视器对应的互斥锁）。在同一时间窗内，等待线程的内核调度状态通常是 Sleeping，但也可能随实现变化。红色标记说明 trace 提供了更具体的锁竞争证据，Linux `thread_state` 本身并没有因此新增单独的 Blocked 状态。

如果详情面板提供了 owner、blocking thread 或关联跳转，应切换到持锁线程逐项检查：

<!-- gracker-diagram: ch14-02-13-lock-owner-chain -->
![锁竞争要回到持锁线程](../../assets/diagrams/ch14/ch14-02-13-lock-owner-chain.png)

图：从等待者找到 owner，再核对 owner 的工作和依赖。埋点提供锁竞争证据，Linux 调度状态仍需独立检查。

1. 持锁线程是否处于 Running。
2. 持锁线程是否也在等待 Binder、I/O 或另一把锁。
3. 锁持有区间是否覆盖了昂贵操作。
4. 这段等待是否落在了当前帧、启动或 ANR 的关键时间窗内。

红色 Slice 本身还不足以证明发生了优先级反转。优先级反转的判定依据是高优先级任务等待低优先级任务持有的资源；中等优先级工作抢占低优先级持锁者，只是把等待进一步拉长的典型放大路径。判断时应核对同一资源、等待者与持锁者的优先级、持锁范围以及调度状态，再确认延迟来源，而不应把第三个抢占者当成所有反转场景都必须具备的条件。参见 [Android 避免优先级反转](https://source.android.com/docs/core/audio/avoiding_pi)。

<!-- gracker-diagram: ch14-02-14-priority-inversion -->
![中等优先级工作放大锁等待的路径](../../assets/diagrams/ch14/ch14-02-14-priority-inversion.png)

图：高优先级任务等待低优先级持锁者时，其他工作可能继续延迟持锁者。这是典型放大路径；需先核对同一资源、优先级和状态，不能单凭颜色证明反转。图中时序条长与间隔仅为示意，非设备实测。

#### Waker 与唤醒路径

采集了 `sched_waking` 或相关 wakeup 事件后，线程状态详情可以关联出 waker，即发起本次唤醒的线程。需要区分的是，waker 未必是最初的业务事件源；而且被唤醒线程也不会立刻获得 CPU，若要衡量唤醒后的调度等待耗时，应观察从 wakeup 到 Running 的区间。

跨 CPU 唤醒时，`sched_waking` 记录在发起唤醒的一侧，而 `sched_wakeup` 的记录位置受唤醒路径影响。日常延迟分析应优先确保 `sched_waking` 存在；若需进一步拆分 IPI（Inter-Processor Interrupt，CPU 核之间发送的中断）和调度器唤醒路径中的各段耗时，再结合更底层的事件分析。

<!-- gracker-diagram: ch14-02-15-wake-to-running -->
![唤醒后还要等 CPU 才执行](../../assets/diagrams/ch14/ch14-02-15-wake-to-running.png)

图：waker 触发可运行状态后，目标线程仍可能等待 CPU。waker 不一定是最初的业务源，跨 CPU 细分还需额外事件。图中时序条长与间隔仅为示意，非设备实测。

### Flow Events 与跨进程关联

Flow 是 trace 显式记录的跨 track 关联关系，在 UI 上以箭头连接不同轨道上的相关事件。选中带有 Flow 的事件后，UI 会高亮相关箭头；未选中时则可能出于界面可读性而减少显示。箭头表达的是“trace 数据声明两者存在关联”，至于这层关联是同步阻塞还是单一因果，仍要沿着两侧事件具体核实。


#### Binder transaction

Binder 分析依赖于相应的驱动 tracepoint 与 Trace Processor 解析。同步调用通常能关联客户端 transaction、服务端 transaction 和 reply；oneway 是单向异步调用，既没有同步 reply，客户端也不会等待服务端完成。遇到嵌套 Binder、回调和线程池排队时路径会分叉，第一条箭头之后往往还有更长的调用树。

阅读同步 Binder 调用时，建议依次检查以下四个阶段：

<!-- gracker-diagram: ch14-02-17-binder-roundtrip -->
![同步 Binder 的等待分段](../../assets/diagrams/ch14/ch14-02-17-binder-roundtrip.png)

图：同步调用需要分别检查排队、服务端处理和客户端恢复。oneway 没有同步 reply，嵌套调用也可能继续分叉。图中时序条长与间隔仅为示意，非设备实测。

1. 客户端 transaction Slice 的墙上时长与线程状态。
2. 服务端 Binder 线程何时开始处理，transaction 到达与实际开始执行之间是否存在排队等待。
3. 服务端 Slice 内是处于 Running、锁等待、D 状态，还是再次发起了下游 Binder。
4. reply 何时返回，以及客户端从唤醒到重新进入 Running 又等待了多久。

Android 17 的 `stdlib/android/binder.sql` 能够把 Binder transaction 与 reply、线程和进程直接关联起来。UI 跳转适合追踪单个典型案例，批量统计时则建议直接使用该标准库或 §14.7 中的查询模板。

#### FrameTimeline Flow

选中 App 的 Actual Timeline Slice 时，Perfetto 可以借助 surface frame token（标识应用提交帧的关联键）跳转到对应的 SurfaceFlinger display frame；反之，选中 display frame 也可以高亮本次合成包含的多个应用 frame。顺着这条 Flow 读到的是帧的消费关系，比单纯按时间重叠匹配要可靠得多。

需要注意的是，Flow 与 BufferQueue frame number 属于两套不同的标识，同步时序仍要以 acquire、present 和 release fence 为准。此外，SurfaceView 这类独立 Surface 路径受 FrameTimeline 覆盖范围限制，具体边界详见 §14.13 和 §15。


### FrameTimeline：从异常帧进入

FrameTimeline 从 Android 12 / API 31 起可用。Android 9–11 上没有 Expected / Actual 主轨道，需要从 `Choreographer#doFrame`、RenderThread、调度事件和 SurfaceFlinger 时间窗手动建立关联。

Expected Timeline 表示调度器为这一帧安排的预计时间窗。App Actual Timeline 从 `Choreographer#doFrame` 或 NDK Choreographer 回调开始，结束点取 GPU 完成时间与帧提交给 SurfaceFlinger 的 post time 中的较晚者；SurfaceFlinger Actual Timeline 则表达这套帧追踪定义下的合成与显示栈呈现结果，整屏扫描完成与光学响应测量属于另外的度量维度。读取 Actual Slice 的 `dur` 时要留意：它只是这套 FrameTimeline 定义下的墙上区间，既不等同于主线程 CPU 时间，也涵盖不了所有显示路径的端到端延迟。

<!-- gracker-diagram: ch14-02-19-expected-actual -->
![Expected 与 Actual 的端点不同](../../assets/diagrams/ch14/ch14-02-19-expected-actual.png)

图：App Actual 终点取 GPU 完成与 post 中较晚者。FrameTimeline 的定义不等同于主线程 CPU 时长或光学响应。图中时序条长与间隔仅为示意，非设备实测。

选中 Actual Slice 后，可重点核对以下字段：

- `Present Type`：Early、On-time 或 Late。
- `On time finish`：生产者是否在预计 deadline 前完成工作。
- `Jank Type`：平台分类，可包含 App、SurfaceFlinger、Display HAL（显示硬件抽象接口）、预测和调度原因。
- `Prediction Type`：预测是否有效或已经过期。
- `GPU Composition`：该帧是否使用了 GPU 合成。
- `Layer Name`：区分同一进程更新的不同 Surface。
- `Is Buffer`：区分 buffer frame 与非 buffer 动画。

#### FrameTimeline 的颜色

官方 UI 为 FrameTimeline 定义了单独的颜色语义：


| 颜色 | 含义 |
| --- | --- |
| 绿色 | 未观察到 jank 的帧 |
| 浅绿色 | 帧率可能平稳，但帧晚呈现并增加输入延迟 |
| 红色 | 该 Slice 所属进程被归因为 jank 来源 |
| 黄色 | App 帧发生 jank，但归因在 SurfaceFlinger |
| 蓝色 | Dropped frame |

颜色适合用来筛选候选帧，分析报告中仍应明确记录 `present_type`、`on_time_finish`、`jank_type`、layer 和 token。`BufferStuffing` 指应用在旧 buffer 尚未呈现时持续提交新 buffer，导致队列积压与延迟攀升；Android 17 的 `FrameTimeline.cpp` 将 `BufferStuffing`、`SurfaceFlingerStuffing` 等状态与 deadline jank 分开计算，如果把它们笼统并作一句“App Deadline Missed”，就会丢失这层重要区分。

<!-- gracker-diagram: ch14-02-21-stuffing-deadline -->
![队列积压与 deadline 归因分别解释](../../assets/diagrams/ch14/ch14-02-21-stuffing-deadline.png)

图：`BufferStuffing` 描述连续提交造成的积压与额外延迟。Android 17 将 stuffing 与 deadline jank 分开处理，报告应保留具体分类。

官方文档也提示 SurfaceView 不在 FrameTimeline 的完整支持范围内。Camera、视频、游戏和跨进程嵌入画面常拥有独立的 Producer、Surface 与 layer，宿主窗口的帧 token 无法替代这些路径的逐帧信息。

<!-- gracker-diagram: ed14-02-frame-identities-and-independent-surfaces -->
![先识别目标 Surface，再分帧关联与资源同步两路证据](../../assets/diagrams/ch14/ed14-02-frame-identities-and-independent-surfaces.png)

图：FrameTimeline 按 surface frame token 关联 App Actual 与 SF display frame，一个 display frame 可包含多个 App frame；它表达消费关系而非常规同步信号，token 也不同于 BQ frame number。独立的 SurfaceView、Camera、视频、游戏或嵌入 Producer 需追踪自身的 Surface、layer、buffer 与 queue 身份，在官方 FrameTimeline 未完整覆盖时不能用宿主 token 代替。Flow 仅声明端点相关，不证明同步阻塞、唯一因果或完整链路。acquire、present、release fence 分别提供可读、呈现与复用同步，API 返回与显示光学测量另属不同边界。

### Android 17 SurfaceFlinger 轨道

Android 17 的主刷新循环由 `Scheduler::onFrameSignal()` 组织。`Scheduler.cpp` 在同一帧信号中先调用 `compositor.commit()` 处理事务、layer 状态和本帧准备工作；满足合成条件后，再调用 `compositor.composite()` 组织合成，对应实现位于 `SurfaceFlinger::commit()` 和 `SurfaceFlinger::composite()`。显示输出阶段继续进入 CompositionEngine 的 `Output::present()` 与 `presentFrameAndReleaseLayers()`。


旧版本 trace 中的 Slice 名称随平台演进有所差异：

| 平台 | SurfaceFlinger 观察入口 |
| --- | --- |
| Android 12 / 12L | 常见 `onMessageReceived`、`onMessageInvalidate`、`onMessageRefresh`、`REFRESH` |
| Android 13-17 | 按 `onFrameSignal`、`commit`、`composite` 以及可见的 present 子阶段阅读 |

Slice 名称受埋点和版本影响，字面为 `presentFrameAndReleaseLayers` 的 Slice 只在部分 Android 17 trace 中出现；源码调用关系用来解释已经采到的阶段，trace 里缺失的数据无法凭源码推演出来。

看到 `composite` 变长时，先别急着归因为 GPU Client Composition：需要同时找到 RenderEngine/`drawLayers` 等 GPU 合成痕迹、HWC（Hardware Composer，硬件显示合成器）的 composition type、layer 特征和 fence 时间。事务处理变重、latch（选定本轮要合成的 buffer）等待、HWC validate/present 或显示提交，都可能拉长 SurfaceFlinger 的单帧耗时。

<!-- gracker-diagram: ed14-02-sf-frame-loop-and-composition-evidence -->
![先按帧循环分阶段，再验证 GPU 合成候选](../../assets/diagrams/ch14/ed14-02-sf-frame-loop-and-composition-evidence.png)

图：Android 17 的 `Scheduler::onFrameSignal()` 先执行 `compositor.commit()` 处理事务与 layer 准备，满足条件后再进入 `composite()`，随后由 `CompositionEngine::Output::present()` 及 `presentFrameAndReleaseLayers()` 完成输出。源码不保证每个函数都有同名 slice，12/12L 的旧 `onMessage*` 入口也不能机械套用于新版本。`composite` 变长可能源自事务/准备/latch、RenderEngine GPU 合成、HWC validate/present 或显示提交；判定 GPU Client 合成需 `drawLayers`/RE、`composition type`、layer 特征及 fence 共同支持。条件不满足时不会执行 `composite`，因此也不应把长 `composite` 自动当成 CLIENT 合成。

### 日志与原始事件

只有采集配置包含 Android log 数据源时，UI 才能显示抓取窗口内的日志；只有保留了对应的 ftrace event，原始事件表里才会有记录。看不到 Android Logs 或 Ftrace Events 时，应先回查采集配置与数据完整性——“UI 上没有轨道”和“系统里没有发生事件”属于两件事。

日志适合标记业务阶段和错误点，时间线则用于核验线程、调度与依赖关系。日志时间戳、trace 时钟和跨文件合并可能采用不同时间基准；做毫秒级因果判断前，需先确认时钟转换和对齐误差。


### 与 Android Studio Profiler 的关系

Android Studio 的 System Trace 同样提供系统级视图，能够展示 CPU 核心、线程、显示、内存以及部分功耗数据。“Android Studio 只能看单个 App、看不到 SurfaceFlinger 或调度”的说法已经不符合当前工具的实际能力。

| 工具 | 适合的工作 |
| --- | --- |
| Android Studio System Trace | 在 IDE 内录制、围绕目标 App 查看线程和显示问题、结合工程工作流 |
| Perfetto UI | 打开多种 trace、完整时间轴导航、PerfettoSQL、Debug Track、宏和跨进程系统分析 |
| Android Studio Method / Function Trace | 查看方法或函数调用树、按调用栈随时间展开的 Flame Chart，以及从调用者或被调用者方向聚合的 Top Down/Bottom Up 视图 |
| Simpleperf / `linux.perf` | 调用栈采样、热点和 CPU profile |

Android Studio 的 System Trace 与 Java Method Trace 属于不同的录制类型，仅凭一个 `.trace` 扩展名无法区分两者。遇到复杂的跨进程系统问题时，可以从 Android Studio 导出 System Trace，再交由 Perfetto UI 进行 SQL 查询与系统级分析。


### 一轮掉帧分析怎么走

拿到滑动卡顿的 trace 后，可以沿这条主线排查：

1. 在 Info / Stats 确认复现窗口、目标进程、FrameTimeline 与调度数据存在，且相关丢包不影响结论。
2. Android 12–17 从 App Actual Timeline 挑选候选帧；Android 9–11 从 `doFrame`、RenderThread 与 SurfaceFlinger 的共同时间窗入手。
3. 记录 `Jank Type`、`Present Type`、`On time finish`、layer 与 token，不要只记录颜色。
4. 回到主线程和 RenderThread，把长 Slice 与 Running、Runnable、S、D 状态求交。
5. Running 较长时结合子 Slice 或调用栈定位 CPU 工作；Runnable 较长时检查全机 CPU、优先级和调度放置约束；S 状态沿 Binder、锁、条件变量或 waker 追查；D 状态检查 `blocked_function` 与 `io_wait`。
6. 沿着 FrameTimeline Flow 检查对应 display frame，再阅读 Android 17 的 `commit`（处理事务与帧准备）、`composite` 和显示输出阶段。
7. 涉及跨进程 Binder 或锁等待时，把客户端、服务端、持锁线程和 reply 放进同一选区对照。
8. 用 SQL 复核同类帧是否重复出现，避免拿单次偶发案例代表整段运行表现。

这条主线用于判断现有证据究竟指向应用、调度、跨进程调用、合成还是显示末端；修复完成后仍需回到代码、配置和目标设备上复现验证，FrameTimeline 的分类不能替代源码与 fence 层面的核对。


### Android 17 源码核对点

| 结论 | Android 17 / kernel 锚点 | 代码能证明什么 |
| --- | --- | --- |
| 调度状态 | `external/perfetto/.../task_state.cc` + kernel `include/linux/sched.h` | Trace Processor 如何解码 `prev_state`，内核如何定义 Running / Interruptible / Uninterruptible 状态位 |
| Self Duration | `external/perfetto/.../slices/self_dur.sql` | `slice_self_dur` 用父 dur 减去直接子 Slice dur 之和；要求区间完整且正确嵌套 |
| Binder 关联 | `external/perfetto/.../android/binder.sql` | transaction、reply、线程与进程的标准库关联 |
| SurfaceFlinger 帧循环 | `Scheduler/Scheduler.cpp:411-506` | `onFrameSignal()` 组织 `commit()` 与 `composite()` |
| SurfaceFlinger 阶段 | `SurfaceFlinger.cpp:2996,3330` | Android 17 的 `commit()` 与 `composite()` 实现入口 |
| 显示输出 | `CompositionEngine/src/Output.cpp:450-517,1726` | `Output::present()` 与 `presentFrameAndReleaseLayers()` 的调用边界 |
| 帧分类 | `Scheduler/FrameTimeline.cpp` | Android 17 jank bit、non-jank 状态、Dropped 与 trace 字段转换 |

源码能够证明平台具备这些实现，但不保证每台厂商设备都采集了对应数据；每份 trace 仍需核对 data source、事件、权限与丢包情况。


## 状态轨道的语义与版本差异

熟悉通用 UI 对象之后，读到状态轨道时还需要额外确认三件事：状态枚举如何定义、数据由哪个源产生，以及 Perfetto 处于哪条版本线上。平台内置组件、Perfetto SDK 与开发机分析器各自独立升级，相同的视觉样式未必代表相同的底层语义；“Android 17 支持 Perfetto v57”这句笼统说法背后，实际上是三条各自推进的版本线。

### 三条版本线

先看平台这一条线：`android-17.0.0_r1` 的 `external/perfetto/CHANGELOG` 顶部记录了一个尚未合入完整上游版本的 Android `aflags` 补丁（`aflags` 是 Android 的功能开关机制，让平台代码按 flag 启用或停用行为）。紧接着的完整上游版本是 **v54.0**（发布于 2026-02-27）；同一 Android 标签下的 `track_event.proto` 只定义到 `TYPE_COUNTER = 4`，`TYPE_STATE` 要到 v57 系列才引入。

再看上游这一条线：Perfetto **v57.1** 于 2026 年 7 月 2 日发布，正式引入 state track；**v57.2** 于 7 月 7 日发布，主要修复内嵌 proto descriptor 的兼容性问题，state wire format 延续自 v57.1。本节的 state 示例沿用 v57.2 历史基线，UI 交互与后续语言 API 的版本对照则固定到 [v58.2](https://github.com/google/perfetto/releases/tag/v58.2)。截至 2026-11-16，官方最新稳定发布为 [v59.1](https://github.com/google/perfetto/releases/tag/v59.1)；采用更新版本前，应先核对该版本的迁移与兼容性说明。需要明确的是，即便上游 SDK、Trace Processor 和 UI 不断更新，设备中的 `/system/bin/perfetto`、`traced`、`traced_probes` 和 Android Framework API 仍随系统镜像演进，必须单独考量升级路径。


| 对象 | 采用的版本 | 在哪里运行 | 能否直接提供 v57 状态轨道 |
|---|---|---|---|
| Android 平台 Perfetto | `android-17.0.0_r1`：v54.0 加平台补丁 | Android 17 设备 | 不能；平台 proto 没有 `TYPE_STATE` |
| Perfetto v57.2 C++ SDK / Trace Processor / UI | `v57.2` tag | 应用、测试工具或开发机 | C++ 生产与解析路径可用；C high-level 与 Java API 另有版本限制 |

这一版本拆分直接决定了方案选择：


- 只升级开发机分析器：可以读取新版 schema（trace 的字段与类型定义）和 PerfettoSQL 标准库，但无法补出设备未录制的数据。
- 想在 trace 中得到原生 `state` 表：producer（生产事件的一端）和 Trace Processor（解析事件的一端）都必须具备 v57 state track 能力。
- 只能依赖 Android 17 系统内置组件：继续使用 slice、instant、counter 等 v54 能力；即使自行写入 `TYPE_STATE`，也不能假定平台自带工具能够解析。

### State track 的数据模型

#### Slice、counter 和 state 各自回答什么

| 轨道类型 | 数据形态 | 适合回答的问题 | 常见误用 |
|---|---|---|---|
| Slice | 开始、结束、可嵌套 | “这个操作执行了多久？” | 用大量首尾相接的 slice 模拟长期状态 |
| Counter | 时间戳加数值 | “这一刻的频率、字节数或队列深度是多少？” | 用整数枚举表达状态，却遗漏枚举表 |
| State | 时间戳加字符串状态，单轨道至多一个当前值 | “这个子系统在这段时间处于什么状态？” | 把同一时间可并存的多个活动塞进单条 state track |


state track 表达单值状态机：一条轨道在任一时刻至多拥有一个当前值，没有当前值时处于 idle。例如播放器的 `Buffering → Playing → Paused` 就很适合用 state track 表达；而并行的下载任务、解码任务和渲染任务可能同时存在，应分别使用 slice 或多条轨道。


#### v57.1 在 trace 二进制格式中增加了什么

v57.1 的 `TrackEvent.Type` 新增了 `TYPE_STATE = 5`，v57.2 延续了同一 wire format（序列化后的二进制字段格式）。事件的 `track_uuid` 作为轨道的 64 位稳定标识，必须指向带有 `StateDescriptor` 的轨道（descriptor 是描述轨道类型和属性的元数据）。`StateDescriptor` 在 v57.1/v57.2 中是空消息，仅负责把轨道标记为 state track。

状态字符串的实际编码走的是 TrackEvent 的事件名路径，即 `name` 或经过 string interning（把重复字符串换成整数 ID）的 `name_iid`。虽然 v57.2 `track_event.proto` 的枚举注释仍提到 `state` 字段，但 schema 已把原字段号 51 标为 `reserved`（保留编号，不再用作普通字段），C++ `TRACE_STATE` 同样把状态值传给事件名参数。

⚠️ 实现差异：“空字符串”与“省略事件名”属于两种不同的编码。使用 v57.2 发布 C++ SDK 录制并由 v57.2/v58.2 主机分析器读取时，`TRACE_STATE(..., "", track)` 会生成空字符串状态行，而 `TRACE_STATE(..., nullptr, track)` 才会关闭当前状态且不生成 idle 行。手工构造 packet 时，省略 `name` / `name_iid` 表达清空；显式传入 `name: ""` 在这两个版本分析器中仍被视为有效状态值。该行为可对照固定版本源码与合成/SDK trace 验证，见 [ParseStateEvent](https://github.com/google/perfetto/blob/v57.2/src/trace_processor/importers/proto/track_event_event_importer.h) 与 [StateTracker](https://github.com/google/perfetto/blob/v57.2/src/trace_processor/importers/common/state_tracker.cc)。


下面的枚举节选展示了 `Type` 的取值范围（省略了 proto 中的大段注释与其他字段）：

```protobuf
enum Type {
  TYPE_UNSPECIFIED = 0;
  TYPE_SLICE_BEGIN = 1;
  TYPE_SLICE_END = 2;
  TYPE_INSTANT = 3;
  TYPE_COUNTER = 4;
  TYPE_STATE = 5;
}
```

Android 17 标签中的同一枚举止步于 `TYPE_COUNTER = 4`。`TYPE_STATE = 5` 只说明 v57 的二进制格式已经分配了该枚举值，并不代表所有语言 SDK 在同一时间都提供了高层接口；设备是否自带 v57 状态轨道必须单独确认，API 37 或 Android 17 的标签本身不能说明这一点。

#### Trace Processor 如何形成持续时间

v57.2 的 `StateTracker::UpdateState()` 体现了以下几条容易被忽视的语义：

- 新值与当前值不同：关闭旧行，将 `dur` 设为两次状态事件的时间差，再创建新行；
- 新值与当前值相同：不创建新行，只把新参数附加到当前状态；
- 未提供状态名（解析为 null string ID）：关闭旧行且不创建 idle 行，而显式空字符串仍可能成为有效值；
- 尚未被下一次转换或清空关闭的行以 `dur = -1` 暂存（`-1` 是“持续时间尚未确定”的哨兵值）。

这也解释了查询 `state` 表时为什么无需再用 `LEAD(ts)` 计算时长：`LEAD()` 只是读取下一行值的 SQL 窗口函数，而 Trace Processor 已经在导入阶段维护好了 `dur`；如果手工用下一行时间戳相减，相同状态合并、显式清空和开放区间的语义就都会丢失。


### 写入 state 事件

#### C++ SDK

下面的片段展示了同一条状态轨道上的三次转换（类别注册、Tracing 初始化与 session 配置沿用 Perfetto SDK 常规写法，此处省略）：

```cpp
perfetto::StateTrack player_state("Player state");

TRACE_STATE("player", "Buffering", player_state);
TRACE_STATE("player", "Playing", player_state);
TRACE_STATE("player", nullptr, player_state);  // 清空当前状态，进入 idle
```

第三次调用传入 `nullptr`，用于关闭 `Playing` 并进入 idle。该片段在官方 v57.2 C++ SDK 发布归档的常规 in-process 会话中编译运行后，分析器只生成 `Buffering` 与 `Playing` 两行；这验证的是 in-process 路径，Android system backend 的兼容性仍需单独测试。

轨道身份同样关键：同一逻辑轨道必须复用稳定的 `StateTrack` 身份，并让后续更新指向同一个 `track_uuid`，在当前 trace 作用域内明确区分不同实例。状态值建议取自有限枚举，请求 ID、文件名等高基数字符串则应放进参数里，否则会产生大量难以聚合的碎片状态。

<!-- gracker-diagram: ed14-02-state-encoding-and-update-branches -->
![同一 StateTrack 按不同值、同值与省略名三路更新](../../assets/diagrams/ch14/ed14-02-state-encoding-and-update-branches.png)

图：`StateTrack` 同一时刻至多拥有一个当前值，稳定的 `track_uuid` 指向带 `StateDescriptor` 的 `TrackDescriptor`（v57.1/57.2 中该 descriptor 为空消息类型标记）。`TYPE_STATE = 5` 使用 `name`/`name_iid` 事件名字段，字段 51 `reserved` 已非现行 `state` 字段。新不同值会关闭旧行并新建 `dur = -1` 行；同值只附加 `args` 而不重建起点；省略 `name`/`name_iid` 或实测的 C++ `nullptr` 会关闭旧行且不建 idle 行，而显式空串在 v57.2/v58.2 中会形成状态行，不能当作清空。尚未被下一次转换或清空关闭的行保持 `dur = -1`；查询时不要用 `LEAD` 重算时长以免丢失同值合并、idle 与开放区间语义，独立并行的活动应使用多条轨道或 slice。

#### C high-level API：v57.2 与 v58.2

下面的调用向已注册的状态轨道写入 `Buffering`。该接口在 [v58.2 C high-level 头文件](https://github.com/google/perfetto/blob/v58.2/include/perfetto/public/te_macros.h) 中可用，而 v57.2 发布头文件尚无该宏（使用两个版本的官方 C SDK 发布归档分别做 C11 语法编译验证时，v58.2 编译通过，v57.2 报 `PERFETTO_TE_STATE` 未定义）。此处同样省略类别定义与轨道注册代码：

```c
PERFETTO_TE(player, PERFETTO_TE_STATE("Buffering"),
            PERFETTO_TE_REGISTERED_TRACK(&player_state_track));
```

`player_state_track` 必须通过对应版本的状态轨道注册接口构建 descriptor，普通 counter 或 named track 的 descriptor 与 state descriptor 属于两类不同对象。由于 v57.2 的公开 C 头文件还没有 `PERFETTO_TE_STATE` 和 `PerfettoTeStateTrackRegister`，v58.2 才正式包含，项目应锁定实际使用的发布版本后再编译完整的注册与调用代码。

#### Android Java SDK 的 release tag 差异

虽然 v57.1 已经发布了 state track，但各语言 SDK 的高层 API 并未在同一个 release tag 中同步到位。核对源码可以看到如下版本差异：

- `v57.1` 与 `v57.2` tag 下的 `src/android_sdk/.../PerfettoTrace.java` 只公开了 slice、instant 和 counter 的事件类型，尚未出现 `TYPE_STATE` 或 `state(...)`；
- 上游 `main` 的 `sdk: add state track event support (C HL API + Java SDK)` 提交 #6464 才加入 `PerfettoTrace.state(...)`、state track builder、C high-level API 和 JNI（Java 与 C/C++ 之间的调用桥梁）路径；
- [v58.2 的 `PerfettoTrace.java`](https://github.com/google/perfetto/blob/v58.2/src/android_sdk/java/main/dev/perfetto/sdk/PerfettoTrace.java) 已公开 `state(Category, String, String)` 及动态名称入口；这只说明对应 tag 源码存在该接口，项目实际解析到的 Maven artifact 仍须另行编译验证。

工程上应以项目实际解析到的 Java artifact 及对应源码 commit 为准：锁定依赖、检查公共方法并编译完整调用代码。由于这里只核对了 Java tag 源码而未执行 Android Java 构建，若项目依赖的 artifact 缺少 state API，可以改用已验证的 v57.2 C++ 路径，或升级到明确包含该接口的 Java SDK 版本。


### 查询 `state` 表

#### 先确认分析器版本和表结构

Android 17 自带的 v54 Trace Processor 还不认识 `state` 表。用 v57.1 或更高版本的兼容分析器打开 trace 后，可以先执行 `PRAGMA table_info(...)`（SQLite/PerfettoSQL 用来列出表或视图字段的命令）确认表结构：

```sql
PRAGMA table_info(state);
```

v57.2 的公开 view（由 SQL 查询定义、读取时计算的表状结果）包含 `id`、`ts`、`dur`、`track_id`、`category`、`value` 和 `arg_set_id`。`ts` 与 `dur` 单位均为纳秒，`arg_set_id` 用于关联该状态附带的参数。注意状态列名是 `value`，不存在名为 `state` 的列。


#### 查询转换与已观测时长

下面的查询按名称查找带有 state 记录的轨道，且仅在恰好匹配到一个 `track.id` 时才计算结果。对于多实例同名轨道，必须先结合 `track`、descriptor UUID、进程和参数选定唯一目标，直接合并会把多个状态机混成一个。缺失或多匹配时该查询返回空集，分析报告应把歧义与零时长分开。查询还会把完整区间和 `dur = -1` 的开放行都裁剪到 `trace_bounds` 的 `[start_ts, end_ts)` 范围内：

```sql
WITH candidates AS (
  SELECT DISTINCT t.id
  FROM track AS t
  JOIN state AS s ON s.track_id = t.id
  WHERE t.name = 'Player state'
), target AS (
  SELECT id FROM candidates WHERE (SELECT COUNT(*) FROM candidates) = 1
), bounded AS (
  SELECT
    s.track_id, s.value, s.category, s.arg_set_id,
    MAX(s.ts, b.start_ts) AS start_ts,
    MIN(CASE WHEN s.dur = -1 THEN b.end_ts ELSE s.ts + s.dur END,
        b.end_ts) AS end_ts
  FROM state AS s
  JOIN target AS t ON t.id = s.track_id
  CROSS JOIN trace_bounds AS b
  WHERE s.dur >= -1
)
SELECT
  track_id, start_ts AS ts, value, category,
  end_ts - start_ts AS observed_dur_ns,
  ROUND((end_ts - start_ts) / 1e6, 3) AS observed_dur_ms,
  arg_set_id
FROM bounded
WHERE end_ts > start_ts
ORDER BY ts;
```

`CROSS JOIN trace_bounds` 把同一 trace 范围附到每条记录。结果反映的是从已记录状态事件开始、落在边界内的观测时长：开放状态可能在 trace 结束后仍在继续，而第一条已知状态之前则属于未知（即使业务早已进入该状态，分析器也推算不出其真实起点）。更严谨的业务对比应把这里的边界替换为明确的目标窗口，并验证事件与增量状态未丢失。


#### 汇总各状态占比

下面的查询把每行裁剪到 trace 边界内再按状态值聚合，可以用来比较一次录制中播放器的缓冲与播放占比：

```sql
WITH candidates AS (
  SELECT DISTINCT t.id
  FROM track AS t
  JOIN state AS s ON s.track_id = t.id
  WHERE t.name = 'Player state'
), target AS (
  SELECT id FROM candidates WHERE (SELECT COUNT(*) FROM candidates) = 1
), bounded AS (
  SELECT
    s.value,
    MIN(CASE WHEN s.dur = -1 THEN b.end_ts ELSE s.ts + s.dur END,
        b.end_ts) - MAX(s.ts, b.start_ts) AS dur
  FROM state AS s
  JOIN target AS t ON t.id = s.track_id
  CROSS JOIN trace_bounds AS b
  WHERE s.dur >= -1
)
SELECT
  value,
  ROUND(SUM(dur) / 1e6, 3) AS total_ms,
  ROUND(100.0 * SUM(dur) / NULLIF(SUM(SUM(dur)) OVER (), 0), 2)
    AS observed_percent
FROM bounded
WHERE dur > 0
GROUP BY value
ORDER BY total_ms DESC;
```

`SUM(SUM(dur)) OVER ()` 汇总所有状态值的合计时长。这个分母仅包含选定轨道中有 `state` 行且与窗口相交的区间：省略状态名的显式清空不会生成 idle 行，因此不进分母；而显式空字符串值会进入分母。若要计算占整个观测窗口的比例，应另取窗口总长作为分母，并把显式清空后的 idle 与首条事件前、丢包造成的未知区间分别统计，不能把所有空白时间都当作 idle。

<!-- gracker-diagram: ed14-02-state-window-and-denominator -->
![先固定唯一轨道与窗口，再分有值、idle 和未知计算占比](../../assets/diagrams/ch14/ed14-02-state-window-and-denominator.png)

图：先执行 `PRAGMA table_info(state)`，v57.2 view 包含 `id`/`ts`/`dur`/`track_id`/`category`/`value`/`arg_set_id`，状态列名为 `value`（不存在 `state` 列）。按 track id/UUID/process/args 选定唯一实例，同名多匹配或缺失均返回空集以保留歧义。正区间按 `max(s.ts, start)` 到 `min(s.ts + dur, end)` 裁剪，`dur = -1` 仅暂裁到窗口末尾且不表示业务结束，首事件前则属于未知。当前 `SUM(dur)` 分母仅覆盖选定轨道有 `state` 行的正交集，显式空串也会计入，而省略名清空不生成 idle 行故不计入。计算完整窗口占比需另取窗口长度，已知 idle 与首事件前/丢失造成的未知区间应分开统计，同时须验证丢失与增量状态完整性。

### 在 Android 17 上采用 v57 能力


#### 路径一：只升级开发机分析器

这是改动最小的路径：

1. Android 17 继续使用系统 Perfetto 录制 sched、ftrace、atrace、FrameTimeline、heap profile 等既有数据；
2. 开发机安装固定版本的 v57.2 或更高 Trace Processor；
3. 用该分析器读取 trace，执行 SQL 并保存查询结果、工具版本和原始文件。

该方案可以直接获得新分析器的表结构、PerfettoSQL 标准库和解析修复，但设备上的旧 producer 依然不会产出 `TYPE_STATE`。

#### 路径二：应用携带新版 SDK 生产 state track

如果确实需要原生状态轨道，应把 producer SDK 与 Trace Processor/UI 作为一套版本对齐的能力来交付：

1. 应用或测试进程链接支持状态轨道的 Perfetto SDK；
2. 在 in-process backend 或经过验证的 system backend 上完成录制；
3. 使用 v57.2 或更高版本的兼容 Trace Processor 与 UI 打开结果；
4. 在目标 Android 17 build 上验证注册、SELinux、缓冲区、丢包统计和 SQL 表；
5. 为旧分析器保留可识别的降级标记，或者明确拒绝旧版本工具。

这里的 backend 指 SDK 写入 trace 的目标：in-process backend 在本进程管理会话与缓冲，system backend 则连接设备 tracing service。官方的 [Tracing Protocol ABI](https://github.com/google/perfetto/blob/v54.0/docs/design-docs/api-and-abi.md) 由 protobuf-over-Unix-socket 协议、共享内存布局与 protobuf 消息构成，按双向兼容维护；它与 C++ SDK 的编译接口属于两层不同的契约。

写入服务与离线解析需要分别验收。在目标镜像上，依然需要核验 SDK 构建是否启用对应 backend、socket 权限、数据源注册策略、SELinux、缓冲区与丢包；旧工具不会因为 service 搬运了新字段就自动理解 `TYPE_STATE`。遇到连接失败时，先排查到具体协议层，再判断笼统的“SDK ABI 不匹配”是否成立。

平台采集服务的升级则应随产品镜像整体验证：`traced` / `traced_probes` 需与 init、Unix socket 权限、SELinux、Producer/Consumer IPC 协议和系统测试一同交付。它们的 Perfetto IPC 是一套独立的协议，与 AIDL/Binder 分属不同体系。离线主机 Trace Processor 可以独立升级；如果把工具放进产品镜像，仍需满足该镜像的权限、构建和兼容性要求，设备服务的兼容性也要在设备侧单独验证。


#### 路径三：维持 Android 17 平台兼容

在无法引入新版 SDK 时，可以按数据语义选用 Android 17 已有的轨道类型作为替代：

- 有明确开始和结束的活动：slice；
- 某个时刻的数值：counter；
- 单次状态转换提示：instant，并通过稳定名称或参数携带值；
- 需要计算状态持续时间：由生产端维护成对 slice，或在 SQL 中依据经过审核的 instant 事件构造区间。

这种兼容表达缺少 state track 的单值约束和专用 UI 展示。生产代码需要自行保证状态转换合法，文档、SQL 和指标名称中也应标明所采用的替代方案，避免与原生 `state` 表混用。

<!-- gracker-diagram: ed14-02-versioned-state-adoption-and-backends -->
![分析器升级、原生 State 与平台兼容表达走不同验证路径](../../assets/diagrams/ch14/ed14-02-versioned-state-adoption-and-backends.png)

图：Android 17 平台内 Perfetto 固定为 v54 + 平台补丁，其 proto 不含 `TYPE_STATE`；v57.1 引入 state track 并由 v57.2 沿用，历史基线 v57.2 与复核基线 v58.2 不混为最新。仅升级 TP/UI 可获得新解析与 SQL 能力，但不能凭空生成旧 Producer 未录制的 state；使用新版 SDK state 需按实际语言 release/artifact 编译验证：v57.2 C++ `nullptr` 在主机 in-process 下完成验证（v57.2 C/Java 高层 API 存在缺口），v58.2 完成了 C11 片段编译（Java 仅核对 tag 源码，不等于项目 Android 构建）。System backend 需在目标镜像验证注册、socket、SELinux、buffer 与 `stats`，其中 Perfetto IPC（protobuf-over-Unix-socket）与 SMB 按 ABI 维护，独立于 Binder/AIDL 与 SDK 编译 ABI。旧版兼容表达需用 slice/counter/instant 自行维护转换字典与区间并明确标注，不可冒充原生 `state` 表。

### v57 系列的其他变化

- `linux.systemd_journald` data source 采集使用 systemd 的 Linux 系统日志 journald，并在统一日志表中用 `log_source` 标明来源。Android 使用 logcat；在 Android 17 上，日志采集仍由 logcat 负责。
- JSON Trace Event Format 用 `"ph": "X"` 表示完整区间，同线程同步事件可以正确嵌套。v57.2 合成测试表明，完整父子区间留在同一轨道，而交叉重叠（A 开始、B 开始、A 结束、B 结束）会被分配到 overflow track，并记录 `slice_spill_overlapping_complete_event`。若要表达独立、可交叉的活动，生产端应改用异步 `"b"` / `"e"` 事件。
- 查询结果网格增加了列排序、重排、隐藏和更清楚的 SQL 错误提示。这些属于 UI 交互能力，底层表结构和 SQL 计算结果保持不变。
- `heapprofd.process_cmdline` 是按进程命令行选择 native heap profiler（C/C++ 堆分析器）目标的配置项。它支持部分通配符，但通配符只能匹配已经运行的进程，且配置必须设置 `no_startup = true`，显式禁用“从进程启动时开始 profiling”的模式。
- C high-level API 和 Android Java SDK 增加了嵌套轨道及同级轨道的排序、合并控制。correlation ID（关联 ID）只表示多个事件属于同一逻辑操作；跨线程的先后或因果关系，仍应使用 flow 表达。
- Trace Processor 支持从公开 URL 或 Perfetto permalink（Perfetto UI 保存并分享 trace 的链接）加载 trace。由于生产 trace 常包含进程、线程与业务信息，公开 URL 只适合经过授权和脱敏的文件。
- `perfetto` Python 包默认选用与包版本对应的 Trace Processor 二进制，便于重复得到相同结果；若切换为 `fetch_latest_trace_processor`，同一脚本在不同日期可能下载不同二进制，导致版本漂移。
- Adreno 是 Qualcomm GPU 系列。它的 `adreno_cmdbatch_retired`、`adreno_cmdbatch_sync` ftrace 事件在 v57.1 中可解析为 GPU timeline slice；目标设备是否提供这些内核事件仍取决于系统 build 与 GPU 驱动。
- v57.2 主要修复了携带自有 proto descriptor 的 trace 在 wire-compatible schema 变化后可能解析失败的问题（wire-compatible 表示字段变更仍遵守 protobuf 的序列化兼容规则）；该修复落在解析兼容层，state track 的数据模型保持原样。


### 评审清单

评审包含 v57 state track 的改动时，可逐项对照检查：

- [ ] Android 平台版本基线写成 Android 17 / API 37 / `android-17.0.0_r1`
- [ ] 平台内置 Perfetto 标为 v54.0 加平台补丁，没有写成 v57
- [ ] producer SDK、Trace Processor 和 UI 各自记录版本或 commit（源码提交标识）
- [ ] state track 使用稳定轨道身份和有限状态集合
- [ ] 清空编码已按所用 SDK/分析器实测，显式空字符串值与 idle 区分；占比分母说明 idle 和未知区间
- [ ] SQL 使用 `state.value` 和 `state.dur`，没有重复用 `LEAD()` 推导时长
- [ ] `dur = -1` 按 trace 边界处理，并注明只是观测窗口
- [ ] C high-level 与 Java 调用由项目实际 artifact 编译验证，注明 v57.2 与 v58.2 的 API 差异；源码核对不冒充 Java 编译
- [ ] trace 上传、公开 URL 和提供给 AI 模型的方式符合数据处理规则


### 源码与官方资料

- [Perfetto v57.1 release notes](https://github.com/google/perfetto/releases/tag/v57.1)
- [Android 17 标签下的 Perfetto CHANGELOG](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/CHANGELOG)
- [Android 17 标签下的 TrackEvent proto](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/protos/perfetto/trace/track_event/track_event.proto)
- [v57.1 TrackEvent proto](https://github.com/google/perfetto/blob/v57.1/protos/perfetto/trace/track_event/track_event.proto)
- [v57.1 StateDescriptor proto](https://github.com/google/perfetto/blob/v57.1/protos/perfetto/trace/track_event/state_descriptor.proto)
- [v57.1 `state` SQL view](https://github.com/google/perfetto/blob/v57.1/src/trace_processor/perfetto_sql/stdlib/prelude/after_eof/views.sql)
- [v57.1 StateTracker](https://github.com/google/perfetto/blob/v57.1/src/trace_processor/importers/common/state_tracker.cc)
- [v57.1 Android Java `PerfettoTrace`](https://github.com/google/perfetto/blob/v57.1/src/android_sdk/java/main/dev/perfetto/sdk/PerfettoTrace.java)
- [上游 Java state track 变更 #6464](https://github.com/google/perfetto/commit/0894477744bf11fa1f08ca81bbceb14cd5385737)


## 常见误区

**Slice 很长，所以 CPU 计算很重。** Slice 只是墙上区间，线程期间可能大部分时间都在等待；真实负载要核对线程状态或可用的线程时间。

**Running 就能知道热点函数。** Running 只证明线程正在占用 CPU；要归因到具体函数，还需结合嵌套 Slice、调用栈采样或方法跟踪。

**Runnable 长就提高线程优先级。** Runnable 只说明线程在等待 CPU 调度。动手调优先级前，需先核对系统负载、affinity、cpuset、热限制和调度策略，盲目提权反而可能挤压其他线程并推高功耗。

**D 状态就是磁盘慢。** D 状态只表示不可中断等待。在缺少 `blocked_function`、`io_wait` 或驱动证据时，先不要把原因限定为磁盘 I/O。

**红色都代表同一种问题。** Thread State、锁竞争 Slice 和 FrameTimeline 各有独立的颜色语义，分析结论应明确写明轨道类型与字段值。

**Android Studio System Trace 只看 App。** 当前的 System Trace 同样能够展示系统级活动。Perfetto UI 的主要优势体现在开放时间轴、PerfettoSQL、扩展生态与跨进程系统分析，“能否看到系统数据”早已不再是两者的分界线。

## 小结

阅读 Perfetto UI 时，先把轨道对象、时间范围和数据源确认清楚，再深入分析 slice、counter、thread state 与 flow。颜色仅作视觉引导，墙上时间与 CPU 运行时间也属于不同口径，最终结论必须落回详情字段、稳定身份和 SQL 查询。至于 state track，它还有独立演进的 producer、分析器与 UI 版本线，跨版本使用时务必将实际 schema 与缺失范围记录在案。


## 参考资料

- [Perfetto UI](https://perfetto.dev/docs/visualization/perfetto-ui)、[Commands and Macros](https://perfetto.dev/docs/visualization/ui-automation)、[Debug Tracks](https://perfetto.dev/docs/analysis/debug-tracks) 与上游 [`colorForThreadState()`](https://github.com/google/perfetto/blob/v58.2/ui/src/plugins/dev.perfetto.Sched/common.ts)：加载、导航、Area Selection、Pin、命令面板、SQL 轨道和配色实现边界。
- [CPU Scheduling events](https://perfetto.dev/docs/data-sources/cpu-scheduling)、[PerfettoSQL tables](https://perfetto.dev/docs/analysis/sql-tables) 与 [Android trace cookbook](https://perfetto.dev/docs/analysis/common-queries)：调度状态、waker、`thread_state`、D 状态和 `blocked_function`。
- [Android Jank detection with FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline) 与 [Track Event flows](https://perfetto.dev/docs/instrumentation/track-events)：Expected / Actual、帧字段、颜色和 Flow 语义。
- [PerfettoSQL standard library](https://perfetto.dev/docs/analysis/stdlib-docs)：`slices.self_dur`、Binder 和 Android 分析模块。
- [Android Studio System Trace](https://developer.android.com/studio/profile/cpu-profiler)：Android Studio 当前系统级时间轴的能力边界。
- Android 17 [`Scheduler.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/Scheduler/Scheduler.cpp)、[`SurfaceFlinger.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/SurfaceFlinger.cpp)、[`Output.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/CompositionEngine/src/Output.cpp) 与 [`FrameTimeline.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/surfaceflinger/Scheduler/FrameTimeline.cpp)：帧调度、提交、合成、显示输出和帧分类。
- Android 17 [`task_state.cc`](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/types/task_state.cc)、[`self_dur.sql`](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/slices/self_dur.sql) 与 [`binder.sql`](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/android/binder.sql)：调度状态、Self Duration 和 Binder 关联实现。
- common kernel [`android17-6.18-2026-06_r6/include/linux/sched.h`](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/linux/sched.h)：Linux task 状态位定义。

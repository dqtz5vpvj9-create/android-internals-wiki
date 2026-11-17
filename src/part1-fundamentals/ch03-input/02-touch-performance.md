---
title: 触摸延迟、预测与低延迟渲染
chapter: '3.2'
section: '3.2'
status: finalized
applicable_versions: Android 10 (API 29) - Android 17 (API 37)
last_verified: '2026-10-12'
last_verified_against: AOSP android-17.0.0_r1 InputFlinger/InputTransport/ViewRootImpl/Choreographer/MotionPredictor/MotionEvent/InputEventAssigner/View.requestUnbufferedDispatch sources; external/perfetto android.input inputevent config and android.input stdlib docs; source.android.com Input/Winscope adb trace docs; AndroidX Input/Graphics low-latency docs | 2026-08-21 deep review added official unbuffered-dispatch warning boundary | 2026-10-12 idle audit checked pinned external/perfetto input.sql and EventHub.cpp, corrected read_time proxy boundary, and rechecked listed API/AndroidX/Winscope sources
last_idle_audit_at: '2026-10-12T14:43:23+08:00'
last_source_verified_at: '2026-10-12T14:43:23+08:00'
confidence: medium-high
sources:
- type: blog
  path: Personal-Knowlodge/source/Android-Systrace-Input.md
- type: blog
  path: Personal-Knowlodge/source/android-systrace-Responsiveness-in-action-1.md
- type: blog
  path: Personal-Knowlodge/source/2026-03-06_wechat_从input响应性能差的issue演示perfetto_trace用法.md
- type: official
  path: source.android.com/docs/core/interaction/input
- type: official
  path: source.android.com/docs/core/graphics/winscope/capture/adb
- type: official
  path: developer.android.com/reference/android/view/MotionEvent
- type: official
  path: developer.android.com/reference/android/view/View#requestUnbufferedDispatch(android.view.MotionEvent)
- type: official
  path: developer.android.com/reference/android/view/MotionPredictor
- type: official
  path: developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features
- type: official
  path: developer.android.com/jetpack/androidx/releases/input
- type: official
  path: developer.android.com/jetpack/androidx/releases/graphics
- type: official
  path: perfetto.dev/docs/analysis/stdlib-docs#android-input
- type: official
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/android/input.sql
- type: research
  path: DeepResearch/2026-05-11-hci-perception-input-latency-analysis.md
- type: research
  path: intake/research-feeds/2026-04-05-15-motionprediction-low-latency-graphics.md
tags:
  - touch
  - input-latency
  - hci
  - inputreader
  - inputdispatcher
  - sampling-rate
  - batching
  - resampling
related_chapters:
- '3.1'
- '2.3'
- '2.4'
- '2.2'
- '22.1'
- '8.1'
- '14.6'
- '16.3'
last_deep_review_at: '2026-08-21T09:15:41+08:00'
last_rework_at: '2026-08-12T09:45:30+08:00'
last_consolidated_at: '2026-08-11'
consolidated_from:
- src/part1-fundamentals/ch03-input/04-input-latency-prediction.md
- src/part1-fundamentals/ch03-input/09-input-latency-budget-perception.md
---

# 触摸延迟、预测与低延迟渲染

触摸体验由硬件采样、事件分发、应用处理、渲染与显示呈现共同决定，单看回调耗时往往会漏掉链路前后两端的等待。本节先统一“从输入到显示”的测量口径，再沿时间线拆解各个阶段的延迟来源，并说明批处理、重采样、轨迹预测与前缓冲低延迟渲染的边界。

## 为什么需要关注触摸响应

在列表滑动场景下抓取一份 Perfetto 系统跟踪，时间轴上会同步出现 `InputReader`、`InputDispatcher`、应用主线程、`RenderThread`、SurfaceFlinger 与显示帧等多条轨道。

从物理动作发生到显示内容更新的时间，通常称为触摸到显示延迟（touch-to-display latency）；若将终点推进到面板像素实际发生光学亮度变化，则称为触摸到光子延迟（touch-to-photon latency）。屏幕刷新周期只是其中的一个时间尺度——60 Hz 下每周期约 16.67 ms，120 Hz 下约 8.33 ms——事件落在 VSYNC 周期的哪个相位、应用是否赶上当前帧、缓冲区是否按期合成，都会显著改变最终结果。因此，讨论端到端延迟必须同步绑定设备型号、操作类型与统计分位数，脱离这些前提条件的“典型毫秒数”缺乏可比性。

工程上，触摸响应主要分为两类：

- **离散响应**：按下按钮后，下一帧何时显示按下态反馈或业务结果。
- **连续跟手**：手指或手写笔持续移动时，屏幕上的内容轨迹与当前物理位置之间存在多少时间与空间滞后。

由于连续跟手会不断暴露位置差，它通常比单次点击更容易让人感知到延迟。开展工程测试时，需要在目标设备上分别统计点击响应与连续手势，并至少记录刷新率、触控模式、冷机与热机状态、P50/P90/P99 分位数以及丢帧情况；只有结合这些运行条件，统计数字才能用于制定产品服务水平目标（SLA）。

## 先统一测量口径

“输入延迟”在不同上下文中可能指代四种起止点完全不同的区间，对比数据时必须先对齐口径：

| 口径 | 起点 | 终点 | 不包含的主要部分 |
|---|---|---|---|
| 硬件到读取（hardware-to-read） | 触控控制器或内核事件 | `EventHub` 或 `InputReader` 读到事件 | 应用处理、渲染和显示 |
| 分发到确认（dispatch-to-ACK） | `InputDispatcher` 发布事件 | 系统框架收到 `FINISHED` | 完成确认后的渲染、合成与面板输出 |
| 读取到呈现（read-to-present） | `EventHub` 记录的 `RawEvent.readTime` | 关联帧的呈现时间 | 触控 IC 扫描前段与面板光学响应 |
| 触摸到光子（touch-to-photon） | 物理接触 | 目标像素实际变化 | 原则上覆盖整条链，通常需要外部仪器 |

若要制定可落地的阶段预算，每一段都必须对应明确的测量依据，而不能将几个经验数值直接相加：

| 阶段 | 常用时间点 | 责任边界 |
|---|---|---|
| 采样与驱动 | 外部接触、evdev `eventTime`、`readTime` | 触控 IC、固件、总线与内核 |
| 读取与分发 | `readTime`、发布时间、接收时间 | `InputReader`、`InputDispatcher`、目标进程调度 |
| 应用处理 | 接收时间、完成时间、`deliverInputEvent` | View、Compose、IME、主线程和异步 `InputStage` |
| 生产与合成 | 帧开始、完成与呈现时间 | `Choreographer`、`RenderThread`、GPU、BufferQueue、SurfaceFlinger |
| 面板输出 | 从系统呈现到光学变化 | HWC、显示时序和面板响应 |

CPU 与 GPU 在时间轴上经常并行推进，多个采样点也可能合并到同一帧中；同时，FrameTimeline 记录的呈现时刻还可能早于面板像素完成光学响应的时刻。因此，预算表主要用于划分各环节的排查边界；将各段经验耗时直接相加，反而会掩盖上述并行与合帧带来的时间重叠。

<!-- gracker-diagram: ch03-02-latency-measurement-boundaries -->
![读取、完成确认、呈现、光学变化是不同终点](../../assets/diagrams/ch03/ch03-02-latency-measurement-boundaries.png)

图：物理接触、设备事件、EventHub 读取、分发确认、目标帧呈现和光学变化各有证据来源。dispatch-to-ACK 只量消息处理往返；真实 read-to-present 需要 RawEvent.readTime 与对应帧；touch-to-photon 还需外部触发和像素测量。图只表示边界先后和关联，不给出固定阶段耗时。

### 人机交互的感知阈值

连续直接操控与离散点击反馈的感知敏感度差异显著。在 UIST 2012 的连续拖动实验中，参与者在特定装置与 1 ms 参照延迟下测得的差别阈限（JND）约为 2.38–11.36 ms（即刚能察觉到延迟变化的最小增量）；而 CHI 2013 的落点反馈实验则给出了更宽的 20–100 ms 区间。这一差异表明，交互任务类型本身会显著改变人的感知敏感度，不能把某一实验阈值直接套用为 Android 17 设备的通用验收线。

制定产品指标时应按交互类型分别设立：点击交互重点关注首个可见反馈延迟；拖动与书写交互需同时考察时间滞后、空间偏差、步幅波动与预测误差；游戏场景还应将本地输入判定、渲染帧与网络确认拆开统计。同一套测试脚本至少应覆盖 P50、P90、P95、刷新率、温控与电源模式。

## 触摸响应延迟的组成

从手指触碰屏幕到画面完成更新，触摸事件依次经过七个阶段。下面按时间顺序逐段梳理各阶段可用的时间戳、观测证据以及适用边界，最后汇总成端到端的延迟全景。

### 1. 硬件采样（触摸屏 → 驱动）

触控控制器扫描面板后，将触点报告发送至 SoC（片上系统）。面板扫描、滤波、去抖、总线上报与驱动中断均由硬件和驱动实现，AOSP 并未规定总线协议或固定采样率。若设备以近似恒定的频率上报，采样周期可按 `1 / samplingRate` 粗略估算：

- **120 Hz**：约 8.33 ms 一个采样周期
- **240 Hz**：约 4.17 ms 一个采样周期
- **480 Hz**：约 2.08 ms 一个采样周期

上述周期仅反映理想条件下的相位等待上界，控制器内部的滤波与上报策略仍需结合具体设备核实。更高的采样率通常有助于缩短首次触摸检测的等待时间，并为轨迹重建提供更密集的 `MOVE` 样本；即便这些样本随后被合并进同一个 `MotionEvent`，应用仍可读取历史样本，系统也能基于它们执行重采样。因此，高于显示帧率的采样点并非无用，它们能否改善画面表现，取决于应用是否消费历史样本、是否启用无缓冲分发，以及渲染和显示环节是否及时完成。

### 2. 内核处理（驱动 → EventHub）

触摸驱动向 Linux input core 上报事件后，evdev 通过 `/dev/input/eventX` 节点暴露 `input_event` 数据流。Android 的 `EventHub` 借助 inotify 监听设备节点增删，并通过 epoll 等待已打开文件描述符上的可读事件；线程被唤醒后，`getEvents()` 会批量读取可用事件。

`EventHub::getEvents()` 会为每条 `RawEvent` 记录两个关键时间戳：

- `when`：经 `processEventTimestamp()` 处理后的内核事件时间；
- `readTime`：`EventHub` 从设备节点读取事件时记录的 `SYSTEM_TIME_MONOTONIC` 时间。

借助 `readTime - when`，可以判断事件在驱动、evdev 与 `EventHub` 读取之间是否出现滞留。这一差值的实际水平需从目标设备的系统跟踪或日志中实测，源码本身并未保证其必然小于 1 ms。

### 3. InputReader 读取和加工

`InputReader` 是运行在 `system_server` 进程中的原生线程。它从 `EventHub` 读取原始 `input_event` 后，完成设备映射、坐标变换、多点触控组装及工具类型识别等操作，生成 `NotifyArgs`；这组参数随后沿着监听链依次经过误触处理、指针视觉状态管理、可选动作分类与过滤等阶段，最终送达 `InputDispatcher`。

核心读取循环位于 `InputReader::loopOnce()` 中：

```cpp
// frameworks/native/services/inputflinger/reader/InputReader.cpp (android-17.0.0_r1)
// 结构化伪代码：保留锁边界，省略配置刷新和设备变更
void InputReader::loopOnce() {
    std::vector<RawEvent> events = mEventHub->getEvents(timeoutMillis);
    std::list<NotifyArgs> notifyArgs;
    {
        std::scoped_lock lock(mLock);
        if (!events.empty()) {
            mPendingArgs += processEventsLocked(events.data(), events.size());
        }
        std::swap(notifyArgs, mPendingArgs);
    }
    for (const NotifyArgs& args : notifyArgs) {
        mNextListener.notify(args);
    }
}
```

这段逻辑揭示了三个关键边界：`getEvents()` 返回 `std::vector<RawEvent>`；事件映射与设备状态更新在 `InputReader` 锁内完成；向后续监听器的分发通知则放在锁外执行。尽管 `loopOnce()` 单次可能读回一批 evdev 事件，但这批 `RawEvent` 与应用侧收到的合成 `MotionEvent` 分属不同抽象层级，排查时需分开对应。

### 4. InputDispatcher 派发

`InputDispatcher` 同样是运行在 `system_server` 中的原生线程。监听链交付 `NotifyArgs` 后，事件入队并唤醒分发器的 Looper。随后分发器依据焦点状态、窗口拓扑、触摸状态、手势监视器与安全策略选出一个或多个目标窗口；由于路由规则始终面向窗口本身，Activity 只是窗口背后的上层组件。

事件在 `InputDispatcher` 内部会依次流经三个核心队列：

1. **输入队列（InboundQueue，计数器 `iq`）**：`InputReader` 交付的事件先进入这里，`InputDispatcher` 从队首取出事件开始处理；
2. **输出队列（OutboundQueue，计数器 `oq`）**：每个目标 `Connection` 都有一条输出队列。事件被包装成 `DispatchEntry` 后进入此队列，等待发布到 `InputChannel`；
3. **等待队列（WaitQueue，计数器 `wq`）**：发布成功后，条目从输出队列移到等待队列，等待应用返回 `FINISHED`。回收路径由 `handleReceiveCallback()` 接收响应，再经 `finishDispatchCycleLocked()` 和 `doDispatchCycleFinishedCommand()` 按序列号删除等待队列条目。

需要注意的是，`FINISHED` 仅代表应用结束了这枚输入事件的分发责任，并不说明对应画面已经呈现。一旦事件触发异步 `InputStage`，或应用主线程迟迟未执行到 `finishInputEvent()`，等待队列就会保持非空；而图形渲染也可能在完成确认发出之后才继续推进。因此，输入确认延迟与触摸到显示延迟必须分开测量。

在 Perfetto 中，上述三个队列以计数器轨道呈现，其数值由 `ATRACE_INT` 写入的 `iq`、`oq:<channel>` 与 `wq:<channel>` 提供，反映的是实时积压数量变化，而不像执行片段那样带有起止区间。其中 `iq` 统计尚未分发的输入事件，`oq` 统计已选定目标但尚未写入通道的事件，`wq` 统计已发布但尚未收回完成确认的事件。

解读这些计数器时必须结合持续时间：在事件发布与确认回传之间，队列长度短暂跳为 1 属于正常现象，只有当数值持续爬升或长时间不归零时，才提示存在背压。进一步地，`wq` 升高只能证明应用侧尚未完成确认；至于瓶颈究竟在于主线程阻塞、异步 `InputStage` 挂起还是套接字回写延迟，仍需回到应用进程内部的时间轴确认。

此外，分析手写笔、手掌误触及边缘触控问题时，还应同步核查 `MotionEvent` 的分类结果与取消路径。分类结果可能会影响触摸位移阈值（touch slop）、长按判定或误触撤回；遇到首笔触控未生效的情况时，应先排查应用是否收到了 `ACTION_CANCEL` 或 `FLAG_CANCELED`，等待队列只是众多线索之一。

### 5. 跨进程传输（socketpair）

`InputDispatcher` 借助 `InputChannel` 将事件投递至目标进程。该通道基于 `socketpair(AF_UNIX, SOCK_SEQPACKET, ...)` 创建并设为非阻塞模式，由 `InputChannel::sendMessage()` 与 `receiveMessage()` 负责收发。应用侧的 `NativeInputEventReceiver` 会将通道文件描述符注册到主线程 Looper，待文件描述符可读时再读取消息。

在此过程中，需要将套接字写入耗时与接收线程实际获得 CPU 的时刻区分开来。即使消息早已写入内核套接字缓冲区，应用主线程处于 Running、Runnable、Blocked 还是 Sleeping 状态，也会导致消费时刻出现显著差异。至于 Binder 压力，只有在它引发 CPU 争抢或导致应用主线程同步等待时才构成间接关联——Binder 与 `InputChannel` 属于两条各自独立的数据通路。

### 6. 应用端处理（View 树）

`NativeInputEventReceiver` 将原生消息转换为 Java `InputEvent` 后，`WindowInputEventReceiver` 会将其入队至 `ViewRootImpl` 的待处理队列，队列长度由 `aq:pending:<window>` 计数器记录，同时系统会打上同步与异步的 `deliverInputEvent` 轨迹区段以覆盖整段处理。触摸等指针事件通常从 IME 后处理阶段切入 `EarlyPostImeInputStage`、`NativePostImeInputStage` 与 `ViewPostImeInputStage`，进而交给 View 树消费。

`DOWN` 事件到来时，`ViewGroup` 可能需要遍历并试探多个候选子 View；一旦确立 `TouchTarget`，后续事件通常沿既定目标路径直达终点，而不会在每次 `MOVE` 时重新扫描整棵 View 树。事件处理可能仅更新滚动偏移或内部状态，也可能触发 `invalidate()`、`requestLayout()` 或属性动画；前者通常只引起重绘，后者则可能在下一帧遍历中触发测量、布局与绘制。

### 7. 渲染上屏

输入触发的状态变化必须汇入具体渲染帧，依次经过应用遍历、`RenderThread`、GPU、BufferQueue、SurfaceFlinger 与显示输出。其中任一环节错过当前帧的截止时间，都可能使可见反馈顺延一个或多个刷新周期。实际排查中，渲染阶段未必总是耗时最长的一环，拿到系统跟踪后需要将主线程调度、输入处理、GPU 执行与合成放到同一条时间线上逐段排查。

### 延迟全景图

相比套用一组脱离上下文的“典型耗时”，直接以源码中存在明确锚点的时间边界构建测量表更为可靠：

| 边界 | Android 17 证据 | 能回答的问题 |
|---|---|---|
| 设备事件 → `EventHub` 读取 | `RawEvent.when`、`RawEvent.readTime` | 驱动与 evdev 到读取之间是否滞留 |
| `InputDispatcher` 入队与发布 | `android.input.inputevent`、`iq`、`oq:*` | 系统侧是否积压、目标窗口是谁 |
| 发布 → 应用消费与完成 | 发布、消费、完成时序，`wq:*` | 调度与应用输入处理是否拖延 |
| 应用输入 → 目标帧 | `deliverInputEvent`、`aq:pending:*`、`Choreographer`、输入事件 ID | 哪枚事件驱动了哪一帧 |
| 目标帧 → 呈现 | FrameTimeline、RenderThread、GPU、SurfaceFlinger | 画面为何晚一个或多个刷新周期 |

使用 `InputEventAssigner` 做端到端关联时需注意一个约束：在连续手势中，每一帧只会关联一枚输入事件 ID。首帧优先关联尚未处理的 `DOWN`，后续帧通常关联该帧之前的最新事件，中间的 `MOVE` 可能没有独立的帧归因。因此，分析连续手势时需同时保留事件 ID 与历史样本，逐帧核对采样点的映射关系。

<!-- gracker-diagram: ch03-02-event-to-frame-attribution -->
![一帧只归因一枚输入 ID，中间 MOVE 可能没有独立帧](../../assets/diagrams/ch03/ch03-02-event-to-frame-attribution.png)

图：源码示例为 DOWN → MOVE1 → MOVE2 → VSYNC1 → MOVE3 → VSYNC2。VSYNC1 对应帧仍优先使用未处理 DOWN 的 ID；notifyFrameProcessed 清除该优先状态后，VSYNC2 对应帧使用 MOVE3。MOVE1 / MOVE2 未独立归因不表示它们没有被消费。

## 触摸采样率与跟手性

### 采样率与刷新率

这两个指标常被并列提及，但度量的是硬件链路中两件相互独立的工作：

- **触摸采样率**：触摸屏硬件每秒检测手指位置的次数。120 Hz 表示每秒检测 120 次；
- **屏幕刷新率**：屏幕每秒更新画面的次数。120 Hz 表示每秒刷新 120 次。

采样率决定了触点坐标的时间密度，刷新率则限定了屏幕更新画面的频率。两者独立运行且相位无需对齐：例如 240 Hz 触控配合 120 Hz 显示时，理想情况下每个显示周期大约能收到两个触控样本；120 Hz 触控配合 60 Hz 显示同样约为两个。尽管前者的采样周期与显示周期都缩短了一半，但具体事件能否赶上最近一帧，仍取决于其到达时刻与后续整条处理链路的耗时，仅凭频率比并不能直接推导出端到端延迟。

### 采样率和渲染帧率的匹配

评估高触控采样率能带来多少收益，主要取决于两个前提：应用如何消费这些样本，以及设备每秒能呈现多少帧：

- **60 fps + 120 Hz 触控**：按理想固定频率估算，一个显示周期约有两个样本。它们可以合并到一个 `MotionEvent` 中，较早的点通过历史样本接口读取；
- **60 fps + 240 Hz 触控**：一个显示周期约有四个样本。列表仍然只能每帧呈现一次位置，但笔迹拟合、速度估计和轨迹预测可以使用更密集的数据；
- **120 fps + 240 Hz 触控**：一个显示周期约有两个样本；更短的显示周期也会缩短错过一帧后的等待；
- **无缓冲分发与前缓冲渲染**：前者缩短 `MOVE` 进入应用前的等待，后者缩短局部笔迹从绘制到可见的路径。两者作用于不同阶段，都需要设备与应用实现配合。

上述样本数基于理想固定频率比估算，设备运行时的实际样本数以实测为准——触控控制器可能动态调整报点率，显示器也可能处于 VRR（可变刷新率）模式。验证硬件规格时，应直接依据驱动事件时间或结构化输入跟踪统计相邻样本的时间间隔。

<!-- gracker-diagram: ch03-02-sampling-display-phases -->
![240 Hz 采样与 120 Hz 显示：频率比不等于每帧延迟](../../assets/diagrams/ch03/ch03-02-sampling-display-phases.png)

图：理想示例中，240 Hz 采样间隔约 4.17 ms，120 Hz 显示周期约 8.33 ms。多个真实样本可以参与同一帧的 MotionEvent 历史点、速度估计或轨迹拟合；实际采样与刷新相位不必对齐，事件还要及时经过处理与渲染才能赶上显示机会。

## 输入事件批处理与 Choreographer 的配合

### 为什么需要批处理

当触摸采样率高于渲染帧率时，单个 VSYNC 周期内往往会到达多个 `ACTION_MOVE` 样本。如果每收到一个样本就立即唤醒应用并执行完整的 View 树分发，不仅会加重 Looper 唤醒与业务回调负担，即使多次重绘请求最终被合并到同一帧，前面重复执行的 CPU 计算也属于浪费。批处理机制正是通过将多个样本打包交付，减少这类冗余开销。

Android 的输入批处理采用合并交付策略，中间采样坐标并不会被丢弃。应用侧的 `InputConsumer` 会将彼此兼容的 `ACTION_MOVE` 或 `ACTION_HOVER_MOVE` 消息聚合成批；消费时以第一条样本初始化 `MotionEvent`，后续样本则通过 `addSample()` 写入历史记录。应用既可以通过 `getX()` 与 `getY()` 获取最新坐标，也可以通过 `getHistorySize()` 与 `getHistorical*()` 遍历较早的样本。

下面的代码按时间顺序遍历包含历史样本的 `MotionEvent`，适用于画笔绘制与轨迹记录场景；普通列表滚动通常只需读取当前最新坐标：

```java
final int historySize = event.getHistorySize();
for (int h = 0; h < historySize; h++) {
    float historicalX = event.getHistoricalX(0, h);
    float historicalY = event.getHistoricalY(0, h);
    // 处理 batched 历史样本
}
float latestX = event.getX();
float latestY = event.getY();
```

由于这些历史点均封装在同一个 `MotionEvent` 中，Perfetto 里通常只会记录一次 Java `deliverInputEvent`；原生轨迹区段 `dispatchInputEvent MotionEvent ... historySize=N` 会直接标明所包含的历史样本数量。分析轨迹时需留意，一个事件携带 N 个历史样本只对应一次 View 分发，不应按 N 次分发来算。

### 批处理之外还有重采样

批处理决定多个样本如何合并交付，而重采样（resampling）则用于让坐标时间更加贴近显示帧时序。在常规 `ViewRootImpl` 路径中，应用进程 JNI 持有的 `InputConsumer` 在消费一批事件时，只要 `frameTimeNanos` 有效且厂商未关闭 `ro.input.resampling`，就会以 `frameTimeNanos - 5 ms` 为目标时刻，在真实样本之间执行线性插值，或基于最近两个样本做受限外推。

这 5 ms 是重采样目标相对于帧时间的相位偏移，目的是为插值留出后续样本并限制错误外推，并不意味着系统额外空等了 5 ms；计算触摸到显示耗时时，也不应把这 5 ms 单独累加进去。当有效帧时间、样本间隔、工具类型或厂商开关不满足要求时，重采样会自动跳过。

从 API 35 起，应用可以通过 `MotionEvent.PointerCoords.isResampled()` 检查指定坐标是否由重采样生成。该方法定义在 `PointerCoords` 上，典型读取方式如下：

```java
MotionEvent.PointerCoords coords = new MotionEvent.PointerCoords();
event.getPointerCoords(pointerIndex, coords);
boolean currentIsResampled = coords.isResampled();

for (int h = 0; h < event.getHistorySize(); h++) {
    event.getHistoricalPointerCoords(pointerIndex, h, coords);
    boolean historicalIsResampled = coords.isResampled();
}
```

生成的重采样坐标会作为新样本追加到当前批次中，但每个事件里至少会保留一个来自设备的真实样本。若应用启用了无缓冲分发，系统会调用 `consumeBatchedInputEvents(-1)` 立即取走所有待处理样本；而旧版 `InputConsumer::consumeBatch()` 在 `frameTime < 0` 时会直接返回，不会执行重采样。

### Choreographer 中输入回调的优先级

在 `android-17.0.0_r1` 的 `Choreographer#doFrame()` 中，各类回调按以下顺序依次执行：

1. `CALLBACK_INPUT`
2. `CALLBACK_ANIMATION`
3. `CALLBACK_INSETS_ANIMATION`
4. `CALLBACK_TRAVERSAL`
5. `CALLBACK_COMMIT`

其中 `CALLBACK_COMMIT` 运行在遍历之后，主要处理该帧的绘制后收尾与时间基准修正，并不负责测量、布局或绘制。分析输入延迟时，重点关注前四段即可：输入回调排在最前，确保随后的动画更新与视图遍历都能基于最新输入状态推进。

对于连续的 `MOVE` 事件，系统默认采用缓冲路径。`ViewRootImpl.WindowInputEventReceiver#onBatchedInputEventPending()` 会检查 `mUnbufferedInputDispatch` 与 `mUnbufferedInputSource`：只有当前序列请求了无缓冲分发时，才会直接调用 `consumeBatchedInputEvents(-1)`；否则调用 `scheduleConsumeBatchedInput()`，让事件在接近下一帧输入阶段时集中消费。

这一分支决定了 `MOVE` 事件是立即送达还是在帧边界消费。对于普通列表滚动，保留默认缓冲路径既能减少 Looper 唤醒与 View 分发次数，也能保留系统重采样的机会；`View.requestUnbufferedDispatch(event)` 的官方文档也明确提示它并不适合多数应用，随意启用可能推高延迟、引入滚动抖动并丧失重采样收益。

在笔迹书写、绘图或签名等场景下，一旦确认目标 View 与手势归属，可以在已 attach 的 View 上针对触摸 `ACTION_DOWN` 或 `ACTION_MOVE` 请求无缓冲分发；该设置仅作用于直至对应 `ACTION_UP` 为止的当前手势序列。即便事件得以提前交付，应用仍需逐个处理事件，CPU 调度与回调负载也会相应上升。

<!-- gracker-diagram: ch03-02-batched-versus-unbuffered -->
![批处理保留历史点，无缓冲分发改变交付时机](../../assets/diagrams/ch03/ch03-02-batched-versus-unbuffered.png)

图：兼容 MOVE / HOVER_MOVE 样本可进入批处理。默认路径安排 CALLBACK_INPUT，携有效 frameTime 消费并保留重采样机会；无缓冲请求则立即以 -1 消费待处理样本，常规实现跳过重采样。无缓冲不是系统通用性能开关，普通滚动仍要考虑唤醒、分发压力和抖动。

### 批处理与等待队列在 Perfetto 中的表现

输入批处理与应用消费能力在 Perfetto 中反映在不同的轨道和片段上，分析时应分别读取：

**InputDispatcher 侧——分发与完成确认的背压**：

1. 找到 `system_server` 进程中的 `InputDispatcher` 线程，看 `iq`、`oq:<channel>`、`wq:<channel>` 这三个 `ATRACE_INT` 计数器的长度和持续时间；三个队列各自的含义见上文“4. InputDispatcher 派发”；
2. `WaitQueue` 反映已经分发、仍在等待应用完成确认的事件数量；`wq` 堆积说明应用端处理缓慢或确认回写延迟，和批处理本身是两回事；
3. 等待队列持续堆积且不下降时，转到目标应用检查主线程、异步 `InputStage` 与回写；这三种原因在计数器上看起来一样，要到应用侧分别确认。

**应用侧——批量事件消费**：

1. 切换到应用进程的主线程轨道；
2. 查找原生区段 `dispatchInputEvent MotionEvent ... historySize=N`，确认应用收到的 `MotionEvent` 是否包含历史样本；
3. 查找 `deliverInputEvent src=... eventTimeNano=... id=...` 与异步 `deliverInputEvent`，确认 Java 输入处理的起止时间；
4. 观察 `aq:pending:<window>`，判断事件是否在 `ViewRootImpl` 待处理队列中等待；
5. 将事件 ID 与 FrameTimeline 和应用帧关联，确认输入更新进入哪一帧，以及该帧何时呈现。

两条证据链各自回答不同问题：`InputDispatcher` 的 `wq:*` 用于排查分发与完成确认环节的背压，而 `historySize` 与 `MotionEvent` 历史样本才是判断批处理的直接证据。`Choreographer` 的输入回调通常显示为 `input` 阶段，具体名称可能随 Perfetto 版本与采集配置略有差异。

## 输入重采样的源码边界

`android-17.0.0_r1` 的源码树中同时并存着两套相关实现：

- `libs/input/InputConsumer.cpp`：当前 `android_view_InputEventReceiver.cpp` 中的 `NativeInputEventReceiver` 直接构造并使用这套 `InputConsumer`，重采样逻辑仍内嵌在该文件中。
- `libs/input/InputConsumerNoResampling.cpp` 与 `libs/input/Resampler.cpp`：将批处理传输与 `LegacyResampler`、`FilteredLegacyResampler` 解耦拆分；Android 17 源树已经编译并测试了这组实现，但常规 `ViewRootImpl` JNI 代码尚未切换到这里。

因此，分析应用现网行为时仍应以第一条实际调用链为准，第二套代码则揭示了后续的重构方向，目前常规应用尚未切换过去。两套实现沿用了同一组经典算法常量与边界条件：

- 目标时间为 `sampleTime = frameTime - 5 ms`；
- 若一批事件中还有目标时间之后的未来样本，则在当前样本与未来样本之间线性插值；两点间隔至少为 2 ms；
- 没有未来样本时，使用最近两个点外推；两点间隔必须在 2 ms 到 20 ms 之间；
- 外推最远到 `current.eventTime + min(delta / 2, 8 ms)`；
- 支持 `FINGER`、`MOUSE`、`STYLUS`、`UNKNOWN` 工具类型，并要求触点 ID、工具类型和显示器等条件一致；
- 只对指针来源的 `ACTION_MOVE` 执行；厂商可以通过只读属性 `ro.input.resampling=0` 关闭。

实际的系统与应用调用链可以概括为：

```text
evdev → EventHub → InputReader → TouchInputMapper → InputDispatcher
    → InputChannel/Unix SOCK_SEQPACKET
    → app NativeInputEventReceiver
    → InputConsumer.consume(..., frameTimeNanos)
    → InputConsumer::consumeBatch()
    → InputConsumer::resampleTouchState()
    → WindowInputEventReceiver → ViewRootImpl InputStage → View
```

由此可见，重采样发生在目标应用进程内部，而不在 `InputReader` 或 `InputDispatcher` 中。虽然插值或受限外推能让 `MOVE` 坐标更贴近帧时序，但在急转弯、速度突变或采样点稀疏时仍可能引入偏差；评估效果时需同时对照真实样本、重采样标记与最终笔迹，不能只看坐标时间戳是否对齐了帧时间。

<!-- gracker-diagram: ch03-02-resampling-time-target -->
![重采样对齐目标时间：插值或有边界的外推](../../assets/diagrams/ch03/ch03-02-resampling-time-target.png)

图：常规 ViewRootImpl JNI 的 InputConsumer 在条件满足时取 sampleTime = frameTime − 5 ms。有后续真实样本时线性插值；没有时用最近两个真实样本受限外推，最远不超过最新样本 eventTime + min(delta / 2, 8 ms)。5 ms 是目标相位偏移，不是额外睡眠。

## 触摸场景的性能分析方法

### 从 Input 事件路径定位瓶颈

定位触摸卡顿或延迟问题时，需要先分清究竟属于“事件晚到”“应用晚处理”还是“画面晚出现”，再沿事件 ID 与帧 ID 按以下顺序逐步追踪：

1. **确认设备事件时间**：比较 evdev 事件时间与 `EventHub` 读取时间，排除触控固件、驱动和读取延迟；
2. **检查 InputDispatcher**：观察结构化输入事件、`iq`、目标连接的 `oq:*` 与 `wq:*`，确认窗口选择、发布和完成确认；
3. **检查应用主线程**：从套接字可读或原生分发到 `deliverInputEvent`，区分 Running、Runnable、Sleeping 和锁等待；
4. **检查批处理**：读取 `historySize`，确认事件是否在 `CALLBACK_INPUT` 中消费，以及业务是否遗漏历史样本；
5. **检查目标帧**：用输入事件 ID、应用 FrameTimeline 和 SurfaceFlinger FrameTimeline 关联到呈现时间；
6. **归因资源瓶颈**：根据调度器、CPU 频率、GPU 和内存轨道解释等待，避免根据一个函数名直接猜测原因。

### 采集结构化 Input Trace

InputFlinger 注册了 `android.input.inputevent` Perfetto 数据源，但仅允许在可调试的 `userdebug` 或 `eng` 构建上采集。该数据源能够记录分发器输入事件和窗口分发信息，支持完整或脱敏记录级别，也可按安全窗口、IME 状态与目标包规则过滤。由于完整记录可能包含敏感坐标，仅适合在本地测试设备上启用，现场采集必须配置严格的脱敏与过滤规则。

下面的最小配置用于在本地测试机上短时间抓取完整输入事件；若还需要查看线程调度、CPU 频率与 ATRACE 轨迹，需同时启用 `linux.ftrace`：

```textproto
buffers: {
  size_kb: 32768
  fill_policy: RING_BUFFER
}
data_sources: {
  config {
    name: "android.input.inputevent"
    android_input_event_config {
      mode: TRACE_MODE_TRACE_ALL
    }
  }
}
```

需要留意，`TRACE_MODE_TRACE_ALL` 不适合直接用于现场或用户数据采集，正式采样配置应改为过滤规则并确认输出已经脱敏。

### 案例：输入提频未生效导致响应变慢

下面这个设备案例展示了如何从函数执行片段切入到底层调度来定位耗时。在某次系统跟踪中，`processInputEventForCompatibility` 区段持续了约 4 ms，但仅靠 AOSP 自身的逻辑复杂度无法解释这么长的墙钟时间。展开线程调度与频率状态后可以看到：

- 线程在该区段内并不总是 Running，中间存在被抢占和 Runnable 等待；
- 第二次触摸没有复现该设备第一次触摸时的频率变化，主线程以较低频率执行；
- 同时唤醒的硬件服务计时器线程占用了 CPU，应用主线程因此延后获得运行机会。

这一结论针对的是当时的具体设备实现：厂商输入提频策略未按预期触发，叠加后台线程 CPU 竞争，共同放大了墙钟耗时。AOSP 本身并不保证所有设备都具备同名的 CPU 提频机制，也未规定输入后必须在几毫秒内升到特定频点。实际排查时，应把执行片段拆分为 Running 时间与非 Running 时间，再结合 CPU 频率、调度与厂商策略解释差值。

### Perfetto 中的关键轨道与执行片段

分析触摸响应时，可以重点对照以下轨道、计数器和执行片段：

**`system_server` 进程：**
- **InputReader 线程**：结合 `android.input.inputevent` 中的 evdev 与输入事件时间和线程调度，统计相邻采样间隔；线程唤醒间隔和硬件固定采样率是两回事。
- **InputDispatcher 线程**：观察 `iq`、`oq:<channel>`、`wq:<channel>` 的长度与持续时间。
  - `iq` 连续增长：dispatcher 消费速度落后于输入或其他进入系统的事件；
  - `oq` 长时间不降：消息尚未成功发布，需要检查连接状态和套接字可写性；
  - `wq` 长时间不降：已发布事件尚未收到完成确认，需要转到目标应用继续分析。

**应用进程：**
- **主线程轨道**：
  - Native `dispatchInputEvent MotionEvent ... historySize=N`
  - `aq:pending:<window>` 与 `deliverInputEvent`
  - Choreographer 的 `input`、`animation`、`insets_animation`、`traversal`、`commit`
- **FrameTimeline**：确认应用帧是否错过截止时间，以及 SurfaceFlinger 帧何时呈现；
- **CPU 与调度器轨道**：确认主线程和 `RenderThread` 的 Running、Runnable、Blocked 区间，再检查 CPU 频率。

### 用 `android.input` 拆分“分发到确认”与“读取到呈现”

Perfetto 标准库中的 `android_input_events` 表将跨进程套接字往返与关联帧拆分统计：

- `dispatch_latency_dur = receive.ts - dispatch.ts`；
- `handling_latency_dur = finish.ts - receive.ts`；
- `ack_latency_dur = finish_ack.ts - finish.ts`；
- `total_latency_dur = finish_ack.ts - dispatch.ts`；
- `end_to_end_latency_dur = frame.present_time - frame.read_time`。

其中 `total_latency_dur` 仅计算到收到 `FINISHED` 完成确认为止，并不代表画面已经上屏。在 `android-17.0.0_r1` 附带的 `android.input` 实现里，`read_time` 取自 `UnwantedInteractionBlocker::notifyMotion...` 区段的起始时刻，作为读取阶段的代理时间点，而没有直接使用 `EventHub` 记录的 `RawEvent.readTime`。因此，`end_to_end_latency_dur` 衡量的是该代理点到关联帧呈现的时间跨度，并不包含触控 IC 前段及面板光学响应；若需要精确计算从设备节点读取到画面呈现的耗时，仍需另行提取真实 `RawEvent.readTime` 并按同一事件关联呈现时刻。

此外，标准库默认将与同线程区间相交的 `doFrame` 作为规则匹配，若无相交帧则选择随后一帧并标记 `is_speculative_frame`。这些结果仅属于待核验的候选帧，不能直接充当输入触发该帧画面的证明。在固定的 r1 实现中，查询最终仅按通道内序号连接附件，且全局未丢弃帧的选择逻辑缺少进程过滤与排序约束——在包含两个独立通道的合成 Trace 中已经复现出两次投递被扩展成四行，并污染输入 ID、读取时间与帧归属的现象。因此，带有推测标记的样本不能直接混入“真实输入到呈现”的总体分布，往返统计也必须先按消息身份去重，详细用法见 §14.5。

<!-- gracker-diagram: ch03-02-perfetto-ack-and-present -->
![Perfetto total_latency 到 ACK，end_to_end 使用读取代理点](../../assets/diagrams/ch03/ch03-02-perfetto-ack-and-present.png)

图：android.input 的 total_latency_dur 是 dispatch 到 finish_ack；end_to_end_latency_dur 是 frame.present_time − frame.read_time。Android17 随附 SQL 的 read_time 来自 UnwantedInteractionBlocker::notifyMotion 区段起点，属于读取阶段代理，不能冒充真实 RawEvent.readTime。帧侧公式表达的是候选区间；推测标记、附件歧义和底层事件/帧身份需共同核验，字段非空不能证明关联正确。

```sql
INCLUDE PERFETTO MODULE android.input;

WITH candidates AS (
  SELECT *, COUNT(*) OVER (
    PARTITION BY upid, event_channel, event_seq, dispatch_ts, receive_ts
  ) AS attachment_row_count
  FROM android_input_events
)
SELECT upid, pid, process_name, thread_name AS finish_thread_name,
  event_channel, event_seq, dispatch_ts, receive_ts, receive_track_id,
  input_event_id AS candidate_input_event_id,
  event_action AS candidate_action,
  total_latency_dur / 1e6 AS dispatch_to_ack_ms,
  end_to_end_latency_dur / 1e6 AS candidate_read_to_present_ms,
  frame_id AS candidate_surface_frame_token, is_speculative_frame,
  attachment_row_count,
  CASE WHEN attachment_row_count > 1 THEN 'ambiguous_attachment'
       WHEN frame_id IS NULL THEN 'missing_frame_candidate'
       ELSE 'unverified_stdlib_candidate' END AS association_status
FROM candidates
WHERE end_to_end_latency_dur IS NOT NULL
ORDER BY total_latency_dur DESC, upid, dispatch_ts, event_channel
LIMIT 50;
```

`android_motion_events`、`android_key_events` 和 `android_input_event_dispatch` 均源自结构化 `android.input.inputevent` 数据源。后者通过 `event_id`、`vsync_id` 与 `window_id` 记录投递映射关系，本身并不包含分发开始、结束或完成确认的耗时字段。

在 FrameTimeline 中，还可能出现“帧率平稳但视觉内容整体滞后一帧”的高延迟状态。例如典型的 Buffer Stuffing（缓冲区持续排队）会让应用在旧缓冲区尚未呈现前就不断提交新缓冲区：虽然每一帧的 CPU 与 GPU 工作都能按时完成，但用户看到的画面始终落后。排查这类问题时，需要联合核对 `on_time_finish`、`present_type`、`jank_type`、SurfaceFlinger `DisplayFrame` 以及实际呈现时间，仅凭“没有掉帧”无法断定输入延迟正常。

### 用 dumpsys input 辅助排查

`adb shell dumpsys input` 可以抓取输入系统的实时状态快照，涵盖以下关键字段：

- `EventHub` 与 `InputReader` 的设备、映射器和配置状态；
- 焦点应用与窗口、当前触摸状态和指针捕获；
- `RecentQueue`：最多 10 个最近分发或丢弃的事件及其 `age`；
- `PendingEvent`、`InboundQueue`；
- 每个连接的状态、是否可响应、输出队列和等待队列；非空条目会附带事件年龄等描述。

其中的 `age` 是执行 `dumpsys` 瞬间计算出的瞬时年龄，并不存在“正常必小于 16 ms”的通用阈值。等待队列的 ANR 截止时间是在事件发布时按连接设定的，默认基值为 5000 ms 再乘 `HwTimeoutMultiplier()`，且窗口或应用均可覆盖该分发超时。评估积压风险时，需要对照具体连接的超时设置、可响应标记以及连续多次采样的变化趋势。

## 常见触摸卡顿原因

### 1. 主线程阻塞

当应用主线程在执行磁盘 I/O、数据库查询、复杂计算或同步等待 Binder 调用返回时，队列中等待分发的输入事件也会顺延推迟。

在 Perfetto 中的典型表现：
- 主线程长时间处于 **Running** 状态但没有处理输入
- 主线程长时间 **Runnable** 却得不到 CPU，或阻塞在 Binder、futex、I/O
- `wq` 持续堆积
- 最早的等待队列条目越过该连接的分发超时后，`InputDispatcher` 会把连接判定为无响应

常见诱因：
- `onCreate()` 或 `onResume()` 中执行了过多初始化工作
- 主线程访问数据库或 SharedPreferences
- 主线程同步等待网络、Binder 或文件 I/O
- 主线程在 `synchronized` 块或 `ReentrantLock` 上持锁等待

### 2. 过深的 View 层级

触摸事件从根 View 进入 `dispatchPointerEvent()`，随后沿着命中的子树与当前 `TouchTarget` 路径执行 `dispatchTouchEvent()`。虽然每一层 `ViewGroup` 都可能执行拦截判断、坐标变换与监听器回调，但后续 `MOVE` 并不需要无条件扫描整棵树。层级过深主要会拉高固定调用栈开销，而复杂的自定义命中测试、业务逻辑监听器与手势识别往往更值得优先排查。

批处理后的一个 `MotionEvent` 只会触发一次 View 分发；只有当应用主动遍历历史样本，或开启无缓冲分发接收到更密集的事件时，才会针对更多样本运行自身的轨迹逻辑。因此，触摸分发的实际开销不能简单按“采样点数量 × 整棵 View 树深度”估算。

常见优化思路：
- 用系统跟踪或方法级采样确认 `dispatchTouchEvent()`、手势检测器和业务监听器的耗时；
- 删除没有布局或语义价值的包装层；是否改用 `ConstraintLayout` 要以测量和布局数据为依据；
- 避免在 MOVE 回调中分配大量临时对象、同步 I/O、复杂路径运算或重复 `requestLayout()`；
- 自定义容器只在手势归属明确后拦截，并正确发送和处理 `ACTION_CANCEL`。

### 3. 事件分发冲突

嵌套滚动、`ViewPager` 与横向列表以及自定义手势识别器之间，常会对滑动方向或触摸位移阈值做出冲突判断。View 树的事件分发属于同进程内的同步裁决：父 View 在当前 `dispatchTouchEvent()` 中调用 `onInterceptTouchEvent()`，若中途决定接管手势，原子 View 目标就会收到 `ACTION_CANCEL`。

这类冲突常表现为手势起步位移被吞掉、父子控件反复争夺状态，或者子 View 收到 `CANCEL` 后仍继续绘制，给用户留下“慢半拍”的错觉。排查时应记录事件动作类型、触点 ID、拦截决策与 `CANCEL` 时序，以免把交互冲突混同为系统触摸延迟。对于 `RecyclerView` 与 `NestedScrolling` 体系，应优先遵循标准的嵌套滚动协议，减少重复的手势归属判断。

### 4. CPU 频率和调度问题

触摸事件到达时，如果设备 CPU 频率偏低或应用主线程被抢占调度出去，即使应用代码本身开销很小，输入处理的墙钟时间依然会拉长。

许多设备会实现 Input Boost、Touch Boost 或类似的输入提频策略，在输入到来后短时间内拉升 CPU/GPU 性能状态或调整 UI 线程的核群放置。但这些策略的名称、触发条件与持续时长属于 SoC 与厂商定制实现，并不属于 Android 17 系统框架的统一规范。

排查时应在同一设备上对照正常与异常样本，核实输入到来后是否触发了预期的频率或调度切换、主线程的 Runnable 等待是否变长，以及温控或省电策略是否正在限频。没有看到常规升频只是表象之一，部分设备也可能通过 uclamp 利用率下限、任务放置或其他调度手段实现相似的响应保障。

### 5. GPU 渲染瓶颈

如果输入处理与 View 树分发都很快，但渲染管线未能跟上——例如 `RenderThread` 回放 `DisplayList` 后提交的 GPU 任务过重、SurfaceFlinger 合成延迟或缓冲区轮转受阻——画面更新依然会滞后，使用户感到“手指动了但画面没跟上”。

这种情况在 Perfetto 中的典型表现：
- 应用 FrameTimeline 标记错过截止时间，但主线程的输入处理与遍历已经按时结束；
- `RenderThread` 的 `DrawFrame`、GPU 队列与完成时间，或栅栏等待延伸到截止时间之后；
- `dequeueBuffer` 长时间等待可用缓冲区；具体原因还要结合 BufferQueue 和消费方状态；
- SurfaceFlinger FrameTimeline 显示合成帧错过截止时间，或者目标图层的缓冲区没有赶上锁存。

需要注意，`GPU Completion` 并不等同于用户看到画面的时刻，显示端必须以呈现时间为准；计算“慢了几帧”也应按照当时实际的刷新周期换算，而不能一概套用 32 ms 的固定值。

### 6. 系统低内存

内存压力会通过多种途径间接放大输入与渲染延迟，例如触发 Java 垃圾回收（GC）停顿、引发重大缺页（major fault）、后台回收或压缩线程抢占 CPU，以及文件页淘汰后的重新读取。判断是否源自内存压力，必须以同一时间窗内的 GC、缺页、内存回收、I/O 与线程调度证据为准。

在 Perfetto 中通常表现为：
- 主线程或 `RenderThread` 的 Runnable 延迟增加；
- 垃圾回收停顿与输入处理或遍历重叠；
- `kswapd` 或内存回收活跃、重大缺页或 I/O 等待与异常帧重叠。

## 轨迹预测：面向笔迹与绘图的感知降延迟

轨迹预测（Motion Prediction）在工程上由四层相互独立的机制协同构成：

- **framework API**：`android.view.MotionPredictor`，API 34 加入。
- **AndroidX 库**：`androidx.input:input-motionprediction`，为不同系统版本提供封装。
- **低延迟输入**：`requestUnbufferedDispatch()` 让真实样本更早到达应用。
- **低延迟绘制**：前缓冲（front-buffer）等方案缩短笔迹从提交到显示的路径。

这四层机制可以按需组合，但各自解决不同环节的问题。轨迹预测只能弥补“已采集到的真实轨迹落后于物理笔尖”的视觉差距，既无法提前真实事件到达应用的时间，也解决不了主线程阻塞、掉帧或 SurfaceFlinger 合成延迟。

### Android 17 framework 实现边界

在 `android-17.0.0_r1` 中，`MotionPredictor` 是从 Java 层通往原生层的轻量封装。设备资源 `config_enableMotionPrediction` 控制 Java API 是否启用，AOSP 默认值为 `false`，需要厂商在确认模型与硬件匹配后覆盖开启；原生层同时还会检查可在运行时关闭该功能的系统属性 `enable_motion_prediction`。`isPredictionAvailable(deviceId, source)` 受上述开关共同约束，且当前原生实现仅支持手写笔来源。因此，即使运行在 Android 17 平台上，也不能默认所有设备都已开启轨迹预测。

原生 `TfLiteMotionPredictorModel` 会优先加载 `/vendor/etc/motion_predictor_model.tflite`，若不存在则回退至 `/system/etc/motion_predictor_model.tflite`，并从同目录的 XML 文件读取预测间隔、噪声下限与急转阈值等配置参数。

模型的输入张量包含相对轨迹的半径 `r`、角度 `phi`、压力、倾斜与方向，输出预测后的 `r`、`phi` 和压力值。平台内部还设有受功能开关控制的急转点裁剪逻辑；无论该开关是否开启，模型的噪声下限、输出序列长度限制或请求目标时间都可能导致 `predict()` 返回 `null`，或者使预测终点落在早于请求时间的位置。

此外，源码中并未为预测事件单独定义 `FLAG_PREDICTED`。应用需要自行分层维护真实笔迹与临时预测笔迹：每当下一批真实事件到来时，清除或修正此前尚未确认的预测线段，再绘制新的真实段与预测段。

### 调用与绘制约束

下面的 Java 代码骨架展示了系统框架 API 的最小调用流程。传入的目标时间必须采用系统运行时间（uptime）时基的纳秒值，且同一 `MotionPredictor` 实例在单次手势期间只能记录来自同一个设备的事件流：

```java
MotionPredictor predictor = new MotionPredictor(context);

void onStylusEvent(MotionEvent event, long targetTimeNanos) {
    if (!predictor.isPredictionAvailable(event.getDeviceId(), event.getSource())) {
        drawRealSamples(event);
        return;
    }

    predictor.record(event);
    drawRealSamples(event);

    MotionEvent predicted = predictor.predict(targetTimeNanos);
    if (predicted != null) {
        drawTemporaryPrediction(predicted); // 同时消费 predicted 的 historical samples
        predicted.recycle();
    }
}
```

实际工程中，还需要在 `ACTION_UP` 或 `ACTION_CANCEL` 到来时清理临时预测层，并妥善处理多触点、重采样点以及模型不可用时的回退逻辑。普通按钮点击不存在可供外推的连续轨迹；对于列表滑动场景，也应先消除调度、主线程与帧截止时间上的瓶颈，再评估是否需要引入轨迹预测。

## 前缓冲与低延迟图形

在传统多缓冲渲染路径中，帧必须经过应用绘制、缓冲区交换、SurfaceFlinger 合成与显示刷新才能呈现在屏幕上。整屏 UI 需要这条稳定的渲染链路；但对于手写输入中的局部增量笔迹，等待完整的多缓冲提交会让墨迹始终落后于笔尖。

为此，Jetpack 低延迟图形库允许将短生命周期的增量笔迹直接写入专用前缓冲图层（front-buffered layer），以可能出现短暂画面撕裂的风险换取更早的屏幕可见性：

- `GLFrontBufferedRenderer`：使用 OpenGL 管理笔迹增量层和持久多缓冲层；
- `CanvasFrontBufferedRenderer`：同时管理前缓冲图层与完整场景，调用 `commit()` 时重画并提交稳定内容；
- `LowLatencyCanvasView`：在 View 层级上方管理临时单缓冲覆盖层，提交后隐藏覆盖层，由普通 View 路径保留最终内容。

| 场景 | 前缓冲适用性 | 原因 |
|---|---|---|
| 签名、白板、手写笔迹 | 适合 | 增量区域小，预测段可在真实样本到达后修正 |
| 整屏列表滚动 | 不适合 | 更新范围大，容易出现撕裂和层次错位 |
| 普通按钮反馈 | 通常不适合 | 需要与 View 状态、无障碍和动画系统保持一致 |
| 画笔、游戏准星 | 取决于引擎 | 只有引擎能正确管理局部增量层才适用 |

典型手写场景的完整闭环如下：读取真实样本及历史点，按需通过无缓冲分发缩短等待时间；调用 `MotionPredictor` 仅生成短时间窗口内的临时预测点并绘制到前缓冲层；待真实样本到达后修正预测段；最后在抬笔或分段结束时调用 `commit()` 将笔迹固化到多缓冲层并清理临时内容。如果只引入预测而不做修正，轨迹急转时便会出现回弹；如果使用前缓冲却不约束重绘区域，屏幕撕裂往往比延迟本身更显眼。对于 `CanvasFrontBufferedRenderer`，收到 `ACTION_CANCEL` 时应当调用 `cancel()` 撤回临时绘制，不能把取消事件当作正常抬笔去 `commit()`，也不应让未确认的预测段成为永久笔迹（见 [API 约定](https://developer.android.com/reference/androidx/graphics/lowlatency/CanvasFrontBufferedRenderer#cancel())）。

<!-- gracker-diagram: ch03-02-prediction-frontbuffer-lifecycle -->
![真实点保留，预测点临时显示，结束时提交稳定内容](../../assets/diagrams/ch03/ch03-02-prediction-frontbuffer-lifecycle.png)

图：手写组件先消费真实点与历史点；可选无缓冲优化交付，预测只补短时临时轨迹，前缓冲承载局部增量。新真实点到来要撤换旧预测，正常结束可 commit 稳定多缓冲内容。ACTION_CANCEL 应取消临时绘制并回滚对应段，不能把尚未确认的预测永久提交。

## 厂商触控优化方案

不同厂商在触控硬件与系统调度层面的实现差异较大，实际排查时主要围绕以下四类可在系统行为中直接观测的共性机制展开。

### 高刷新率屏幕

更高的屏幕刷新率直接缩短了单帧刷新周期：60 Hz 约为 16.67 ms，120 Hz 约为 8.33 ms，144 Hz 约为 6.94 ms。只要应用与系统能够按期生成帧，更高刷新率就能缩短事件等待显示机会的时间。在支持 VRR（可变刷新率）的设备上，屏幕可能会根据画面内容、触摸状态、功耗与温控动态切换刷新率，因此分析时必须以系统跟踪中该时段真实的 FrameTimeline 为准，系统设置页或规格表上的最高刷新率仅作参考。

### 触控固件与控制器调校

量产设备通常会定制触控固件、滤波参数、采样率与上报节拍。硬件规格中常见的 240 Hz、480 Hz、720 Hz 乃至更高的触控采样率，代表的是触控控制器提供采样点的频次；这些高密度样本最终能否转化为更低的触摸到显示延迟，仍需结合驱动处理、`ViewRootImpl` 批处理策略、应用是否消费历史样本以及实际显示刷新周期综合评估。

### 调度与提频策略

厂商系统常在输入事件到达后短时拉升 CPU 或 GPU 频率，或提升 UI 相关线程的调度优先级，其底层原理与判读边界见上文“4. CPU 频率和调度问题”。这类策略在各平台上的名称、触发条件、持续时长以及是否将线程迁往高性能核心各不相同，需以目标设备的系统跟踪、内核与系统实现为准，排查时可直接核对 Perfetto 中的 CPU 频率、线程调度、SurfaceFlinger 与 `RenderThread` 行为。

### 交互提示与自适应刷新率（ARR）的边界

`InputDispatcher` 会将符合条件的按键、触摸动作及其他动作事件归类为用户活动，默认对同类型活动设置 100 ms 的最小通知间隔。PowerManager 产生的交互提频信号一方面送往 Power HAL，另一方面通知 SurfaceFlinger；Scheduler 随后把仍处于有效期内的触摸计时器转化为全局触摸信号。虽然部分内部方法名中带有 touch，但上游交互提频并非只由触摸事件触发。

需要注意的是，该信号只是 `RefreshRateSelector` 进行模式排序时的参考输入之一，图层的显式帧率投票、显示策略范围、候选模式集合、面板与 HAL 能力以及设备温控状态仍可能改变最终决策。应用可以通过 `Window.setFrameRateBoostOnTouchEnabled()` 声明是否允许触摸升频，也可以利用 View 或 Window 帧率 API 提交刷新率偏好，但这些设置均不保证当前帧必定运行在最高刷新率下。

验证此类行为时，应同步观察 Power `userActivity`、SurfaceFlinger `TouchState`、`Touch Boost`、`Touch Boost [late]`、图层投票、当前渲染帧率、实际刷新率与 FrameTimeline。自适应刷新率（ARR）的完整选择逻辑与显示时序详见 2.2，本节聚焦其与输入延迟相关的交互触发边界。

## 与其他章节的关系

触摸响应与输入分发、帧调度和渲染链路交叉关联：

- **3.1 Input 事件分发：队列、反压与丢弃**：输入事件从硬件到应用的完整分发机制；
- **2.3 VSYNC 机制**：缓冲的 `MOVE` 会接近 `Choreographer` 输入回调时消费，目标帧也由 VSYNC 驱动；无缓冲路径则不等待这一回调。理解 VSYNC 周期、截止时间和实际刷新率，才能解释事件赶上了当前帧还是顺延到下一帧；
- **2.3 Choreographer 与渲染流水线**：说明 `CALLBACK_INPUT` 优先级、`doFrame()` 执行顺序与批处理实现；
- **2.4 MainThread 与 RenderThread 协作**：View 输入分发和遍历位于主线程，部分硬件加速渲染工作交给 `RenderThread` 与 GPU；
- **8.1 响应速度原理**：输入延迟 → 处理延迟 → 输出延迟的通用模型与量化方法。

## 常见问题与误区

### 误区：触摸采样率越高越好

更高的采样率确实能提供更密集、时间戳更接近当前时刻的真实坐标，但屏幕最终能呈现多少帧依然受限于显示刷新率与渲染吞吐。在普通滚动场景下，多出的 `MOVE` 样本往往会被合并进同一个 `MotionEvent`，若应用只读取当前坐标，视觉上的提升会比较有限；手写笔、轨迹拟合、轨迹预测以及高刷新率、高帧率场景才更能充分发挥历史样本的价值。

### 误区：触摸卡顿一定是应用的问题

触摸事件可能在触控固件、内核驱动、InputFlinger、应用进程、GPU、SurfaceFlinger 或显示扫描输出中的任一环节发生滞留。只有当轨迹明确显示事件进入应用后的处理或 View 树遍历阶段显著超时，才能将问题范围收窄到应用侧；若观察到 CPU 频率偏低或未出现预期提频信号，也需结合线程调度、温控限制与正常对照样本一并分析。

### 误区：输入 ANR 等于应用卡死

连接型输入 ANR 检查的是等待队列中条目的 `timeoutTime`。在 Android 17 中，默认分发超时尚未乘系数时的基值为 5000 ms，运行时还会乘以 `HwTimeoutMultiplier()`，且窗口或应用均可覆盖该阈值。触发超时只表明系统未能在规定时间内收回 `FINISHED` 完成确认，其背后原因可能是主线程长耗时任务、Runnable 调度饥饿、锁等待、同步 Binder 或 I/O、异步 `InputStage` 挂起或进程异常。此外，完成确认本身也不代表画面已经呈现，ANR 监控与跟手性延迟度量各自覆盖不同维度，需分开统计。

## 参考资料

- AOSP `android-17.0.0_r1`：
  - `frameworks/native/services/inputflinger/reader/EventHub.cpp`
  - `frameworks/native/services/inputflinger/reader/InputReader.cpp`
  - `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp`
  - `frameworks/native/services/inputflinger/dispatcher/LatencyTracker.cpp`
  - `frameworks/native/services/inputflinger/trace/InputTracingPerfettoBackend.cpp`
  - `frameworks/native/libs/input/InputConsumer.cpp`
  - `frameworks/native/libs/input/InputConsumerNoResampling.cpp`
  - `frameworks/native/libs/input/Resampler.cpp`
  - `frameworks/native/libs/input/MotionPredictor.cpp`
  - `frameworks/native/libs/input/TfLiteMotionPredictor.cpp`
  - `frameworks/base/core/jni/android_view_InputEventReceiver.cpp`
  - `frameworks/base/core/jni/android_view_MotionPredictor.cpp`
  - `frameworks/base/core/java/android/view/ViewRootImpl.java`
  - `frameworks/base/core/java/android/view/View.java`
  - `frameworks/base/core/java/android/view/Choreographer.java`
  - `frameworks/base/core/java/android/view/InputEventAssigner.java`
  - `frameworks/base/core/java/android/view/MotionEvent.java`
  - `frameworks/base/core/java/android/view/MotionPredictor.java`
  - `external/perfetto/protos/perfetto/config/android/android_input_event_config.proto`
  - `external/perfetto/src/trace_processor/perfetto_sql/stdlib/android/input.sql`（`_input_read_time` 与 `android_input_events` 的测量起点和关联规则）
- Android 官方文档：[Input 系统概述](https://source.android.com/docs/core/interaction/input)、[通过 adb 抓取 Input Trace](https://source.android.com/docs/core/graphics/winscope/capture/adb)、[MotionEvent](https://developer.android.com/reference/android/view/MotionEvent)、[MotionPredictor](https://developer.android.com/reference/android/view/MotionPredictor)、[Advanced Stylus](https://developer.android.com/develop/ui/views/touch-and-input/stylus-input/advanced-stylus-features)、[AndroidX Input](https://developer.android.com/jetpack/androidx/releases/input)
- AndroidX 低延迟图形：[`CanvasFrontBufferedRenderer`](https://developer.android.com/reference/androidx/graphics/lowlatency/CanvasFrontBufferedRenderer)、[`LowLatencyCanvasView`](https://developer.android.com/reference/androidx/graphics/lowlatency/LowLatencyCanvasView)
- Perfetto：[`android.input` 标准库](https://perfetto.dev/docs/analysis/stdlib-docs#android-input)、[FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline)
- HCI 原始研究：[Ng 等，UIST 2012](https://dl.acm.org/doi/10.1145/2380116.2380124)、[Jota 等，CHI 2013](https://www.tactuallabs.com/papers/howFastIsFastEnoughCHI13.pdf)、[Henze 等，MobileHCI 2016](https://nhenze.net/uploads/Software-Reduced-Touchscreen-Latency.pdf)
- [高爷 - Systrace 基础知识：Input 解读](https://www.androidperformance.com/2019/10/27/Android-Systrace-Input/)
- [高爷 - Systrace 响应速度实战 1](https://www.androidperformance.com/2022/03/20/android-systrace-Responsiveness-in-action-1/)

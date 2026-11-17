---
title: 低内存对系统性能的影响
chapter: '10.2'
section: '10.2'
status: finalized
applicable_versions: Android 10 (API 29) - Android 17 (API 37)
last_verified: '2026-10-24'
last_verified_against: AOSP android-17.0.0_r1; Android common kernel android17-6.18-2026-06_r6
confidence: high
sources:
- type: blog
  path: Cubox/kswapd介绍-2022-04-08.md
- type: blog
  path: Cubox/Linux内存变低会发生什么问题-2024-09-09.md
- type: blog
  path: Cubox/Android帝国之进程杀手--lmkd-2024-09-07.md
- type: research
  path: intake/research-feeds/2026-04-02-11-ch04-zram-multialgo-mglru-2025.md
- type: aosp
  path: platform/system/memory/lmkd/lmkd.cpp@android-17.0.0_r1
- type: aosp
  path: platform/system/memory/libmeminfo/libmemevents@android-17.0.0_r1
- type: aosp
  path: platform/frameworks/base/services/core/java/com/android/server/am/LowMemDetector.java@android-17.0.0_r1
- type: aosp
  path: platform/frameworks/base/services/core/java/com/android/server/am/CachedAppOptimizer.java@android-17.0.0_r1
- type: aosp
  path: platform/frameworks/base/services/core/java/com/android/server/am/MemoryLimiter.java@android-17.0.0_r1
- type: kernel
  path: kernel/common/mm/page_alloc.c@android17-6.18-2026-06_r6
- type: kernel
  path: kernel/common/mm/vmscan.c@android17-6.18-2026-06_r6
- type: kernel
  path: kernel/common/include/trace/events/vmscan.h@android17-6.18-2026-06_r6
- type: official
  path: https://source.android.com/docs/core/perf/lmkd
- type: official
  path: https://docs.kernel.org/accounting/psi.html
- type: official
  path: https://perfetto.dev/docs/data-sources/memory-counters
tags:
  - low-memory
  - kswapd
  - direct-reclaim
  - lmkd
  - gc
  - memory-pressure
  - psi
  - zram
related_chapters:
- '4.1'
- '4.3'
- '4.4'
- '4.6'
- '10.1'
- '10.3'
---

# 低内存对系统性能的影响

低内存引发的性能退化并不遵循单一的固定顺序。系统可能直接丢弃未修改的文件页（clean file page）、把匿名页换入内存压缩交换设备（ZRAM）、迫使分配线程同步进入直接回收（direct reclaim），也可能终止缓存进程（cached process）；在 Android 17 上，Memory Limiter 还会对内存异常的进程施加约束。这些路径各自消耗 CPU、I/O、内存带宽或冷启动时间。排查低内存问题时，我们需要在同一段 Trace 中核对事件的先后与因果关系，确认究竟是哪几条路径在当前现场起作用。

> 源码基线：AOSP `android-17.0.0_r1`，适用 Android 10（API 29）至 Android 17（API 37）；回收、水位线、PSI、ZRAM 与页规整的内核源码按 `android17-6.18-2026-06_r6` 核对。


## 1. 从分配失败到回收

### 1.1 Zone 水位线与 kswapd

内存回收的起点在分配侧。Linux 将物理内存划分为多个区域（zone），每个 zone 各自维护 `min`、`low`、`high` 等水位阈值（watermark）。当分配路径发现水位或内存碎片条件不满足，且允许 `__GFP_KSWAPD_RECLAIM` 等条件成立时，就会尝试唤醒对应 NUMA 节点（memory node）的后台回收线程 `kswapd`；`mm/vmscan.c` 中的 `balance_pgdat()` 负责扫描和回收页面，完成后再尝试休眠。需要留意，水位线同时参与分配快速路径、保留页与高阶分配的判断，系统空闲页有多少只是其中的一项条件。

这条唤醒规则受多个条件影响：

- 分配请求的 order（连续页块阶数）、GFP flags（内核分配约束）、允许使用的 zone 与保留页各不相同。
- per-CPU page list（每 CPU 页缓存）、watermark boost（水位临时增量）、碎片和 compaction（内存规整）会改变分配慢路径。
- `kswapd0` 短暂运行属于正常回收；持续扫描、扫描收益低或频繁 wake/sleep 才值得追查。

对应的 6.18 内核源码位置：

- `mm/page_alloc.c`：watermark 检查、分配慢路径与 `wakeup_kswapd()`。
- `mm/vmscan.c`：`balance_pgdat()`、`shrink_node()` 与 direct reclaim。
- `include/trace/events/vmscan.h`：kswapd、direct reclaim 和 LRU 扫描 tracepoint。

### 1.2 Direct reclaim

当分配请求在快速路径上失败，且 GFP 标志允许 `__GFP_DIRECT_RECLAIM` 时，发起分配的线程就可能同步进入直接回收（direct reclaim）。空闲页低于 `min` 水位并不会无条件触发这条路径，分配阶数（order）、zone、保留页（reserve）、内存控制组（memcg）以及 GFP 语义都会左右最终的判断。

Direct reclaim 消耗的是当前分配线程自己的执行时间。线程既可能在 CPU 上扫描页面，也可能因限速（throttle）、swap 或 I/O 等待进入不可中断睡眠（D 状态）。因此，在 trace 里看到主线程处于 `D` 状态时，不要急着归因到内存回收，应先结合 `sched_switch`、阻塞原因（blocked reason）或内核调用栈确认它到底在等待什么，再下结论。

### 1.3 回收成本来自哪里

不同页面的代价不同：

| 被处理的内存 | 回收动作 | 后续成本 |
| --- | --- | --- |
| clean file page | 丢弃页 | 再访问时可能 refault（页面被回收后很快再次访问）并读取文件 |
| dirty file page（已修改的文件页） | 需要完成回写才可丢弃；本轮也可能跳过或等待 | 写回、等待与存储竞争 |
| anonymous page（匿名页） | 换出到 ZRAM 或其他 swap | 压缩 CPU、swap-in（换入）解压与延迟 |
| slab / 内核缓存 | shrinker（内核缓存回收器）回收 | 由具体子系统决定 |
| 高阶物理页需求 | compaction / retry（规整后重试） | 页迁移、扫描与分配延迟 |


高阶分配还可能先尝试内存规整（compaction），再进入 direct reclaim；若依然失败，后续是重试、继续规整、触发 OOM 还是直接返回失败，取决于具体的 GFP 与 order 条件——内核中并不存在一条所有分配都会依次经历的固定流水线。

<!-- gracker-diagram: ed10-02-allocation-and-reclaim-conditions -->
![按分配请求分别判断后台回收、同步回收与物理页规整](../../assets/diagrams/ch10/ed10-02-allocation-and-reclaim-conditions.png)

图：固定6.18内核的条件/线程关系示意，不是完整page_alloc控制流。先按node/zone、order、GFP、reserve与碎片核对请求，各zone min/low/high参与不同判断，不构成全机free三级流水线。后台回收需允许等条件才可唤醒对应node的kswapd；快速尝试失败且GFP/上下文允许后，当前分配线程才可能同步direct reclaim。高阶需求还要连续块，基础页足够仍可受碎片限制，部分路径先compaction，后续reclaim/retry/失败不能固定排序。三机制可以交叠，用同TID事件、sched与调用栈追当前关键路径；kswapd Running与main D共现仅是线索，D也可能来自Binder/文件系统/fence等等待，回收不保证产生磁盘I/O。

Direct reclaim 是否产生存储 I/O，取决于被处理页面的类型：clean file page 可以直接丢弃；匿名页在常见 Android 配置中会换入 ZRAM，只有当设备启用了 ZRAM 回写（writeback）时，部分数据才可能进一步写入后备存储设备（backing device）。因此，分析时需要将 vmscan、block I/O、ZRAM、refault 和线程状态放在一起联合观察。

## 2. PSI 怎样描述系统停顿

Pressure Stall Information（PSI，资源压力停顿信息）统计的是任务因 CPU、内存或 I/O 资源不足而陷入停顿的时间。查看 memory PSI 时，主要关注以下四个字段：

- `some`：时间窗内至少有一个非 idle（非空闲）任务因内存压力停顿。
- `full`：时间窗内所有非 idle 任务同时因内存压力停顿。
- `avg10`、`avg60`、`avg300`：以 10、60、300 秒为尺度的指数移动平均百分比，不同于对应窗口的精确算术平均。
- `total`：累计停顿时间，单位为微秒。

即使 `full` 为零，也并不说明系统没有内存压力：只要此时仍有其他任务能够继续运行，压力往往只反映在 `some` 上。此外，PSI 指不出具体是哪一页、哪个进程或哪条分配路径造成了停顿，这部分归因必须结合回收事件与进程数据来分析。

下面几条命令分别用于读取当前的 PSI、vmstat、ZRAM 与进程退出记录：

```bash
adb shell cat /proc/pressure/memory
adb shell cat /proc/vmstat
adb shell cat /proc/swaps
adb shell dumpsys activity exit-info com.example.app
```

`/proc/pressure/memory` 提供的是系统级累计停顿与平均信息，`vmstat` 则需要抓取两个时间点做差分。另外，当前 PSI 读数只反映此刻的状态，要确认或回溯某次进程退出的原因，仍须查看退出记录。

<!-- gracker-diagram: ed10-02-psi-task-sets-and-time-views -->
![PSI some / full 是不同任务集合，avg 与 total 也用不同时间口径](../../assets/diagrams/ch10/ed10-02-psi-task-sets-and-time-views.png)

图：轨道只作教学：同一memory资源/统计范围仅A/B两项任务且全段non-idle，没有测量值或真实时长比例。some是至少一项任务因内存压力停顿的时间并集，full是全部非idle任务同时停顿的交集；full为零仍可有some或严重局部延迟。avg10/60/300为10/60/300秒尺度指数移动平均，不是精确滑窗算术平均；total以微秒累计，在同一计数范围且无重置时用两次读数差分，并保留实际t1/t2。系统级和cgroup范围不混算；PSI不提供具体页/进程/分配根因，当前读数不能反推过去某次退出，需同窗回收、线程和进程证据。

## 3. Android 17 的两个 PSI 消费者

### 3.1 lmkd

低内存终止守护进程（lmkd）初始化 PSI 监听器（monitor）时默认采用新策略，`use_new_strategy` 属性以及 low-RAM、`use_minfree_levels` 的配置组合仍会影响最终选择（旧策略仅支持 v1 memcg）。按新策略的分级方式：LOW 档关闭，MEDIUM 映射到可配置的部分任务停顿（partial stall），CRITICAL 映射到可配置的全部非空闲任务停顿（complete stall）。收到 PSI 事件后，lmkd 还会综合读取 zone 水位、swap 状态、工作集频繁换入引起的抖动（working-set refault / thrashing）、进程保护级别（`oom_score_adj`）与内存占用（footprint），再决定是否挑选进程终止。

需要注意的是，`use_minfree_levels` 在 Android 17 中影响的是查杀策略（kill strategy）。早年“用 `ro.lmk.use_psi=false` 关闭 PSI”的旧用法在 Android 17 源码中已经移除，不能继续沿用。

排查 lmkd 选择目标时，应以事件证据为准：

- 被杀 PID、UID 与进程名。
- 目标 `oom_score_adj` 与本轮 `min_oom_score`（本轮允许选择的最低 OOM 分值）。
- kill reason（终止原因）、thrashing 数据。
- RSS、anon RSS、swap、DMA-BUF PSS/RSS。

至于杀进程的 adj 界限，并没有全设备通用的定值：进程当前状态、设备属性、OEM 策略以及当时的系统压力都会改变候选范围。

Android 17 在 `reaper.kill()` 返回成功后会调用 `ATRACE_INSTANT_FOR_TRACK()`，描述格式为 `lmk,pid,reason,oomadj,min_oom_score,max_thrashing`，正常压力选择路径还会写入 `lowmemorykiller` 日志与统计。需要留意，这个 instant 事件标记的是提交终止请求的时刻，进程何时真正退出、物理页是否回收完，还需另找证据核对。在现代设备上排查时，应优先读取这个用户空间瞬时事件、logcat/statsd 与 `ApplicationExitInfo`；旧版（legacy）的 `lowmemorykiller/lowmemory_kill` 内核事件在很多设备上可能已经不存在，不宜当作依赖。

### 3.2 system_server 的 LowMemDetector

`LowMemDetector` 是 `system_server` 内部的另一条 PSI 路径。Android 17 的 Native 实现注册了三个 monitor：

| 内部等级 | PSI 类型 | AOSP Android 17 窗口与 stall |
| --- | --- | --- |
| LOW | `PSI_SOME` | 1 s 窗口内 15 ms |
| MEDIUM | `PSI_FULL` | 1 s 窗口内 30 ms |
| HIGH | `PSI_FULL` | 1 s 窗口内 50 ms |

表中的窗口与停顿阈值属于 `android-17.0.0_r1` 的 Framework 常量，在 OEM 分支上仅作参考，各厂商可能配置自己的性能阈值。Java 层的 `LowMemThread` 经由 JNI 通过 epoll 等待事件，在同批到达的事件中取最高等级。当系统已存在压力时，线程以 1 秒超时继续等待，若无新事件则返回 NORMAL；无压力时则会无限等待。Trace 中的 `criticalLowMemory` 时间片标记的是这套检测器处于 CRITICAL 状态的区间，与原始的 PSI full 停顿时长应当分开看。ActivityManager 读取该状态后，还可能结合覆盖配置和进程数量等门限，再更新 memory factor 与进程统计。

`LowMemDetector` 与 `lmkd` 监听的是同一个 PSI 子系统，只是两者的触发配置与动作不同：前者服务于 `system_server` 内部状态管理，后者负责在内存压力下筛选并终止进程。因此，看到两个监听文件描述符（fd），并不代表 PSI 停顿被重复计算。

<!-- gracker-diagram: ed10-02-psi-consumers-and-detector-state -->
![同一个 PSI 子系统供两个消费者各自注册触发器](../../assets/diagrams/ch10/ed10-02-psi-consumers-and-detector-state.png)

图：两个消费者各自注册trigger，监听数不意味着PSI停顿重复记账。固定r1 lmkd按use_new_strategy和low-RAM/minfree等产品组合选策略：新策略LOW关闭、MEDIUM partial stall/CRITICAL complete stall，旧策略仍用PSI且仅支持v1memcg；minfree不是已不存在的旧use_psi开关。收到事件还需watermark/swap/refault/thrashing/adj/footprint等上下文才决定是否选进程。LowMemDetector则用三个1s固定framework窗口：some15ms、full30ms、full50ms；同批取最高，无压力无限等待，已有压力至多等1s，无新事件回NORMAL。Java状态和criticalLowMemory区间还经AppProfiler覆盖值/进程数门限更新memory factor；critical slice不是raw full停顿时长，这些阈值也不是全部OEM性能阈值。

## 4. lmkd kill 怎样转化为用户性能损失

缓存进程退出后会释放它的地址空间与资源引用，但实际能收回多少物理内存，仍取决于共享页、其他资源持有者以及内核回收时机，并不能直接等同于被杀前的 RSS。当用户再次切回该应用而对应进程已不在时，系统需要重新创建进程、加载代码与资源、初始化 Application 与 ContentProvider，并按入口恢复 Activity 和业务状态。这笔恢复代价随包体、I/O、初始化工作、编译状态和系统当前压力浮动，无法用单一的固定毫秒数来概括。

评估低内存造成的产品影响时，至少需要关联以下五项指标：

<!-- gracker-diagram: ed10-02-kill-submission-to-return-evidence -->
![从终止请求标记到实际退出、用户返回与冷启动分别取证](../../assets/diagrams/ch10/ed10-02-kill-submission-to-return-evidence.png)

图：仅正常压力选择且reaper.kill返回成功的r1路径写lmk instant及相应日志统计，失败或hook已处理有别的分支。instant记录pid/reason/oomadj/min_oom_score/max_thrashing，是提交请求标记，不能当实际死亡或全部物理页回收完成点。图中箭头表示证据关联，不规定实际死亡一定晚于instant；按PID/进程代次另对死亡通知和资源持有者状态，共享页与同包其他进程另看，回收量不直接等于kill前RSS。只有实际用户返回同一入口且目标进程此时不存在，才关联重建进程、代码/资源、Application/Provider、首帧及状态恢复CPU/I/O，并同设备同入口比较返回间隔/冷热转换比例/完成时间，无通用毫秒数。lmkd REASON_LOW_MEMORY与Limiter REASON_OTHER/MemoryLimiter:AnonSwap分开统计。

1. lmkd kill 时间与原因。
2. 用户返回该 App 的时间间隔。
3. warm/hot resume（温启动或热恢复）变成 cold start（冷启动）的比例。
4. 冷启动 CPU、I/O、首帧与状态恢复。
5. 同一进程是否在短时间内反复启动和退出。

`ApplicationExitInfo.REASON_LOW_MEMORY` 可以用来识别低内存退出。需要注意的是，Android 17 Memory Limiter 引发的进程退出使用的是 `REASON_OTHER`，且 description 中包含 `MemoryLimiter:AnonSwap`，统计时应将其与普通 `lmkd` kill 分开。

## 5. 全局低内存与 ART GC

ART GC 的触发频率主要由应用的分配速率（allocation rate）、存活对象集合（live set）、堆目标大小（heap target）、收集器类型（collector）与进程状态决定。全局 PSI 升高，本身并不足以说明前台应用已经切换到某种更重的 GC；要得出这一结论，仍须分别核对 GC 原因、收集器与执行片段。实际排查中，以下现象可能同时发生，需要逐一验证：

- 应用自身分配率高、live heap 接近目标上限，导致 GC 时间片（slice）变密。
- `kswapd`、ZRAM 或内存规整消耗大量 CPU，导致并发 GC 线程分到的 CPU 时间减少。
- 分配线程进入 direct reclaim，使分配停顿（allocation stall）与 GC pause 出现在相邻时间窗内。
- 缓存进程被 Framework 压减驻留内存（compact）或冻结调度（freeze），这属于进程驻留优化，与 ART 的 Java 堆 GC 分属两套独立机制。

从帧预算上看，60 Hz 屏幕的一帧约 16.67 ms，120 Hz 则压缩到约 8.33 ms；刷新率越高，留给 GC pause、调度延迟与系统回收干扰的余量就越小。不过具体会不会掉帧，仍要依据实际的 FrameTimeline（帧时间线）、GC slice 与调度耗时来判定，通用的“GC 毫秒阈值”在这里并不适用。

借助信号之间的交叉对比可以快速定界：如果 GC 密度上升而 PSI、vmscan 和 `kswapd` 保持平稳，问题多半出自应用自身的 allocation churn；若 PSI 和 direct reclaim 上升而 GC 频率不变，瓶颈则更可能在系统回收或 I/O；当两组信号同时走高时，再进一步检查 CPU 竞争与分配线程的调用栈。

## 6. Android 17 中 `memevents` 与旧 `mm_events`

这两个名字十分相近，但指向的是两套不同的机制：

- `libmemevents`：Android 17 引入的基于 BPF 的内存事件库。`lmkd` 的 `MemEventListener` 要求 direct reclaim begin/end 与 `kswapd` wake/sleep 四个事件注册成功，而 vendor kill 与 zone info 更新属于可选事件。当 listener 不可用、必需事件或 epoll 注册失败时，会回退到 `vmstat`（内核虚拟内存统计）；仅有可选事件缺失时，整个 listener 仍可继续工作。
- Perfetto `mm_events` service：旧版本中用于常驻启用 `kmem_activity` trigger 的脚本与探针（probe）。

<!-- gracker-diagram: ch10-02-14-memevents-gates -->
![memevents 必需事件与可选事件分开](../../assets/diagrams/ch10/ch10-02-14-memevents-gates.png)

图：固定 r1 要求四个回收事件及 ring buffer/epoll 可用；vendor kill 与 zone info 事件缺失不会单独迫使 listener 整体回退。

在 `android-17.0.0_r1` 的 Perfetto `tools/`、`src/traced/probes/` 与 `test/configs/` 目录中，已经找不到旧的 `mm_events` 工具、`kmem_activity_trigger` probe 及相关配置入口。因此在 Android 17 上排查时，不要默认 `persist.mm_events.enabled`、`/vendor/etc/mm_events.cfg` 或 `mem.mm_events` SQL 视图必然存在，使用前务必先核验。OEM 或旧系统上即便保留了自己的版本，同样应从设备镜像和 trace schema 中确认。

在 Android 17 上排查低内存时，通用的核心证据来源仍然是 vmscan / compaction 的 ftrace 事件、PSI、vmstat、`lmkd` 用户空间事件、进程统计以及应用 trace。


## 7. 用 Perfetto 还原压力时间窗

### 7.1 需要观察的事件

| 信号 | 能回答的问题 |
| --- | --- |
| `mm_vmscan_kswapd_wake/sleep` | 后台回收何时开始和结束 |
| `mm_vmscan_direct_reclaim_begin/end` | 哪个线程同步回收、持续多久 |
| `mm_vmscan_lru_shrink_inactive` | 扫描与回收的规模 |
| `mm_compaction_begin/end` | 页规整窗口与连续页块 order |
| PSI some/full | 系统停顿程度 |
| sched state / blocked reason | 目标线程正在运行、等待 CPU 或处于 D 状态 |
| ART GC slice | App GC 类型与时序 |
| lmkd instant / log | 谁被 kill、原因和候选边界 |
| process stats | 进程创建、退出与 RSS 变化 |

复现低内存问题时，可以从下面这份配置起步；轨迹缓冲区（buffer）大小和采样时长属于采集参数，可按实际复现窗口调整。

```protobuf
buffers {
  size_kb: 65536
  fill_policy: RING_BUFFER
}
duration_ms: 30000

data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_wakeup"
      ftrace_events: "vmscan/mm_vmscan_kswapd_wake"
      ftrace_events: "vmscan/mm_vmscan_kswapd_sleep"
      ftrace_events: "vmscan/mm_vmscan_direct_reclaim_begin"
      ftrace_events: "vmscan/mm_vmscan_direct_reclaim_end"
      ftrace_events: "vmscan/mm_vmscan_lru_shrink_inactive"
      ftrace_events: "compaction/mm_compaction_begin"
      ftrace_events: "compaction/mm_compaction_end"
      atrace_categories: "am"
      atrace_categories: "dalvik"
      atrace_categories: "memreclaim"
    }
  }
}

data_sources {
  config {
    name: "linux.process_stats"
    process_stats_config {
      scan_all_processes_on_start: true
      proc_stats_poll_ms: 1000
    }
  }
}

data_sources {
  config {
    name: "linux.sys_stats"
    sys_stats_config {
      meminfo_period_ms: 1000
      vmstat_period_ms: 1000
      stat_period_ms: 1000
      psi_period_ms: 1000
    }
  }
}

data_sources {
  config {
    name: "android.surfaceflinger.frametimeline"
  }
}
```

Android 17 的 `atrace.cpp` 明确定义了 `memreclaim` 类别（category），它会开启 direct reclaim、kswapd 以及可选的 lowmemorykiller 事件组；上面的配置同时显式列出了 vmscan 事件，方便在设备裁剪了类别时直接核对。需要注意，`linux.process_stats` 按 1 秒轮询进程计数，可能会漏掉短时峰值；FrameTimeline 数据源也需要设备端支持。同时，这份起始配置并没有覆盖全部低内存信号：如果要排查块 I/O、ZRAM 内部工作或内核阻塞栈，还需按目标设备补加相应的事件与计数器。录制前应先确认 tracefs（内核跟踪文件系统）中实际存在这些事件，缺少可选事件时按设备能力删减。

### 7.2 阅读顺序

1. 在卡顿、启动或 kill 附近划定时间窗。
2. 看 PSI some/full 与 vmstat 差分，确认是否有系统级停顿。
3. 看 kswapd 与 direct reclaim，区分后台回收和分配线程同步回收。
4. 看 sched state、block I/O（块设备 I/O）与 ZRAM，识别 CPU 扫描、压缩、swap 或存储等待。
5. 看 GC slice 与 FrameTimeline，确认 App 自身分配是否叠加影响。
6. 看 lmkd instant、日志和进程生命周期，确认回收后的启动代价。

最后需要注意，“`kswapd` Running 与主线程处于 D 状态同时出现”，本身不足以证明主线程因内存回收而阻塞。要把主线程的卡顿与内存回收关联起来，必须依赖 direct reclaim 事件或内核调用栈证据，并排除 Binder 通信、文件系统锁、GPU 同步栅栏（fence）以及其他不可中断等待的干扰。

## 8. 系统侧调优的手段与评估

### 8.1 ZRAM

ZRAM 利用 RAM 存放压缩后的交换页（swap page），从而提高匿名页的存储密度，同时消耗物理内存和压缩/解压所需的 CPU 算力；部分设备还会启用回写（writeback）或重压缩（recompression）。由于设备配置和业务负载差异较大，ZRAM 的大小、压缩比、算法选择与交换倾向参数（swappiness）都不存在跨设备通用的取值。

下列节点保存了交换与 ZRAM 的配置及运行统计：

```bash
adb shell cat /proc/swaps
adb shell cat /sys/block/zram0/mm_stat
adb shell cat /sys/block/zram0/comp_algorithm
adb shell cat /sys/block/zram0/recomp_algorithm
adb shell cat /proc/sys/vm/swappiness
adb shell cat /proc/sys/vm/page-cluster
```

这些节点是否存在取决于具体的内核配置。`mm_stat` 记录了原始数据量、压缩后数据量、内存总量以及页面状态；算法列表则用方括号标出了当前生效的算法。`page-cluster = n` 给出了一次 swap 预读的页数上限尺度 `2^n`，设为 `0` 则关闭额外预读；这里所说的“相邻”指的是 swap 空间上的连续，与虚拟或物理地址是否相邻无关。需要注意，同样的 `n` 值在 16 KiB 设备上对应的字节上限是 4 KiB 设备的四倍，而每次实际读取多少页，仍取决于访问模式与可用页等条件。是否需要调整，还应结合 swap-in 命中率、解压 CPU 开销、PSI 与应用切换时延综合判断。

<!-- gracker-diagram: ch10-02-19-swap-readahead-scale -->
![page-cluster 是页数上限的对数尺度](../../assets/diagrams/ch10/ch10-02-19-swap-readahead-scale.png)

图：教学算例：n=3 对应至多 8 页的尺度，4 KiB 与 16 KiB 基础页分别是 32 KiB 和 128 KiB。实际预读量可能更少。

评估 ZRAM 改动要同时比较：


- `pswpin` / `pswpout`（累计换入/换出页数）、ZRAM 占用和压缩效率。
- memory PSI、direct reclaim 和 kswapd 时间。
- swap-in 后的启动、页面恢复和交互延迟。
- 压缩线程 CPU 与功耗。
- lmkd kill、refault 和 cached App 存活。

片面追求高压缩比可能会明显推高 CPU 开销；另外，`disksize` 代表的是逻辑设备容量，将它设大并不会立即预分配等量 RAM，只有当真实数据不断写入时，压缩池、不可压缩页以及元数据才会逐步占用物理内存。因此，ZRAM 参数应按目标 SoC、RAM 档位与实际负载做测试调优。

### 8.2 MGLRU

Multi-Gen LRU（MGLRU，多代最近最少使用算法）用“代（generation）”来追踪页面访问热度，并在回收时优先淘汰较老的一代。Android 17 的 6.18 内核已包含该路径，但具体设备是否启用，仍须读取 `/sys/kernel/mm/lru_gen/enabled` 并核对配置。

评估 MGLRU 的效果不能只看开关是否开启，还要对比调优前后的 refault、扫描与成功回收页数（scan/steal）、direct reclaim、PSI、swap 行为与冷启动回访表现。读取 `enabled` 时注意，这个位掩码（bitmask）控制的是 MGLRU 主开关、叶/非叶页表访问位批量清理等子组件，不要误读为 generation 编号；由于可用组件受制于内核配置与硬件能力，同一个十六进制值换到另一台设备上含义就可能不同。

### 8.3 Cached App Optimizer

Android 17 的 `CachedAppOptimizer` 同时管理着缓存进程内存压减（cached app compaction）与进程冻结（freezer）两条逻辑。其中 compaction profile 包括 `SOME`（file）、`ANON` 和 `FULL`（file + anon），系统会根据 RSS、时间间隔、swap 余量与配置决定是否执行或降级该次操作。

<!-- gracker-diagram: ch10-02-22-cached-compaction-resolution -->
![Cached App profile 还要经过降级和能力检查](../../assets/diagrams/ch10/ch10-02-22-cached-compaction-resolution.png)

图：固定 r1 的请求 profile 不保证原样执行。策略筛选、降级、能力与页面状态都要核对，再比较实际 RSS 和回访成本。

Cached app compaction 通过 `process_madvise` 或受支持的 memcg/task profile 来请求压减驻留内存。其中 `MADV_COLD` 主要用于给页面降温，并不保证立刻降低 RSS；`MADV_PAGEOUT` 则尝试主动回收或换出页面，实际效果仍受页面状态和权限条件限制。需要注意，这些机制完整保留了业务对象的语义，对仍被强引用持有的对象泄漏无能为力。至于 Freezer，它负责暂停缓存进程的调度，解冻时则必须处理积压的 Binder 事务、文件锁与调度任务，它和物理页规整、ART GC 属于完全不同的机制。

### 8.4 cgroup、Task Profiles 与 Android 17 Memory Limiter

Android 的控制组（cgroup）抽象与任务资源配置（Task Profiles）负责进程分组和资源策略，PSI 负责度量任务停顿，而 `lmkd` 负责在内存压力下筛选并终止进程。这三项职责彼此独立，排查时应分别核对。

Android 17 还在部分设备上启用了 App Memory Limiter。Framework 按进程状态选择配置，JNI 实际写入的是 cgroup 节点 `memory.high` 与 `memory.swap.max`，其中 Swap 项还受开关控制。需要注意，Java 侧 `swapHigh` 的命名和部分 `memory.swap.high` 注释，都与 JNI 实际写入的节点对不上。

在 `android-17.0.0_r1` 中，这套机制监控的组合指标是 `memory.stat` 中的 anon + shmem 再加上 `memory.swap.current`，与 PSS、RSS 或 Java heap 的统计范围各不相同。当组合指标超过配置阈值后，系统会先撤销该进程的限制，并在 feature flag、包名和系统策略允许时请求 anomaly profiling，随后排队等待 30 秒再请求终止进程（实际执行还受禁杀配置、AMS 状态与消息调度影响）。另外，这条 Injector 路径只把 PID 传给了 `killPids()`，并未用入参 UID 再核对一遍进程身份。由它触发的进程退出在退出记录中使用 `REASON_OTHER`，description 包含 `MemoryLimiter:AnonSwap`，统计时应与 `lmkd` 的系统压力终止分开。

<!-- gracker-diagram: ch10-02-24-memory-limiter-real-path -->
![Memory Limiter 要沿 JNI 和异步动作看](../../assets/diagrams/ch10/ch10-02-24-memory-limiter-real-path.png)

图：组合指标不是 PSS、RSS 或 Java heap。profiling 与终止都有条件；30 秒是固定 r1 的消息延迟，不是实际退出时刻保证。

下列命令用于检查设备是否支持该机制，也可以在测试设备上验证受限场景：

```bash
adb shell am memory-limiter status
app_pid=12345  # 换成可重启测试进程的真实 PID
adb shell am memory-limiter manual "$app_pid" 30
```

这些命令在未启用 Memory Limiter 的设备上不会生效。参数里的 `30` 在 `android-17.0.0_r1` 中会经 Java 层乘以 `1024 * 1024`，作为内存与 Swap 两项的 MiB 输入——虽然命令帮助文本仍写着 PERCENT，但执行代码并没有做百分比换算。此外，`manual … none` 会先解析成 `-1` 再乘算为 `-1048576`，JNI 遇到该负值会跳过节点写入，因此靠它无法可靠撤销现有限制；`max` 也不被这份 shell 解析器接受。测试完成后，建议直接重启目标进程并读取其实际的 cgroup 节点来确认状态。需要注意的是，当前官方文档可能反映了后续修订，实际行为仍应以基线 `android-17.0.0_r1` 的代码为准；手动设置的测试值仅用于验证恢复流程，不能拿来推导产品阈值。

<!-- gracker-diagram: ch10-02-25-manual-limit-version-trap -->
![手动测试要核对单位与撤销路径](../../assets/diagrams/ch10/ch10-02-25-manual-limit-version-trap.png)

图：固定 r1 的 max 也不被 shell 解析器接受。手动值只验证恢复流程，不能当作产品阈值。

## 9. App 与低 RAM 产品适配

先看两个查询接口：`ActivityManager.isLowRamDevice()` 反映的是设备是否采用低内存（low-RAM）产品配置，判断依据就是这套系统配置，因此不能用“物理内存小于等于某个 GB 数”的经验线来代替。而 `getMemoryClass()` 只描述 ART 堆的近似预算，进程 PSS 上限仍需单独查询。

App 可以按产品档位调整以下策略：

- 图片解码尺寸、内存缓存与预取窗口。
- 列表、地图瓦片、消息和模型的内存页数。
- WebView、Codec、Camera、Surface 与后台进程的并发数量。
- 非必要 SDK 与进程的初始化时机。
- 冷启动状态恢复和缓存进程被杀后的数据重新加载。

Android Go Edition 是一整套面向低内存设备的产品配置与系统应用策略，光看物理 RAM 容量无法判断是否属于 Go 设备。测试范围应覆盖真实的 Go / low-RAM 设备、普通 4 KB 与 16 KB page size 设备，以及启用和未启用 Android 17 Memory Limiter 的机型。

### 9.1 `onTrimMemory()`

在 Android 17 上，应用侧稳定可用的状态提示包括 `TRIM_MEMORY_UI_HIDDEN` 与 `TRIM_MEMORY_BACKGROUND`；`TRIM_MEMORY_RUNNING_*`、`MODERATE`、`COMPLETE` 自 API 34 起不再投递，并在 API 35 正式标为 deprecated。

应用应当在 UI 隐藏和进入后台时主动缩减可重新生成的缓存、停止预取并关闭界面资源。需要注意的是，这个回调既不携带实时 PSI 数值，也无法替代应用自身的内存硬上限（hard memory budget）；至于主动调用 `System.gc()`，它释放不了仍被引用的对象，反而容易干扰正常的 GC 与调度节奏。


## 10. 诊断表

| 现象 | 需要验证 | 常见方向 |
| --- | --- | --- |
| kswapd 活跃，direct reclaim 少 | 后台 scan/steal、refault、ZRAM CPU | 工作集、文件页、MGLRU、ZRAM |
| App 线程出现 direct reclaim | GFP 调用栈、持续时间、回收结果 | 减少峰值分配、预分配、系统余量 |
| memory PSI full 升高 | sched、I/O、vmscan、并发任务 | 系统级停顿来源 |
| lmkd kill 后冷启动增加 | kill reason、`oom_score_adj`、返回间隔 | 降低后台内存占用、状态恢复 |
| GC slice 变密，PSI 平稳 | allocation rate、live heap | App churn、对象生命周期 |
| PSI 与 GC 同时升高 | CPU 竞争、分配线程、FrameTimeline | App 分配与系统压力分别处理 |
| ZRAM 使用高且切回慢 | pswpin/out、解压 CPU、page-cluster | 容量、算法、预读与工作集 |
| Android 17 `MemoryLimiter:AnonSwap` | exit-info、anomaly profile（异常诊断数据）、进程状态 | 单进程预算、泄漏、恢复 |


## 版本边界

- Android 10 起，userspace lmkd 的 PSI 路径成为现代 Android 的主要实现方向。
- Android 14（API 34）起，App 不再收到旧的运行时压力 trim levels。
- Android 15（API 35）起，AOSP 支持 16 KB page size 设备；内存基线要按 page size 分组。
- Android 17（API 37）的 lmkd 直接初始化 PSI monitors，并优先使用 BPF `libmemevents` 观察回收事件，失败时回退到 vmstat。
- Android 17 在部分设备启用 App Memory Limiter，本文对相关平台机制的讨论截止到 Android 17。
- 内核机制以 `android17-6.18-2026-06_r6` 的 vmscan、PSI、ZRAM、MGLRU 与 compaction 为准。

## 检查清单


- 是否把 kswapd、direct reclaim、PSI 与 lmkd 当作不同证据？
- D 状态（不可中断睡眠）是否有 blocked reason、调用栈或 direct reclaim event 支撑？
- clean file reclaim、ZRAM、dirty writeback 与 refault 是否分开？
- lmkd kill 是否记录 PID、adj、reason、RSS、swap 与 DMA-BUF？
- GC 变密是否有 App allocation rate 与 live heap 证据？
- 是否误用 Android 17 已删除的 Perfetto `mm_events` service？
- ZRAM 与 MGLRU 参数是否经过同设备 A/B 对照测试，而非套用固定值？
- cached app compaction、freezer、ART GC 与物理页 compaction 是否分开？
- Android 17 退出记录是否区分 lmkd 与 `MemoryLimiter:AnonSwap`？
- 低 RAM 档位是否来自产品配置和实机，而非固定 GB 线？

## 与其他章节的关系

- [4.1 Android 与 Linux 内存管理全景](../../part1-fundamentals/ch04-memory/01-android-linux-memory-overview.md)：进程内存口径，以及 watermark、reclaim、swap 与 compaction 等系统物理页机制。
- [§4.3 Low Memory Killer](../../part1-fundamentals/ch04-memory/03-lmkd-freezer-memory-pressure.md)：lmkd 选择策略与进程优先级。
- [§4.4 App 内存优化](../../part1-fundamentals/ch04-memory/04-app-memory-optimization.md)：App hard budget、trim 与资源生命周期。
- [10.1 App 内存分析与案例](01-app-memory-analysis-cases.md)：PSS、RSS、Graphics、heap 与退出信息。
- [§10.3 内存抖动与频繁 GC](03-memory-churn.md)：allocation rate、GC 与帧时间。

## 参考资料

- [AOSP `lmkd.cpp`（android-17.0.0_r1）](https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/lmkd.cpp)
- [AOSP `libmemevents`（android-17.0.0_r1）](https://android.googlesource.com/platform/system/memory/libmeminfo/+/refs/tags/android-17.0.0_r1/libmemevents/)
- [AOSP `LowMemDetector.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/am/LowMemDetector.java)
- [AOSP `LowMemDetector.cpp`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/jni/com_android_server_am_LowMemDetector.cpp)
- [AOSP `CachedAppOptimizer.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/am/CachedAppOptimizer.java)
- [AOSP `MemoryLimiter.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/am/MemoryLimiter.java)
- [AOSP `atrace.cpp`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/cmds/atrace/atrace.cpp)
- [Kernel `mm/page_alloc.c`（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/mm/page_alloc.c)
- [Kernel `mm/vmscan.c`（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/mm/vmscan.c)
- [Kernel vmscan tracepoints（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/trace/events/vmscan.h)
- [Kernel PSI documentation](https://docs.kernel.org/accounting/psi.html)
- [Kernel ZRAM documentation](https://docs.kernel.org/admin-guide/blockdev/zram.html)
- [Kernel Multi-Gen LRU documentation](https://docs.kernel.org/admin-guide/mm/multigen_lru.html)
- [Android lmkd documentation](https://source.android.com/docs/core/perf/lmkd)
- [Android cgroups and Task Profiles](https://source.android.com/docs/core/perf/cgroups)
- [Perfetto memory counters](https://perfetto.dev/docs/data-sources/memory-counters)
- [Android 17 App memory limits](https://developer.android.com/about/versions/17/behavior-changes-all#app-memory-limits)
- [Android `ComponentCallbacks2`](https://developer.android.com/reference/android/content/ComponentCallbacks2)
- [AOSP MemoryLimiter JNI（固定 r1，实际节点与组合指标）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/jni/com_android_server_am_MemoryLimiter.cpp)
- [AOSP MemoryLimiter shell 解析（固定 r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/am/ActivityManagerShellCommand.java)
- [Kernel VM sysctl（固定 6.18，page-cluster 与 swappiness）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/Documentation/admin-guide/sysctl/vm.rst)
- [Perfetto ProcessStatsConfig（固定 r1）](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/protos/perfetto/config/process_stats/process_stats_config.proto)

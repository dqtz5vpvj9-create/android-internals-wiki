---
title: 线程 CPU 状态分析
section: '14.3'
chapter: '14.3'
status: finalized
applicable_versions: Android 8.0 (API 26) - Android 17 (API 37)
last_verified: '2026-10-25'
last_verified_against: AOSP android-17.0.0_r1 external/perfetto, android17-6.18-2026-06_r6, perfetto.dev (2026-10-25); host Trace Processor v54.0/v57.2/v58.2 synthetic traces
confidence: high
sources:
- type: blog
  path: https://www.androidperformance.com/2025/11/12/Android-Perfetto-09-CPU/
- type: blog
  path: https://www.androidperformance.com/2022/01/21/android-systrace-cpu-state-runnable/
- type: blog
  path: https://www.androidperformance.com/2022/03/13/android-systrace-cpu-state-running/
- type: blog
  path: https://www.androidperformance.com/2022/03/13/android-systrace-cpu-state-sleep/
- type: official
  path: https://perfetto.dev/docs/data-sources/cpu-scheduling
- type: official
  path: https://perfetto.dev/docs/case-studies/scheduling-blockages
- type: source
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/importers/common/thread_state_tracker.cc
- type: source
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/importers/ftrace/ftrace_parser.cc
- type: source
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/tables/sched_tables.py
- type: source
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/sched/latency.sql
- type: source
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/sched/time_in_state.sql
- type: source
  path: https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/protos/perfetto/config/ftrace/ftrace_config.proto
- type: source
  path: https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/linux/sched.h
- type: source
  path: https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/trace/events/sched.h
- type: source
  path: https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/kernel/sched/core.c
tags:
- perfetto
- thread-state
- sched-switch
- running
- runnable
- sleep
- uninterruptible-sleep
- cpu-scheduling
related_chapters:
- '5.1'
- '14.1'
- '14.7'
- '14.9'
---

# 线程 CPU 状态分析

线程状态只回答一个问题：在一段墙钟时间（wall-clock time，即现实经过的时间）里，线程是否具备运行条件、是否正占着 CPU。至于线程在执行哪个函数、等待哪把锁或哪次 I/O，还必须把状态区间与 Slice（Trace 时间轴上的事件区间）、调用栈、唤醒者、Binder（Android 的进程间通信机制）、文件系统和设备事件放到同一时间范围内核对，才能给出答案。


> 源码基线：AOSP `android-17.0.0_r1`（Android 17 / API 37）的 Perfetto 导入逻辑；内核 `android17-6.18-2026-06_r6`。
>
> 状态转换、四段 SQL 与数据缺失时的行为，另在主机上以 Trace Processor v54.0、v57.2、v58.2 解析合成 Trace 复核；这只覆盖解析逻辑，目标设备上的采集与性能表现要另行实测，且各发布版代码与该 tag 各有差异。旧平台同样有调度事件，但字段、内核符号和标准库模块可能有出入。

## 14.3.1 状态从哪里来

### 从任务位到 UI 状态的三个层次

UI 里这些状态字符串从哪里来？我们从内核的任务状态位说起。Linux 6.18 的 `include/linux/sched.h` 把 `TASK_RUNNING` 定义为 0，这个值同时覆盖正在 CPU 上执行的任务和具备运行条件、还没上 CPU 的任务；因此只看 `task_struct->__state` 分不出 Running 与 Runnable，这一步区分必须依靠调度事件来完成。


Perfetto 依靠以下三步调度事件补出时间线：

- `sched_switch` 记录前一个线程何时离开 CPU、下一个线程何时进入 CPU。Perfetto 把下一个线程记为 `Running`，并用 `prev_state` 为离开的线程打开后续状态区间。
- `sched_waking` 记录唤醒动作。在正常的阻塞到可运行转换中，Perfetto 关闭旧阻塞区间并打开 `R`；首次观察到线程时也可能直接打开 `R`。重复唤醒与 `R+` 的导入行为见 14.3.5；每条 waking 未必都对应一次新的睡眠结束。
- 下一次 `sched_switch` 选中该线程时，Perfetto 关闭 `R` 或 `R+`，打开 `Running`。


`utid` 是 Perfetto 在单份 Trace 内分配的线程唯一标识，`upid` 则是进程唯一标识；当操作系统进程号（PID）或线程号（TID）被复用时，我们靠它们区分前后不同的实例。`waker_utid` 标识执行唤醒动作的线程；`waker_id` 要等导入器找到该唤醒线程当时的 Running 行才会填充并指向它，因此两者可能只存在前者。`irq_context` 来自唤醒记录所保留的中断标志。这些标识都只在当前 Trace 内有效。


同一份调度事实在 Trace 中对应两个视角：`sched_slice` 从 CPU 视角记录“哪个 `utid` 在哪个 CPU 上运行了多久、切出时是什么状态”；`thread_state` 从线程视角重建状态区间，并附带 CPU、I/O 等待、阻塞函数和唤醒者等可选字段，事件缺失时覆盖未必连续完整。两张表中的 `dur = -1` 表示没有可靠的结束时间，常见于 Trace 尾部或数据丢失，聚合时要把它排除在统计之外。本节的区间函数只统计 `dur > 0` 的已闭合状态，同时报告未覆盖时间；未知区间只是没有计入，它的真实耗时仍属未知。

<!-- gracker-diagram: ch14-03-05-cpu-vs-thread -->
![同一调度事实的 CPU 与线程视角](../../assets/diagrams/ch14/ch14-03-05-cpu-vs-thread.png)

图：`sched_slice` 回答 CPU 由谁运行，`thread_state` 回答线程的状态与可用线索。状态重建可能有缺口；`dur = −1` 要留在聚合之外。

### 常见状态与跨版本字符

| Perfetto 状态 | 含义 | 能直接得出的事实 |
| --- | --- | --- |
| `Running` | 线程被调度在某个 CPU 上 | 该调度区间占用 CPU 时间线 |
| `R` | Runnable | 线程具备运行条件，尚未进入 CPU |
| `R+` | Runnable (Preempted) | 前一次切出被内核标为抢占式切换 |
| `S` | Sleeping | 线程处于可中断睡眠 |
| `D` | Uninterruptible Sleep | 线程处于不可中断睡眠 |
| `T` | Stopped | 线程被停止 |
| `t` | Traced | 线程受跟踪控制 |
| `X` / `Z` | 退出 / 僵尸状态 | 线程处于退出流程 |
| `I` / `P` | `TASK_IDLE` 的报告态 / Parked（停驻） | 特殊任务状态；`I` 不等于 CPU idle 轨道，也不能据此认定为 swapper 线程 |
| `W` / `K` / `N` / `x` 等兼容字符 | Waking / Wake Kill / No Load / Task Dead | 来自旧内核位布局或文本输入等兼容路径，不保证出现在当前 6.18 二进制调度事件中 |

分析时应以详情面板或 SQL 字段中的状态名称为准。内核 `__state` 位、`sched_switch.prev_state` 的报告编码、Perfetto 解析后的字符串分属三个层次：当前内核会掩码并重编码部分状态，直接把 `TASK_*` 数值塞进 `prev_state` 未必对得上。此外，Perfetto 的二进制解码还依赖 Trace 中记录的内核版本，缺失时该 tag 会回退到旧布局。至于 UI 颜色，它会随版本、主题和选中状态变化，不能当作稳定接口。

<!-- gracker-diagram: ed14-03-versioned-state-reconstruction -->
![从内核位图到报告编码，再到可见线程状态](../../assets/diagrams/ch14/ed14-03-versioned-state-reconstruction.png)

图：内核 `task.__state` 位图、`sched_switch.prev_state` 报告编码和 TP 重建字符串属于不同层次；`TASK_RUNNING = 0` 同时覆盖实际运行与可运行，需依赖调度事件区分。解析时需固定内核版本与二进制/文本输入，旧版缺内核版本时可能走兼容解码。在 Android 17 / 内核 6.18 语境下，`R+` 来自抢占报告位，不直接证明用户态或内核态来源以及由谁抢占。`T`/`t`/`Z` 及兼容字母需保留原始 `state`/`end_state` 并结合生命周期判断，不能假定旧字符表全部在当前编码中可达。

### `R+` 的抢占编码

Tracepoint 是内核预先定义的静态事件记录点。在 `sched_switch` Tracepoint 里，6.18 内核按如下逻辑编码抢占：

```c
if (preempt)
    return TASK_REPORT_MAX;

/* TP_printk() 在 TASK_REPORT_MAX 置位时追加 "+"。 */
```

这段逻辑把所有抢占式切出的线程统一呈现为 `R+`。至于抢占发生在用户态还是内核态、抢占者是谁、为什么抢占，`R+` 本身没有任何记录。要回答这些问题，需回到同一 CPU 上紧接着的 `sched_slice`，对照线程各自的优先级与调度策略；时间片耗尽、调度类差异和唤醒抢占都可能涉及其中。

<!-- gracker-diagram: ch14-03-07-rplus-meaning -->
![R+ 记录抢占标志，不保存抢占者身份](../../assets/diagrams/ch14/ch14-03-07-rplus-meaning.png)

图：`preempt` 切出报告 `R+`，需从同 CPU 的后继执行重建现场。用户态还是内核态、抢占原因是什么，都要靠后继执行还原。

读 `R` 时还要留意区分：它未必总是“由睡眠刚刚唤醒”。线程在保持可运行状态时主动或被动离开 CPU，同样可能产生 `R`；判断唤醒来源时，应以实际记录的 `sched_waking` 和 `waker_utid` 为准。


## 14.3.2 采集与 UI 读取

状态重建的质量取决于采集配置。下面的配置通过 ftrace（Linux 内核跟踪机制）采集线程状态、唤醒、D 状态原因、频率和中断，适合十几秒的定点复现：

```protobuf
buffers {
  size_kb: 65536
  fill_policy: RING_BUFFER
}
duration_ms: 15000

data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      compact_sched {
        enabled: true
      }

      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_waking"
      ftrace_events: "sched/sched_wakeup_new"
      ftrace_events: "sched/sched_blocked_reason"
      ftrace_events: "sched/sched_process_exit"
      ftrace_events: "sched/sched_process_free"
      ftrace_events: "task/task_newtask"
      ftrace_events: "task/task_rename"

      ftrace_events: "power/cpu_frequency"
      ftrace_events: "power/cpu_idle"

      ftrace_events: "irq/irq_handler_entry"
      ftrace_events: "irq/irq_handler_exit"
      ftrace_events: "irq/softirq_entry"
      ftrace_events: "irq/softirq_exit"

      symbolize_ksyms: true
    }
  }
}

data_sources {
  config {
    name: "linux.process_stats"
    process_stats_config {
      scan_all_processes_on_start: true
    }
  }
}
```

这里有两层缓冲必须分清：`buffers.size_kb` 配置的是 Perfetto 服务端 Trace buffer，`RING_BUFFER` 写满会覆盖最早的数据，事件突增时可能冲掉 Trace 开头；而内核每 CPU 的 ftrace ring buffer 是另一层，由 `ftrace_config.buffer_size_kb` 等控制，单纯调大服务端 buffer 并不能自动消除内核 overrun。


三个关键调度事件分工明确：`sched_switch` 是构建 Running 和切出状态的基础，`sched_waking` 补充唤醒与 Runnable 起点，`sched_blocked_reason` 补充 D 状态的 `io_wait` 和睡眠函数。


`compact_sched` 只对 `sched_switch` / `sched_waking` 启用紧凑编码，格式不兼容时可回退到逐事件编码，其余 ftrace 事件保持原样。两条唤醒路径在中断标志上还有一处细微差别：紧凑 waking 保留的 `common_flags` 会传给线程状态的 `irq_context`，而逐事件 `ParseSchedWaking()` 不传该参数。因此 `irq_context` 为 NULL 时只表示“这次没记录”，不能当作“非中断”来解读。


`symbolize_ksyms` 会尝试把内核地址解析为函数名。Android 平台构建可使用 init 预先打开并继承的 `/proc/kallsyms` 文件描述符，Linux / 独立构建还可依赖 capabilities（进程能力）、root 或允许读取地址的 sysctl 配置（因此“traced_probes 必须是 root”只涵盖其中一条路径）。无论走哪条路径，都要核验符号实际可读、Tracepoint 是否采到以及导入结果；解析失败时 `blocked_function` 可能为空。


设备可能缺少某些 Tracepoint，量产构建也可能限制内核符号，因此录制完成后最好先做一次体检：先检查 `stats` 表中 `name = 'ftrace_setup_errors'` 的统计值，再查看该 tag 下 `metadata` 表中同名条目的详情。注意 `unknown_ftrace_events` / `failed_ftrace_events` 是 Trace 内 `FtraceStats` 消息的字段，与这两个同名 `stats` 行属于不同概念。丢失情况则需另查 `ftrace_cpu_has_data_loss`、`ftrace_cpu_overrun_delta` 等统计；如果启用了 `linux.perf`，还要查看 `perf_cpu_lost_records` 等统计。不同发布版可能调整详情的保存位置，应以所用处理器的表结构为准；至于空字段，它说明的只是“没查到”，远不能证明“没有发生”。


确认采集质量过关后，UI 中有两个互补的观察入口：

- CPU Scheduling 轨道按 CPU 展示 `sched_slice`。选中区间可查看 `utid`、CPU、优先级和 `end_state`，也能看到之前的 Runnable 延迟与唤醒信息。
- 进程下的 `Thread State` 轨道按线程展示 `thread_state`。选中状态可查看持续时间、CPU、`io_wait`、`blocked_function`、唤醒者和中断环境。

分析关键路径时，应先固定业务 Slice 或 FrameTimeline 帧（FrameTimeline 是 Android 12 起记录预期帧与实际帧时间线的机制；Looper 是 Android 线程处理消息队列的循环），再检查该时间范围内的线程状态。如果直接拉出整条线程生命周期的状态占比，主导结果的通常是 Looper 的正常睡眠，这对解释某次掉帧或启动并没有帮助。


## 14.3.3 Running：已被调度，不等于应用代码独占 CPU

先看 Running。`Running` 表示调度器让该线程占据了某颗 CPU 的任务时间线，这段执行可能在用户态，也可能在系统调用或异常处理的内核态。硬中断（HardIRQ）会立即暂停当前任务去处理设备事件，但通常不会引发 `sched_switch`，因此这段 IRQ 时间仍落在外层的 Running 调度区间内；SoftIRQ 则是随后处理延迟中断工作的机制，既可能在当前 CPU 的中断返回路径上执行，也可能交给 `ksoftirqd` 内核线程处理。

<!-- gracker-diagram: ch14-03-15-running-interrupt-layers -->
![Running 外层可以包含中断处理](../../assets/diagrams/ch14/ch14-03-15-running-interrupt-layers.png)

图：没有 `sched_switch` 时，中断处理仍可落在当前任务外层 Running 内。轨道只表达嵌套关系，条长与实测或 CPU 比例无关。

因此，遇到较长的 Running 区间需要分层验证：

- 应用或框架 Slice 能否解释这段工作；
- `linux.perf`（Perfetto 的 Linux perf 采样数据源）或 simpleperf（Android 原生性能采样器）样本中的 `cpu_mode`（样本落在用户态、内核态或其他执行模式）和调用栈指向用户态还是内核态；
- 同一 CPU 的 IRQ / SoftIRQ 轨道是否覆盖了其中一部分时间；
- 线程运行在哪颗 CPU 上，该 CPU 的 `capacity`（调度器描述 CPU 相对计算能力的指标，不同于实时利用率）、频率与空闲状态如何；
- 该区间是否处于启动、帧、输入或 Binder 的关键路径上。

Running 的绝对长度本身定不了性：一次必须完成的后台计算可以合法占满 CPU；而一段很短的 Running 也可能因为频繁唤醒、缓存失效或跨线程串行化而拖慢关键路径。


### 单帧 Running 与名义刷新周期

60 Hz 的名义周期约为 16.67 毫秒，120 Hz 约为 8.33 毫秒，这两个数字描述的是屏幕刷新周期。单个 `doFrame` 的 Running 时间必须放回整帧链路来看：一帧还包含 Runnable、同步等待、`RenderThread`、GPU 和 SurfaceFlinger（Android 显示合成服务），调度偏移、刷新率切换与预测都会改变最终的 deadline（截止时刻）。

在 Android 12 及以上版本，通常先读取 FrameTimeline 的 Expected / Actual Timeline（预期 / 实际帧时间线）与 overrun（实际帧超出预期截止时刻的时间），再回看线程状态。


### CPU 类型、容量与频率

CPU 编号与大小核布局由 SoC（System on Chip，系统级芯片）决定，“0—3 是小核、4—7 是大核”只对部分设备成立。应当先从 Perfetto 的 `cpu` 表确认实际拓扑：`cluster_id`、`processor` 和 `capacity`，频率轨道则提供对应时刻的 kHz 数值。相同频率下，不同微架构和容量的 CPU 吞吐量可能不同；高频也不直接说明线程负载高，因为 Governor（动态调频策略）、Boost（临时提高性能目标）与热策略都会主动拉高或压低频点。


手工绑核会缩小调度器可选的 CPU 集合，并且还会受到 cpuset、在线 CPU 状态和权限限制。这几个调度概念容易混淆：亲和性（affinity）限定线程允许在哪些 CPU 上运行，cpuset 用控制组为一组任务划定可用 CPU；而 uclamp 限定的是调度器使用的有效利用率提示上下界，影响容量选择和调频决策，它既算不上 CPU 允许掩码，也不保证锁定特定核心或频率。


对普通应用而言，硬编码 CPU 编号和固定亲和性都不可靠；平台侧如果要调整这些参数，也应使用同场景 Trace 对比验证延迟、能耗和热稳定性。

## 14.3.4 Runnable：测量唤醒到运行的等待

分析 Runnable，本质上是在测量线程从“可以运行”到“真正上核运行”之间的等待。Runnable 区间代表线程已经具备运行条件但尚未占用 CPU：由 `sched_waking` 打开的 `R`，其持续时间近似“被唤醒到被调度”的延迟；`R+` 则从抢占式切出一直持续到下一次运行。

Runnable 变长常见于以下几类原因：

- 所有合适的 CPU 都在运行其他任务，或高调度优先级任务、实时任务与 IRQ 持续占用；
- 调度类（如普通公平调度或实时调度）、nice（普通调度任务的相对优先级）与厂商策略影响竞争；cpuset / 亲和性约束可用 CPU；uclamp 等利用率提示影响容量与调频决策（注意这些机制中只有一部分直接限制 CPU 集合）；
- CPU 离线、热限制、频率降低或设备计算容量不足，导致队列消化速度下降；
- 唤醒放置（线程被唤醒时选择目标 CPU）与负载均衡策略暂时保留线程在原 CPU 上，避免跨核迁移开销；
- cgroup（Linux 控制组）的 CPU 带宽配额、实时节流（限制实时任务持续占用 CPU）或其他资源控制延后了执行。

如果 Trace 里明明有空闲 CPU、目标线程却一直在排队，先不要急着判定调度器出错。Perfetto 官方文档指出，普通 Linux 调度配置并不保证严格 work-conserving（即“只要存在可运行任务和可用 CPU，就尽量不让 CPU 空闲”）。调度器可能出于缓存复用和降功耗的考虑暂缓迁移，把线程留在原 CPU；遇到这种情况，还需确认目标线程的允许集是否包含那颗空闲 CPU。

<!-- gracker-diagram: ed14-03-runnable-eligibility-and-placement -->
![看到 Runnable 排队，先确认哪些 CPU 真有资格运行它](../../assets/diagrams/ch14/ed14-03-runnable-eligibility-and-placement.png)

图：`R`/`R+` 说明可运行但未执行，分析延迟需排查 affinity、cpuset 与在线核的交集、优先级与实时任务竞争、quotas/throttling、负载以及放置偏好。uclamp 属于有效利用率约束提示，不改变允许核掩码，也不承诺固定核心或频率。排查前应先核对 CPU capacity、cluster、频率与温控环境，不能按固定编号猜测核型；可见的 idle CPU 可能不在允许集合内，或因迁移代价与能耗策略保留当前放置。延迟查询 SQL 还需满足闭合（`dur >= 0`）与 `R`/`R+` 结束精确相邻 Running，空结果并不等于零延迟。

### 查询每次运行前的 Runnable 延迟

`sched.latency` 标准库会把每个 Running 状态关联到它之前的 Runnable 状态。下面的查询列出 SystemUI 主线程最长的 20 次调度延迟：

```sql
INCLUDE PERFETTO MODULE sched.latency;

SELECT
  p.upid,
  t.utid,
  running.id AS running_state_id,
  runnable.id AS runnable_state_id,
  running.ts AS running_ts,
  runnable.state AS runnable_state,
  ROUND(l.latency_dur / 1e6, 3) AS latency_ms,
  ss.cpu,
  ss.priority,
  wp.name AS waker_process,
  wt.name AS waker_thread,
  runnable.irq_context
FROM sched_latency_for_running_interval AS l
JOIN thread_state AS running
  ON running.id = l.thread_state_id
JOIN thread_state AS runnable
  ON runnable.id = l.runnable_latency_id
JOIN sched_slice AS ss
  ON ss.id = l.sched_id
JOIN thread AS t
  ON t.utid = running.utid
JOIN process AS p
  USING (upid)
LEFT JOIN thread AS wt
  ON wt.utid = runnable.waker_utid
LEFT JOIN process AS wp
  ON wp.upid = wt.upid
WHERE p.name = 'com.android.systemui'
  AND t.is_main_thread
  AND runnable.dur >= 0
  AND running.dur >= 0
  AND runnable.ts + runnable.dur = running.ts
ORDER BY l.latency_dur DESC, running.ts, running.id
LIMIT 20;
```

这条查询会把同名进程的多个实例全部列出来，结果中通过 `upid` / `utid` 和状态行 ID 加以区分；排查某次具体复现时，应进一步限定现场实例与时间窗。其中的邻接条件要求 Runnable 的结束时刻恰好等于 Running 的开始时刻，这样在缺唤醒事件时，历史上的旧 `R` 不会被误连过来，未闭合的 Running 也不会混入结果。因此拿到空结果，含义是“查询未覆盖到完整邻接区间”，而非“没有调度延迟”。`waker_process` 为空通常有几种来源：保持可运行的切出、Trace 边界、数据丢失或缺少 waking 事件。`irq_context = 1` 说明记录的 HardIRQ / SoftIRQ 标志置位，此时对应的当前任务名多半属于被中断的线程，真正的业务唤醒源需要另找；NULL 则表示未保留该标志信息。

<!-- gracker-diagram: ch14-03-21-latency-sql-adjacency -->
![Runnable 延迟查询必须复核邻接关系](../../assets/diagrams/ch14/ch14-03-21-latency-sql-adjacency.png)

图：结果保留实例与状态行，并要求 Runnable 的结束等于 Running 的开始。缺 wake 或未闭合 Running 会使结果不完整；空结果与零延迟属于两回事。

### 解读 `R` 与 `R+`

当 `R+` 频繁出现时，说明线程多次遭遇抢占式切换。次数或占比偏高时，先不要急于归因到优先级配置，建议顺着四件事逐一排查：切出后哪条任务在相同 CPU 上运行、它属于哪个调度类、目标线程允许在哪些 CPU 执行，以及这段等待是否越过了业务 deadline。关于优先级的判断，必须建立在这些事实之上。


读 `R` 时要先区分来源：它既可能是唤醒后的排队，也可能是线程保持可运行状态时的切出。SQL 里可以通过 `waker_utid` 追查执行唤醒的一方；该 tag 的 UI Woken by（由谁唤醒）引用则依赖可用的 `waker_id`，仅有 `waker_utid` 时界面跳转未必可用。中断标志为真时 UI 可能仅显示 Interrupt，标志未知时也可能提示 maybe interrupt。同时要记住，唤醒者只是把线程重新变为可运行的那一方，锁持有者、Binder 服务端或设备中断的源头，仍要靠 Binder Flow（Binder 事务的跨线程因果连线）、锁事件或代码路径另行确认。

## 14.3.5 Sleeping：找到等待条件和唤醒者

`S` 是可中断睡眠，以下等待都会表现为 `S`：

- Looper 调用 `epoll_wait()`，等待文件描述符（进程访问文件、socket 等内核对象所用的编号）上的消息事件；
- 线程等待条件变量或 futex（用户态锁常用的内核等待机制）；
- 同步 Binder 客户端等待回复；
- 定时器等待到期。

对大多数后台或空闲线程而言，长期处于 Sleeping 是正常的空闲表现。

当关键 Slice 内出现较长的 `S` 区间时，应顺着以下线索追查：

- Slice 名称或事件触发采样栈指明线程是在哪个等待 API 进入睡眠的；
- `thread_state.waker_utid` 与 `waker_id` 指向了哪个线程状态；
- Binder 事务、Monitor Contention（Java / Kotlin 监视器锁竞争）、futex、Flow（Trace 事件之间的因果连线）或定时器事件能否解释这层唤醒关系；
- 线程从被唤醒到真正 Running 之间的 `R` 区间，是否也贡献了不可忽视的调度延迟。

一次同步等待的墙钟时间往往由 `S + R + Running` 共同组成：线程先睡眠等待条件，条件满足后进入 Runnable 排队，获得 CPU 后继续执行。只测量 `S` 会漏掉唤醒后的调度排队时间。

<!-- gracker-diagram: ch14-03-23-sleeping-wait-chain -->
![同步等待的完整墙钟路径](../../assets/diagrams/ch14/ch14-03-23-sleeping-wait-chain.png)

图：一次等待可同时包含睡眠、唤醒后排队与恢复执行。只计 `S` 会漏掉 `R`；图中为顺序示意，时长比例以实际 Trace 为准。

### Woken by 的来源与实现

Woken by 是 Perfetto UI 对唤醒来源的展示。在当前核对的 tag 中，`PushWakingEvent()` 会按三种情况处理 waking：线程没有历史状态行时直接打开 `R`；已有历史行且状态为 `Running` 或恰好为 `R` 时，把重复唤醒记入 `spurious_sched_wakeup` 并保留当前状态；其余阻塞状态则被关闭，并新开一条 `R`。


这里有一个容易踩中的实现细节：该 tag 的 `IsRunnable()` 只比较字符串 `R`，并不包含 `R+`。如果 `R+` 区间内又收到一次 waking，原区间会被截断，转为带新唤醒线索的 `R`。因此，“所有 Runnable 状态收到重复唤醒都不改状态”对这个 tag 并不成立，新开出的 `R` 时长也无法代替完整的抢占等待。主机 v54.0 / v57.2 / v58.2 的合成输入已经复现了这一分段行为；这属于所核对导入器的实现逻辑，内核本身并没有规定线程必须按这种方式转换。

<!-- gracker-diagram: ed14-03-waking-state-branches -->
![同一次 waking 在不同当前状态下走不同重建分支](../../assets/diagrams/ch14/ed14-03-waking-state-branches.png)

图：`sched_switch` 切出时按报告打开后继状态，切入时打开 `Running`；正常阻塞后收到 waking 打开 `R`，而 `R` 也可能来自可运行状态的切出。在固定 TP 实现中，`PushWakingEvent` 在无历史行时打开 `R`，当前为 `Running` 或恰好为 `R` 时忽略冗余唤醒，其余当前状态则关闭旧行并开启 `R`。由于 `IsRunnable` 仅识别 `R`，waking 落在 `R+` 内时会截断 `R+` 并另开 `R` 且附带 waker 线索，因此完整等待需合并观察两段。这是在固定 tag 与合成 trace 下观察到的导入行为，不代表内核必然发生重新唤醒。

Woken by 记录的是直接执行唤醒动作的线程：

- 解锁路径中，它可能是释放锁的线程；
- Binder 回复中，它可能落在驱动或服务端执行路径；
- 中断唤醒中，`irq_context` 会标记 HardIRQ / SoftIRQ，此时的当前被中断线程只是恰好占着这颗 CPU，设备事件的业务源头需另行追查；
- 缺少事件、Trace 起点覆盖不足或 ftrace 丢包都会导致唤醒关系中断。

<!-- gracker-diagram: ed14-03-waker-identity-and-causal-evidence -->
![先识别观测到的 waker，再验证真正的业务依赖](../../assets/diagrams/ch14/ed14-03-waker-identity-and-causal-evidence.png)

图：`utid`/`upid` 为 trace 内唯一身份，不可按复用的 `tid`/`pid` 混淆线程。`waker_utid` 是执行 waking 时的任务，`waker_id` 则关联它已有的 `Running` 状态行，后者缺失时前者仍可能存在；UI 中的 Woken by 跳转需有效的 `waker_id`。`compact` waking 会保留 `common_flags` 至 `irq_context`，而逐事件 `ParseSchedWaking()` 未传该参数，此时 NULL 表示未知而非“非 IRQ”。`irq_context = 1` 仅说明置位了 Hard/SoftIRQ 标志，当前任务可能正被中断；锁 owner、Binder 业务发起者与设备完成来源仍需另行佐证，waker 不保证就是唯一根因。

遇到复杂的跨线程等待，可以借助 UI 的 Critical Path（关键路径）视图查看依赖链路。该视图依据唤醒关系推导路径，结果受 Trace 完整性约束，最终仍需回到原始状态、Slice 与代码核对。

Perfetto 官方的调度阻塞案例还展示了基于事件的调用栈采样：利用 `linux.perf` 在 `sched_switch` 和 `sched_waking` 发生时采样，并通过 `prev_comm`、`next_comm` 或 `comm`（内核记录的任务名）过滤目标线程。若对全系统每次调度切换都取栈，采样器很快会跟不上事件速率，因此必须限制过滤范围并检查丢样统计。

<!-- gracker-diagram: ch14-03-27-event-sampling -->
![事件触发调用栈需要限制目标与检查丢样](../../assets/diagrams/ch14/ch14-03-27-event-sampling.png)

图：对目标调度事件取栈，补充线程进入等待或执行唤醒时的代码证据。全系统每次切换都采栈可能跟不上事件速率，采样过滤和丢失统计是解释的前提。

## 14.3.6 Uninterruptible Sleep：D 只说明不可中断等待

再来看不可中断睡眠。Linux 6.18 将 `TASK_UNINTERRUPTIBLE` 定义为独立的任务状态：处于该状态的线程不会被普通信号打断并提前返回，只有等待条件满足并被唤醒后，挂起的信号才有机会处理。内核还提供了 `TASK_KILLABLE = TASK_WAKEKILL | TASK_UNINTERRUPTIBLE`，供允许致命信号唤醒的等待点使用。

D 状态可能出现在块 I/O、Swap（交换区页面换入换出）、内存回收、页迁移、驱动等待和内核同步路径中，磁盘 I/O 只是其中一种来源。两类缺页异常也应区分开来：Minor Page Fault（次缺页）通常表示所需页面已在内存中，既不需要存储 I/O，也未必让线程进入睡眠；Major Page Fault（主缺页）则可能等待文件页或 Swap 读入，判断时仍需核对页故障与块设备两边的记录。把所有 Page Fault 或所有 D 状态一律归结为磁盘问题，往往会带偏方向。


### `io_wait` 与 `blocked_function` 的源码含义

锚点内核的 `sched_blocked_reason` Tracepoint 写入了两个字段：

```c
__entry->caller = (void *)__get_wchan(tsk);
__entry->io_wait = tsk->in_iowait;
```

`io_wait` 来自任务的 `in_iowait` 记账标志。值为 1 只表明内核将该任务标为 I/O 等待记账，字段本身既不含文件名、设备名、请求类型或调用方，也推不出业务原因；同理，值为 0 也无法定性为“内核锁”。`caller` 来自 `__get_wchan()`，其中 wchan（wait channel）表示内核观察到的睡眠位置；至于最初发起等待的应用函数或锁持有者是谁，它只能提供线索。


在导入侧，`ParseSchedBlockedReason()` 会把事件交给 `ThreadStateTracker`，当还能匹配到对应的最近阻塞行时，补写 `io_wait` 与可解析的睡眠函数。这条链路要求每一步都成立：Tracepoint 已采集、成功关联阻塞行，且函数名解析具备有效地址与符号映射。缺事件、时序边界、0 地址或符号缺失都可能导致字段为 NULL，“配置过该事件”离“字段必有值”还隔着这几步。

还需要区分采集前后的 `caller` 表示：内核原始事件记录的是睡眠地址，而 Perfetto 采集端会把内核地址改写为索引，并将可解析名称放入 `InternedData.kernel_symbols`。导入器正是通过该索引查名称，并不会把 Trace 中的数值直接当作原始内核地址；如果缺少索引映射，同样会拿不到 `blocked_function`。

<!-- gracker-diagram: ed14-03-blocked-reason-field-chain -->
![blocked reason 先匹配阻塞行，再解释字段和符号](../../assets/diagrams/ch14/ed14-03-blocked-reason-field-chain.png)

图：`sched_blocked_reason` 携带 `pid`、`caller` 与 `io_wait`，TP 需按线程找到最近的阻塞状态行才会补全字段。`io_wait` 来自 `in_iowait`，属于 I/O 等待记账：1 不证明具体设备、文件或 API，0 也不证明内核锁。`caller` 来自 `__get_wchan()`，仅代表内核观测到的睡眠位置，非原始应用调用或锁 owner；采集端可将地址改写为 interned kernel symbol 索引（名称存入 `InternedData.kernel_symbols`），导入时依赖有效索引与映射，不可把索引当原始地址。符号来源依赖继承的 `kallsyms` FD 或平台允许路径，并不以 root 为唯一前提；字段为 NULL 可能是缺事件、缺状态历史或符号链断裂所致，需核查完整性。

### 查询 D 状态

下面的查询列出 SystemUI 主线程耗时最长的 20 个 D 区间及其可用线索：

```sql
SELECT
  p.upid,
  t.utid,
  ts.id AS thread_state_id,
  ts.ts,
  ROUND(ts.dur / 1e6, 3) AS duration_ms,
  ts.io_wait,
  ts.blocked_function
FROM thread_state AS ts
JOIN thread AS t
  USING (utid)
JOIN process AS p
  USING (upid)
WHERE p.name = 'com.android.systemui'
  AND t.is_main_thread
  AND ts.state = 'D'
  AND ts.dur > 0
ORDER BY ts.dur DESC, ts.ts, ts.id
LIMIT 20;
```

该查询严格匹配 `state = 'D'`；如果输入是旧版或文本 Trace，还应核对是否存在 `D|K` 等复合字符串，并保留原始值。由于非 Running 状态没有“正在执行的 CPU”，相邻 CPU 与 waking 的目标 CPU 只能补充放置线索，不能用作阻塞期间的执行归属。当 `blocked_function` 为空时，依次检查 Tracepoint、符号权限、数据丢失和工具版本；空值说明链路在某处断裂，尚不足以得出“没有内核阻塞”的结论。

进一步归因 D 区间时，可以顺着线索选择排查方向：

- `io_wait = 1` 且与块设备或文件系统事件重叠：继续核查设备、inode（文件系统对象编号）、页故障、Swap 与发起调用栈；
- 与内存回收、压缩或页迁移事件重叠：检查 PSI（Pressure Stall Information，资源压力停顿统计）、reclaim（内存回收）、compaction（内存页整理）和进程内存压力；
- `blocked_function` 指向特定驱动或同步路径：查看对应子系统源码、等待条件与负责唤醒的执行路径；
- 多个线程等待同一资源：检查持有者是否处于 Sleeping、Runnable 或被其他任务抢占，识别优先级反转（高优先级任务被持锁的低优先级任务间接拖延）和锁队列串行化。

<!-- gracker-diagram: ed14-03-d-state-candidate-validation -->
![D 只给等待候选，三类资源方向分别验证](../../assets/diagrams/ch14/ed14-03-d-state-candidate-validation.png)

图：D 表示不可中断等待类别（`TASK_KILLABLE` 另允许致命信号唤醒），不等同于磁盘 I/O。文件/块 I/O/Swap、内存 reclaim/压缩/迁页以及驱动/内核同步都可能引发 D 状态；minor fault 通常无需睡眠，major fault 是否涉及实际 I/O 需独立证据验证。`io_wait` 与 `wchan` 仅作为候选线索，不可把 0 解释为锁或把 1 解释为文件。非 Running 行没有正在执行的 CPU，相邻 CPU 或 `target_cpu` 仅提供放置线索。要证明 D 状态影响 ANR，必须确认其阻断了实际受监控的工作与对应的框架期限，不存在适用于 D 状态的通用 ANR 秒数阈值。

D 状态与 ANR（Application Not Responding，应用无响应）的关系也经常被过度简化。ANR 由输入分发、服务、广播等框架监控条件触发；只有当 D 状态确实阻止了受监控工作按时完成时，它才会参与这条因果链，并不存在所谓“D 状态超过多少秒就必定 ANR”的通用阈值。


## 14.3.7 Stopped 与其他状态

`T` 常见于 `SIGSTOP`（强制暂停进程的信号）、Shell 作业控制或调试操作，`t` 表示被调试器等工具跟踪——在调试会话中看到它们往往完全符合预期。`Z` 表示退出后等待父进程回收的僵尸状态，短暂出现未必代表性能故障，只有持续堆积才需要排查父进程的回收逻辑。

`X`、`I`、`P` 以及兼容路径中的 `x`、`W`、`K`、`N` 须结合输入格式与内核版本来解读，Perfetto 官方文档也提示其中部分字符组合原本就没有实际含义。遇到复合状态时，应同时保留 `thread_state.state` 与 `sched_slice.end_state`，先核对 `sched_switch` 的报告编码，再对照对应版本的 `TASK_*` 定义；旧字符表与 6.18 的完整可达状态集合并不相同。


## 14.3.8 IRQ / SoftIRQ：调度区间里的隐含执行

Running 区间里还可能藏着一层中断执行。HardIRQ 在中断上下文中运行，会暂停当前 CPU 上的任务；SoftIRQ 则可能在中断返回路径上执行，也可能交给 `ksoftirqd` 内核线程处理。由于 HardIRQ 以及在中断返回路径执行的 SoftIRQ 都不要求发生任务切换，外层线程在 `thread_state` 中仍可能连续显示为 Running——如果把这整段 Running 全部算作应用函数的耗时，就会高估应用代码自身的执行时间。

下面的查询汇总已采集的 IRQ 与 SoftIRQ Slice：

```sql
SELECT
  tr.type AS interrupt_type,
  s.name,
  COUNT(*) AS event_count,
  ROUND(SUM(s.dur) / 1e6, 3) AS total_ms,
  ROUND(MAX(s.dur) / 1e6, 3) AS max_ms
FROM slice AS s
JOIN track AS tr
  ON tr.id = s.track_id
WHERE tr.type IN ('cpu_irq', 'cpu_softirq')
  AND s.dur > 0
GROUP BY tr.type, s.name
ORDER BY SUM(s.dur) DESC
LIMIT 30;
```

Ftrace 导入器会把这两类区间分别放入 `cpu_irq` 和 `cpu_softirq` 轨道。上述查询按类型和名称跨 CPU 汇总，`SUM(dur)` 给出的是已记录区间的包含式时长之和；不同 CPU 上的并行区间、嵌套的 HardIRQ 与 SoftIRQ 都可能发生重叠，因此它并不等于业务墙钟时间，如果把整表相加后直接从某个线程的 Running 中扣减就会算错。实际归因时，应先限定业务窗口、目标线程实际运行的同一 CPU 与交集区间，再对重叠的中断区间取并集，结合对应设备驱动和业务动作一起验证。

<!-- gracker-diagram: ch14-03-34-irq-window-union -->
![IRQ 汇总候选需要同 CPU 裁剪和并集](../../assets/diagrams/ch14/ch14-03-34-irq-window-union.png)

图：整表 `SUM` 只能筛选候选，业务归因需与目标 Running 在同一 CPU 上求交。跨 CPU 并行和嵌套 IRQ 可能重叠，直接把整表 `SUM` 从 Running 中扣掉会算错。

`ksoftirqd/<cpu>` 是对应 CPU 的可调度内核线程，它的 Running 会出现在 CPU Scheduling 轨道上，内部也可能包含 SoftIRQ Slice。同时使用 CPU 调度时间和 SoftIRQ 事件统计同一份工作时，必须先核对重叠关系：把 `ksoftirqd` 的全部 Running 与其中的 SoftIRQ 时长直接相加，会把同一份执行计算两次。实际排查中，CPU 在线状态、线程化中断和内核配置也需一并核对。

<!-- gracker-diagram: ch14-03-35-ksoftirqd-overlap -->
![ksoftirqd 的调度时间可包住 SoftIRQ Slice](../../assets/diagrams/ch14/ch14-03-35-ksoftirqd-overlap.png)

图：`ksoftirqd` 是可调度内核线程，其内部 SoftIRQ 事件可能已包含在外层 Running 中。若将 Running 与内部 SoftIRQ 两次累加会导致耗时翻倍；条长仅作机制示意。

## 14.3.9 在业务区间内量化状态

统计线程整段生命周期的状态占比很少能直接定位卡顿，量化分析应该从具体的业务区间切入。`sched.time_in_state` 模块提供了区间函数，能够把线程状态裁剪到指定的起止时间。下面的查询选取 SystemUI 主线程中最长的 `Choreographer#doFrame`，汇总该 Slice 内的线程状态分布：

```sql
INCLUDE PERFETTO MODULE sched.time_in_state;

WITH process_choice AS MATERIALIZED (
  SELECT upid
  FROM process
  WHERE name = 'com.android.systemui'
    AND (SELECT COUNT(*) FROM process
         WHERE name = 'com.android.systemui') = 1
), target AS MATERIALIZED (
  SELECT s.id AS slice_id, s.ts, s.dur, t.utid, p.upid
  FROM slice AS s
  JOIN thread_track AS tt ON s.track_id = tt.id
  JOIN thread AS t USING (utid)
  JOIN process_choice AS p USING (upid)
  WHERE t.is_main_thread
    AND s.name GLOB 'Choreographer#doFrame*'
    AND s.dur > 0
  ORDER BY s.dur DESC, s.ts, s.id
  LIMIT 1
), states AS MATERIALIZED (
  SELECT x.state, x.io_wait, x.blocked_function, x.dur
  FROM target
  JOIN sched_time_in_state_for_thread_in_interval(
    target.ts, target.dur, target.utid
  ) AS x
), coverage AS (
  SELECT target.*,
    COALESCE((SELECT SUM(dur) FROM states), 0) AS observed_ns
  FROM target
)
SELECT
  c.upid, c.utid, c.slice_id,
  ROUND(c.dur / 1e6, 3) AS window_ms,
  ROUND(c.observed_ns / 1e6, 3) AS observed_ms,
  ROUND((c.dur - c.observed_ns) / 1e6, 3) AS unobserved_ms,
  x.state, x.io_wait, x.blocked_function,
  ROUND(x.dur / 1e6, 3) AS state_ms
FROM coverage AS c
LEFT JOIN states AS x ON TRUE
ORDER BY x.dur DESC, x.state, x.io_wait, x.blocked_function;

```

`MATERIALIZED` 让 Trace Processor 求值并复用公共表表达式，`GLOB` 则按通配符匹配名称。该示例只在包名恰好对应唯一 `upid` 时选取最长且已闭合的候选 Slice；当同名进程实例超过一个或没有匹配 Slice 时返回空结果，此时应先确认现场实例，把 `process_choice` 替换为精确的 `upid` 条件。输出保留的 `slice_id` 和 `utid` 便于后续回查；同时要注意，最长的 `doFrame` 只是分析起点，距离真正影响用户体验的最差帧还差一层业务筛选。


该函数按半开区间 `[ts, ts + dur)` 裁剪，只累计正时长且已闭合的状态。`observed_ms` 代表这些已知状态的总覆盖时长，`unobserved_ms` 则是业务窗口减去已覆盖部分，未闭合尾部或数据缺口都会留在这个未知部分里。目标区间存在但没有任何已知状态时，查询仍会保留一行且 `state_ms` 为 NULL——这行只表示“没有观测到”，还不能据此得出某状态耗时为零的结论。一旦出现覆盖时长超过窗口、负的未知值或明显断裂，应先排查输入数据和区间重叠，在修正之前这组数字算不上有效占比。


在 Android 12 及以上版本中，可以先从 FrameTimeline 中锁定目标进程、Layer、Actual / Expected 的 token 与完整区间，再按截止超时与 jank 分类筛选帧。需要注意，表内 row id、应用 token 和 display token 属于三个不同的标识，统称为 `frame_id` 会混淆对象边界。把选定窗口及明确的目标 `utid` 传入状态函数，得到的是该线程在此窗口内的状态分解，而 GPU 与 SurfaceFlinger 侧的整帧归因仍需另行追踪。此外，该 tag 下的这些区间函数面向少量窗口，如果要批量分析大量 Slice，应改用 `slices.time_in_state` 等批量标准库。

<!-- gracker-diagram: ed14-03-window-identity-and-state-coverage -->
![先选唯一业务对象，再裁状态覆盖并报告未知](../../assets/diagrams/ch14/ed14-03-window-identity-and-state-coverage.png)

图：上述 SQL 仅在同名候选进程恰有唯一 `upid` 时继续，选取正闭合的最长 `doFrame` 并按 `dur`/`ts`/`id` 稳定排序，保留 `slice_id` 与 `utid`（最长 `doFrame` 仅作为候选，不等同于最差帧）。FrameTimeline 则另按 Actual/Expected、进程 layer、完整区间与 token 身份选帧，其中 row id、app token 与 display token 不可互换，GPU/SF 需另线关联。针对同一线程的半开窗口，仅裁剪 `dur > 0` 的闭合状态：`known` 来自 `observed` 正区间和，`unknown = 窗口 - 覆盖`（非已知状态）。目标存在但无状态时通过 `LEFT JOIN` 保留一行且 `state_ms` 为 NULL 而非 0；若覆盖超窗或 `unknown` 为负，需先排查重叠与输入错误。标准库及批量函数各按当前版本 schema 使用。

### 从状态走到修改点

| 区间特征 | 下一组证据 | 可以形成的结论 |
| --- | --- | --- |
| Running 为主 | Slice、用户态/内核态调用栈、CPU capacity/freq（相对容量 / 频率）、IRQ | 哪段执行或中断贡献 CPU 时间 |
| `R` 为主 | waker、同 CPU 运行者、调度类、cpuset/affinity（CPU 集合 / 亲和性）、CPU 在线状态 | 唤醒后为什么未及时运行 |
| `R+` 为主 | 切出后的任务、优先级、实时与 IRQ 活动 | 哪类抢占与 deadline 重叠 |
| `S` 为主 | 阻塞栈、waker、Binder、锁、Flow、定时器 | 等待条件由谁满足 |
| `D` 为主 | `io_wait`、`blocked_function`、页故障、回收、块设备、驱动 | 不可中断等待发生在哪个内核路径 |
| IRQ / SoftIRQ 高 | 中断名称、CPU、设备驱动、业务时间范围 | 中断处理占用了多少关键区间 |

做完状态分解后，还要回到实际产出。状态本身只是分析入口；一份可靠的结论至少应包含业务区间、`upid` / `utid`、状态持续时间、至少一种能够解释根因的独立旁证，以及修改前后的同条件对照。


## 14.3.10 常见误读

### “线程 Running 占比高，所以它有性能故障”

Running 只表示线程被调度在 CPU 上运行。仍要核对它是否位于关键路径、执行内容能否精简，以及 IRQ 是否占据了其中一部分；例如后台吞吐任务出现较高的 CPU 使用率，可能符合设计预期。

### “Runnable 长就是调度器选错”

Runnable 时长只是观测到的排队结果。系统负载、调度类、优先级、亲和性、cpuset、CPU 容量、热限制、带宽控制和唤醒放置都可能贡献延迟。看到界面上有空闲 CPU 也不能直接判定调度器失误，因为目标线程未必被允许迁移过去。

### “`R+` 就是某条高优先级线程抢占”

`R+` 只记录了这次切出带有抢占标志。至于具体是谁抢占的、因何抢占，还需检查同一 CPU 上随后运行的任务、调度类与优先级。

### “Sleeping 不消耗 CPU，所以不影响性能”

空闲线程处于 Sleeping 很正常，但关键路径上的 Sleeping 会直接拉长墙钟时间，必须顺着等待条件、唤醒者以及唤醒后的 Runnable 延迟继续深挖。

### “D 或 `io_wait = 1` 就是应用磁盘 I/O”

D 状态涵盖多种不可中断等待，`in_iowait` 也只是内核记账标志。落到应用层归因时，仍要依赖调用栈、页故障、文件系统、块设备或驱动事件来坐实。

### “把各进程 CPU 利用率相加后应小于 100%”

如果以分析窗口的墙钟时长作为分母，多线程进程并行运行时 CPU 利用率完全可以超过 100%；而单条线程在有效且不重叠的调度记录中，最多只能贡献一份该窗口的 CPU 时间。当在线 CPU 数恒定时，全系统在这个口径下的理论上限是 CPU 数乘以 100%；在线核心数动态变化时，上限则是窗口内平均在线 CPU 数乘以 100%。若要报告占设备可用 CPU 时间的比例，应改用窗口内在线 CPU 时间的积分作为分母。按核秒归一化与按异构 CPU capacity 加权属于两种不同口径，因此报告中必须写明窗口、统计对象、是否包含 IRQ、分母定义以及是否做容量加权，或者直接给出原始 CPU 时间。

<!-- gracker-diagram: ch14-03-40-cpu-percent-denominator -->
![CPU 百分比先说明对象与分母](../../assets/diagrams/ch14/ch14-03-40-cpu-percent-denominator.png)

图：按墙钟归一化时，多线程进程可超过 100%；按在线核秒或容量加权属于不同口径。单线程没有并行的放大通道；在线数变化时需积分计算，异构 capacity 加权则须另行声明。

## 参考资料

- [Perfetto：CPU Scheduling events](https://perfetto.dev/docs/data-sources/cpu-scheduling)
- [Perfetto：用调度事件和调用栈分析阻塞](https://perfetto.dev/docs/case-studies/scheduling-blockages)
- [Android 17 `ThreadStateTracker` 源码](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/importers/common/thread_state_tracker.cc)
- [Android 17 Ftrace Parser 源码](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/importers/ftrace/ftrace_parser.cc)
- [Android 17 `thread_state` 表定义](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/tables/sched_tables.py)
- [Android 17 `sched.latency` 标准库](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/sched/latency.sql)
- [Android 17 `sched.time_in_state` 标准库](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/sched/time_in_state.sql)
- [Android 17 `FtraceConfig` 源码](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/protos/perfetto/config/ftrace/ftrace_config.proto)
- [Android 17 / Linux 6.18 `TASK_*` 定义](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/linux/sched.h)
- [Android 17 / Linux 6.18 调度 Tracepoint 定义](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/trace/events/sched.h)
- [Android 17 / Linux 6.18 调度器主流程](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/kernel/sched/core.c)
- [Android 17 任务状态编码](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/types/task_state.cc)
- [Android 17 采集错误统计](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/storage/stats.h)
- [Android 17 内核符号读取](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/kallsyms/lazy_kernel_symbolizer.cc)
- [Android 17 紧凑调度事件导入](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/importers/ftrace/ftrace_sched_event_tracker.cc)
- [Android 17 Runnable 标准库](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/sched/runnable.sql)
- [高爷：Android Perfetto 系列 9，CPU 信息解读](https://www.androidperformance.com/2025/11/12/Android-Perfetto-09-CPU/)
- [高爷：Systrace Runnable 分析](https://www.androidperformance.com/2022/01/21/android-systrace-cpu-state-runnable/)
- [高爷：Systrace Running 分析](https://www.androidperformance.com/2022/03/13/android-systrace-cpu-state-running/)
- [高爷：Systrace Sleep 与 Uninterruptible Sleep 分析](https://www.androidperformance.com/2022/03/13/android-systrace-cpu-state-sleep/)

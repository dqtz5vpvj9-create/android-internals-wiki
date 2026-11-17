---
title: Perfetto 指标自动化与分析平台
chapter: '14.4'
section: '14.4'
applicable_versions: Android 8.0 (API 26) - Android 17 (API 37)
last_verified: '2026-10-25'
last_verified_against: Android 17 / API 37 / android-17.0.0_r1 (Perfetto ece66975738007dd0978b911d8a2077e49b8f31e); Perfetto Trace Processor v57.2-da1d152cf; android17-6.18-2026-06_r6; perfetto.dev (2026-10-22)
last_source_verified_at: '2026-10-25'
last_idle_audit_at: '2026-10-22'
confidence: medium
sources:
- type: official
  path: https://android.googlesource.com/platform/external/perfetto/+/android-17.0.0_r1/
- type: official
  path: https://android.googlesource.com/platform/system/core/+/android-17.0.0_r1/libcutils/include/cutils/trace.h
- type: official
  path: https://perfetto.dev/docs/analysis/trace-summary
- type: official
  path: https://perfetto.dev/docs/analysis/metrics
- type: official
  path: https://android.googlesource.com/platform/external/perfetto/+/android-17.0.0_r1/protos/perfetto/trace_summary/file.proto
- type: official
  path: https://github.com/google/perfetto/blob/v57.2/src/trace_processor/tables/metadata_tables.py
- type: official
  path: https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/core/java/android/os/Trace.java
- type: official
  path: https://perfetto.dev/docs/analysis/trace-processor-python
- type: official
  path: https://perfetto.dev/docs/analysis/batch-trace-processor
- type: official
  path: https://perfetto.dev/docs/visualization/ui-automation
- type: official
  path: https://perfetto.dev/docs/visualization/commands-automation-reference
- type: official
  path: https://perfetto.dev/docs/visualization/extension-servers
- type: official
  path: https://perfetto.dev/docs/instrumentation/tracing-sdk
- type: official
  path: https://perfetto.dev/docs/getting-started/atrace
- type: official
  path: https://developer.android.com/topic/performance/benchmarking/benchmarking-in-ci
- type: official
  path: https://developer.android.com/topic/performance/measuring-performance
- type: blog
  path: rss-tech/2026-05-18_RSS_886623bf54.md
- type: github
  path: https://github.com/Gracker/SmartPerfetto
- type: internal
  path: src/part3-tools/ch14-perfetto/07-perfetto-sql-span-join-jank-cuj.md
- type: internal
  path: src/part3-tools/ch14-perfetto/11-agent-perfetto-analysis-protocol.md
- type: internal
  path: src/part3-tools/ch14-perfetto/12-perfetto-sdk-in-app-tracing.md
- type: internal
  path: src/part5-app/ch26-observability/01-app-observability-performance-collection.md
- type: internal
  path: src/part5-app/ch26-observability/04-ab-testing-regression.md
tags:
  - perfetto
  - smartperfetto
  - trace-analysis
  - ai-assistant
  - sql-guardrail
  - observability
status: finalized
related_chapters:
- '14.2'
- '14.7'
- '14.11'
- '14.12'
- '26.1'
- '26.4'
- '26.6'
last_consolidated_at: '2026-08-24'
consolidated_from:
- src/part3-tools/ch14-perfetto/06-advanced-usage.md
- src/part3-tools/ch14-perfetto/17-smartperfetto-trace-analysis-platform.md
---

# Perfetto 指标自动化与分析平台

单份 Trace 足以支撑一次现场诊断，但要把分析能力沉淀成可复用的查询、结构化指标、批量回归与持续集成，首先得解决跨人员、跨构建与跨日期的一致性问题：同一条分析规则应始终产出语义一致的结果，异常发生时也要留得下足够的原始证据。

> 源码基线：Android 17 / API 37 / `android-17.0.0_r1`；`external/perfetto` 指向提交 `ece66975738007dd0978b911d8a2077e49b8f31e`；内核 `android17-6.18-2026-06_r6`，ftrace（Linux 内核跟踪机制）采集行为以它为准核对。实际设备可能使用其他内核分支。

开展自动化之前，先明确一条核心原则：自动化分析把 Trace Processor SQL、指标规格与设备批处理组合成流水线，它的产出必须经得起复查——同一条规则，换人、换机器、隔一周再跑，结果依然要对得上。由于主机侧的 Perfetto UI、Python 包和 Trace Processor 独立于设备系统升级，流水线还必须把主机工具版本一并锁定。在这两重前提之下，查询版本、输入质量、证据出处与回归基线，远比“跑出一个分数”更关键。

## SQL Metric、批处理与回归比较

要把一条临时能跑的 SQL 变成团队长期依赖的工程资产，需要依次解决几件事：选对复用机制、定义指标和宏、接入 Python 批处理与持续集成门禁，再配套埋点规范与团队知识库。贯穿这些步骤的是同一个要求——换人、换机器、升级工具后，数值语义依然保持可比。

### 四种可复用能力

Perfetto 提供了四套名称相近但用途各异的机制。选错层次后，查询虽然仍能跑通，后续却难以长期维护，因此先厘清各自的分工：

| 机制 | 输入 | 输出 | 适用位置 |
|---|---|---|---|
| PerfettoSQL 标准库 | `INCLUDE PERFETTO MODULE` | 稳定表、视图和函数 | 单份 Trace 查询的公共语义层 |
| Trace Summarization | 指标规格 + 标准库或 SQL | 统一的 `TraceSummary` protobuf | 新建自动化指标和跨 Trace 分析 |
| 旧版 v1 指标 | SQL + 自定义 protobuf | `TraceMetrics` protobuf | 维护已有指标，或兼容现有读取服务 |
| UI 命令宏 | JSON 命令序列 | 工作区、查询页、调试轨道等界面状态 | 重复执行人工诊断步骤 |

表中的 protobuf（Protocol Buffers）是一种带字段类型的结构化消息格式。所谓输出契约，指的是字段名、类型、单位和语义都能被消费端稳定依赖；至于文件本身是否采用二进制编码，反而在其次。

PerfettoSQL 还提供 `CREATE PERFETTO MACRO`，用于在查询执行前展开表达式或子查询。它与 UI 设置里的命令宏属于两套互不相通的机制，配置既不共享，执行方式也完全不同。


### 自定义指标：新项目从 Trace Summarization 开始

#### v1 指标的现状与选择顺序

Android 17 标签与 v57.2 命令帮助均已将 v1 指标标为 soft deprecated：现有指标与命令行兼容接口可以继续运行，但官方不再为这套体系新增功能或指标。新项目应直接选用 Trace Summarization。两者的 SQL 表达能力相近，输出契约的差异却很大，选型时主要看消费端与维护成本：

v1 指标要求每个团队维护独立的输出 protobuf（消息类型由 `.proto` 文件定义，textproto 是消息实例的文本表示）；而 Trace Summarization 统一输出 `TraceSummary`，并在规格中显式声明维度（进程名、场景等分组字段）、数值列、单位和极性（说明数值升高还是降低更优）。有了统一的数据结构，批量处理、仪表板与长期性能回归追踪才更容易对接。

建议按以下优先级选型：

1. 先在标准库中查找已有模块，核实表的语义与适用版本；
2. 用 Trace Summarization 编写新指标；
3. 标准库存在缺口时，在仓库内补充自定义 PerfettoSQL 包；
4. 仅当已有消费服务强依赖 `TraceMetrics` 时，才继续维护或增改 v1 指标。

#### Trace Summarization 的完整示例

下面看一个具体规格：按进程计算 `RSS + Swap` 的持续时间加权均值（RSS，Resident Set Size，指进程当前驻留在物理内存中的页面量；Swap 指换出到交换区的页面量）。规格采用可读文本形式的 textproto 编写，直接引用官方 `linux.memory.process` 模块并声明字节单位：

```textproto
metric_spec {
  id: "memory_per_process"
  dimensions: "upid"
  dimensions: "process_name"
  value: "avg_rss_and_swap"
  unit: BYTES
  query {
    table {
      table_name: "memory_rss_and_swap_per_process"
    }
    referenced_modules: "linux.memory.process"
    group_by {
      column_names: "upid"
      column_names: "process_name"
      aggregates {
        column_name: "rss_and_swap"
        op: DURATION_WEIGHTED_MEAN
        result_column_name: "avg_rss_and_swap"
      }
    }
  }
}
```

`DURATION_WEIGHTED_MEAN` 会按每个样本覆盖的时间长度加权，非常适合由计数器样本还原出的区间数据。例如一个数值保持了 9 秒、另一个只保持了 1 秒，前者就应当获得 9 倍的权重；普通算术平均会抹平这层差异。

<!-- gracker-diagram: ch14-04-02-weighted-intervals -->
![持续时间加权与普通样本平均的区别](../../assets/diagrams/ch14/ch14-04-02-weighted-intervals.png)

图：以区间持续时间作为权重，计算 `Σ(value × dur) / Σ(dur)`。9∶1 为教学示例；缺失区间与 NULL 覆盖需另行检查。

这份规格同时按 `upid` 与名称分组，防止同名进程、进程重启或 PID 复用导致统计混叠；需要注意 `upid` 只在当前 Trace 内有效，跨 Trace 对齐仍要依赖业务身份。这里计算的是模块内可用内存区间的 `Σ(value × dur) / Σ(dur)`，未限定到特定业务窗口，采样缺失的区间也未纳入统计。在固定模块中，anon/file RSS 缺失会传播为 NULL，而 shmem/swap 按模块约定可能补零；上线前应检查覆盖时间与数据源，先分辨每个缺项的含义，不要把所有缺项一概补成零。

可通过子命令接口执行这份规格：

```bash
trace_processor summarize \
  --metrics-v2 memory_per_process \
  trace.perfetto-trace \
  spec.textproto
```

命令输出 `TraceSummary`，结果存放在 `metric_bundles`（结果包列表）中，每个 bundle 可保存一组共享维度结构的指标。传入 `--format binary` 可输出二进制 protobuf，默认的 textproto 则更便于人工核查。v57.2 仍完整兼容旧式 `--summary` 参数，但新脚本建议直接采用子命令接口并固定二进制版本。


同一份规格也可以通过 Python 调用：

```python
from pathlib import Path
from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig

config = TraceProcessorConfig(bin_path="tools/perfetto/trace_processor")
spec_text = Path("spec.textproto").read_text(encoding="utf-8")

with TraceProcessor(trace="trace.perfetto-trace", config=config) as tp:
    summary = tp.trace_summary(
        specs=[spec_text],
        metric_ids=["memory_per_process"],
    )
    print(summary)
```

`metric_ids` 用于只执行本次所需的指标 ID。省略该参数时，API 会运行规格中的全部指标；对于大型规格库，显式指定 ID 可以避免跑出无关查询。

#### 存量 v1 指标：SQL 与 protobuf 的约定

如果团队已有读取 `TraceMetrics` 的线上服务，v1 指标仍可继续维护。下面以 CPU 运行时间为例展示完整的目录与命名约定，同时避开容易随版本变动的不稳定时间片名称（如 `activityStart`、`FirstFrame`）。

存量指标可以把两个同名文件放进同一目录：

```text
legacy_metric/
├── top_five_processes.proto
└── top_five_processes.sql
```

Trace Processor 会根据传入的 SQL 路径查找同目录、同基本名的 protobuf 文件，并将自定义消息注册为 `TraceMetrics` 的扩展字段。扩展字段是 protobuf 在既有根消息上追加自定义结果的机制，内置指标会原样保留。

输出 protobuf 定义如下：

```protobuf
syntax = "proto2";

package perfetto.protos;

import "protos/perfetto/metrics/metrics.proto";

message ProcessCpuInfo {
  optional string process_name = 1;
  optional int64 cpu_time_ms = 2;
  optional uint32 scheduled_thread_count = 3;
  optional int64 upid = 4;
}

message TopFiveProcesses {
  repeated ProcessCpuInfo process = 1;
}

extend TraceMetrics {
  optional TopFiveProcesses top_five_processes = 450;
}
```

字段号 `450` 取自 Perfetto 为本地开发预留的 `450–500` 区间。字段号是 protobuf 在编码格式中识别字段的数字标识，冲突会导致解析失败，因此团队内部仍需做好登记；扩展字段名 `top_five_processes` 同时决定了 SQL 文件名与输出视图名。

<!-- gracker-diagram: ch14-04-04-legacy-contract -->
![v1 的文件、扩展字段与输出视图约定](../../assets/diagrams/ch14/ch14-04-04-legacy-contract.png)

图：SQL 与同名 proto 注册自定义字段，由规定名称的输出视图生成根结果。450–500 为本地开发区间，团队仍需登记字段号以免冲突。

对应的 SQL 统计 `sched` 中已闭合的调度时间片：

```sql
CREATE PERFETTO VIEW top_five_processes_by_cpu AS
SELECT
  p.upid,
  p.name AS process_name,
  CAST(SUM(s.dur) / 1e6 AS INT64) AS cpu_time_ms,
  COUNT(DISTINCT t.utid) AS scheduled_thread_count
FROM sched AS s
JOIN thread AS t USING (utid)
JOIN process AS p USING (upid)
WHERE s.dur > 0
  AND t.is_idle = 0
GROUP BY p.upid, p.name
ORDER BY SUM(s.dur) DESC, p.upid
LIMIT 5;

CREATE PERFETTO VIEW top_five_processes_output AS
SELECT TopFiveProcesses(
  'process',
  (
    SELECT RepeatedField(
      ProcessCpuInfo(
        'upid', upid,
        'process_name', process_name,
        'cpu_time_ms', cpu_time_ms,
        'scheduled_thread_count', scheduled_thread_count
      )
    )
    FROM top_five_processes_by_cpu
  )
);
```

`upid` 是 Perfetto 在当前 Trace 内分配的进程唯一标识，按 `upid` 分组能避免系统 PID 复用与同名进程合并的问题。`thread.is_idle` 用于标识内核空闲任务（Linux 上 PID 为 0），示例中通过 `t.is_idle = 0` 将其排除，以免把 CPU 空闲时间计入进程消耗榜。

榜单按原始纳秒总量排序，`cpu_time_ms` 仅在输出时截断为整数毫秒；由于多核并行运行的 CPU 时间会相加，总量可能大于 Trace 的墙钟时长。`scheduled_thread_count` 统计的是 Trace 中出现过正时长、已闭合 `sched` 时间片的非空闲线程，与进程创建过的全部线程数属于不同口径；`top_five_processes_output` 必须遵循 `{TraceMetrics 扩展字段名}_output` 的命名格式，Trace Processor 依靠这个约定查找根消息。

<!-- gracker-diagram: ch14-04-05-cpu-ranking -->
![CPU 榜单保留实例与排序精度](../../assets/diagrams/ch14/ch14-04-05-cpu-ranking.png)

图：闭合调度时间按实例求和，先以原始精度排序，再输出展示值。多核 CPU 时间相加可超过墙钟时长；调度线程数不等同于进程全部线程数。

命令行提供两套等价写法，推荐使用参数结构更直观的新子命令接口：

```bash
trace_processor metrics \
  --run legacy_metric/top_five_processes.sql \
  --output json \
  trace.perfetto-trace
```

旧脚本中的 `--run-metrics legacy_metric/top_five_processes.sql` 与 `--metrics-output=json` 仍由兼容接口支持。`--metric-extension DISK_PATH@VIRTUAL_PATH` 可把磁盘目录映射到 Trace Processor 内部的指标路径；若要挂到虚拟根路径 `/` 并覆盖内置指标，工具还要求同时传入 `--dev`。

`--dev` 开启的是可能随时变动的本地开发特性，生产流水线应默认保持关闭。每次升级主机工具时，应先在固定测试 Trace 上对比新旧输出，确认无误后再更新锁定版本。

#### 指标空结果与采集条件

查询执行成功但返回空表，只说明没有匹配到记录，背后的原因可能是场景未发生，也可能是采集或过滤条件不匹配。工程上必须把测得零、SQL NULL、空表与执行失败这四种状态严格分开，常见排查项包括：

- 采集配置未启用指标依赖的数据源；
- 录制在目标事件发生前就已经结束；
- 目标进程未列入 `atrace_apps`；
- 工具版本缺少规格引用的标准库模块（通常会直接报错失败，应保留错误信息）；
- `stats` 数据质量表已记录丢包、截断或时钟异常；
- 进程名、包名或启动模式与查询条件不一致。

因此，每份指标规格都应写明依赖的数据源、支持的系统版本、单位、极性、空值含义及已知失效场景。CI（Continuous Integration，持续集成）中遵循同一条原则：空值与零分开处理，只有真正测得的数值零才算作 0。

<!-- gracker-diagram: ch14-04-06-result-states -->
![零、NULL、空表与执行失败分开处理](../../assets/diagrams/ch14/ch14-04-06-result-states.png)

图：先保留查询状态和数值缺失含义，再决定是否纳入对比。查询成功返回空表仅说明无匹配记录，不能推导出“系统没有问题”。

### 两类宏：SQL 复用与 UI 自动化

#### PerfettoSQL 宏

SQL 宏适合复用表、子查询或表达式片段：常规的标量计算继续用普通函数即可，宏的价值在于能把表名或列名作为参数传入。

下面的宏从任意兼容表中筛选出超过指定时长的时间片：

```sql
CREATE PERFETTO MACRO long_slices(
  input TableOrSubquery,
  min_dur Expr
)
RETURNS TableOrSubquery AS
(
  SELECT ts, dur, name, track_id
  FROM $input
  WHERE dur >= 0 AND dur >= $min_dur
);

SELECT ts, dur, name
FROM long_slices!(slice, 8 * 1000 * 1000)
ORDER BY dur DESC
LIMIT 20;
```

`TableOrSubquery` 与 `Expr` 分别是表示表/子查询和普通 SQL 表达式的宏参数类型；调用宏时以 `!` 结尾，参数会在查询真正执行前展开。示例中的 8 ms 仅作过滤条件演示，实际判断一帧是否超时，仍要对比该帧自身的显示期限。


供多人协作使用的 SQL 逻辑，建议从临时查询页抽离出来，组织成自定义 SQL 包，并通过 `TraceProcessorConfig.add_sql_packages` 或命令行 `--add-sql-package` 注册。包名相当于模块命名空间，避免团队模块与标准库或其他团队重名；包名、查询接口与测试 Trace 都应纳入版本控制。

#### UI 命令宏

Perfetto UI 的宏是一组命名的稳定命令序列。配置入口位于 `Settings > Macros`，格式为 JSON 数组，可由工程师在命令面板手动触发，也能由启动命令自动引用。

下面的宏会先折叠所有现有轨道、固定 CPU 轨道，再为所有进程主线程中超过 8 ms 的时间片生成分组调试轨道：

```json
[
  {
    "id": "user.myteam.LongMainThreadSlices",
    "name": "Long Main-thread Slices",
    "run": [
      {
        "id": "dev.perfetto.CollapseTracksByRegex",
        "args": [".*"]
      },
      {
        "id": "dev.perfetto.PinTracksByRegex",
        "args": [".*CPU \\d+$"]
      },
      {
        "id": "dev.perfetto.AddDebugSliceTrackWithPivot",
        "args": [
          "SELECT s.ts, s.dur, s.name, printf('%s [upid=%d]', COALESCE(p.name, '[unnamed]'), p.upid) AS process_key FROM slice AS s JOIN thread_track AS tt ON s.track_id = tt.id JOIN thread AS t USING (utid) JOIN process AS p USING (upid) WHERE t.tid = p.pid AND s.dur >= 8000000",
          "process_key",
          "Long main-thread slices"
        ]
      }
    ]
  }
]
```

`AddDebugSliceTrackWithPivot` 要求查询返回 `ts`、`dur`、`name` 与分组列，其中 Pivot 表示按分组列的不同取值拆出多条调试轨道（示例用包含 `upid` 的 `process_key` 区分同一 Trace 内的不同进程实例）。执行语义上，固定版本 UI 的 `registerMacro()` 会逐条 `await runCommand()` 且未做逐条异常捕获，因此某条命令抛错或返回 rejected Promise 时整个宏会中断，只有命令内部自行处理错误并正常返回时才会继续执行。共享前建议用典型 Trace 测试每一步及失败分支，且命令 ID 应选自 Perfetto 的稳定自动化参考，避免依赖插件私有命令。

<!-- gracker-diagram: ed14-04-sql-and-ui-macro-execution -->
![SQL 宏在查询前展开，UI 宏逐条执行命令](../../assets/diagrams/ch14/ed14-04-sql-and-ui-macro-execution.png)

图：SQL 宏通过 `CREATE PERFETTO MACRO` 接收 `TableOrSubquery` 与 `Expr`，调用带 `!` 并在查询执行前展开；示例中的 `dur >= 0` 和 8 ms 仅作过滤条件演示，不代表帧 deadline。UI 宏为 JSON 命令序列，在 `registerMacro()` 中逐条 `await runCommand()`，抛错或 rejected 时中断，命令内部吞错并正常返回则可继续；Pivot 需返回 `ts`/`dur`/`name`/分组列，以含 `upid` 的键区分进程实例。SQL 包与 UI 扩展共享均须固定版本、反向域名命名空间与稳定命令 ID，两者机制和配置互不互通。

宏可以保存在本地设置中。个人使用时把 JSON 存入仓库并附上安装说明即可；在固定录制流程中，还可以通过 `record_android_trace --ui-startup-commands`、带参数的深链接或浏览器窗口消息接口 `postMessage` 注入允许的启动命令。

团队多人共享更适合部署 Perfetto 扩展服务器。当前接口支持分发宏、SQL 模块与 protobuf descriptor（描述字段结构的类型信息），兼容 GitHub 仓库或带认证的 HTTPS 端点。服务器需声明反向域名命名空间（如 `com.example.perfetto`），宏 ID 与 SQL 模块名必须以此为前缀以防重名。扩展加载失败时 UI 仍会正常打开 Trace，因此团队要把服务端清单、源码和发布版本纳入版本控制，确保分析结论能回溯到固定提交。

#### 单轨迹仪表板与跨轨迹仪表板

Perfetto UI 擅长针对单份轨迹做交互式诊断，工作区、查询页和调试轨道可以组成单轨迹仪表板；而跨构建的长期趋势则需要交给后面的指标文件与时序存储来承载。

跨 Trace 仪表板应消费 Trace Summarization 输出或 Benchmark JSON（AndroidX Benchmark 生成的结构化测量报告）：

| 层次 | 保存内容 | 回答的问题 |
|---|---|---|
| Perfetto UI | 宏、工作区、调试轨道、查询页 | 这次慢在哪里 |
| 指标文件 | `TraceSummary`、Benchmark JSON、工具版本 | 这次测到了什么 |
| 时序存储 | 按时间保存构建、设备、场景、样本与指标 | 何时开始变化 |
| 可视化与告警 | 分位数、基线区间、Trace 链接 | 是否需要人工复核 |

这张表只搭出了骨架，真正发挥作用靠的是回溯路径：趋势图上的每一个异常拐点，都必须能跳回原始 Trace、构建信息与指标规格版本。分位数反映样本排序后的位置（如 P50 即中位数），保存聚合值的同时必须保留回溯路径，否则丢失了根因线索。

<!-- gracker-diagram: ch14-04-09-trend-backtrace -->
![趋势异常点回查原始测量与 Trace](../../assets/diagrams/ch14/ch14-04-09-trend-backtrace.png)

图：从趋势点沿样本、规格和原始轨迹回查，才能解释性能变化。P50 / P95 等聚合值本身不保留每次迭代的完整因果线索。

### Trace Processor Python API

#### 固定二进制与工具版本记录

Python 侧的接入入口是 `pip install perfetto`。客户端默认按照包内 prebuilt manifest 下载匹配的 Trace Processor，也支持显式指定二进制路径；需要注意 Python 包版本号与原生二进制版本号并不一定相同——例如复核所用的 `perfetto==0.57.2` 包内清单固定的是原生 v56.1，实际执行哪个版本取决于是否显式指定二进制。文中的 `tools/perfetto/trace_processor` 应放置并校验所选的 v57.2 二进制；运行 Pandas 示例还需安装 `pandas`。在 CI（持续集成）环境中，更稳妥的做法是同时锁定 Python 依赖版本与原生二进制摘要（用于确认文件内容未变的哈希值），并将版本号和摘要一并写入报告。


下面的示例使用指定二进制查询 `slice` 表中最长的正时长事件：

```python
from perfetto.trace_processor import TraceProcessor, TraceProcessorConfig

config = TraceProcessorConfig(
    bin_path="tools/perfetto/trace_processor",
)

with TraceProcessor(
    trace="trace.perfetto-trace",
    config=config,
) as tp:
    rows = tp.query("""
        SELECT ts, dur, name
        FROM slice
        WHERE dur > 0
        ORDER BY dur DESC
        LIMIT 20
    """)
    frame = rows.as_pandas_dataframe()
    print(frame.to_string(index=False))
```

`with` 上下文管理器会在代码块退出时关闭 Trace Processor 子进程。`as_pandas_dataframe()` 会把查询结果复制成 Pandas DataFrame（带列名的内存表格）以方便后续统计；如果只需逐行处理少量结果，直接遍历 `rows` 可以省去在内存中再保留一份表格数据的开销。

#### 批量查询

`BatchTraceProcessor` 会为每份 Trace 启动独立实例并并行执行同一查询：`query()` 返回与各份 Trace 对应的结果表列表，`query_and_flatten()` 则把这些表纵向合并，并由 resolver（把 URI 或路径解析成数据来源的组件）补上来源列。

下面的代码统计每份轨迹中的 `slice` 行数及正时长切片累计时长。由于 `slice` 包含线程、设备、IRQ、GPU 等各类轨道，嵌套和并行区间会重复覆盖同一段墙钟时间，这里的累加值只用于评估数据规模，CPU 消耗、互斥业务耗时或 Trace 时长应按各自口径另行统计：

```python
from glob import glob
from perfetto.trace_processor import TraceProcessorConfig
from perfetto.batch_trace_processor.api import (
    BatchTraceProcessor, BatchTraceProcessorConfig,
)

trace_paths = sorted(glob("traces/*.perfetto-trace"))

config = BatchTraceProcessorConfig(
    tp_config=TraceProcessorConfig(bin_path="tools/perfetto/trace_processor"),
)

with BatchTraceProcessor(trace_paths, config=config) as batch:
    summary = batch.query_and_flatten("""
        SELECT
          COUNT(*) AS slice_count,
          SUM(CASE WHEN dur > 0 THEN dur ELSE 0 END) AS total_slice_dur_ns
        FROM slice
    """)
    print(summary)
```

<!-- gracker-diagram: ch14-04-11-slice-sum-overlap -->
![Slice 累计时长与墙钟、CPU 时间是不同的量](../../assets/diagrams/ch14/ch14-04-11-slice-sum-overlap.png)

图：`slice` 是通用事件视图，嵌套与并行会重复覆盖相同墙钟时间。图中条长仅示意包含关系；`SUM(dur)` 不能直接当作业务独占耗时。

来源列的列名取决于所用的 Trace 地址 resolver，解析结果的代码应先确认实际列名，再引用 `source` 等字段名。需要留意内存模型：`BatchTraceProcessor` 会加载并保留本批所有 Trace 实例，worker 数量限制的只是加载与查询的并发度，驻留实例数并不受它限制。内存不足时应拆分输入批次，处理完并关闭一批实例后再加载下一批。单批规模与并发数需按 Trace 内容和主机内存实测，压缩文件体积仅供参考；官方文档给出的 `2 × 平均文件大小 × Trace 数量` 仅适合粗略估算起步，数据类型和压缩率会让实际占用明显偏离。

<!-- gracker-diagram: ch14-04-12-batch-memory -->
![批处理实例与结果合并的生命周期](../../assets/diagrams/ch14/ch14-04-12-batch-memory.png)

图：每份 Trace 各持有一个驻留实例，结果表再纵向合并。worker 限额不限制驻留实例总数；内存不足时需拆分输入批次。

当批量规模超出单机资源上限时，可以考虑 Bigtrace。它是分布式 Trace Processor 服务，借助 Kubernetes（容器集群编排系统）调度多个工作进程，适合已经具备对象存储和集群运维能力的团队；如果只是为了处理几十份 Trace 而引入 Bigtrace，运维成本通常会高于收益。

#### 远程 Trace Processor 服务

v57.2 与 Android 17 标签都已内置服务子命令。下面的命令在本机 9001 端口启动原生 Trace Processor，开放 RPC（Remote Procedure Call，远程过程调用）接口供 Perfetto UI 接入：

```bash
trace_processor server http --ip-address 127.0.0.1 --port 9001 trace.perfetto-trace
```

旧写法 `trace_processor --httpd trace.perfetto-trace` 在 v57.2 中仍完整支持。原生进程可以绕开浏览器 WebAssembly（浏览器内的沙箱二进制执行环境）的内存上限，但 Trace 解析后的内存占用仍可能远超文件本身大小。

`external/perfetto/src/trace_processor/rpc/` 中的 `Rpc` 负责 protobuf 编解码，HTTP、stdio 与 WebAssembly 桥接负责传输。Python 客户端已经封装好协议协商、分批响应和错误处理，业务脚本直接调用 Python API 或命令行接口即可，无需手动处理 `/rpc` 请求、分块传输或序列号管理。

<!-- gracker-diagram: ch14-04-13-native-rpc -->
![UI 经回环 RPC 访问原生 Trace Processor](../../assets/diagrams/ch14/ch14-04-13-native-rpc.png)

图：UI 或封装客户端把查询交给本机原生进程，Trace 数据驻留在主机。原生进程仍受主机内存限制；版本与 RPC 协议需成套验证。

服务应始终只监听回环地址（仅本机可访问的 `127.0.0.1` 或 `::1`）。由于 Trace 可能包含进程名、文件路径、埋点文本和业务标识，9001 端口应留在本地，避免暴露到共享网络。此外，当 UI 与服务器版本相差过大时可能出现 RPC 协议不匹配，升级时需成套验证。

### 把 Perfetto 放进持续集成

#### 测量值与诊断证据的分工

AndroidX Macrobenchmark 是在 Android 设备上重复执行启动、滚动等场景的基准测试库，它会输出 Benchmark JSON，并为每次测量保留一份 Perfetto Trace。持续集成中的门禁（根据测量结果自动裁决构建是否放行）适合拆成两层来用：

- 以 Benchmark JSON 作为门禁的主要数值来源；
- 用 Perfetto SQL 或 Trace Summarization 生成诊断指标，并归档异常样本的原始轨迹。


需要注意，不要随意从某个可能随版本变化的 Slice 名称重新计算启动时间，再去和 Macrobenchmark 的 `StartupTimingMetric` 混为一谈——系统升级或埋点名称微调后，两套口径之间很容易出现不易察觉的偏差。

#### 可复现的流水线

一条可靠的基准流水线至少应记录以下元数据：

1. 目标 APK（被测应用安装包）、测试 APK、代码提交与构建参数；
2. 真机序列号、机型、系统指纹（build fingerprint）、API 级别和电量状态；
3. 启动模式、编译模式（如无预编译、部分预编译或完整预编译）、场景参数和迭代次数；
4. Benchmark JSON、每次迭代的轨迹文件和测试日志；
5. Perfetto Python 包、Trace Processor 二进制版本与校验摘要；
6. 指标规格、SQL 包与门禁策略的版本。

官方文档不建议用模拟器数值代表真机表现。固定真机适合合入代码前的自动门禁，共享设备池则更适合趋势观察与夜间复测。对于低电量、可调试 APK 或未声明 `profileable`（允许性能分析）的 APK 这类 Macrobenchmark 配置异常，应逐项拦截处理；如果统一忽略，不同批次的测量条件就会失真。

以官方示例模块名为例，连接本地真机后可以运行整组基准：

```bash
./gradlew :macrobenchmark:connectedCheck
```

Gradle（Android 项目常用的构建系统）会把 Benchmark JSON 和每次迭代的 `.perfetto-trace` 复制到 `build/outputs/connected_android_test_additional_output/` 下；当前插件还会按测试变体、连接方式和设备继续细分出子目录（例如 `debugAndroidTest/connected/<device>/`），因此收集脚本必须递归扫描报告，若只把父目录当作唯一路径就会漏掉文件。

设备农场通常会把构建、安装、运行和拉取测试产物拆成独立阶段；无论运行在哪套基础设施上，指标本身的统计口径都必须保持一致。

#### 门禁阈值与设备噪声

看到“变慢 10%”或“p 值小于 0.05”这类经验数字时，先要问它在自己的设备池上是否成立（p 值源自假设检验，只有结合实验设计、样本量与预先选定的检验方法才有意义）。合理做法是在固定设备和固定构建条件下反复运行未改代码，摸清设备与场景自身的自然波动范围，再针对每个场景制定阈值与复测规则。

下面的脚本仅读取 Macrobenchmark JSON 中 `metrics.<指标>.runs` 的每次迭代标量（如非负、越低越好的启动耗时；像帧采样这样的 `sampledMetrics.<指标>.runs` 属于嵌套数组，需要单独设计聚合规则与实验单位）。脚本会先校验当前报告和基线的机型与系统指纹，再对比指定标量指标的中位数（样本排序后的中间值；基线指已批准用于对比的历史结果），阈值由调用方从版本库中的场景策略传入：

```python
#!/usr/bin/env python3
import argparse
import json
import math
import statistics
import sys
from pathlib import Path


def load_report(path, benchmark_name, metric_name):
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = [
        item for item in report["benchmarks"]
        if item["name"] == benchmark_name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"{path}: expected one benchmark named {benchmark_name!r}, "
            f"found {len(matches)}"
        )

    metric = matches[0]["metrics"][metric_name]
    values = metric["runs"]
    if not isinstance(values, list) or not values:
        raise ValueError(f"{path}: expected nonempty scalar runs")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or value < 0
        for value in values
    ):
        raise ValueError(f"{path}: samples must be finite nonnegative numbers")
    runs = [float(value) for value in values]
    return report["context"], runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--metric", required=True)
    parser.add_argument("--max-regression-ratio", required=True, type=float)
    args = parser.parse_args()
    if not math.isfinite(args.max_regression_ratio) or args.max_regression_ratio < 0:
        raise ValueError("threshold must be finite and nonnegative")

    current_context, current_runs = load_report(
        args.current, args.benchmark, args.metric
    )
    baseline_context, baseline_runs = load_report(
        args.baseline, args.benchmark, args.metric
    )

    current_build = current_context["build"]
    baseline_build = baseline_context["build"]
    for key in ("model", "fingerprint"):
        if current_build[key] != baseline_build[key]:
            raise ValueError(f"environment mismatch: build.{key}")

    current_median = statistics.median(current_runs)
    baseline_median = statistics.median(baseline_runs)
    if baseline_median <= 0:
        raise ValueError("baseline median must be positive")
    ratio = current_median / baseline_median - 1.0
    if not math.isfinite(ratio):
        raise ValueError("regression ratio is not finite")

    print(
        json.dumps(
            {
                "benchmark": args.benchmark,
                "metric": args.metric,
                "current_median": current_median,
                "baseline_median": baseline_median,
                "regression_ratio": ratio,
                "current_sample_count": len(current_runs),
                "baseline_sample_count": len(baseline_runs),
            },
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
    )
    return 2 if ratio > args.max_regression_ratio else 0


if __name__ == "__main__":
    sys.exit(main())
```

脚本本身不硬编码阈值，并拒绝空样本、非数值/非有限/负样本、非法阈值与零基线中位数；无效输入以非零状态失败，超过阈值返回 2，通过返回 0。业务要求的最小样本数、场景参数与编译模式校验应放在正式流水线中完成。比值计算适用于“数值越低越好”且基线中位数大于零的指标；对于基线为零、可能为负或方向相反的指标，需改用相应的判定规则。首次触发超限后，应在同一设备上复测，并将两轮报告与 Trace 一并提交评审。

<!-- gracker-diagram: ch14-04-15-finite-gate -->
![标量门禁先验证输入，再比较中位数](../../assets/diagrams/ch14/ch14-04-15-finite-gate.png)

图：只对有限非负标量与正基线中位数执行越低越好的回归比较。机型和指纹一致仍不足以证明条件一致，样本数、场景和编译模式需另行校验。

#### 门禁采集与深度诊断的分离

追加 ftrace 事件、堆采样或密集应用埋点本身就会改变系统开销。为了避免诊断开销污染日常测量数值，可以把门禁采集与深度诊断拆开：

- 常规门禁只采集 Macrobenchmark 所需的最小数据；
- 超过阈值后，基于同一提交复测并启用更详细的数据源；
- 诊断轨迹仅用于根因定位，不拿来替换原门禁样本；
- 每次变更采集配置都建立新的基线，避免把工具开销变化误判为产品性能变化。

这样既控制了日常门禁的测量扰动，一旦发生异常也能拿到调度、Binder、内存或渲染维度的详细线索。

<!-- gracker-diagram: ed14-04-gate-evidence-and-diagnostic-capture -->
![门禁用测量样本判定，详细复测补原因证据](../../assets/diagrams/ch14/ed14-04-gate-evidence-and-diagnostic-capture.png)

图：Macrobenchmark JSON 是主要门禁数值源，各次迭代的 Perfetto Trace 作为诊断证据，并同时保存 APK、设备、编译模式、场景、采集配置、toolchain 与策略等条件。自定义 Slice 重算应与 `StartupTimingMetric` 分开定义，避免混用。判定需基于设备自然波动与已批准阈值；首次超限后应在同设备、同提交下复测，更密集的数据源会改变采集开销，因此诊断样本不替换原样本，且变更采集配置后需重建基线。上述标量脚本仅处理 `metrics.<id>.runs`，嵌套结构的 `sampledMetrics` 需另行设计聚合逻辑。

### 自定义 Trace Point（埋点）

#### 选择平台 API 还是 Perfetto SDK

给应用或引擎加 Trace Point 前，需要先在平台 API 与 Perfetto SDK 之间作出选择。这里的 Trace Point 指代码主动写入 Trace 的应用或平台埋点，与 Linux 内核预定义的 Tracepoint 分属不同机制。按事件形态可分为三类：同步时间片是同一线程上有明确起止的工作，异步时间片可跨线程或跨回调配对，计数器记录随时间变化的数值。如果 Android 应用只用到这三类，平台 `Trace` 或 NDK（Native Development Kit，C/C++ 开发工具包）提供的 `ATrace_*` 已经足够；若是 C++ 引擎、跨平台程序，或者需要分类过滤、流事件与强类型扩展字段，再选用 Perfetto SDK。


| 接口 | 可用边界 | 适合场景 |
|---|---|---|
| `Trace.beginSection/endSection` | API 18+ | Java/Kotlin 同线程嵌套阶段 |
| `ATrace_beginSection/endSection` | NDK API 23+ | C/C++ 同线程嵌套阶段 |
| `Trace.beginAsyncSection/endAsyncSection` | API 29+ | Java/Kotlin 跨线程阶段 |
| `ATrace_beginAsyncSection/endAsyncSection` | NDK API 29+ | C/C++ 跨线程阶段 |
| `Trace.setCounter` / `ATrace_setCounter` | API 29+ | 随时间变化的数值 |
| Perfetto SDK `TRACE_EVENT` | C++17 SDK | 分类、流、计数器和扩展字段 |

#### Java/Kotlin 同步时间片

同步时间片必须在同一线程内成对闭合，下面的包装可以在异常路径上保证配对：

```kotlin
inline fun <T> tracedSection(name: String, block: () -> T): T {
    android.os.Trace.beginSection(name)
    return try {
        block()
    } finally {
        android.os.Trace.endSection()
    }
}

val bitmap = tracedSection("ImageDecode") {
    decodeImage(bytes)
}
```

`Trace.java` 将名称上限限定为 127 个 UTF-16 代码单元（普通汉字通常占一个，部分 emoji 等补充平面字符占两个）。`beginSection()` 在应用追踪启用时会检查长度，超长名称会抛出 `IllegalArgumentException`；`|`、换行与空字符则会在底层被替换为空格。名称应保持简短、稳定且不含用户数据。


跨线程任务则要使用相同的名称与 cookie 配对：

```kotlin
fun startCapture(requestId: Int) {
    android.os.Trace.beginAsyncSection("CameraCapture", requestId)
}

fun finishCapture(requestId: Int) {
    android.os.Trace.endAsyncSection("CameraCapture", requestId)
}

fun updateQueueDepth(depth: Int) {
    android.os.Trace.setCounter("DecodeQueueDepth", depth.toLong())
}
```

cookie 是异步区间的整数关联 ID。时间上重叠的同名异步事件必须使用不同的 cookie，结束事件再凭借同一名称与 cookie 找回对应起点。cookie 只用于配对，把账号、文件名等敏感信息放进去只会扩大暴露面。

<!-- gracker-diagram: ch14-04-19-async-cookie -->
![异步区间用名称与 cookie 找回起点](../../assets/diagrams/ch14/ch14-04-19-async-cookie.png)

图：在开始和完成回调中使用同一名称与 cookie，允许跨线程配对。重叠的同名任务需使用不同 cookie；配对标识只用于配对，不放敏感业务内容。

#### NDK `ATrace_*`

C/C++ 同步阶段的语义与 Java 层一致：

```cpp
#include <android/trace.h>

void DecodeFrame(const EncodedFrame& frame) {
  ATrace_beginSection("ImageDecode");
  Decode(frame);
  ATrace_endSection();
}
```

如果 C++ 代码可能抛出异常或提前返回，建议再封装一层 RAII（Resource Acquisition Is Initialization，利用对象析构自动清理）守卫，确保 `ATrace_endSection()` 总能执行。异步 NDK API 从 API 29 起支持，同样使用名称与 cookie 配对。

Android 平台、系统服务和 HAL（Hardware Abstraction Layer，硬件抽象层）还会用到 `libcutils` 的小写 `atrace_begin()`，它允许显式指定 `ATRACE_TAG_*`。下面的代码把显示配置阶段归入 graphics 分类：

```cpp
#include <cutils/trace.h>

void ConfigureDisplay(Display& display) {
  atrace_begin(ATRACE_TAG_GRAPHICS, "ConfigureDisplay");
  display.ApplyPendingConfiguration();
  atrace_end(ATRACE_TAG_GRAPHICS);
}
```

`libcutils/include/cutils/trace.h` 还提供了 `ATRACE_BEGIN` / `ATRACE_END` 宏，默认使用编译单元中定义的 `ATRACE_TAG`。这套接口属于平台私有 API，普通应用应坚持使用 SDK `Trace` 或 NDK `ATrace_*`，不要把 `libcutils` 头文件当作稳定的 NDK 接口。

应用 Trace Point 只有在采集配置放行时才会进入系统 Trace。下面的 Android Perfetto 配置通过 `atrace_apps` 允许列表启用目标应用的 `TRACE_TAG_APP` 分类事件：

```textproto
buffers {
  size_kb: 32768
  fill_policy: RING_BUFFER
}

data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      atrace_apps: "com.example.app"
      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_waking"
    }
  }
}
```

`RING_BUFFER` 表示缓冲区满后覆盖最早的数据。`atrace_apps` 应填写具体包名；使用 `*` 会放开所有应用的 ATrace 事件，使数据量与隐私暴露同时放大，团队默认配置宜限定为具体包名。


#### Native（C/C++） Perfetto SDK

如果希望把应用事件与系统调度、ftrace 等数据放进同一条时间轴，应选用 system backend（系统后端）。下面是 TrackEvent 的最小初始化与同步时间片示例：

```cpp
#include <perfetto.h>

PERFETTO_DEFINE_CATEGORIES(
    perfetto::Category("rendering"),
    perfetto::Category("camera"));
PERFETTO_TRACK_EVENT_STATIC_STORAGE();

void InitTracing() {
  perfetto::TracingInitArgs args;
  args.backends |= perfetto::kSystemBackend;
  perfetto::Tracing::Initialize(args);
  perfetto::TrackEvent::Register();
}

void RenderFrame() {
  TRACE_EVENT("rendering", "RenderFrame");
  SubmitRenderWork();
}
```

`kSystemBackend` 会连接系统内的 Perfetto 追踪服务 `traced`，由外部 Perfetto 客户端控制采集会话。`Initialize()` 与 `Register()` 只是注册能力，外部会话仍需启用 `track_event` 数据源并放行对应的 category——前面的 `linux.ftrace`/`atrace_apps` 配置只管平台 ATrace，TrackEvent 走的是另一套配置路径。该模式适合能控制设备与部署的本地调试或实验室环境。相比之下，`kInProcessBackend`（进程内后端）则是在本进程内部创建、配置并启动 tracing session，所得 Trace 仅包含本进程数据，系统调度需另外采集；两种后端可以同时注册，输出仍按各自会话分开。

<!-- gracker-diagram: ed14-04-event-source-and-session-matching -->
![埋点接口、数据源与会话控制者按三条路径匹配](../../assets/diagrams/ch14/ed14-04-event-source-and-session-matching.png)

图：平台 `Trace`/ATrace 属于 APP 分类，由 `linux.ftrace` 与 `atrace_apps` 目标包控制采集；`RING_BUFFER` 满后会覆盖最早数据。SDK system backend 连接 `traced`，`Initialize()`/`Register()` 仅负责注册，外部会话仍需启用 `track_event` 与对应 category。SDK in-process backend 需在本进程创建、配置并启动 session，仅记录本进程而不含整机调度；两类 backend 可同时注册，但输出不自动合并。请求配置并不保证设备实际覆盖，也不赋予应用额外的系统采集权限。

TrackEvent 目前已支持时间片、计数器、Flow（事件之间的因果连线）与调试注解（附加的键值信息）。Android 17 所带 Perfetto 还支持 TrackEvent protobuf descriptor；需要强类型业务字段时，可以把字段类型描述嵌入 Trace，让 Trace Processor 自动将数据解码到 `args` 表。

自定义 `perfetto::DataSource<T>` 的门槛更高：它能写入自定义数据包，但同时也要求 Trace Processor 具备对应的导入逻辑。

如果只定义一个独立 `.proto`，指望代码生成器生成的 setter（字段写入方法）能自动进入上游 `TracePacket`，这条路是走不通的；`TracePacket` 是 Perfetto Trace 的顶层数据包容器，缺少平台 protobuf 扩展、descriptor 或自定义导入器，这类代码产出的数据无法形成可查询的结构化表。

<!-- gracker-diagram: ch14-04-22-typed-import -->
![结构化业务字段需要可识别的导入路径](../../assets/diagrams/ch14/ch14-04-22-typed-import.png)

图：字段描述与导入能力共同决定 Trace Processor 能否查询结构化内容。独立 `.proto` 生成的 setter 不会自动扩展上游 `TracePacket`。

#### 生产包治理

Trace 埋点的设计质量直接影响轨迹可读性与线上信息安全：

- 使用稳定的阶段名，动态标识放入 cookie、计数器或受控字段；
- 同步区间严格嵌套，异步区间严格配对；
- 不写入账号、URL 参数、文件路径、令牌或用户输入；
- 避免在每个元素、每个像素或极短循环中密集埋点；
- 字符串需要格式化时先检查 `Trace.isEnabled()`，避免未开启追踪时仍创建临时字符串对象；
- 埋点开销必须在目标设备上实测，不直接沿用其他设备的纳秒级估算值。

Android 性能文档给出的经验开销约为每个区间 5 微秒，并建议优先标记耗时大于 0.1 ms 的工作；这只是选择粒度的参考基准，真实开销仍受设备、系统与采集配置影响。

发布包中要避免使用全局 `-assumenosideeffects class android.os.Trace` 规则清除平台 Trace 调用：这条 R8（Android 字节码优化与压缩工具）规则会假定方法无副作用并删除全部调用，波及应用及所有依赖库，还会让诊断能力随构建配置飘移。更可控的做法是只包装团队自己的可选埋点：

```kotlin
object AppTrace {
    inline fun <T> section(name: String, block: () -> T): T {
        if (!BuildConfig.ENABLE_APP_TRACE) {
            return block()
        }
        android.os.Trace.beginSection(name)
        return try {
            block()
        } finally {
            android.os.Trace.endSection()
        }
    }
}
```

把 `ENABLE_APP_TRACE` 设为构建期常量后，R8 可以安全移除不可达的 Trace 调用分支。发布前仍应检查 APK、混淆映射文件与实际 Trace，确保敏感字符串已剥离而必需的诊断点仍在。


### 团队级 Perfetto 分析知识库

仅仅把零散 SQL 丢进共享目录算不上知识库。一个可审查的最小仓库可以按如下结构组织：

```text
perfetto-analysis/
├── toolchain.lock
├── trace-configs/
│   ├── startup.textproto
│   └── rendering.textproto
├── sql-packages/
│   └── team.android/
├── summaries/
│   ├── startup.textproto
│   └── memory.textproto
├── ui-macros/
│   └── macros.json
├── gates/
│   └── policy.json
├── golden-traces/
│   └── manifest.json
└── tests/
```

`toolchain.lock` 用来固定 Python 包、Trace Processor 版本和二进制摘要。

黄金轨迹（golden trace，指结果已确认的基准轨迹）是用于回归测试的代表性 Trace；清单中需记录其来源、系统版本、许可范围与预期结果，含敏感数据的样本本身则应保存在受控存储中。

每次知识库变更至少执行四类检查：

1. SQL 能在空轨迹和代表性轨迹上正常执行；
2. 指标单位、维度、空值与极性符合事先声明的输出契约；
3. UI 宏中的命令 ID 属于稳定的自动化接口；
4. 旧工具与新工具之间的输出差异已在固定轨迹上完成比对。

知识库的评审重点应落在语义变更上。格式调整可以自动化校验，而指标定义、时间窗口、连接键（JOIN 的匹配字段）、阈值与采集依赖的改动，必须由熟悉该领域的工程师审核确认。



## 分析平台的任务、证据与版本治理

单个指标回答的是预设好的固定问题，而分析平台还要进一步管住 Trace 输入、查询版本、任务编排与证据链，确保每一条结论都能回溯到原始时间线。

这一需求来自很实际的痛点：同一份 Perfetto trace 可以用来回答许多问题，但如果换一位工程师分析、隔一周再复查，或者升级了一次工具，同一指标的过滤条件、单位和计算口径就可能悄悄变样。SmartPerfetto 用一条统一流水线把 Perfetto UI、`trace_processor_shell`、YAML Skill、场景策略、模型运行时、证据字段与报告存储串在一起，使 SQL 可以重跑、结论可以回查，多次分析也能按同一套指标横向对比。

下文涉及字段、阈值、runtime（调用模型和工具的执行适配层）选择及企业迁移的实现细节，固定在 SmartPerfetto v1.3.0（提交 `24eba544cebf231524294aa50def33ee0e267c9e`），该版本绑定使用 Perfetto v57.2 的 host 侧 `trace_processor_shell`。截至 2026-10-25 查询公开 release，最新版本已到 v1.16.2（2026-10-14 发布）；这里仍只以 v1.3.0 快照为准展开，新版本的新增或修复行为需另行对照对应源码。

Android 版本与 host 工具版本属于两条独立的版本线，必须分开看待：Android 版本决定设备能采集到哪些数据源，host 侧 Perfetto 版本决定 trace 解析器、SQL schema 和 stdlib（PerfettoSQL 标准库）能力。用 v57.2 分析 Android 10～17 的 trace，设备端未必同样在运行 v57.2。

<!-- gracker-diagram: ed14-04-independent-version-axes-and-toolchain -->
![设备、主机工具和平台代码分别固定版本](../../assets/diagrams/ch14/ed14-04-independent-version-axes-and-toolchain.png)

图：Android 17 设备与内核决定实际数据源和权限，主机 TP、Python 与 UI 决定 schema、stdlib 与 RPC，SmartPerfetto 固定 v1.3.0 提交决定 runtime、证据与存储实现。`perfetto` Python `0.57.2` 清单绑定原生 `v56.1`，Python 包号不证明运行 `v57.2`；代码中显式 `bin_path` 需放置并验证所选的 `v57.2` 二进制。流水线应保存实际 version/hash/toolchain，升级任意一条版本线时用 canonical/golden trace 核对输入与 contract；最新 release 仅作版本参考，旧快照语义仍以 v1.3.0 为准。

### 从单次 Trace 问答到可复用分析结果

手工分析的常见场景是：打开 Perfetto UI 跑几段 SQL，把截图贴进 issue。会话结束后截图还在，但“查询条件怎么写的”“数字出自哪一行”“换份 trace 如何用相同条件复测”往往就无从查起了。SmartPerfetto 把一次分析的产出拆成四类：

| 产物 | 主要用途 | 复核能力 |
| --- | --- | --- |
| 聊天答案 | 当前会话内解释现象、安排下一步查询 | 依赖会话中的工具结果 |
| SQL / Skill 表格 | 保存确定性取数结果 | 可检查查询、参数、列与行 |
| HTML 报告 | 分享一次完整调查 | 保留结论、限制和证据入口 |
| analysis result snapshot（分析结果快照） | 跨窗口、跨人员、跨版本比较 | 保存标准化指标、证据引用和报告身份 |

四类产物的留存周期不同：聊天答案随会话结束即可；snapshot 与报告则必须携带指标来源、证据引用、运行模式、provider（模型服务提供方）、runtime 和部分失败原因。团队做回归对比时应优先留存 snapshot 或报告——如果后来的人手里只有一句模型生成的结论，就无法判断它源自 trace 实测、外部知识还是模型推断。


此外，SmartPerfetto 面向的是单条和少量 trace，与线上性能平台各有分工。线上第 90 / 99 百分位值（P90 / P99）、慢帧率和启动耗时用于评估影响范围与趋势；少量代表性 trace 则用来剖析阶段耗时、线程状态和资源竞争究竟怎样变化。两者采样机制不同，复盘时应并列对照，不能拿单条 trace 去推导全量用户分布。

### Perfetto AI Assistant 的最小工作流

一次最小分析流程包括五个步骤：加载 `.pftrace` 或 `.perfetto-trace`、说明包名与问题、限定场景或时间窗、选择分析模式，最后检查报告里的证据。如果在 Perfetto UI 中已经选中了 area（时间区间）或 track event（时间线事件），前端可以把该选区作为上下文提交给后端；选区的作用是缩小查询范围，根因是否真在其中仍需进一步查证。

`fast`、`full`、`auto` 三种模式控制分析 Agent 可调用的工具范围、运行时间与模型调用量：

| 模式 | v1.3.0 行为 | 适合场景 |
| --- | --- | --- |
| `fast` | 轻量提示词、核心证据工具子集、较少的运行时间与模型调用量 | 已知问题的快速检查 |
| `full` | 完整工具、必须完成的计划与质量检查、notes 和 artifact | 因果链较长或需要逐层排除的问题 |
| `auto` | 由硬规则和轻量分类器决定；无法可靠分类时走 `full` | 日常入口 |

当引用了 reference trace（对照轨迹）、已注册源码或私有知识源时，后端会把 `fast` / `auto` 自动解析为 `full`，以便启用调用这些材料所需的工具。


Smart Profile 负责选定分析场景：preview 阶段先识别可分析的时间段，用户选中启动、滑动、点击、导航、设备状态或 ANR 后，系统再创建对应的深度分析 run（一次分析执行）。Smart Profile 决定“分析哪段场景”，`fast` / `full` 决定“投入多少工具和运行时间”，两者互不替代。

分析过程中，模型并不直接读取整份 trace 字节，而是先由后端通过 `trace_processor_shell`、SQL 和 Skill 取数，再把结构化结果、经过行列截断的表格片段、选区上下文与受控报告片段交给 runtime——既控制了上下文体积，也让诊断先经过查询约束。即便如此，数据外发风险依然存在：查询结果仍可能携带进程名、线程名、slice 文本或业务标识，接入外部 provider 前必须完成脱敏与合规评估。

复核分析结果时，应记录 Result ID（分析结果标识）、`evidenceRefId`（证据引用标识）、表格行列、查询限制和 runtime 身份。只反馈一句“回答不对”很难定位缺陷，保留这些字段才能区分 SQL 条件或单位错误、Skill 兼容问题、trace 数据源缺失、模型过度推断还是报告展示错误。

### YAML Skill 与场景策略的分层设计

把可复用分析写成一段提示词，还是写成可执行的定义，直接决定了它能否被测试。SmartPerfetto 把可复用逻辑分成 Skill、strategy 和 template 三层，其中 v1.3.0 仓库里的 Skill 是可执行的 YAML 分析定义，与自由文本提示词有着本质区别。

Skill 可以声明参数、SQL、其他 Skill 引用、迭代、并行、条件分支、诊断输出和展示 schema，目录按 atomic（单项查询）、composite（组合查询）、comparison（对比）、deep（深入分析）、pipelines（多步流程）、modules（共用模块）与 vendor（厂商扩展）七类组织（具体文件数随版本演进，以仓库实际为准）：

| 层级 | 主要职责 | 失败时的症状 | 复核方式 |
| --- | --- | --- | --- |
| Skill | 查询、参数、输出列、执行状态与证据来源 | 空表、错列、错时间窗、单位不一致 | 独立执行并检查 DataEnvelope |
| strategy | 场景路由、执行顺序、质量要求与误诊规则 | 选错调查路径、缺关键分支、过早收敛 | 对照场景和中间证据 |
| template | 报告结构与证据呈现 | 数字可见却无来源，限制项被遗漏 | 检查报告合约与证据引用 |

这种分层减少了临时拼凑 SQL 的比例：高频查询沉淀为 Skill，调查路径由 strategy 约束，报告呈现交给 template。模型依然可以解释数据、建议下一步查询并排列假设，但核心的查询条件、单位换算与空结果语义应留在可测试的执行层。


Skill 的输出会经兼容适配器转换为 `DataEnvelope`，即 SmartPerfetto 的标准结果对象。

其中 `meta` 记录 schema 版本、来源、时间、Skill/step、执行状态和证据身份；`data` 存放表格、图表、文本或诊断内容；`display` 描述展示层级、列定义与格式。执行状态 `observed`（得到数据）、`empty`（查询成功但无匹配行）与 `optional_error`（可选查询失败）必须分开处理，把查询失败写成“没有发现问题”只会把故障掩盖在结论里。


### SQL guardrail（规则式风险检查）、stdlib 文档与证据来源索引

编写 Perfetto SQL 时常见几类错误：工具升级后表或字段变更、漏写 stdlib module（PerfettoSQL 标准库模块）、忽略 `dur = -1` 表示事件未闭合、混用 Trace Processor 内部的 `utid/upid`（内部唯一 ID）与操作系统的 `tid/pid`（系统线程/进程 ID）、未限定时间窗，以及在大表上执行无边界 JOIN。

SmartPerfetto 对用户直接提交的 raw SQL 与 Skill SQL 采用不同的 include 构建路径：raw SQL 基于生成的 stdlib symbol index（标准库符号索引）分析依赖并按固定顺序补入 `INCLUDE PERFETTO MODULE ...;`，Skill 执行器则按 Skill 声明构造 include。由于自动补全只覆盖索引中已知的符号，当 symbol index 为空或语句未能识别时，查询仍需显式写出 include。

执行后的 SQL 会生成 `QueryReviewV1` 元数据，记录实际读取的表、过滤条件、输出列、guardrail 告警、stdlib 注入、执行时长、行数与截断状态。

当遇到复杂 CTE（公用表表达式）、嵌套查询、JOIN 或窗口函数而只能完成部分静态解析时，该元数据必须标记为 `partial`（证据不完整）。`QueryReviewV1` 的允许用途固定为 `review_metadata_only`：它只用来让人核对查询做了什么，诊断结论仍要由证据体系支撑。

完整的 Query Review 会随 `DataEnvelope` 或 Artifact（保存的分析产物）进入最终报告；提供给模型的 compact projection（压缩内容片段）则不含可执行 SQL。因此报告中的可执行 SQL 是完整的，模型每轮看到的往往只是截断视图。


诊断证据通过独立的 Evidence Contract 表达，其中的 contract 是一组必填字段，规定了结论如何指回原始查询结果。

一条数值证据可以记录 `traceId`、current（当前 trace）/reference（对照 trace）、producer kind（数据生产方类型）、Skill 与 step、`queryHash`、`queryReviewId`、artifact、计划阶段，以及具体的 row selector（行定位条件）、column、actual value、单位和时间范围。claim（结论陈述）的支持等级分为 `verified`（证据完整）、`partial`、`inference`（推断）与 `unsupported`（无支持）。

举个例子：如果报告写“主线程 Runnable 120 ms”，至少要能定位到对应的证据行和列；若进一步写“CPU 争用导致这 120 ms”，还必须有调度关系或其他旁证来支撑因果判断。

<!-- gracker-diagram: ed14-04-query-metadata-evidence-and-claims -->
![查询结果、查询复核元数据与结论证据分别保存](../../assets/diagrams/ch14/ed14-04-query-metadata-evidence-and-claims.png)

图：SQL 与 YAML Skill 经 TP 取数，`DataEnvelope` 的 `meta`/`data`/`display` 保留来源与状态，`observed`/`empty`/`optional_error` 不可互换。`QueryReviewV1` 记录表、过滤条件、include、列、时长、行数与截断情况，静态解析不全时标为 `partial`，用途固定为 `review_metadata_only`；完整 SQL 留存报告，模型侧 `compact projection` 不含可执行 SQL。Evidence Contract 另绑定 trace 的 `current`/`reference`、Skill/step、`queryHash`/`queryReviewId`/artifact 及行列实际值、单位与窗口。单凭“Runnable 120 ms”的数值证据尚不足以支撑“CPU 竞争”的因果结论，claim 需标明 `verified`/`partial`/`inference`/`unsupported`。报告与 snapshot 应保留运行身份及缺失原因，模型不直接读取整份 trace 字节，也不能拿单条 trace 推导全量用户分布。

guardrail 只能拦截规则里明确列出的风险，规则之外的语义正确性仍需人工把关。遇到缺少 FrameTimeline、Binder、sched、GPU counter 或关键应用标记的情况，报告必须列出缺失数据、下调支持等级并给出补采配置；`empty` 状态也应如实呈现，不能写成“系统没有问题”。

### 多 Trace 对比与性能回归判断

SmartPerfetto 支持两类对比：raw reference trace 对比要求当前会话同时能访问 current 与 reference 两份原始 trace，适合围绕同一问题继续迭代查询；analysis result snapshot 对比则直接读取已保存的分析产物，适合版本回归、A/B 测试、多候选对比与跨窗口复盘——它只对比快照中保留的标准化指标与证据引用，不会重查原始 trace。

<!-- gracker-diagram: ch14-04-32-two-comparisons -->
![原始对照与快照对照的两条路径](../../assets/diagrams/ch14/ch14-04-32-two-comparisons.png)

图：原始 Trace 可继续取数，结果快照只能比较已经保存的指标与依据。快照比较不会重新查询原始 Trace，缺失指标必须显式呈现。

标准指标键覆盖以下四类：

- 启动：总耗时、首帧、`bindApplication`、Activity start、主线程 blocked；
- 滑动：平均 FPS（每秒帧数）、帧数、Jank（卡顿帧）数量与比例、帧时长 P50/P95/P99；
- CPU：主线程 Running/Runnable、大核占比、平均频率；
- 环境：trace 时长、设备型号、Android 版本和抓取配置摘要。

标准回填的范围较窄，仅包含 `startup.total_ms`、`scrolling.avg_fps`、`scrolling.frame_count`、`scrolling.jank_count` 和 `scrolling.jank_rate_pct`。要特别留意 v1.3.0 的默认回填 SQL：启动耗时从整份 Trace 的 `android_startups` 取最大非 NULL `dur`，没有包名或场景窗口过滤；滑动统计则读取整份 Trace 所有正时长的 `actual_frame_timeline_slice`，没有进程、Layer、token 去重或场景窗口限制。因此这些回填值只能用作全局候选，“目标应用启动耗时”或“某次滑动 FPS”等明确命名必须等核验后再赋予。正式回归应改用已校验身份、窗口和帧口径的 Skill/SQL，并在 golden Trace 上验证。TTFD（Time to Full Display，完全显示耗时）、PSS（按共享比例分摊的内存）、Java/Native Heap、DMA-BUF（Linux 设备驱动间共享的缓冲区）、bitmap、RSS 与 swap 等指标可由 Skill、SQL 或报告模板补充，均不在 v1.3.0 的内置回填集合中。缺失字段应展示为 `missing metric`，按零值参与比较会掩盖真实缺失。

<!-- gracker-diagram: ch14-04-33-global-backfill -->
![v1.3.0 默认回填是全局候选](../../assets/diagrams/ch14/ch14-04-33-global-backfill.png)

图：默认 SQL 未限制应用、Layer 和业务窗口，核验后才可用于场景回归。启动取全局最大 `dur`，帧统计可能混入多进程、多 Layer 与 SF 行。

v1.3.0 的变化高亮同时结合了相对阈值与按单位设定的绝对阈值。通用相对阈值为 5%；按单位设定的绝对阈值分别为 `ms` 5 ms、`fps` 1 fps、百分比 1 个百分点、计数 1、字节 1 MiB、纳秒 5,000,000 ns。规则同时比较绝对变化幅度与相对变化幅度，增加和减少均可能触发高亮。当数值有效且 assessment 不为 `same/unknown` 时，时间、FPS、字节与纳秒指标须达到绝对阈值，且在相对变化有限时同时达到 5%（相对变化为 NULL 或非有限数时仅检查绝对阈值）；百分比与计数满足绝对或相对幅度阈值之一即可；未匹配上述单位时，有有限相对变化用 5%，否则用绝对变化幅度大于 `1e-9` 兜底。

<!-- gracker-diagram: ch14-04-34-highlight-threshold -->
![变化高亮按单位选择判断分支](../../assets/diagrams/ch14/ch14-04-34-highlight-threshold.png)

图：有效变化先按单位检查绝对与相对阈值，再决定界面高亮。这只是 UI 变化规则，不等同于统计显著性检验；NULL 和 `unknown` 分支须保留。

上述规则只控制界面高亮显示；统计显著性检验以及 26.4 节讨论的置信区间、样本量与实验设计属于统计推断范畴，正式回归裁决仍以后者为准。

例如在发现启动 P90 上升后，可以分别抽取改动前的 baseline（基线）与改动后的 candidate（候选版本）两份 trace 生成 snapshot，再比对启动阶段、主线程状态、Binder、I/O 与首帧提交记录。若设备、温控、编译状态或抓取配置存在不一致，应先标注环境差异再比对，避免把不可比样本的波动误判为代码回归。

### Provider Manager：模型服务与执行适配层

模型配置分为三层，职责清晰分离：Connection 保存前端访问 SmartPerfetto 后端的地址及可选后端 token；Provider profile 保存模型 endpoint（服务地址）、模型凭证、模型 ID、通信协议及 runtime 选择；runtime 则决定通过哪套 Agent SDK 或 server adapter 调用 SmartPerfetto 工具。

<!-- gracker-diagram: ch14-04-35-connection-provider-runtime -->
![后端连接、模型配置和执行适配层](../../assets/diagrams/ch14/ch14-04-35-connection-provider-runtime.png)

图：Connection、Provider profile 与 runtime 分别管理服务入口、模型与执行机制。后端 token 与 provider key 授权对象不同，健康检查也需核对实际 runtime。

| 配置项 | 作用 | 常见误解 |
| --- | --- | --- |
| Connection | 前端连接 SmartPerfetto 后端 | 把后端 token 当成模型 key |
| Provider profile | 配模型服务、模型 ID、协议类型 | 保存 profile 后忘记设为 active |
| active provider | 当前会话优先使用的 provider | 以为改 `.env` 会覆盖 active profile |
| env fallback | 脚本和服务端部署的默认凭证 | 只查 `.env`，不看 Provider Manager |
| runtime | 选择 Agent SDK / server adapter | provider 能对话就认定工具调用也一定可用 |

v1.3.0 注册了五种可用于正式运行的 runtime：

| runtime | 适配层 | 配置边界 |
| --- | --- | --- |
| `claude-agent-sdk` | Claude Agent SDK | 默认 runtime；支持 Anthropic、Bedrock、Vertex、DeepSeek 与兼容网关 |
| `openai-agents-sdk` | OpenAI Agents SDK | OpenAI、Ollama 与 OpenAI-compatible endpoint |
| `pi-agent-core` | Pi Agent Core | 仅 custom provider；禁用项目发现和 shell/file tools |
| `opencode` | 隔离的 OpenCode server / SDK | 仅 custom provider；不读取用户本机 OpenCode 项目状态 |
| `qoder-agent-sdk` | Qoder Agent SDK / `qodercli` | custom provider 或显式 env；SDK 为可选依赖 |

Qoder SDK 不随默认 Docker、portable 或 npm 安装提供，启用前需审阅其独立条款并显式安装 optional peer（可选同级依赖）。Pi、OpenCode 和 Qoder 在 SmartPerfetto 中拿到的都是按请求生成的分析工具，不能套用通用 coding agent 的文件、shell 或网络权限来理解。

新建 session 时，系统按顺序检查请求指定的 `providerId`、Provider Manager 当前 active provider、`SMARTPERFETTO_AGENT_RUNTIME`，最后回落到默认的 `claude-agent-sdk`。若请求明确指定的 provider 不存在，会立即 fail-fast 报错。这段顺序适用于未传 `runtimeOverride`、未显式传 `providerId: null` 且未启用 experimental runtime 的常规新请求，选择器对那些显式选项另有独立分支。


恢复历史 session 时，系统沿用会话内保存的 provider/runtime：已保存的 provider 依然优先，env/default session 的 `runtimeOverride` 优先于当前环境变量，后续切换的 active provider 不会影响旧会话。若已绑定的 provider 已被删除，系统会立即报错提示，避免静默切换到其他 provider。

v1.3.0 的会话快照还存在一处实现缺口：常规 runtime 选择器已经支持 `qoder-agent-sdk`，但 `providerSnapshot.ts` 在解析纯环境变量配置时只列出了 Claude、OpenAI、Pi 和 OpenCode。如果仅设置 `SMARTPERFETTO_AGENT_RUNTIME=qoder-agent-sdk`，当次运行可以进入 Qoder，但 env/default 会话快照无法确认 Qoder 身份是否被正确持久化。这一限制不影响显式 provider 的存在性检查；恢复这类 Qoder session 前，建议先在已修复版本上回归验证，或直接新建 session。

<!-- gracker-diagram: ed14-04-new-versus-resumed-session-identity -->
![新建会话按当前优先级选择，恢复会话按保存身份](../../assets/diagrams/ch14/ed14-04-new-versus-resumed-session-identity.png)

图：SmartPerfetto v1.3.0 的常规新请求（未传 `runtimeOverride`、未显式传 `providerId: null`、未启用 experimental）依次按请求 `providerId` → active profile → `runtime` env → 默认 Claude 选择，不适用时才进入下一层，显式指定的 provider 不存在则 fail-fast。恢复历史会话时沿用已保存的 provider/runtime，绑定的 provider 被删除时立即失败；env/default 保存的 `override` 优先于当前环境变量，不受后续 active 切换影响。纯 env Qoder 虽可通过选择器运行，但 snapshot 解析未包含 Qoder，身份保存情况存疑，应在修复版本回归或重新创建会话。真实身份需经鉴权 `/api/runtime-health` 核验，公开 `/health` 仅反映存活，且 backend token 与 provider key 不可混用。

排障时应请求需要鉴权的 `GET /api/runtime-health`，核对实际生效的 runtime、模型与 credential source（凭证来源）。公开的 `GET /health` 只说明服务进程存活，要确认分析 runtime 是否已按预期切换，仍以 `GET /api/runtime-health` 为准。

### 运行分发、权限与隐私

部署与运行方式应结合维护责任选择：Docker 适合服务端集中部署；三平台 portable（免安装便携版）内置了 Node.js 24、后端、预构建前端和固定版本的 trace processor；源码运行适合维护 Skill、strategy 与后端逻辑；npm CLI 提供 `smp` / `smartperfetto` 命令，复用同一套 runtime、MCP（Model Context Protocol）工具、报告与 session snapshot，不启动 Web UI。批处理、CI 或内部服务可按需接入 CLI、API 或 MCP。

部署者配置 `SMARTPERFETTO_API_KEY` 后，受保护 API 需携带相应凭证；企业环境也可使用带角色和 scope（权限范围）的持久 API key。后端 API key 保护的是 SmartPerfetto 服务入口，provider key 授权的是模型服务，两者各司其职、不可混用。若将服务暴露到非可信网络，还须限制上传体积、代理超时、报告下载与管理接口。

trace 文件通常包含进程名、线程名、业务路径、URL 片段、用户操作节奏、设备信息与 slice 参数。因此上传给 provider 的内容片段、Result ID、HTML 报告、日志、workspace（隔离的工作空间）分享以及过期清理策略，都应按敏感数据标准管理。

私有源码与外部知识源只有在当前请求显式选择、且 scope 与授权校验通过后才会进入 runtime，不会自动暴露给普通 trace 会话。启用 `provider_send` 时，还须同时具备“该来源允许发送给 provider”与“本次运行允许发送”两项许可。

<!-- gracker-diagram: ch14-04-38-private-context-permission -->
![私有上下文按本次请求与许可进入 runtime](../../assets/diagrams/ch14/ch14-04-38-private-context-permission.png)

图：显式选择、scope 与许可共同约束私有材料的检索与外发。背景知识与当前 Trace 证据应分开存放；授权变更时应使旧的私有会话失效。

同时，SmartPerfetto 只能分析调用方有权采集并提供的 trace。Perfetto SDK 或 AndroidX Tracing 可以补充应用内埋点，并不会赋予应用读取整机 ftrace、其他进程或系统服务内部数据的权限。系统级采集依然受 Manifest 中的 `profileable` / `debuggable` 属性、adb、ProfilingManager、系统签名权限和设备策略约束，详见 14.12 与 26.6 节。

### SmartPerfetto 与其他工具的分工

把整套工具链放在一起看，各自的边界就很清楚：Perfetto UI 负责时间轴观察和人工核对，`trace_processor_shell` 执行可重复的查询，Perfetto SDK 负责把应用内事件写入 trace，ProfilingManager 提供受平台管控的 profiling 请求，APM（Application Performance Monitoring，应用性能监控）平台统计长期线上趋势。SmartPerfetto 处于解析器与团队调查流程之间，负责编排查询、汇集依据、生成报告与对比结果。

| 工具 | 更适合的问题 | 产物 |
| --- | --- | --- |
| Perfetto UI | 手工观察时间轴、验证某段事件关系 | 截图、选区、手动 SQL |
| `trace_processor_shell` | 批量查询、可重复 SQL、CI 检查 | CSV / SQL 输出 |
| SmartPerfetto | 开放式 trace 调查、证据报告、多 trace 对比 | Result ID、报告、Skill 表格 |
| Perfetto SDK / AndroidX Tracing | 把应用内部阶段写进 trace | 自定义 slice、counter、data source |
| ProfilingManager | Android 15（API 35）起的受控 profiling 请求 | 系统返回的 profiling 结果 |
| APM 平台 | 长期线上趋势、分位值、告警 | 指标、事件、抽样现场 |

具体到工作场景：开发期适合分析单条 trace，专项排障可沉淀 Skill 与模板，灰度回归可以把异常样本与 baseline snapshot 对照。需要强调的是，Agent 生成的因果结论最终仍要回到 Perfetto UI 或 SQL 结果复核；涉及渲染链路时，还要按 App、BufferQueue、SurfaceFlinger、HWC（Hardware Composer，硬件合成器）与显示设备五段组织材料并逐段排查，不要拿单个长 slice 代替整条链路的判断。

### Skill 质量评估与回归测试

Skill 进入团队工作流后，必须按可执行代码来维护。最小测试集应包含固定 trace、固定参数、输出列校验、空结果与可选错误分支、证据引用校验，以及 SQL smoke test（确认基础路径可跑通的冒烟测试）和 golden report（用于逐次比对的基准报告）。由于 Perfetto schema、stdlib、设备数据源与厂商实现都会演进，只验证 YAML 能否解析远远不够。

测试建议拆成四层：

1. SQL 能在固定 trace 上顺利执行；
2. `DataEnvelope` 的列、单位、layer（展示层）、level（详细程度）及执行状态符合 contract；
3. 关键指标与 golden 基准保持在允许误差范围内；
4. 报告中的 evidence anchor 能准确定位表格行列，且 claim support 没有把 `partial` 越级标成 `verified`。


启动、滑动、ANR、Binder、I/O、内存和功耗等场景都应同时准备正常样本与缺字段样本。缺字段样本用来测试降级路径，例如缺少 FrameTimeline 时帧级结论必须标记为不完整。SmartPerfetto 锁定 trace processor 版本后，仍须在 canonical trace（团队指定的标准测试 trace）上做回归；升级 v57.2 之后的新版本时，还要重新核对 schema、stdlib symbol index、标准指标与 golden 输出。

14.7 节的 SQL 查询条件、单位与 Jank/CUJ 查询，14.11 节的调查协议，以及 26.4 节的回归判定都可以沉淀为 Skill contract，声明清楚输入、输出、单位、证据解释、适用版本、缺失数据分支和人工复核入口。

### 企业内部 Trace 分析平台接入清单

企业部署前需要明确 trace 存储、留存周期、报告可见范围、provider 凭证归属、模型请求出网策略、脱敏规则和审计范围（tenant 指租户，workspace 指租户内隔离的工作空间）。表中的条目应落实到部署配置、权限测试与删除演练，不能只停留在文档里：

| 维度 | 建议检查项 |
| --- | --- |
| 多租户 | tenant / workspace 隔离、跨组报告分享审批 |
| Provider 隔离 | 每个租户单独 profile、独立 token、独立用量审计 |
| Trace 留存 | 上传大小限制、过期清理、敏感样本删除流程 |
| 报告权限 | Result ID 可见性、HTML report 分享范围、导出水印 |
| 审计 | 上传、分析、查看、分享、删除和 provider 修改记录 |
| 脱敏 | 包名、URL、账号、地理位置、业务参数、截图附件 |
| 回归 | 固定 trace 集合、Skill golden 基准、发布前 smoke test |

权限测试需覆盖同租户不同 workspace、跨 tenant、资源 owner（所有者）、过期数据以及已被删除的 provider。能够查看报告，并不代表同时有权查看原始 trace；这两类资源应分别执行授权校验并留存审计记录。

### SmartPerfetto 与技术知识库联动

技术知识库承载机制原理、对应源码版本与排查顺序，SmartPerfetto 则在具体 trace 上运行查询并留下依据。像输入参数、SQL、输出列、单位和失败分支这类确定性规则适合抽成 Skill，而依赖机型、版本或上下文权衡的经验更适合写在 strategy 或机制章节中。

一种可行的维护闭环是：从技术章节挑选可观测问题，编写对应的 Skill 并在固定 trace 上执行，检查报告里的依据是否充分，再把发现的缺字段、厂商差异与误诊条件反哺回章节。同样地，章节内容修订后，也要评估 Skill contract 是否需要同步调整，让“机制说明—可执行查询—真实样本”三者保持同步。

<!-- gracker-diagram: ed14-04-versioned-semantic-regression-loop -->
![机制章节、可执行规则与固定样本组成回归循环](../../assets/diagrams/ch14/ed14-04-versioned-semantic-regression-loop.png)

图：知识库需固定 toolchain、配置、SQL 包、summary、UI 宏、门禁策略与 golden manifest，基准 Trace 需记录来源、系统、许可与预期，敏感样本受控存放。从机制章节的可观察问题出发编写 Skill contract，锁定参数、窗口、JOIN、单位与缺失分支；SQL 能执行与 YAML 能解析并不证明指标语义正确。应使用代表样本、空 trace 与缺字段样本分别验证 SQL、`DataEnvelope` 列/单位/层级/状态、golden 误差、`evidence anchor` 行列及 claim 支持度（`partial` 不得升为 `verified`）。新旧工具、schema 与 `stdlib symbol index` 的差异须经领域审核，失效条件及时回写章节或 Skill；单次成功仅覆盖当次条件，推广到其他厂商或系统版本前需重新验证。

### 企业版迁移与 404 排查

SmartPerfetto 的企业迁移阶段决定了 trace metadata（文件路径、归属和访问范围等元数据）究竟从文件系统还是数据库读取。v1.3.0 定义的四个阶段如下：

| 阶段 | metadata 读取来源 | 写文件系统 | 写数据库 | 回退方式 |
| --- | --- | --- | --- | --- |
| `legacy` | filesystem | 是 | 否 | 关闭企业模式 |
| `dual-write` | filesystem | 是 | 是 | 删除数据库副本，文件系统仍为权威 |
| `cutover` | DB | 否 | 是 | 恢复切换前已验证的文件系统与 DB 快照 |
| `retired` | DB | 否 | 是 | 恢复退役前快照；不承诺反向转换 |

启用企业功能但未配置 `SMARTPERFETTO_ENTERPRISE_MIGRATION_PHASE` 时，默认阶段为 `dual-write`。切换到 `cutover` 时还必须设置 `SMARTPERFETTO_ENTERPRISE_CUTOVER_CONFIRMED=true`；缺少该确认开关时，服务在解析迁移计划阶段就会拒绝启动。


需要留意，该启动检查只校验开关本身，数据一致性必须靠切换前的准备来保证。运维人员应在开启确认开关前完成 filesystem 与 DB 之间的 reconciliation（逐项比对并修正不一致记录），并验证好可用于恢复的快照。

排查环境当前所处阶段时，可以用下面的命令只打印两个迁移开关，避免把数据库口令或 provider key 带进工单：

```bash
printf 'phase=%s\n' "${SMARTPERFETTO_ENTERPRISE_MIGRATION_PHASE:-<unset>}"
printf 'cutover_confirmed=%s\n' "${SMARTPERFETTO_ENTERPRISE_CUTOVER_CONFIRMED:-<unset>}"
```

这两行只输出迁移阶段与切换确认状态，不会泄露敏感凭证。若第一行未设置且企业功能已开启，实际阶段为 `dual-write`；第二行只有在准备进入 `cutover` 时才应设为 `true`。

在 `cutover` 阶段，`readTraceMetadataForContext()` 仅按当前 RequestContext 中的 tenant、workspace 与 owner 权限范围查询 `trace_assets`；查不到就直接返回 `null`，不会回退去查旧文件系统。

这里的 RequestContext 代表本次请求携带的身份与授权上下文，RBAC（Role-Based Access Control）指基于角色的访问控制。如果查询失败后私下回退去读文件系统，不仅可能绕过 DB 上的 RBAC 权限校验，还会掩盖尚未迁移的数据缺口，因此不能把这种回退当作解决 404 的办法。

切换后若出现 404，可按以下顺序排查：

1. 确认当前生效阶段、enterprise feature flag（企业功能开关）与 cutover confirmation；
2. 按请求的 tenant、workspace 和 owner 核查 `trace_assets` 中是否存在对应记录；
3. 检查记录里的 `local_path`、文件搬运结果及服务进程的文件访问权限；
4. 检查 SSO（Single Sign-On，单点登录）映射、API key scope 与 RBAC 策略，分清“记录缺失”与“当前用户无权访问”；
5. 对照切换前的 dry-run fingerprint（试运行结果摘要）、snapshot manifest（快照内容清单）与数据库表行数；
6. 若确认切换数据不完整，先停止写入，按项目提供的 snapshot restore 流程恢复文件系统与 SQLite 快照，再重新处理 reconciliation 中暴露的不一致记录。

只把环境变量改回 `dual-write` 并指望 DB 数据会自动写回文件系统，是行不通的：源码已明确说明 dual-write 未实现 reverse importer（从数据库反向导回文件系统的工具）。由于快照恢复会覆盖目标文件或目录，必须在维护窗口内由部署负责人操作，并在恢复前留存现场副本。

<!-- gracker-diagram: ed14-04-migration-authority-and-scoped-404 -->
![迁移先改变 metadata 权威来源，再按当前 scope 查 404](../../assets/diagrams/ch14/ed14-04-migration-authority-and-scoped-404.png)

图：v1.3.0 中 `legacy` 读写 FS；`dual-write` 读 FS、同时写 FS 与 DB（启用企业功能且未设 phase 时默认此阶段）；`cutover` 与 `retired` 读写 DB，进入 `cutover` 需确认开关但开关本身不保证数据一致，事前应完成 reconciliation 并备好可恢复快照。`cutover` 按 `RequestContext` 的 `tenant`/`workspace`/`owner` 查询 `trace_assets`，未命中返回 `null` 而不会回查旧 FS，以免绕过 RBAC。排查 404 需依次检查实际阶段、scoped 记录、`local_path`/文件/权限、SSO/key scope/RBAC 及迁移指纹计数快照。若数据不完整，应停止写入、保留现场，由负责人在维护窗恢复并校验 FS 与 SQLite 快照；仅改回 `dual-write` 并无 reverse importer，`retired` 也不承诺反向转换。

至于 404 率、trace 访问成功率与数据库延迟的告警阈值，应由各团队结合自身的 SLO（Service Level Objective，服务等级目标）和流量规模制定，SmartPerfetto 源码中并未硬编码 99.5% 或 0.5% 这类通用指标。迁移期间的监控还应涵盖 reconciliation 失败数、snapshot 完整性、按 scope 查询未命中的原因分类，以及恢复演练结果。

### 复核准则

使用 SmartPerfetto 产出报告时，可以用四个问题把关分析质量：

1. 报告中的关键数值能否回溯到具体的证据行列与 trace 身份？
2. 因果结论的支持等级是否与调度、时间关系或跨层证据匹配？
3. 多 trace 对比是否基于相同的查询条件、单位与采集环境，且明确标出缺失字段？
4. provider、runtime、私有上下文与企业存储是否严格遵守当前部署的权限边界？

四项中只要有一项答不上来，就应将结论留在待验证状态。SmartPerfetto 能分担重复查询与报告整理的工作量，但 Android 底层机制判断、Perfetto UI 人工核验以及可重复的实验设计，最终仍要由工程师来完成。

## 小结

Perfetto 自动化通常从一条可复用的 SQL 起步，再逐步扩展到 Trace Summary、Python 批处理、CI 门禁与团队级分析平台。在这个演进过程中，每个产出数值都必须保留 trace 身份、查询逻辑、单位、样本数和工具版本；Agent、provider 与企业存储负责的是编排与治理，无法突破 trace 自身缺字段、缺因果链时的证据上限。


## 参考资料

- [Android 17 `external/perfetto` 源码](https://android.googlesource.com/platform/external/perfetto/+/android-17.0.0_r1/)
- [Android 17 `Trace.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/core/java/android/os/Trace.java)
- [Android 17 `libcutils` ATrace 接口](https://android.googlesource.com/platform/system/core/+/android-17.0.0_r1/libcutils/include/cutils/trace.h)
- [Trace Summarization](https://perfetto.dev/docs/analysis/trace-summary)
- [旧版 Trace-based Metrics](https://perfetto.dev/docs/analysis/metrics)
- [Android 17 `TraceSummary` 输出消息定义](https://android.googlesource.com/platform/external/perfetto/+/android-17.0.0_r1/protos/perfetto/trace_summary/file.proto)
- [Perfetto v57.2 线程表与 `is_idle` 定义](https://github.com/google/perfetto/blob/v57.2/src/trace_processor/tables/metadata_tables.py)
- [PerfettoSQL 语法](https://perfetto.dev/docs/analysis/perfetto-sql-syntax)
- [Trace Processor Python API](https://perfetto.dev/docs/analysis/trace-processor-python)
- [Batch Trace Processor](https://perfetto.dev/docs/analysis/batch-trace-processor)
- [Perfetto UI 命令与宏](https://perfetto.dev/docs/visualization/ui-automation)
- [稳定 UI 自动化命令参考](https://perfetto.dev/docs/visualization/commands-automation-reference)
- [Perfetto 扩展服务器](https://perfetto.dev/docs/visualization/extension-servers)
- [Perfetto Tracing SDK](https://perfetto.dev/docs/instrumentation/tracing-sdk)
- [Android ATrace 埋点](https://perfetto.dev/docs/getting-started/atrace)
- [Android NDK Tracing API](https://developer.android.com/ndk/reference/group/tracing)
- [Macrobenchmark 持续集成](https://developer.android.com/topic/performance/benchmarking/benchmarking-in-ci)
- [Android 性能测量与 Trace Point 开销建议](https://developer.android.com/topic/performance/measuring-performance)

- [SmartPerfetto v1.3.0 核对提交](https://github.com/Gracker/SmartPerfetto/tree/24eba544cebf231524294aa50def33ee0e267c9e)
- [Perfetto v57.2 host 工具固定配置](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/scripts/trace-processor-pin.env)
- [Agent runtime 架构](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/docs/architecture/agent-runtime.md)
- [runtime 选择与 snapshot override 顺序](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/agentRuntime/runtimeSelection.ts)
- [v1.3.0 provider/runtime 快照解析](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/services/providerManager/providerSnapshot.ts)
- [私有分析上下文边界](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/docs/architecture/private-analysis-context.md)
- [DataEnvelope、Query Review 与 Analysis Receipt](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/docs/DATA_CONTRACT_DESIGN.md)
- [raw SQL stdlib include 注入](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/agentv3/sqlIncludeInjector.ts)
- [证据合约类型](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/types/evidenceContract.ts)
- [标准对比指标](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/types/multiTraceComparison.ts)
- [标准指标回填范围](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/services/standardMetricBackfillService.ts)
- [显著变化阈值](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/services/comparisonSignificance.ts)
- [企业迁移状态机与快照恢复](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/services/enterpriseMigration.ts)
- [企业 trace metadata 的 scoped 读取](https://github.com/Gracker/SmartPerfetto/blob/24eba544cebf231524294aa50def33ee0e267c9e/backend/src/services/traceMetadataStore.ts)

- [内存区间与 NULL 约定](https://android.googlesource.com/platform/external/perfetto/+/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/linux/memory/process.sql)
- [UI 宏顺序执行与异常传播](https://android.googlesource.com/platform/external/perfetto/+/android-17.0.0_r1/ui/src/core/command_manager.ts)
- [Python v57.2 包内原生工具清单](https://github.com/google/perfetto/blob/v57.2/python/perfetto/prebuilts/manifests/trace_processor_shell.py)
- [Python 批处理实例生命周期](https://github.com/google/perfetto/blob/v57.2/python/perfetto/batch_trace_processor/api.py)
- [最新 release 查询](https://github.com/Gracker/SmartPerfetto/releases/tag/v1.16.2)

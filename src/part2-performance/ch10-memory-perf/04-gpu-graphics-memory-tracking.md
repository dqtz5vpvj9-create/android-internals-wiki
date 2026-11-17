---
title: GPU 与图形内存统计、归因与诊断
chapter: '10.4'
section: '10.4'
status: finalized
applicable_versions: Android 12 (API 31) - Android 17 (API 37)
last_verified: '2026-10-24'
last_verified_against: AOSP android-17.0.0_r1（memtrack、libmeminfo/Debug、GpuMem/BPF/Tracer、BufferQueue、Perfetto parser/SQL）/ ACK android17-6.18-2026-06_r6 DMA-BUF / Perfetto v54.0 与 v58.2 主机合成 trace / 官方 Bitmap、Surface/ImageReader、GL ES 3.2 与 Vulkan 生命周期资料
verified_note: 源码、发布工具与设备实测分开；SQL 和采集配置及 shell 示例在主机验证，不声称目标设备支持、权限或真实性能收益
confidence: high
sources:
- type: aosp
  path: hardware/interfaces/memtrack/aidl/android/hardware/memtrack/IMemtrack.aidl
- type: aosp
  path: frameworks/base/core/jni/android_os_Debug.cpp
- type: aosp
  path: frameworks/base/core/java/android/os/Debug.java
- type: aosp
  path: frameworks/native/services/gpuservice/GpuService.cpp
- type: aosp
  path: frameworks/native/services/gpuservice/gpumem/GpuMem.cpp
- type: aosp
  path: frameworks/native/services/gpuservice/tracing/GpuMemTracer.cpp
- type: aosp
  path: frameworks/native/libs/gui/BufferQueueCore.cpp
- type: aosp
  path: frameworks/native/libs/gui/BufferQueueProducer.cpp
- type: aosp
  path: system/memory/libdmabufheap/BufferAllocator.cpp
- type: kernel
  path: android17-6.18-2026-06_r6/include/trace/events/gpu_mem.h
- type: kernel
  path: android17-6.18-2026-06_r6/drivers/dma-buf/dma-heap.c
- type: kernel
  path: android17-6.18-2026-06_r6/Documentation/driver-api/dma-buf.rst
- type: official
  path: perfetto.dev/docs/data-sources/gpu
- type: official
  path: perfetto.dev/docs/analysis/stdlib-docs#androidgpu-memory
- type: official
  path: developer.android.com/reference/android/graphics/Bitmap
- type: official
  path: developer.android.com/reference/android/graphics/Bitmap.Config
- type: official
  path: developer.android.com/reference/android/view/TextureView
- type: official
  path: developer.android.com/agi
- type: research
  path: ../DeepResearch/2026-07-11-android17-gpu-memory-tracking-pool-defrag.md
tags:
- gpu-memory
- dmabuf
- gralloc
- perfetto
- memory-tracking
- graphics
- memtrack
related_chapters:
- '2.8'
- '4.1'
- '10.1'
- '15.11'
- '22.9'
- '22.14'
- '23.4'
last_consolidated_at: '2026-08-11'
---

# GPU 与图形内存统计、归因与诊断

面对图形内存问题，手里没有一个单一的数字能一次回答所有疑问：`dumpsys meminfo` 按进程 PSS（按引用者比例分摊共享页）与 memtrack（厂商图形内存记账接口）分类，`dumpsys gpu --gpumem` 读取驱动上报的 GPU 地址空间总量，DMA-BUF 描述设备间共享的缓冲区，Vulkan tracker 则记录 API 级别的分配事件。这些统计既可能同时覆盖同一块资源，也可能各自漏掉一部分。

因此，排查图形内存增长时，必须先给每一个数字补齐四项限定条件：采集接口、设备与系统构建版本（build）、被归因的进程，以及资源是否跨进程共享。缺了这四项上下文，单凭“Graphics = 120 MB”既说不清实际占用了多少物理内存，也证明不了应用存在泄漏。

## 1. 先区分资源，再选择计数器

### 1.1 两类常见图形分配

`GraphicBuffer` / `HardwareBuffer` 由图形缓冲区分配器（Gralloc）创建，通常以 DMA-BUF 文件描述符的形式跨进程、跨硬件模块共享。生产者（producer）、SurfaceFlinger、显示控制器、相机、视频编解码器与 GPU 都可能引用同一个 buffer；至于它究竟映射到 CPU 地址空间、GPU 地址空间还是两者兼具，取决于用途标志（usage）、映射接口（mapper）与驱动实现。

另一方面，GPU 驱动还会直接管理 API 私有资源，比如纹理、渲染目标（render target）、Vulkan 设备内存（device memory）、命令缓冲区与内部缓存。这类资源往往没有可供应用检查的 DMA-BUF fd，或者交由厂商专用分配器管理。

因此，在 AOSP 里找不到统一的用户态“显存分配器”或“显存碎片整理器”；具体的内存格式布局、heap 划分、映射与回收策略均由 Gralloc HAL 与 GPU 驱动决定。

同一张逻辑图片也可能沿着不同路径落到不同内存域：

- 软件 Bitmap 的像素位于 native heap，首次硬件绘制还可能建立 GPU 纹理缓存；
- `Bitmap.Config.HARDWARE` 的像素放在图形内存中，Bitmap 对象仍由 Java 引用链控制生命周期；
- 相机或视频帧常由 Gralloc buffer 组成，多个 Surface 各有自己的 BufferQueue；
- Vulkan 应用可显式申请 `VkDeviceMemory`，再把 image 或 buffer 绑定到该内存。

因此不能只按 Java 对象数量去换算图形内存：一个对象背后可能没有独立的底层内存分配（backing allocation），而多个对象也可能共享同一个 DMA-BUF。

### 1.2 同一资源在不同工具里的视角

同一块图形资源，换用不同工具就会看到完全不同的视角。下表先对齐各个工具各自能回答什么问题：

| 工具或指标 | 主要回答的问题 | 不能直接回答的问题 |
|---|---|---|
| `dumpsys meminfo` | 进程的 smaps（逐映射内存统计）分类与 memtrack 补充归因 | 系统中唯一物理 buffer 总量、分配调用栈 |
| `dumpsys gpu --gpumem` | 驱动上报的全局及各 PID GPU-addressable（GPU 可寻址）总量 | 资源类型、创建位置、DMA-BUF 唯一物理占用 |
| `/proc/PID/fdinfo/FD` | 某进程仍持有的 DMA-BUF fd 及 size/exporter（导出方） | 没有 fd 的 GPU 私有资源、由别处持有的引用 |
| `/sys/kernel/dmabuf/buffers` | 系统中每个 DMA-BUF inode（内核文件对象标识）的 size/exporter | 实际驻留物理页清点、创建调用栈与阻止释放的完整引用 |
| Perfetto GPU memory | GPU 总量随时间的变化及进程归因 | 单个纹理名称、完整分配栈 |
| Vulkan memory tracker / AGI（Android GPU Inspector） | Vulkan API 分配、绑定及单帧资源 | 非 Vulkan 路径的全部系统图形内存 |
| ART heap dump / allocation profile / native heap profile | heap dump 查 Java 引用；allocation profile 查其覆盖范围内的创建栈 | allocation profile 不给完整保留引用图，也不清点全部 GPU backing 字节数 |

正因为视角各异，不同工具给出的数字必须分开解读：进程维度的 GPU 总量可能会把跨进程导入（import）的共享资源重复计入各进程，而 memtrack 则要求 HAL 按 PSS 规则处理共享并排除类型间重叠，直接相加存在重复计算的风险。

## 2. `dumpsys meminfo`：Graphics 摘要由什么组成

### 2.1 详细行里的三个来源

排查时，首先保存一份应用的完整进程内存明细：

```bash
adb shell dumpsys meminfo com.example.gallery
```

对于多进程应用，输出中会出现多个 PID，需要逐个保存结果。App Summary 里的 `Graphics` 来自 Framework 侧的重新聚合，并不等于 memtrack `GRAPHICS` 类型的原样输出。

这层聚合发生在 `Debug.MemoryInfo.getSummaryGraphics()`：它把以下三类的 `getOtherPrivate()` 字段相加，即各自对应的 private clean + private dirty：

1. `Gfx dev`：libmeminfo 从 smaps 按映射名称识别的设备项；在 `android-17.0.0_r1` 中，这处分支匹配 `kgsl-3d0`，并不是覆盖所有 GPU 厂商设备映射的统一总表；
2. `EGL mtrack`：memtrack `GRAPHICS` 中尚未被 smaps 统计的记录；
3. `GL mtrack`：memtrack `GL` 中尚未被 smaps 统计的记录。

这里要看清字段的承载方式：`android_os_Debug.cpp` 会把 libmemtrack 返回的 PSS 值（换算为 KiB 后）同时写进对应行的 `pss`、`privateDirty` 和 `rss` 三列。也就是说，mtrack 行里这三列装的是同一份上报值的 Framework 表示，如果误读成三份独立测量就会算错；至于底层的 backing 页是否物理私有，`privateDirty` 这个列名本身也回答不了。此外，`android-17.0.0_r1` 的 libmemtrack 只按类型和 flag 求和，并不会替 HAL 再按进程数做一次 PSS 分摊。

详细表里还可能出现 `Other mtrack`，它汇总自 memtrack 的 `MULTIMEDIA`、`CAMERA` 与 `OTHER` 分类，App Summary 的 `Graphics` 项并不包含它。旧版工具或 OEM 定制输出的标签可能有所不同，因此分析报告中应保留原始文本。

### 2.2 `SMAPS_UNACCOUNTED` 的设计目的

再看聚合的另一半：`android_os_Debug.cpp` 调用以下三个 libmemtrack 聚合函数：

- `memtrack_proc_graphics_pss()`
- `memtrack_proc_gl_pss()`
- `memtrack_proc_other_pss()`

这三个函数只累加带 `MemtrackRecord.FLAG_SMAPS_UNACCOUNTED` 的记录。这个标志标记的是 smaps 还没计入的内存，用来避免 `Debug.MemoryInfo` 把同一映射统计两遍。

`IMemtrack.aidl` 对类别给出了更具体的要求：

<!-- gracker-diagram: ed10-04-memtrack-to-graphics-summary -->
![从 HAL 类型与 flag 到 JNI 字段，再到 Graphics 摘要](../../assets/diagrams/ch10/ed10-04-memtrack-to-graphics-summary.png)

图：固定r1数据流：HAL负责共享/PSS、类型不重叠及GRAPHICS中CPU/GPU mapped DMA-BUF集合去重；GL补GPUprivate，OTHER等补其余未统计设备内存。libmemtrack仅按type和SMAPS_UNACCOUNTED求和，不再替HAL按进程分摊。JNI把每类上报字节转KiB，同写该行pss/privateDirty/rss，不能把三列当三份测量或由privateDirty推backing全私有。独立smaps Gfxdev这处分支只匹配kgsl-3d0，非跨GPU总表；getSummaryGraphics把Gfxdev/EGLmtrack/GLmtrack三类private clean+dirty相加，Othermtrack不入摘要。flag不自动发现驱动漏报，HAL缺项/不支持/分类错误会影响结果，0不等无资源，VM_PFNMAP等需正确补充，跨设备保留HAL/driver/build。

- `GRAPHICS + SMAPS_UNACCOUNTED` 报告该 PID 的 CPU-mapped 与 GPU-mapped（映射到 CPU/GPU 地址空间的）DMA-BUF PSS，并去掉两个集合的交集；
- `GL + SMAPS_UNACCOUNTED` 报告该 PID 未被 smaps 统计的 GPU private allocation（GPU 私有分配）；
- `OTHER + SMAPS_UNACCOUNTED` 报告剩余的未统计设备内存；
- `VM_PFNMAP`（按物理页帧号建立的特殊映射）在 smaps 中可能得到 0 RSS/PSS，也属于 memtrack 要补充的范围。

如果 HAL 实现缺项或不支持某种 type，相应行就可能显示为 0 或缺失。看到 0 时，只说明该接口没有返回可计入值；进程是否真正持有 GPU 资源，仍要结合其他观测点交叉判断。跨设备比较数据之前，也应先确认 memtrack HAL、GPU 驱动和系统 build 是否一致。

### 2.3 PSS、GPU 映射总量与唯一 buffer 容量

这三个指标各自回答的问题并不相同：

- PSS 尝试把共享资源按引用者分摊，回答进程该分摊多少共享成本；
- `gpu_mem_total` 描述驱动认为某 PID 映射到 GPU 地址空间的总量，回答该进程的 GPU 地址空间目前覆盖多少内存；
- `/sys/kernel/dmabuf/buffers` 按 inode 列出唯一 DMA-BUF，回答系统当前存在哪些唯一共享 buffer。

当同一个 DMA-BUF 被两个进程导入 GPU 时，各 PID 的驱动上报量都可能覆盖这块资源，因此将所有 PID 的 `gpu_mem_total` 相加，替代不了同一 GPU 的 `pid = 0` 全局记录。另一方面，sysfs 按 inode 去重得到的也只是 DMA-BUF 对象容量汇总——每个字节是否已实际驻留物理内存、不同对象的 backing 页是否重叠，它都回答不了，与 App Summary 的 `Graphics` 之间也做不了等式校验。需要注意，全局 `pid = 0` 本身同样属于驱动上报口径。

<!-- gracker-diagram: ed10-04-shared-buffer-accounting-views -->
![同一 DMA-BUF 的多方导入、GPU 总量与对象容量分开记账](../../assets/diagrams/ch10/ed10-04-shared-buffer-accounting-views.png)

图：只示一个DMA-BUF被producer、consumer/合成器及设备多方引用，usage/mapper/driver决定CPU/GPU映射集合，它们不必相同。各PID GPU-addressable总量可同时覆盖该资源，不能求和替同GPU pid0全局记录，后者也仍是驱动口径。sysfs按inode去重只列一次对象容量，不证明各字节已驻留或不同对象backing页互不重叠。PSS/memtrack按对应HAL共享规则归因，不从容量直接除进程数推PSS，也不与Graphics或GPU总量建等式。图中虚线是同一对象另一视角，不是资源额外复制。

## 3. GpuService：从 tracepoint 到快照

### 3.1 `dumpsys gpu --gpumem`

Android Common Kernel 的 `gpu_mem/gpu_mem_total` tracepoint（跟踪点）要求 GPU 驱动在 allocate、free、import、unimport（分配、释放、导入、取消导入）改变 GPU-addressable 总量时发出更新。事件字段包含 `gpu_id`、`pid` 和当前 size；`pid = 0` 表示全局总量，正 PID 表示进程总量。

Android 17 的 GpuService 将 eBPF 程序挂到该 tracepoint 上，并维护了一张以 `(gpu_id, pid)` 为 key 的内核 BPF map。在 `android-17.0.0_r1` 的 `gpuMem.c` 中，这张 map 最多保留 1024 个 key，收到 size 为 0 的事件时会删除对应条目，收到非零事件则更新现有值或尝试插入。因此，map 中缺少某个 PID 条目与读到明确的 0 属于两种不同状态。更重要的是，map 保存的是已收到事件的最新值，并不会主动向驱动重新清点；初始化状态、驱动上报、map 容量与更新成功情况都会影响数据覆盖度。在调用 `dump()` 逐项读取期间，map 仍可能并发更新，各条目的取值时刻彼此错开，整个输出算不上严格意义上的原子快照：


```bash
adb shell dumpsys gpu --gpumem
```

输出中的 `Global total` 与各项 `Proc PID total` 均以字节为单位；同一 GPU 缺少 `pid = 0` 条目时会显示 `Global total: N/A`。初始化失败、map 为空、条目缺失与实际收到过 size = 0 事件，分别代表不同的现场状况；读取中途若发生失败，还可能只输出此前已遍历到的部分。因此拿到输出后，应保留错误文本，并结合驱动支持、同窗口 ftrace、重复采样与资源操作交叉确认完整性。

<!-- gracker-diagram: ed10-04-bpf-updates-and-missing-values -->
![BPF 非零更新与零值删 key 决定快照怎样解释](../../assets/diagrams/ch10/ed10-04-bpf-updates-and-missing-values.png)

图：驱动tracepoint size是当前GPU-addressable总量，不是这次alloc差值。固定r1按(gpu_id<<32)|pid记录，最多1024keys，非零更新/尝试插入，size0删除key，因此没有条目不等读到显式0。初始化、驱动上报、容量或更新成功影响覆盖；map仅保存已收最新值，不向驱动重新清点。dump逐项读可与更新交叠、非原子，中途失败可留部分输出，同GPU缺pid0显示Global total:N/A。空map/PID缺项可能由零删除、未上报/初始/更新缺口造成，初始化/读取失败另保存错误文本，与同窗事件和资源操作交叉核对，命令完成不是完整性证明。

这条命令适合回答“增长集中在哪个 PID”，但里面没有分配标识（allocation ID）、格式、调用栈或资源名称，驱动内部碎片也无法从中看到。要进一步定位创建点，仍需依赖 API 级 tracker、应用埋点或厂商工具。

### 3.2 Perfetto 的初始值与增量

`GpuMemTracer` 注册了 `android.gpu.memory` 数据源。trace 启动后，工作线程会遍历 BPF map 并写入 `GpuMemTotalEvent`；每个条目分别取 `systemTime()`，标记 MONOTONIC 时钟。因此，我们拿到的是一组遍历期间的初始值，各 GPU/PID 的取值时刻彼此错开；后续变化则由额外配置的 `gpu_mem/gpu_mem_total` ftrace 事件提供，采集后仍需检查事件可用性、丢失情况与时间覆盖范围。

要同时拿到初始快照与后续变化，需把两个数据源都配上：

```protobuf
data_sources {
  config {
    name: "android.gpu.memory"
  }
}

data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "gpu_mem/gpu_mem_total"
    }
  }
}
```

如果只开 ftrace，trace 开始前就已存在且采集期间不变化的资源会缺少基线；如果只开 `android.gpu.memory`，则只能得到启动时的遍历快照。两者都依赖对应的驱动 tracepoint，初始快照还要求 GpuMem/BPF 已完成初始化。另外，上面的片段只包含数据源部分，实际采集时需放进含 buffer 与持续时间等参数的完整 TraceConfig 中才能执行。

<!-- gracker-diagram: ed10-04-initial-traversal-and-ftrace-coverage -->
![初始逐项遍历与变化事件共同构成时间覆盖](../../assets/diagrams/ch10/ed10-04-initial-traversal-and-ftrace-coverage.png)

图：完整TraceConfig同时包含android.gpu.memory和linux.ftrace gpu_mem/gpu_mem_total，并核对tracepoint/权限、BPF初始化、buffer/duration与丢失/结束状态；正文片段不是独立可执行全配置。GpuMemTracer启动后工作线程逐项遍历BPF map，每条分别systemTime并标MONOTONIC，非所有GPU/PID同一原子瞬间。独立ftrace负责变化，可以和遍历交叠；轨道仅示可能关系、无真实时长比例或先后保证。仅ftrace缺采集前既有不变资源基线，仅初始遍历缺后续变化；首样本前不补零，跨丢事件区间不确定，两侧不能自动补回缺口。

虽然 `android.gpu.memory` 标准库提供了按进程聚合的区间 counter，但在本文核验的 `android-17.0.0_r1` 标准表 `android_gpu_memory_per_process` 中，输出仅包含 ts/dur/upid/gpu_memory，并未保留 GPU 维度。在多 GPU 设备上，这些行分属不同 GPU，直接相加或混作同一条进程曲线都会算错。因此我们改从 GPU 轨道直接取值，保留 `gpu_id` 和 `track_id`，并在每条轨道内计算持续时间：


```sql
WITH gpu_counters AS (
  SELECT c.ts, c.track_id, c.value,
    CAST(EXTRACT_ARG(t.dimension_arg_set_id, 'gpu') AS INT) AS gpu_id,
    CAST(EXTRACT_ARG(t.dimension_arg_set_id, 'upid') AS INT) AS upid
  FROM counter AS c
  JOIN track AS t ON t.id = c.track_id
  WHERE t.type = 'process_gpu_memory'
), intervals AS (
  SELECT *,
    COALESCE(LEAD(ts) OVER (PARTITION BY track_id ORDER BY ts), trace_end()) - ts AS dur
  FROM gpu_counters
)
SELECT g.ts, g.dur, g.gpu_id, g.track_id, p.pid,
  p.name AS process_name, g.value / 1048576.0 AS gpu_memory_mib
FROM intervals AS g
JOIN process AS p USING (upid)
WHERE g.gpu_id IS NOT NULL
ORDER BY g.ts, g.gpu_id, p.pid;
```

⚠ 工具版本差异：在同一份主机合成的双 GPU trace 测试中，`android-17.0.0_r1` 启动脚本附带的 Perfetto v54.0 会把同 PID 的两个 GPU 样本混入同一轨道；而本次使用的 v58.2 能保留独立的 GPU 轨道，以上 SQL 已在 v58.2 上通过验证。当 v54.0 缺失 GPU 维度时，这条查询因 `gpu_id IS NOT NULL` 条件一行都不会返回——这反映的是解析器在导入时丢失了维度，设备的真实 GPU 内存状态仍需结合解析器版本与原始 trace 核对，导入时丢掉的维度靠 SQL 也补不回来。

<!-- gracker-diagram: ed10-04-parser-gpu-dimensions-and-sql -->
![解析器先保留 GPU 维度，SQL 才能在每条轨道内算持续时间](../../assets/diagrams/ch10/ed10-04-parser-gpu-dimensions-and-sql.png)

图：仅正文主机合成双GPU同PID测试：v54.0混为一进程轨且缺GPU维度，v58.2保留独立GPU轨，不是Android设备采集或性能结果。修订SQL过滤gpu_id非空，缺维度输入不返行不等无GPU内存，SQL不能恢复导入丢失信息。固定r1标准表只有ts/dur/upid/gpu_memory而无GPU列，所以从track.dimension_arg_set_id取gpu/upid，在track_id内LEAD算dur，末段只到trace_end；驱动bytes除1048576为MiB非PSS，ts/dur纳秒。首样本前不补零，丢事件区间可失真，归属用事件PID对应upid，不以packet生产者当资源owner。设备支持/权限/初始化/丢失仍另核对，保存解析器和原始trace。

阅读查询结果时，先分清几处统计口径：`gpu_memory_mib` 是驱动上报量除以 1048576 得到的 MiB，与 PSS 属于两套不同的统计；ts 与 dur 的单位为纳秒，末段只延伸至 trace 结束，首样本之前不会自动补零，跨丢失事件的区间也可能失真。此外，JOIN 使用事件中的 PID 所对应的 upid 来认定归属，发出 trace packet 的进程在这里没有决定权。在设备上采集时，依然要检查 tracepoint、权限、初始化和事件丢失情况。

### 3.3 其他 GPU 数据源各有用途

- `gpu.counters` 采集厂商定义的硬件 counter；含义、单位与支持范围依设备而变，频率等指标也可能来自 ftrace。实际注册名还可能带 `.adreno` 等后缀，采集配置需要精确匹配已注册的数据源名。
- `gpu.renderstages` 提供 graphics/compute submission（图形与计算提交）的执行阶段和时长，不保证存在名为“texture upload”的统一 stage。
- `vulkan.memory_tracker` 记录 Vulkan 的 driver/device memory allocation 与 bind（绑定）事件，适合观察 Vulkan 资源生命周期；它不覆盖 OpenGL、HWUI、Camera 和 SurfaceFlinger 的全部资源。
- 部分旧版或厂商内核还导出 DMA heap allocation/free tracepoint；`android17-6.18-2026-06_r6` 这个通用基线里找不到一条可移植的 `dmabuf_heap/dma_heap_stat` 事件，采集配置应以目标设备的 `available_events` 为准。


`dumpsys gfxinfo` 关注帧时间、HWUI 状态和渲染统计，可以与内存时间线对齐；通用 GPU 内存总账仍要用前面 GpuMem/Perfetto 的数据源。

## 4. Kernel 6.18 的 DMA-BUF 观测入口

### 4.1 进程 fd：谁还持有共享 buffer

标准 Linux 接口位于 `/proc/PID/fdinfo/FD`。DMA-BUF fd 会额外输出 `size`、`count`、`exp_name`，有名称时还会输出 `name`。

查示例应用当前持有哪些 DMA-BUF fd，遍历它的 fdinfo：

```bash
adb shell '
pids=$(pidof com.example.gallery)
if [ -z "$pids" ]; then
  echo "no matching process" >&2
  exit 1
fi
for pid in $pids; do
  case "$pid" in *[!0-9]*|"") continue ;; esac
  for info in /proc/$pid/fdinfo/*; do
    [ -r "$info" ] || continue
    if grep -q "^exp_name:" "$info"; then
      printf "pid=%s fd=%s\n" "$pid" "${info##*/}"
      grep -E "^(ino|size|count|exp_name|name):" "$info"
    fi
  done
done
'
```

`size` 表示 buffer 容量，`count` 是 dma-buf file 的引用计数（当前基线内核会减去本次 procfs 读取的临时引用），但仅凭它们还回答不了持有进程数、GPU 映射数或可回收比例。`exp_name` 标明导出方（exporter），`ino` 可在同一次观测窗口内与 sysfs 的 inode 关联。由于进程列表、fd 和引用计数都在不断变化，PID 与 inode 一旦经历释放重用就会指向新对象，无法充当永久标识。此外，权限不足、进程退出、fd 转交以及当前没有匹配 buffer 都可能导致输出缺失，报告中应保留错误信息与采样起止时间。

Linux 侧提供的通用观测入口就到 fdinfo 为止，并不存在 `/proc/PID/dmabuf` 这样的通用文件；即便某些设备导出了私有节点，那也只是单台设备的定制行为，不具备 Android 平台级保证。

### 4.2 全局 sysfs：系统里有哪些唯一 DMA-BUF

在 `CONFIG_DMABUF_SYSFS_STATS` 开启时，`/sys/kernel/dmabuf/buffers/<inode>/` 提供 `size` 与 `exporter_name`。我们按 inode 生成一份快照：

```bash
adb shell '
root=/sys/kernel/dmabuf/buffers
if [ ! -d "$root" ] || [ ! -r "$root" ]; then
  echo "DMA-BUF sysfs unavailable or unreadable" >&2
  exit 1
fi
for entry in "$root"/*; do
  [ -d "$entry" ] || continue
  inode=${entry##*/}
  size=$(cat "$entry/size") || continue
  exporter=$(cat "$entry/exporter_name") || continue
  printf "%s %s %s\n" "$inode" "$size" "$exporter"
done
'
```

在开启该配置且具备访问权限的前提下，sysfs（内核对象信息文件系统）会列出当前已登记的 DMA-BUF 对象容量，适合按 inode 去重以及按 exporter 聚合。由于目录遍历与先后读取两个属性文件的间隙都可能发生对象创建或释放，脚本也会跳过读取失败的条目，因此输出只是一次尽力而为的快照，做不到完全原子和无遗漏。sysfs 同样保存不了创建调用栈；在同窗口内将 inode 与进程 fd 对上，证明的只是观测时刻的文件持有线索，最初的业务创建点仍需另外定位。在 Android user build 上，shell 读取该路径还可能受到权限限制。

<!-- gracker-diagram: ed10-04-fdinfo-and-sysfs-inode-correlation -->
![同一观测窗口用 inode 关联进程文件引用与全局对象容量](../../assets/diagrams/ch10/ed10-04-fdinfo-and-sysfs-inode-correlation.png)

图：进程脚本处理多个pidof结果并筛可读fdinfo，ino是同窗对象线索，size容量、exp_name导出方、name可选；count为dma-buf file引用计数，固定内核扣本次procfs临时引用，非进程数/GPU映射数/回收比例。sysfs需CONFIG_DMABUF_SYSFS_STATS和权限，按登记inode读size/exporter、去重聚合，失败项跳过留stderr，遍历和两属性读取可遇创建/释放，不是原子无遗漏或物理驻留快照。同采样起止窗按inode关联只证明观测时文件持有，PID/inode可释放重用，权限/退出/fd交接/无匹配均可缺输出。最初创建点与完整持有链另靠资源表/APItracker/heapdump等，不能把当前持有者当创建者或把capacity当可回收量。

### 4.3 debugfs：实验室设备上的全局调试视图

实验室设备已 root 且挂载 debugfs 时，可以直接读全局列表：

```bash
adb shell su 0 cat /sys/kernel/debug/dma_buf/bufinfo
```

debugfs（内核调试文件系统）属于实验室接口，格式不承诺稳定，生产环境不能依赖它。厂商 GPU 节点同样受驱动、内核版本和 SELinux 策略约束；撰写报告时应记录设备路径并保留原始输出，避免把 Adreno、Mali、PowerVR 的私有路径互相套用。

## 5. 从增长曲线定位资源持有者

### 5.1 先辨认缓存、延迟释放与泄漏

图形资源释放经常受到三类延迟因素的影响：

<!-- gracker-diagram: ch10-04-19-deferred-release -->
![释放请求之后还要核对异步使用与引用](../../assets/diagrams/ch10/ch10-04-19-deferred-release.png)

图：示意队列任务完成与引用清理可能延后于页面退出。缓存平台、异步释放和泄漏需要多轮同状态比较，不能靠一次 System.gc 判断归零。

- GPU command 尚未完成，driver 要等待 fence signal（同步栅栏发出完成信号）后才回收 backing memory；
- BufferQueue 的 producer、consumer（消费者）或 SurfaceFlinger 仍持有 slot（缓冲槽位）；
- 图片库、HWUI 或图形 API 保留高水位缓存，复用后不继续增长。

排查时可以按三种曲线形态来区分：如果预热后数值保持稳定、不再上升，通常符合有上限的高水位缓存；如果每轮相同操作后基线持续上移，则更像是持有者未释放引用或资源销毁不完整；如果退出页面后短时间内未见回落，就需要把 fence 等待和队列排空（queue drain）的时间窗口纳入采样范围。显然，调用一次 `System.gc()` 并不能让图形资源立刻归零。

### 5.2 可复查的诊断实验

建议按同一套脚本保存下列数据：

1. 记录设备型号、Android build、GPU driver、kernel page size 和 app 版本。
2. 冷启动后等待页面稳定，采集 `meminfo`、`--gpumem`、DMA-BUF inode 快照和 Perfetto 基线。
3. 用固定数据集执行同一段页面、相机、视频或渲染操作。
4. 每轮在相同 UI 状态采样，并给 GPU fence 与异步销毁留下可观察区间。
5. 比较进程 GPU 总量、唯一 DMA-BUF、EGL/GL mtrack 与 Java/native 持有者数量。
6. 找到最早开始增长的指标，再选择 Bitmap、Surface、GL/Vulkan 或厂商工具继续定位。

报告应当保存原始值与轮次差值。如果手里只有 App Summary 的 `Graphics` 一个数字，就把 `Gfx dev`、`EGL mtrack` 和 `GL mtrack` 混在了一起，无法区分各自来源。

### 5.3 Java 与 native profile 能发现什么

排查仍被引用的 `Bitmap`、`Drawable`、`Surface`、`SurfaceTexture`、`ImageReader`、`Image`、`HardwareBuffer` 及业务缓存时，应使用 ART heap dump；要定位覆盖到的 wrapper、命令构建对象与 allocator 分配栈，可以使用 native heap profile，但它本身不提供完整的保留引用图。

这里的 native heapprofd 默认 heap 只覆盖 `malloc` 家族的分配，其他分配器需要单独集成；ART 分配剖析则使用另行注册的 `com.android.art` heap。Gralloc DMA-BUF 与 GPU 驱动私有分配不受普通 malloc hook 管理，heap profile 里的包装对象字节数也代替不了真正的 GPU backing 大小。因此，我们通常先用分配栈圈定创建候选，再用 heap dump、应用所有权记录或资源表追查仍被持有的对象，最后与 GPU/DMA-BUF 指标对齐；走到这一步之前，分配栈还只是线索，资源是否依然存活尚不能确定。

### 5.4 16 KB kernel page 的精确边界

在 `android17-6.18-2026-06_r6` 中，`dma_heap_buffer_alloc()` 使用 `__PAGE_ALIGN(len)`，使 DMA heap 分配的起止按内核页（kernel page）对齐。在 16 KB 内核页下，小尺寸分配尾部向上取整后的额外字节数上限会更高。

<!-- gracker-diagram: ch10-04-22-page-rounding -->
![按页取整只解释一部分容量差异](../../assets/diagrams/ch10/ch10-04-22-page-rounding.png)

图：示意数学例子：同为 17 KiB 请求，按 4 KiB 页取整得到 20 KiB，按 16 KiB 页得到 32 KiB；只验证页取整，不冒充实际 Gralloc 分配或固定增长率。

不过，单靠这条对齐规则推不出一个统一的“图形内存增加百分比”：Gralloc 的行跨度（stride）、图像分量平面（plane）、格式、硬件压缩、分块布局（tiling）、受保护内存区域（secure heap）以及驱动页表粒度带来的差异，都可能超过尾部按页向上取整（page rounding）的影响。比较 4 KB 与 16 KB 构建版本时，应以 DMA-BUF inode size 与 GPU counter 的实测为准，再按分配尺寸分布来解释差异。


## 6. 资源类型与修复方向

### 6.1 Hardware Bitmap

`Bitmap.Config.HARDWARE` 从 API 26 起引入，其像素保存在图形内存（graphic memory）中，且 Bitmap 本身不可变。它避免了每次绘制都从软件像素上传纹理的开销，但会直接占用图形资源，并限制像素直接读写与部分 Canvas 操作。

在现代 Android 上，`Bitmap.recycle()` 并不适合作为 Hardware Bitmap 的常规释放协议，常规释放路径是解除引用：当 Java/native 引用、View、Canvas、RenderThread 与缓存中的使用关系全部解除后，底层资源才具备回收条件；系统并不承诺 Java 引用一消失图形内存就立刻归零。`recycle()` 文档也提醒避免对曾交给 View 或仍可能被别处引用的 Bitmap 手工回收。至于文档中提到的“`invalidate()` 后还需一次 draw pass”，那是 `reconfigure()` 方法的使用前提，脱离这一前提它就只是一个具体示例，成不了任意 Bitmap 都能安全调用 `recycle()` 的通用同步协议。

<!-- gracker-diagram: ed10-04-hardware-bitmap-owners-and-release -->
![Hardware Bitmap 的持有关系与回收前提分开核对](../../assets/diagrams/ch10/ed10-04-hardware-bitmap-owners-and-release.png)

图：API26+ HARDWARE像素immutable且在图形内存，Java包装/业务引用与backing设备使用分别核对。正常处理优先按显示尺寸解码、限制缓存、解除己方页面/请求/缓存引用并遵守图片库池协议；View/Canvas/RenderThread/native/其他使用者和驱动同步条件仍可延后回收，Java引用消失/一次GC/调用返回均不保证图形值即时归零。手工recycle不是HardwareBitmap常规释放协议，必须先证明没有其他使用者。reconfigure文档invalidate后一次drawpass是该方法前提例子，图下方只作独立语义注解，不表示正常释放后必须执行reconfigure，更不是任意recycle通用同步屏障；不靠固定延迟猜设备使用结束。

处理图片页面时，优先的动作包括：按目标显示尺寸解码、限制内存缓存权重、在页面退出或请求取消时及时移除引用，并让 Glide/Coil 等图片库管理资源池。从 API 24 起，`prepareToDraw()` 可以发起尚未上传 Bitmap 的异步 RenderThread 上传，把部分工作移到首次绘制之前；但它不会等待上传完成，也不承诺一定能改善帧时间或驻留内存，而且修改像素后还可能触发重新上传。

<!-- gracker-diagram: ch10-04-26-prepare-upload -->
![prepareToDraw 将部分上传工作提前](../../assets/diagrams/ch10/ch10-04-26-prepare-upload.png)

图：API 24 起 prepareToDraw 可异步触发 RenderThread 上传；函数返回不代表上传完成，像素修改后还可能需要重传。轨道只示一种可能调度，不保证上传在首次绘制前完成，也不提供性能测量或驻留内存下降保证。

### 6.2 Surface、BufferQueue 与媒体资源

应用自己创建的 `Surface`、`SurfaceTexture`、`ImageReader`、`Image`、`MediaCodec` 与相机 session，必须严格按 API 生命周期及时关闭。特别是通过 `ImageReader.acquire*()` 获取的每一个 `Image` 都需要及时调用 `close()`；未关闭的 `Image` 会持续占用 `maxImages` 配额以及对应的底层 buffer。

当 Surface 销毁后，底层 buffer 依然可能被消费者或同步栅栏（fence）短暂持有。看到图形内存回落滞后时，需要同时核对 `onSurfaceTextureDestroyed()` 的返回值与释放责任、codec 的 stop/release 调用、camera session 的关闭状态、GPU counter 以及实际引用关系。具体来说，当 `TextureView` 回调返回 `true` 时由它负责释放 `SurfaceTexture`；返回 `false` 时则由调用方自行负责释放。此外，`Surface.release()` 只解除本地对服务端 Surface 的引用；即使调用了 `SurfaceTexture.release()`，仍被其他客户端或 GL 引用的 buffer 也可能继续占用资源。

<!-- gracker-diagram: ch10-04-28-texture-callback -->
![TextureView 回调返回值决定 SurfaceTexture 释放方](../../assets/diagrams/ch10/ch10-04-28-texture-callback.png)

图：销毁回调返回 true 时由 TextureView 释放 SurfaceTexture；返回 false 时调用方保留责任。SurfaceTexture.release 后仍可能有外部 buffer 引用。

至于常说的“三缓冲”，在 BufferQueue 中其实有明确的前提条件，并不存在适用于所有 producer/consumer 组合的固定缓冲数：可用 slot 数量与同时分配的 buffer 数，取决于最大可出队数（max dequeued）、队列中最少保留数（min undequeued）、消费者最大持有数（max acquired）、异步模式以及生产者的实际行为。单个 buffer 的逻辑有效载荷（payload）可用 `width × height × bytesPerPixel` 粗略估算，真实分配大小还受 stride、plane、格式、压缩和对齐影响。

<!-- gracker-diagram: ch10-04-29-bufferqueue-count -->
![BufferQueue 数量由配置和状态共同决定](../../assets/diagrams/ch10/ch10-04-29-bufferqueue-count.png)

图：固定 r1 的上限由 maxAcquired、maxDequeued、async/cannotBlock 与 mMaxBufferCount 共同限制；这不是所有场景固定分配三块 buffer 的结论。

### 6.3 OpenGL ES 与 Vulkan

销毁 OpenGL ES 资源时，需要按对象类型分别核对生命周期：纹理、buffer 和 renderbuffer 可由同一 share group 中的 context 共享，而 FBO（framebuffer object）属于各 context 私有的非共享容器——附件纹理可以共享，但 FBO 本身并不共享，切勿混淆两者类型。调用对应的 `glDelete*` 删除名称后，其他 context 的绑定或容器附件仍可能继续持有底层对象；只要引用未解除或 GPU 使用尚未完成，底层内存就不会立即回收。

<!-- gracker-diagram: ch10-04-30-gl-objects -->
![GL 共享对象与 context 容器分开销毁](../../assets/diagrams/ch10/ch10-04-30-gl-objects.png)

图：GL ES3.2 允许纹理、buffer、renderbuffer 等共享，FBO 是不共享容器。删除名称后，其他绑定或容器附件还可能持有底层对象。

EGL Surface 走独立的 `eglDestroySurface(display, surface)` 协议；若该 surface 仍是某个线程的 current surface，销毁操作会延后到它不再处于 current 状态时才执行，pbuffer 的纹理绑定还另有释放条件。它并不在前面的 GL share-group 对象清单里。

<!-- gracker-diagram: ch10-04-31-egl-surface -->
![EGL Surface 有独立的 current 状态边界](../../assets/diagrams/ch10/ch10-04-31-egl-surface.png)

图：流程中的条件描述 EGL API 语义，不承诺所有 driver backing 或跨进程资源在调用返回时归零。

Vulkan 侧则需要把对象与绑定的设备内存（bound memory）分开管理：销毁 `VkImage` 并不会隐式释放所有 `vkFreeMemory()`，从大块内存中切出的子分配（suballocation）也还要交还给应用自身的 allocator，释放前必须满足 Vulkan 的生命周期与同步规则。在诊断构建中，可以结合校验层（validation layer）、`vulkan.memory_tracker` 与 AGI frame profile 来核对 allocation/bind/free 过程。

<!-- gracker-diagram: ch10-04-32-vulkan-lifetime -->
![Vulkan object 与 device memory 分别管理](../../assets/diagrams/ch10/ch10-04-32-vulkan-lifetime.png)

图：销毁 VkImage 与释放 VkDeviceMemory 是不同操作；子分配还需归还应用 allocator。两者都要满足已提交使用完成、引用与同步规则。

销毁资源时切忌一概插入 `vkDeviceWaitIdle()`：它会阻塞等待该逻辑设备上所有队列的工作全部完成，很容易排空整条流水线。更合理的做法是按实际依赖关系用 fence 等同步机制确认相关工作已经完成，再处理对象与内存；只有在少数确实需要整设备空闲的阶段才单独评估使用 `vkDeviceWaitIdle()`。

<!-- gracker-diagram: ch10-04-33-wait-idle -->
![等待相关 fence 与全设备空闲粒度不同](../../assets/diagrams/ch10/ch10-04-33-wait-idle.png)

图：wait-idle 会等待逻辑设备所有队列；按依赖用 fence 可只等待相关使用完成。以下仅示意等待粒度，不构造测量时长或通用性能收益。

此外，RenderScript 已在 API 31 废弃。维护存量代码时仍需注意销毁 `Allocation` 等对象，新项目则应迁移到当前的图形、计算或媒体 API。

### 6.4 SurfaceView 与 TextureView

`SurfaceView` 由独立的 Surface 图层提供内容，系统有机会直接交给硬件合成器（Hardware Composer，HWC）处理；而 `TextureView` 则把 `SurfaceTexture` 内容作为 View 层级的一部分交由 HWUI 采样，依赖硬件加速窗口，在软件渲染下不会绘制内容。虽然 `TextureView` 支持 View 的 alpha、旋转和裁剪变换，但各组件的能力随系统版本不断演进——例如 `SurfaceView` 从 Android U 起也支持相应的 alpha 能力，因此并不存在一张一成不变的“仅属于 `TextureView`”的能力清单。两者渲染路径的差异，也会相应带来不同的采样与合成工作量。

<!-- gracker-diagram: ch10-04-34-view-composition -->
![SurfaceView 与 TextureView 路径不同](../../assets/diagrams/ch10/ch10-04-34-view-composition.png)

图：SurfaceView 可由合成策略交给 HWC；TextureView 在硬件加速 View 路径采样内容。能力与 overlay 资格受版本和内容限制，不能只按组件名比较内存。

在内存占用上，同样不存在“TextureView 必然更费内存”的固定排序：`SurfaceView` 自己维护了 BufferQueue，而 `TextureView` 所在的应用窗口也需要 window buffers，最终内存总量由分辨率、像素格式、queue 深度、overlay 资格（能否直接交由硬件合成器处理）以及内容渲染路径共同决定。针对相机和视频页面选型时，建议在同一台设备上实测对比进程 GPU counter、DMA-BUF inode 与帧时间，再结合画面变换、HDR、DRM 与生命周期需求做决定。

## 7. Game、Camera 与 AR 的预算方法

游戏场景中的纹理、render target、深度/模板缓冲（depth/stencil）、交换链图像（swapchain image）、传输暂存缓冲区（staging buffer）以及分配器管理的大块内存（allocator block），都需要纳入统一的预算管理。

引擎的纹理流式加载（texture streaming）或 Vulkan 子分配器（suballocator）改变的是应用层资源调度方式，驱动内部的内存碎片（driver fragmentation）对 AOSP 依然是不可见的。排查时，可以用 AGI frame profile 查看单帧内的纹理、shader、render target 与 RAM/GPU memory，而系统级的长期变化趋势仍需使用 Perfetto 或 `dumpsys gpu --gpumem`。

Camera2 / CameraX 的每一路输出 Surface 都可能维护独立的 buffer 集合。当预览、录制、图像分析、JPEG/RAW 拍照同时开启时，必须按每一路的分辨率、格式、`maxImages` 与 queue 行为分别核算，并确认分析线程及时关闭 `Image`。如果只按相机传感器分辨率乘上一个固定 buffer 数，就会漏掉多 plane、stride 以及各 consumer 独立队列带来的开销。

<!-- gracker-diagram: ch10-04-36-camera-budget -->
![相机预算按输出路径分别核对](../../assets/diagrams/ch10/ch10-04-36-camera-budget.png)

图：预览、录制、分析与 JPEG/RAW 的输出路径可能有不同 buffer 集合；不能只用传感器分辨率乘一个固定数量推导全部容量。

AR 场景还会同时涉及相机输入、环境纹理、深度数据（depth）、网格（mesh）、点云与 render target。如果切换 session 后 GPU 总量与 DMA-BUF inode 持续攀升，就需要把 session 持有者、Surface/Image 生命周期与引擎资源表一同纳入排查，避免遗漏 Java 堆之外的图形资源。

## 8. 观测链的局限与发布检查

把前面涉及的 AOSP 图形内存观测点串起来，各自的分工如下：

- memtrack 为 `dumpsys meminfo` 补充 smaps 看不到的进程图形内存；
- GpuMem 用 eBPF map 保存驱动 `gpu_mem_total` 的全局与进程总量；
- GpuMemTracer 给 Perfetto 提供 trace 启动时的初始快照；
- ftrace 记录 trace 期间的 GPU 总量变化；
- kernel DMA-BUF sysfs/debugfs/fdinfo 描述共享 buffer。

不过，这条观测链还无法提供跨厂商统一的分配调用栈（allocation call stack）、资源名称或碎片率，AOSP 中也没有向应用开放的 GPU 内存规整（compact）API。当排查需要精确到具体的纹理、`VkImage` 或厂商内部 heap 时，就必须结合应用自身的资源注册表、AGI、Vulkan tracker 或目标 GPU 的官方调试工具。

发布前至少确认以下十项：


- 指标名称、单位、设备 build、GPU driver 与采样时间写进报告。
- `Graphics` 摘要与 `EGL mtrack`、`GL mtrack`、`Gfx dev` 没有混写。
- `--gpumem` 支持已验证，0 与“不支持”能够区分。
- Perfetto 同时具备基线和增量，保存解析器版本；多 GPU 查询保留 GPU/轨道维度并检查旧解析器丢失。
- DMA-BUF 按 inode 去重，进程 fd 总和没有冒充系统唯一物理量。
- Hardware Bitmap 通过引用与缓存策略释放，没有依赖随意 `recycle()`。
- Image、Surface、SurfaceTexture、codec、camera session 都有明确负责 close/release 的持有者。
- GL/Vulkan 资源销毁满足 context、share group、queue 和 fence 生命周期。
- 4 KB / 16 KB 差异来自同一 workload（工作负载）实测，没有套用固定增长比例。
- 高水位缓存、GPU 延迟释放和持续泄漏已经用多轮时间线区分。

## 参考资料

- [Android 17 `IMemtrack.aidl`](https://android.googlesource.com/platform/hardware/interfaces/+/refs/tags/android-17.0.0_r1/memtrack/aidl/android/hardware/memtrack/IMemtrack.aidl)
- [Android 17 `android_os_Debug.cpp`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/jni/android_os_Debug.cpp)
- [Android 17 `Debug.MemoryInfo`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/os/Debug.java)
- [Android 17 `GpuService.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/gpuservice/GpuService.cpp)
- [Android 17 `GpuMem.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/gpuservice/gpumem/GpuMem.cpp)
- [Android 17 `GpuMemTracer.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/gpuservice/tracing/GpuMemTracer.cpp)
- [Android 17 `BufferQueueCore.cpp`](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/libs/gui/BufferQueueCore.cpp)
- [Kernel `android17-6.18-2026-06_r6` `gpu_mem.h`](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/trace/events/gpu_mem.h)
- [Kernel `android17-6.18-2026-06_r6` `dma-heap.c`](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/drivers/dma-buf/dma-heap.c)
- [Linux DMA-BUF 文档](https://docs.kernel.org/driver-api/dma-buf.html)
- [Perfetto GPU 数据源](https://perfetto.dev/docs/data-sources/gpu)
- [Perfetto `android.gpu.memory`](https://perfetto.dev/docs/analysis/stdlib-docs#androidgpu-memory)
- [Bitmap API](https://developer.android.com/reference/android/graphics/Bitmap)
- [Bitmap.Config API](https://developer.android.com/reference/android/graphics/Bitmap.Config)
- [TextureView API](https://developer.android.com/reference/android/view/TextureView)
- [Android GPU Inspector](https://developer.android.com/agi)

- [Android17 gpuMem.c](https://android.googlesource.com/platform/frameworks/native/+/refs/tags/android-17.0.0_r1/services/gpuservice/bpfprogs/gpuMem.c)
- [Android17 libmemtrack](https://android.googlesource.com/platform/system/memory/libmemtrack/+/refs/tags/android-17.0.0_r1/memtrack.cpp)
- [Android17 libmeminfo](https://android.googlesource.com/platform/system/memory/libmeminfo/+/refs/tags/android-17.0.0_r1/androidprocheaps.cpp)
- [Perfetto固定r1 memory.sql](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/perfetto_sql/stdlib/android/gpu/memory.sql)
- [Perfetto固定r1 GPU parser](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/src/trace_processor/importers/proto/gpu_event_parser.cc)
- [OpenGL ES3.2规格 §2.6、§5](https://registry.khronos.org/OpenGL/specs/es/3.2/es_spec_3.2.pdf)
- [EGL eglDestroySurface](https://registry.khronos.org/EGL/sdk/docs/man/html/eglDestroySurface.xhtml)
- [Vulkan vkFreeMemory](https://docs.vulkan.org/refpages/latest/refpages/source/vkFreeMemory.html)
- [Vulkan wait-idle示例](https://docs.vulkan.org/samples/latest/samples/performance/wait_idle/README.html)
- [SurfaceTexture](https://developer.android.com/reference/android/graphics/SurfaceTexture)
- [Surface](https://developer.android.com/reference/android/view/Surface)
- [ImageReader](https://developer.android.com/reference/android/media/ImageReader)
- [16KB page sizes](https://developer.android.com/guide/practices/page-sizes)

- [Perfetto heapprofd 与 ART allocation profiling](https://perfetto.dev/docs/data-sources/native-heap-profiler)

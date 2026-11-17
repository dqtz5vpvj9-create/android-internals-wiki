---
title: 内存抖动与频繁 GC
chapter: '10.3'
section: '10.3'
status: finalized
applicable_versions: Android 8.0 (API 26) - Android 17 (API 37)
last_verified: '2026-10-24'
last_verified_against: AOSP android-17.0.0_r1（ART 分配器、heap/runtime/mark_compact、BinderInternal、Message/MotionEvent/Bitmap）/ ACK android17-6.18-2026-06_r6 UFFD/mremap / 固定 r1 Perfetto CLI 与官方 heapprofd、Studio allocation 文档 / Compose Runtime 1.12.0-rc01 发布源码、AAR 和 Gradle module；官方 1.12 release notes、strong skipping / Kotlin 2.2.20 编译与 stdlib 源码
verified_note: 2026-10-24 核对固定 r1 分配/CMC/GcWatcher/Message 分支、内核 UFFD、Perfetto CLI、Studio 统计口径与 Compose 1.12.0-rc01 实际发布源码及 AAR 元数据；示例仅做主机编译/行为验证，不声称 Android 设备性能实测
confidence: high
sources:
- type: material
  path: ../Cubox/Android深入卡顿分析与实践-2023-12-19.md
- type: official
  path: developer.android.com/studio/profile/record-java-kotlin-allocations
- type: official
  path: developer.android.com/topic/performance/memory/manage-app-memory
- type: official
  path: perfetto.dev/docs/data-sources/native-heap-profiler
- type: official
  path: source.android.com/docs/core/runtime/gc-debug
- type: aosp
  path: android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/collector_type.h
- type: aosp
  path: android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/runtime.cc
- type: aosp
  path: android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/heap.cc
- type: aosp
  path: android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/collector/mark_compact.cc
- type: kernel
  path: android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/fs/userfaultfd.c
- type: kernel
  path: android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/mm/mremap.c
- type: official
  path: developer.android.com/jetpack/androidx/releases/compose-runtime
- type: official
  path: developer.android.com/develop/ui/compose/performance/stability/strongskipping
- type: official
  path: developer.android.com/develop/ui/compose/performance/bestpractices
- type: official
  path: developer.android.com/reference/kotlin/androidx/compose/runtime/MutableIntState
- type: reference
  path: kotlinlang.org/docs/inline-classes.html
tags:
- memory
- gc
- churn
- object-pool
- tlab
- autoboxing
- heapprofd
related_chapters:
- '4.2'
- '7.1'
- '10.1'
- '10.2'
---

# 内存抖动与频繁 GC

内存抖动（allocation churn）描述的是高频分配与回收：大量对象在短时间内创建又很快失去引用，堆曲线随之反复攀升与回落。它和内存泄漏是两种不同的问题——泄漏是指对象超出预期生命周期仍被强引用持有，如果持续累积，GC 后的堆基线就会不断抬升，而单个或有界泄漏则可能停留在平台期。在真实页面中，这两种现象也可能并存，比如页面既在每帧创建临时对象，又把少量对象留在了错误的生命周期里。

看到单次 GC 事件本身只是一条线索。要把 GC 和卡顿关联起来，诊断必须证明三件事：目标场景的分配速率确实异常；GC 活动或分配等待与慢帧时间重叠；削减热点分配后，同场景的帧时间与 GC 指标随之改善。这里说的热点分配，指的是在目标时间窗内反复出现、或累计字节数较高的分配调用栈。排查时抖动与泄漏应当分开取证：前者关注时间窗内的分配速率与创建调用栈，后者关注 GC 后依然存活的对象数量和引用关系。

## 从分配到慢帧发生了什么

小对象分配走的是快路径，为什么依然可能拖慢渲染帧？这一节把中间的因果链条补齐：先看小对象分配快在哪里、后续成本又落在何处，再对照源码梳理 CMC 收集器的停顿阶段，最后把这些影响对齐到帧时间线上。

### 分配的快路径与后续成本

ART 为小对象留出了一条线程本地的分配快路径。TLAB（Thread-Local Allocation Buffer，线程本地分配缓冲区）让线程可以在自己的缓冲区中直接推进分配指针，省去每次分配抢占堆全局锁的开销。这条快路径受收集器类型与 `use_tlab` 配置共同控制：在 `android-17.0.0_r1` 中，CC 收集器开启 TLAB 时选择 `RegionTLAB`，关闭时选择 `Region`；CMC 收集器则分别选择 `TLAB` 或 `BumpPointer`。需要注意，大对象空间、插桩逻辑以及慢路径各有独立的分配分支，分析分配路径时必须把它们区分开，避免将所有分配都简化成一次线程本地指针移动。

<!-- gracker-diagram: ch10-03-03-tlab-pointer -->
![TLAB 快路径推进线程自己的指针](../../assets/diagrams/ch10/ch10-03-03-tlab-pointer.png)

图：TLAB 可容纳该次对象时，线程返回原 pos 并推进指针；空间不足需要申请新 TLAB。这里只画启用 TLAB 后的局部路径。

快路径省掉的是抢锁开销，对象的后续成本还在：

- TLAB 或 RegionTLAB（按堆区域划分的 TLAB）用尽后需要补充空间。
- 分配要计入标记、扫描和回收的工作量；活对象越多，收集器需要处理的引用越多。
- 大对象或突发分配更容易离开最轻的分配路径。
- 回收线程会消耗 CPU 和内存带宽，与 UI 线程、RenderThread（渲染线程）竞争。
- 可分配空间不足时，发起分配的线程可能等待 GC 完成。


以 120 Hz 屏幕为例，理论帧间隔只有约 8.33 ms。把前述成本对齐到帧预算上，只要 GC 暂停、分配等待或 CPU 竞争恰好落在已经接近预算上限的那一帧内，就可能产生未按时呈现的掉帧（missed frame）。至于实际暂停究竟有多长，并没有跨设备通用的常量，结论应以实机 trace 测量为准。

<!-- gracker-diagram: ch10-03-05-gc-frame-timeline -->
![并发 GC 仍可通过不同路径影响帧](../../assets/diagrams/ch10/ch10-03-05-gc-frame-timeline.png)

图：示意轨道分别标出 mutator 暂停、并发 GC 的资源竞争与分配等待；不表示它们每次都同时发生，条宽不代表测量时长。

### CMC 的源码路径与配置条件

先对照源码梳理机制。在 `android-17.0.0_r1` 中，`collector_type.h` 将 `kCollectorTypeCMC` 定义为 **Concurrent mark-compact**；`heap.cc` 在 `gUseUserfaultfd` 为真时，会校验前台收集器为 CMC、后台收集器为 CMCBackground，若启用分代垃圾回收（generational GC），还会创建负责年轻代的 `YoungMarkCompact`。而 `runtime.cc` 在选择 generational GC 时，会同时检查收集器能力、`-Xgc` 启动选项以及 `ShouldUseGenerationalGC()` 的返回值。

这几处源码表明，Android 17 平台具备 CMC 与分代 CMC 的执行路径。但要判断手上的设备实际走了哪条路径，仍应查看目标进程 ART 启动日志里的 collector 描述：源码中存在 `YoungMarkCompact` 只说明平台支持该能力，OEM 配置、ART Mainline 模块以及进程自身的启动选项，依然可能改变每个进程的实际收集器选择。

<!-- gracker-diagram: ed10-03-cmc-config-and-process-evidence -->
![CMC 可选配置与进程实际收集器需要两组证据](../../assets/diagrams/ch10/ed10-03-cmc-config-and-process-evidence.png)

图：固定r1配置/证据关系示意，不是完整ART启动算法。左侧核对ART模块、构建/OEM、进程-Xgc、属性和内核能力；gUseUserfaultfd为真时heap校验CMC/CMCBackground，分代还需collector能力、generational选项及ShouldUseGenerationalGC，强制STW是另一路例外。右侧独立看目标进程启动collector描述，再看这一轮GC/等待trace的实际阶段、pause、allocation wait和CPU。源码存在YoungMarkCompact或平台API相同，不保证每个进程启用分代CMC，也不能由启动collector名称推每轮固定停顿；静态条件需和目标进程运行证据对齐。

常规 UFFD 路径在 `mark_compact.cc` 中会检查 `UFFD_FEATURE_SIGBUS` 与 `MREMAP_DONTUNMAP`；同时，显式 GC 选项、系统属性、内核能力和强制 STW 压缩选项都会影响选择。其中的 `SigbusHandler()` 只处理符合条件的缺页故障：在校验信号原因、压缩状态与地址范围后，按页推进处理。换言之，只有部分对象访问会触发 SIGBUS，ART 接管的也仅是命中这些条件的故障。内核侧实现按 `android17-6.18-2026-06_r6` 的 `fs/userfaultfd.c` 与 `mm/mremap.c` 核对。

<!-- gracker-diagram: ch10-03-08-uffd-fault -->
![UFFD 页面故障只在有效范围内处理](../../assets/diagrams/ch10/ch10-03-08-uffd-fault.png)

图：只画常规 SIGBUS/UFFD 机制；强制 STW 是独立配置例外。并非所有对象访问都会触发故障，也不是每轮 GC 都进入压缩。

在工作阶段上，`RunPhases()` 包含并发标记、MarkingPause、回收与压缩准备；需要压缩时还会执行线程根翻转暂停，随后仅在 UFFD 有效时进入并发 `CompactionPhase()`（某一轮 GC 也可以跳过压缩，强制 STW 则是另一条独立配置路径）。这些机制缩小的是部分 mutator（执行应用代码的线程）的停顿窗口，但 GC 本身的工作量依然存在：只要应用持续制造短命对象，就仍需测量年轻代回收开销、CPU 占用以及分配等待（allocation stall）。

<!-- gracker-diagram: ch10-03-09-cmc-phases -->
![CMC 的暂停和压缩都有实际分支](../../assets/diagrams/ch10/ch10-03-09-cmc-phases.png)

图：阶段名按固定 r1 RunPhases 核对。标记暂停和根翻转暂停仍存在，不捏造每轮固定时长或所有阶段必经关系。

## 识别抖动、泄漏与正常波动

| 现象 | 常见曲线 | 优先证据 | 主要处理方向 |
| --- | --- | --- | --- |
| 短命对象抖动 | 分配量快速增长，GC 后大幅回落 | allocation call stack（分配调用栈）、GC 时间、慢帧重叠 | 降低分配次数或单次大小 |
| 引用泄漏 | 多轮 GC 后存活基线持续上升 | heap dump、Retained Size、GC Root | 修正引用所有权 |
| 缓存或对象池增长 | 上升后停在容量上限 | 容量、命中率、逐出记录 | 校准容量和失效策略 |
| 大对象突发 | 单次或少数分配拉高曲线 | 分配大小、调用栈、业务事件 | 复用 buffer、分块或移出关键路径 |
| 正常预热 | 启动阶段增长，随后稳定 | 类加载、资源初始化、后续稳态 | 通常不改，保留基线 |

阅读这张表时，先按曲线形态做初步归类，再通过对应的证据来验证。“锯齿形”曲线只是表象线索：如果每次 GC 结束后堆基线也在同步上升，就必须同时排查存活对象泄漏；反之，如果分配量虽然偏高，但帧时间、CPU 竞争和 GC 等待都没有出现退化，优化的优先级就可以往后放。

## 用证据定位

定位问题需要借助工具采集数据：Android Studio 擅长录制 Java/Kotlin 分配细节，heapprofd 负责调用栈采样，系统 trace 则能把分配、GC 与渲染帧放进同一条时间窗口。

### Android Studio：记录 Java/Kotlin 分配

Android Studio 的 “Track Memory Consumption (Java/Kotlin Allocations)” 可以展示对象的分配类型、大小、线程、调用栈和释放时间。需要注意，这项 allocation recording 功能仅在 `debuggable` 构建下可用，只配置 `profileable` 并不足以开启。由于完整记录会明显拖慢高频分配的应用，官方工具因此提供了抽样（sampled）模式以降低运行影响。

一次有效的录制应满足以下五个条件：

1. 在可重复的用户动作前开始录制。
2. 只保留足以覆盖该动作的时间窗。
3. 分别按 Allocations、Allocation Size 与 Total Count 排序。
4. 回到调用栈，确认对象来自业务路径、profiler（分析器）自身或框架预热。
5. 修复后在同设备、同构建类型、同数据集下复测。

分析 churn 时，重点关注时间窗内的累计分配次数与字节数。Studio 的 `Total Count = Allocations - Deallocations`、`Remaining Size = Allocations Size - Deallocations Size` 统计范围都限定在当前选中的记录区间内，只描述这一次录制期内的净变化；若要清点进程完整的存活堆，或在泄漏分析中核查跨越预期生命周期的存活对象与引用关系，仍要借助 heap dump。

<!-- gracker-diagram: ch10-03-11-studio-columns -->
![Studio 的净值列有记录区间边界](../../assets/diagrams/ch10/ch10-03-11-studio-columns.png)

图：所选区间的创建减释放用于解读这次录制；它不自动包含录制外的全部存活对象，引用关系仍由 heap dump 取证。

### Perfetto heapprofd：调用栈采样

heapprofd 从 Android 10 起支持采样 native `malloc/free` 分配调用栈，覆盖经由对应分配器的 `new/delete`（自定义分配器要接入这条路径，需完成相应的 heap 集成）。从 Android 12 起，还可以把 heap 指定为 `com.android.art`，采样 Java 分配调用栈。不过，ART allocation profile 只记录对象的创建位置，对象删除时间和完整引用图都不在它的覆盖范围内，分析存活对象的引用关系依然要靠 heap dump。

下面两条命令按 AOSP `android-17.0.0_r1` 所含 Perfetto `tools/heap_profile` 脚本核对；执行前需先取得相应的 Perfetto checkout，并从其根目录运行。若使用不同版本，建议先通过 `--help` 核对参数。

```bash
# Native malloc/free allocation profile
tools/heap_profile android -n com.example.app

# Java allocation profile（Android 12+）
tools/heap_profile android -n com.example.app --heaps com.android.art
```

在日常发布版本的系统镜像（user build）上，heapprofd 只允许分析在 manifest 中标记为 `debuggable` 或 `profileable` 的应用。

解读 Java profile 时，先把两个核心计数区分清楚：`Total allocation size` 和 `Total allocation count` 是根据采样估算的累计创建字节数与次数，即便对象稍后已被 GC 回收也照常计入，因此它们描述的是累计创建量，当前存活堆大小仍要另外采集。此外，运行中附加之前、Zygote 中的分配以及未覆盖的分配器都不会自动补入；如果分配突发导致共享缓冲区溢出，Perfetto 会提前终止 profile，此时需要调大采样间隔（sampling interval）或按官方建议调整缓冲区配置。

<!-- gracker-diagram: ed10-03-profile-modes-and-art-creation-window -->
![按数据语义选择 native profile、ART 创建采样或 heap dump](../../assets/diagrams/ch10/ed10-03-profile-modes-and-art-creation-window.png)

图：三个分支是工具选择而非采集阶段。Android10+ native profile采样对应allocator的malloc/free及new/delete，自定义allocator需集成；Android12+ com.android.art只记录对象创建调用栈；heap dump提供某时刻对象引用用于持有分析。user-build采样目标需profileable或debuggable，Studio Java/Kotlin allocation recording另要求debuggable。图下半仅展开ART：附加前、Zygote及未覆盖allocator不会自动补录，Total allocation size/count是累计创建估算，窗口对象即使后来回收也没有删除时间可扣，不能当当前live set或完整引用图。先确认真实覆盖/结束状态，突发溢出可能提前结束，按sampling interval/缓冲配置处理并保存符号和启动时机；缺口不等零分配，Java/native像素/graphics仍按域区分。

### Perfetto：把分配、GC 和帧放进同一窗口

系统 trace 至少应包含调度、频率、Frame Timeline 与 ART/应用 trace。分析顺序如下：

1. 从 missed frame 或业务事件确定时间窗。
2. 检查 UI 线程是否暂停、处于 Runnable（可运行但在等待 CPU）状态，或正在等待分配。
3. 对齐 GC slice、`HeapTaskDaemon` 活动和 CPU 频率。
4. 用 allocation profile 找到同一场景的高频调用栈。
5. 排除锁竞争、I/O、Binder、thermal throttling（温控限频）等同时发生的原因。

注意区分共现与因果：ART 堆任务线程（`HeapTaskDaemon`）活跃且附近恰好出现慢帧，只说明两者在时间上相近；要确认因果关系，仍需结合线程调度状态、GC 时间片（slice）以及优化前后的对照数据进行验证。

### framework 的 `GcWatcher` 机制

framework 内部有一套用于感知 GC 的机制：Android 17 的 `BinderInternal.GcWatcher` 仍通过 `WeakReference` 与 `finalize()` 来检测 GC，并向内部观察者（watcher）分发回调。不过，它依赖的两个条件在应用侧都站不住脚——`BinderInternal` 属于隐藏 API，而终结处理（finalization）的执行时机也没有确定性。因此，线上 GC 监控应避开这种写法，watcher 的 `finalize()` 也无法当作每次 GC 的精确通知。

<!-- gracker-diagram: ch10-03-16-gcwatcher -->
![GcWatcher 的回调来自终结处理链](../../assets/diagrams/ch10/ch10-03-16-gcwatcher.png)

图：按 BinderInternal 固定 r1 的 finalize / watcher / rearm 逻辑说明边界；不把内部实现包装成可用的 App GC 通知协议。

开发期我们主要依靠 Android Studio、Perfetto 与 ART 日志；线上环境则只保留经过开销评估的场景指标。Android 17 的 `ProfilingManager` 可以提供受系统策略控制的分析产物（profile artifact），但它同样不提供实时的 GC 回调 API。

## 常见分配热点

拿到 allocation profile 之后，可以先从下面几类高发位置筛选候选热点。

### `onDraw()`、布局和动画回调

每帧回调会让同一处分配随屏幕刷新反复执行。不过，`Paint`、`Path`、`Rect`、数组、Lambda 或临时集合究竟是不是真正的热点，要靠 allocation profile（分配记录）说话，单看代码外观只能用来圈定嫌疑范围。

下面的示例展示了如何把可复用的绘制状态移出 `onDraw()`：

```kotlin
class MeterView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {
    private val barPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.RED
    }
    private val barBounds = RectF()

    override fun onDraw(canvas: Canvas) {
        barBounds.set(0f, 0f, width.toFloat(), height.toFloat())
        canvas.drawRect(barBounds, barPaint)
    }
}
```

在这个示例里，`Paint` 与 `RectF` 只在 View 创建时分配一次，后续每帧回调里仅更新字段。如果需要跨线程使用绘制状态，复用对象还必须满足相应的线程所有权要求。

<!-- gracker-diagram: ch10-03-17-view-reuse -->
![绘制状态随 View 保存而非逐帧重建](../../assets/diagrams/ch10/ch10-03-17-view-reuse.png)

图：示例每个 View 创建一组 Paint 和 RectF；各帧更新同一个 RectF，再传给 Canvas。这里只减少显式绘制状态的重建，不能代表整帧零分配。

### 循环、列表绑定与流式转换

在循环内部创建集合、正则表达式、格式化器或中间数据传输对象（DTO），会让分配次数随着元素数量成倍增加。Kotlin 的集合操作链（collection pipeline）同样可能生成中间集合；改用 `Sequence` 虽然能减少部分中间集合，但迭代器包装与间接调用也有成本，元素很少的短小集合未必能从中受益。

优化这类循环时，可以先问自己三个问题：

- 中间结果是否必须保存？
- 容器能否移到循环外并通过 `clear()` 复用？
- 能否提供预估容量，减少数组扩容与复制？

复用容器之前，务必确认调用方没有把容器引用传递给异步任务或直接作为返回值暴露出去；同一实例一旦被跨步或并发误用，就会引发数据覆盖和竞态错误。

### 字符串与日志

循环中的 `result += item` 会反复生成新的 String 对象。同样容易忽略的是日志调用：参数表达式在进入日志方法前就已经完成求值，等到方法内部再判断日志开关时，临时文本早已构造出来。

下面的示例将多次不可变字符串拼接改用同一个可变构建器（builder）完成：

```kotlin
fun joinNames(items: List<String>): String = buildString {
    items.forEachIndexed { index, item ->
        if (index > 0) append(", ")
        append(item)
    }
}
```

返回结果 String 本身仍会触发一次分配，这段代码省下的是循环内的重复拷贝。对于高频日志，可以在调用点先检查日志级别，或改用接收 Lambda 的延迟求值日志 API，确保禁用日志时不构造文本。

### 装箱

泛型集合、可空原始类型以及接口调用都可能将 `Int`、`Long` 等原始值包装成堆对象，这一过程称为装箱。不过装箱未必每次都会产生新对象：JVM 对部分小范围数值维护了包装对象缓存（wrapper cache），编译器也可能在局部消除一些临时对象。是否值得优化，最终要看该路径在 allocation profile 中出现的频率和字节数。

在已经证实的热点路径中，可以评估以下替代结构：

| 当前结构 | 候选结构 |
| --- | --- |
| `HashMap<Int, T>` | `SparseArray<T>` |
| `HashMap<Int, Int>` | `SparseIntArray` |
| `HashMap<Int, Long>` | `SparseLongArray` |
| `HashMap<Long, T>` | `LongSparseArray<T>` |
| `List<Int>` 的密集数值计算 | `IntArray` |

`SparseArray` 内部维护了排序后的原始类型 key 数组，能省去 key 的装箱开销，但它的查找和插入特征与哈希表不同。实际选型应基于真实数据规模与读写模式，通过基准测试（benchmark）来决定，“元素超过某个固定数量就切换”这类统一经验规则并不具备普适依据。

<!-- gracker-diagram: ch10-03-20-boxing-containers -->
![原始类型存储与泛型对象存储不同](../../assets/diagrams/ch10/ch10-03-20-boxing-containers.png)

图：SparseArray 的 int key 与原始类型数组可减少特定装箱；values 的对象表示与查找更新代价仍要分别看。缓存或编译器优化也可能避免新 wrapper。

### 大型 buffer 与图像

相机帧、音视频编解码、Bitmap 与序列化操作常会产生大数组或 native buffer。这类问题的 Java 对象数量未必很高，但累计分配字节数（allocation bytes）却很可观，分析时如果只按对象数量排序很容易漏掉。常规优化方向包括固定数量的 buffer 轮转、按目标显示尺寸解码、分块处理以及遵守三方库的缓冲池所有权协议。

从 Android 8.0（API 26）起，普通软件 Bitmap 的像素数据位于 native heap，而 `Bitmap.Config.HARDWARE` 的像素保存在图形内存中，归类统计时要把这两种路径分开。由图片库管理的 Bitmap 应按库的协议归还缓冲池；只要无法确定其他调用方是否还在使用该 Bitmap，业务代码就应避免提前调用 `recycle()`。


## 优化策略

### 优先删除分配

收益最高且风险较低的改动通常是：

- 把逐帧创建的绘制对象变为 View 或 renderer（渲染器）的成员。
- 移除不必要的中间集合和 DTO。
- 给已知规模的数组、集合、builder（构建器）设置合理初始容量。
- 让相机、音视频与网络 buffer 按清晰所有权复用。
- 关闭的日志在调用点跳过字符串与参数构造。
- 密集数值路径使用原始类型数组，减少泛型装箱。

预分配会把成本移到更早的时机，并延长对象的存活期。如果应用启动路径本就吃紧，或者预分配的对象很少用到，它反而可能拖累整体表现；因此要不要做预分配，应在目标场景的基准测试中评估后再定。

<!-- gracker-diagram: ch10-03-23-preallocation -->
![预分配把代价移到更早并延长持有](../../assets/diagrams/ch10/ch10-03-23-preallocation.png)

图：两条示意轨道比较成本落点。预分配可能改善目标操作，也可能拖慢启动并扩大存活集；这里没有推定净收益或测量时长。

### 对象池的适用条件

Android framework 自身的对象池化也受版本和运行模式制约。在 `android-17.0.0_r1` 中，`Message.obtain()` 只有在 `MessageQueue.getUseConcurrent()` 为假时才会尝试复用全局池；如果走了并发队列路径，就会直接创建新的 `Message`，而 `recycleUnchecked()` 也只清理引用并标记使用状态。相比之下，`MotionEvent.obtain()/recycle()` 仍然拥有独立的 recycler。因此看到 `obtain` 这样的 API 名称时，不要默认它一定会命中对象池，也不要替 framework 提前归还仍在使用的对象。业务对象若想引入对象池，必须先满足以下六个条件：

<!-- gracker-diagram: ch10-03-24-framework-pool-branches -->
![Message 的并发队列路径不使用旧全局池](../../assets/diagrams/ch10/ch10-03-24-framework-pool-branches.png)

图：固定 r1 的 Message 池受 MessageQueue.getUseConcurrent() 控制。MotionEvent 有独立 recycler，不能据 obtain 名称推断所有模式都池化。

- profiler 已确认分配点占据显著成本；
- 对象构造或 backing storage（底层存储）成本较高；
- 同时在用的实例数有稳定上限；
- `acquire/release`（获取/归还）所有权能被审查；
- 每个字段都能可靠重置；
- 池命中率、容量与内存占用可观测。

对象池会延长对象的存活周期，同时也带来同步锁、状态清理以及持有泄漏的风险。对于小型不可变对象或构造成本很低的对象，直接交给 ART 的快路径分配与年轻代回收往往更合适。池容量应由并发峰值和实测命中率决定，16、32 这类经验数字不适合直接照搬。

<!-- gracker-diagram: ed10-03-buffer-pool-return-and-reset -->
![以 buffer 为例画出业务池的归还与重置闭环](../../assets/diagrams/ch10/ed10-03-buffer-pool-return-and-reset.png)

图：以buffer为例的业务所有权协议，不假定所有库同实现，也不是建议所有对象池化。先用profiler确认热点和收益，定义owner、容量及同时在用数上限、可靠重置与观测。acquire只复用已归还空闲实例，未命中按业务容量策略创建/等待，不默认把等待放主线程。生产者交接后不能覆盖；同步或异步消费者实际全部完成才能归还，投递任务不是完成。release后按类型协议重置引用、数据、错误与外部资源，再按容量留空闲池或丢弃；虚线表示完成归还/清理后可下一次acquire。持续观察命中率、并发峰值、在用字节、存活集、同步/清理成本，池会延长持有且可能增锁或泄漏，小对象仍可能直接分配更合适；库资源按库协议归还，不提前recycle。

### `System.gc()` 的实际作用

`System.gc()` 只是向虚拟机发出一次 GC 请求：实际执行时机没有任何保证，制造抖动的分配源也依然存在；在生产代码里主动触发，还可能让回收恰好落在用户交互的敏感窗口中。测试工具可以在明确目的下借助它辅助观测，而产品代码真正需要治理的仍是分配速率、对象生命周期与缓存容量。

## Kotlin value class 的边界

`@JvmInline value class` 在 JVM 上可以直接用底层值来表示，适合在不引入额外包装开销的前提下为原始类型增加类型安全。不过，能够省去包装对象（wrapper）的只涵盖部分路径：例如下面定义的 `UserId`，在直接传参与局部变量路径上通常可以展开为原生 `long`。

```kotlin
@JvmInline
value class UserId(val raw: Long)
```

Kotlin 官方文档指出，涉及泛型、接口和可空类型时仍可能需要装箱生成 wrapper。就这里以 `Long` 为底层的 `UserId` 而言，放进 `List<UserId>`、传给泛型函数，或者作为 `UserId?` 使用时，都存在装箱路径；而只有当该类型实际实现了某个接口时，才会发生以该接口类型传递时的装箱（上面的 `UserId` 并未实现 `Comparable<UserId>`，无法直接传给接收该接口的参数）。简言之，value class 只是消除特定路径装箱的工具，泛型集合并不会因此自动变成原始类型存储；如果是高频密集的数值计算，仍然可以评估使用 `LongArray`。

<!-- gracker-diagram: ch10-03-27-valueclass-representation -->
![UserId 的底层 long 不覆盖所有用法](../../assets/diagrams/ch10/ch10-03-27-valueclass-representation.png)

图：对本文 Long 底层 UserId，直接路径可使用 long，泛型和 nullable 有 wrapper 路径；接口传递必须先满足实际实现该接口的类型关系。

## Jetpack Compose 中的分配

以本文核验的 Compose Runtime 1.12.0-rc01 为例，默认的 GapComposer 使用 SlotTable 保存组合结构，并配合 RecomposeScope（重组作用域）与快照状态（snapshot state）工作；而 LinkTable/LinkComposer 自 1.11 起作为实验性路径存在，在该制品中 `ComposeRuntimeFlags.isLinkBufferComposerEnabled` 默认值为 `false`，且受构建期 flag 与 R8 规则影响。两者属于按条件选择的实现分支，不会在每次 composition 时依次经过两张表。组合结构本身固然占用内存，但业务代码里更常见的抖动来源，往往是重组期间反复执行的对象构造、不断变化的参数身份以及不必要的状态派生。

<!-- gracker-diagram: ch10-03-28-compose-engines -->
![组合结构的两个实现是条件选择](../../assets/diagrams/ch10/ch10-03-28-compose-engines.png)

图：固定核验 RC 的实验 flag 默认 false，默认使用 GapComposer / SlotTable；LinkComposer / LinkTable 是可选择的实验路径，不能串成必经两级。

### `remember` 与重组期重建

在可组合函数（composable）中直接创建集合、格式化器或状态对象时，只要函数重新执行就会创建新实例；需要跨重组保留的对象，应当用 `remember(keys)` 缓存，并让 key 精确描述对象何时失效。

下面的示例让 `formatter` 只在 `locale` 改变时重建：

```kotlin
@Composable
fun PriceText(
    price: BigDecimal,
    locale: Locale,
) {
    val formatter = remember(locale) {
        NumberFormat.getCurrencyInstance(locale)
    }
    Text(formatter.format(price))
}
```

`remember(locale)` 在该调用位置仍留在组合中且 key 按 `==` 未变时会复用 `formatter`；一旦移出 composition 再重新进入就会重建，且无法跨进程保留。此外，`formatter.format(price)` 在函数体执行时依然会运行并通常产生结果字符串，因此缓存 `formatter` 省掉的只是一部分分配；还要注意 `NumberFormat` 属于可变对象，需要遵守线程所有权。

<!-- gracker-diagram: ch10-03-29-remember-lifetime -->
![remember 缓存位置与 key 决定 formatter 生命周期](../../assets/diagrams/ch10/ch10-03-29-remember-lifetime.png)

图：缓存的是 formatter 实例。只有组保留且 key 未变才复用，不能把 remember 画成持久缓存或整段函数永不执行。

需要注意的是，`remember` 会延长对象的存活时间，不适合缓存可能无限增长的数据。如果 key 变化过于频繁，缓存就会反复失效；而如果遗漏了关键 key，又可能读到与新输入不匹配的旧对象。

### strong skipping 的跳过条件

自 Kotlin 2.0.20 起，Compose 编译器默认启用强跳过模式（strong skipping）。在此模式下，可重启 composable 默认具备跳过资格（可以通过 `@NonSkippableComposable` 显式退出），而不可重启函数则不会因此变为可跳过。参数比较方面，unstable 参数按引用相等（`===`）比较，stable 参数按 `equals()` 比较。不过参数相等只是前提：如果作用域内读取的 state 发生了有效变化、属于首次插入，或者触发了其他强制重组条件，该函数体仍可能被要求执行。

与此同时，编译器还会自动记忆 composable 内捕获了外部值的 Lambda：捕获的 unstable 值按身份比较，stable 值按 `equals()` 比较（可用 `@DontMemoize` 退出）。这与手写 `remember(keys)` 时对所有 key 一律使用 `==` 比较的规则不同，具体效果应以目标工程的编译配置和编译器报告为准。

<!-- gracker-diagram: ed10-03-strong-skip-and-lambda-rules -->
![强跳过的函数资格与 Lambda 记忆是两个并列机制](../../assets/diagrams/ch10/ed10-03-strong-skip-and-lambda-rules.png)

图：Kotlin2.0.20起默认strong skipping，目标工程仍核对编译配置/报告。左支函数资格：restartable默认可跳过，NonSkippable可退出，不可重启不因此变可跳过；参数unstable按===、stable按equals，参数相等仍可被读取state有效失效、首次插入或强制重组要求执行，资格/参数/运行条件合适才可能跳过函数体。右支为并列自动Lambda记忆：不稳定capture===、稳定equals，DontMemoize退出。右下手写remember所有key==仅作独立规则对照，没有从自动Lambda到它的执行箭头，不把unstable手写key改按身份比较。Stable是行为契约，误标可漏UI更新，实际分配与重组效果继续由编译报告和目标allocation profile确认。

`@Stable` 本质上是一份行为契约：公开属性的变化必须能被 Compose 感知，`equals()` 也必须遵守约定。如果为了跳过重组而随意加上 `@Stable`，一旦标注错误，UI 就可能漏掉更新。优化前建议先通过 Compose 编译器报告（compiler reports）核对稳定性推断，再针对频繁重组的节点下手。

### `derivedStateOf` 的适用条件

`derivedStateOf` 适合“输入变化频率高、输出变化频率低”的场景，比如列表滚动位置持续变化，但按钮只需要关心“是否已经离开列表顶部”。需要注意，它本身也有维护依赖追踪与计算状态的成本：下游重组虽然减少了，但上游依赖变化时依然会更新，派生值也仍会重算。无 policy 的重载与显式传入 `SnapshotMutationPolicy` 的重载具有不同的等价性约定，下游究竟是否失效还取决于具体观察者。如果每次输入变化都必然要求更新结果（例如两个输入框每次改动都要重新拼接文本），直接计算往往更简单划算。

<!-- gracker-diagram: ch10-03-32-derived-state -->
![派生阈值减少下游更新，计算仍有成本](../../assets/diagrams/ch10/ch10-03-32-derived-state.png)

图：逻辑值序列只是示例。derivedStateOf 不承诺永不重算；有无 mutation policy 的重载与观察者等价判断需分别解释。

Compose 官方示例通常把 `derivedStateOf` 放进 `remember` 中，这一写法在底层有明确依据：Compose Runtime 1.12.0-beta01 修复了一个潜在的对象保留问题——未正确 `remember` 的派生状态（derived state）在 forward write（前向写入）路径上可能一直被 composition 持有到销毁。该修复包含在 2026-07-29 发布的 1.12.0-rc01，以及后续的 1.12.0 稳定版（2026-08-12）和 1.12.1（2026-09-09；相对 1.12.0 无改动）。这里以 1.12.0-rc01 制品作机制核验，实际工程升级仍应结合各自的版本与稳定性策略评估。

### 原始类型 state

对于计数器等高频更新的数值状态，可以使用 `mutableIntStateOf()`、`mutableLongStateOf()` 等原始类型 state API，并通过 `intValue`、`longValue` 访问，从而减少 `MutableState<Int>` 在 JVM 路径上的装箱机会。不过这是否成为瓶颈仍需用 allocation profile 验证——在多数界面里，UI 状态的读写频率与重组范围往往比单个包装对象更值得优先排查。

<!-- gracker-diagram: ch10-03-33-primitive-state -->
![原始类型 state 的存储和访问要配套](../../assets/diagrams/ch10/ch10-03-33-primitive-state.png)

图：MutableIntState 以原始 int 存值并提供 intValue；通过泛型 value 桥接访问仍有装箱语义。优化后也要验证重组范围。

### Compose 与 Android 17 的版本关系

Compose 通过 AndroidX 独立发布，并不与平台 API 级别一一绑定。⚠ 这里有一处值得注意的证据差异：1.12.0-alpha01 发布说明中写着 `compileSdk 37` 与最低 AGP（Android Gradle Plugin）`9.2.0`；但本次下载核验的 `runtime-android:1.12.0-rc01` AAR 中，`aar-metadata.properties` 声明的却是 `minCompileSdk=34` 与 `minAndroidGradlePluginVersion=8.1.1`，对应的 Gradle module Android 变体也指向该 AAR。因此，最低工具链要求应以实际解析到的制品、其他依赖与本地构建结果为准，alpha 发布说明代表不了所有 RC 消费者。说到底，库自身的 `compileSdk`、消费者的最低构建要求、设备运行时的平台 API 以及 ART 收集器属于四个不同维度，单靠版本对应推不出 Android 17 专属的 SlotTable、LinkTable 或 Lazy list GC 行为。

## 验证优化

优化前后应当使用同一套测试脚本与数据集来对照：

| 维度 | 建议指标 |
| --- | --- |
| 分配 | 每次业务操作的 allocation count、allocation bytes、热点调用栈占比 |
| GC | 事件次数、暂停区间、blocking GC/allocation wait、GC 线程 CPU |
| 帧 | Frame Timeline 的 missed frame、帧时长分位数 |
| 资源 | Java heap、native heap、graphics、RSS/PSS 与 CPU 频率 |
| 正确性 | 对象池状态、并发、画面、数据一致性和生命周期 |

验收时不能只盯峰值 heap，否则很容易漏掉“总分配量下降但存活集反而上升”的情况；反过来只比较 GC 次数也不够全面，因为 GC 次数还会受到堆上限、收集器类型和设备配置的影响。只有把目标场景的分配速率、GC 开销、帧时间与功能正确性同时纳入验收，得出的结论才具备可复用性。


## 排查清单

- 高分配发生在启动、滚动、动画、相机、编解码还是后台任务？
- 对象是短命、长期存活，还是被缓存/池持有？
- 排序依据是 allocation count、bytes 还是 live objects？
- 慢帧时间窗内是否存在 GC pause、allocation wait 或 GC CPU 竞争？
- profiler 自身是否改变了应用速度或内存分类？
- `onDraw()`、循环和日志是否仍有可移出的对象构造？
- 装箱是否经过 allocation call stack 证实？
- 对象池是否有容量、重置、所有权和并发规则？
- Compose 的 `remember` key、参数身份和重组范围是否符合预期？
- 修复后是否在相同构建、设备、数据和操作脚本下复测？

## 与其他章节的关系

- **4.2 ART 虚拟机内存管理**：CC、CMC、TLAB、RegionTLAB 与 GC 日志。
- **7.1/7.2 卡顿分析**：Frame Timeline、线程状态与 CPU 竞争。
- [10.1 App 内存分析与案例](01-app-memory-analysis-cases.md)：Java、native、graphics 与 mmap 的分类工具，缓存、pool、碎片和虚拟地址空间的增长诊断，以及 MemoryThrashing 的平台边界与差分采样。
- [23.2 内存泄漏检测与治理](../../part5-app/ch23-memory-practice/02-memory-leak-governance.md)：存活对象、GC Root 与引用所有权。
- **10.2 低内存影响**：进程内 GC 与整机回收压力的区别。

## 参考资料

- [Android Studio：Record Java/Kotlin allocations](https://developer.android.com/studio/profile/record-java-kotlin-allocations)
- [Android Developers：Manage your app's memory](https://developer.android.com/topic/performance/memory/manage-app-memory)
- [AOSP：Debug ART garbage collection](https://source.android.com/docs/core/runtime/gc-debug)
- [Perfetto：Callstack-based allocation profiling](https://perfetto.dev/docs/data-sources/native-heap-profiler)
- [AOSP `collector_type.h`（android-17.0.0_r1）](https://android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/collector_type.h)
- [AOSP `runtime.cc`（android-17.0.0_r1）](https://android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/runtime.cc)
- [AOSP `heap.cc`（android-17.0.0_r1）](https://android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/heap.cc)
- [AOSP `mark_compact.cc`（android-17.0.0_r1）](https://android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/collector/mark_compact.cc)
- [AOSP `region_space.cc`（android-17.0.0_r1）](https://android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/space/region_space.cc)
- [AOSP `BinderInternal.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/com/android/internal/os/BinderInternal.java)
- [Android Common Kernel `fs/userfaultfd.c`（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/fs/userfaultfd.c)
- [Android Common Kernel `mm/mremap.c`（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/mm/mremap.c)
- [Android Developers：SparseArray](https://developer.android.com/reference/android/util/SparseArray)
- [Kotlin：Inline value classes](https://kotlinlang.org/docs/inline-classes.html)
- [Compose：Strong skipping mode](https://developer.android.com/develop/ui/compose/performance/stability/strongskipping)
- [Compose：Performance best practices](https://developer.android.com/develop/ui/compose/performance/bestpractices)
- [Compose Runtime：MutableIntState](https://developer.android.com/reference/kotlin/androidx/compose/runtime/MutableIntState)
- [Compose Runtime release notes](https://developer.android.com/jetpack/androidx/releases/compose-runtime)

- [AOSP `heap-inl.h`（android-17.0.0_r1）](https://android.googlesource.com/platform/art/+/refs/tags/android-17.0.0_r1/runtime/gc/heap-inl.h)
- [AOSP `Message.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/os/Message.java)
- [AOSP `MotionEvent.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/view/MotionEvent.java)
- [Perfetto `tools/heap_profile`（android-17.0.0_r1）](https://android.googlesource.com/platform/external/perfetto/+/refs/tags/android-17.0.0_r1/tools/heap_profile)
- [Compose 1.12.0-rc01 Android 发布源码 JAR](https://dl.google.com/dl/android/maven2/androidx/compose/runtime/runtime-android/1.12.0-rc01/runtime-android-1.12.0-rc01-sources.jar)
- [Compose 1.12.0-rc01 AAR](https://dl.google.com/dl/android/maven2/androidx/compose/runtime/runtime-android/1.12.0-rc01/runtime-android-1.12.0-rc01.aar)
- [Compose 1.12.0-rc01 Gradle module](https://dl.google.com/dl/android/maven2/androidx/compose/runtime/runtime-android/1.12.0-rc01/runtime-android-1.12.0-rc01.module)
- [Android Developers：Managing Bitmap Memory](https://developer.android.com/topic/performance/graphics/manage-memory)

---
title: App 内存分析与案例
chapter: '10.1'
applicable_versions: Android 8.0 (API 26) - Android 17 (API 37)
last_verified: '2026-10-24'
last_verified_against: AOSP android-17.0.0_r1 / kernel android17-6.18-2026-06_r6; Android Developers memory/profiling/trim docs and Perfetto heapprofd docs checked 2026-10-24
confidence: medium
sources:
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/os/Debug.java
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/app/ActivityManager.java
- type: aosp
  path: https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/app/ApplicationExitInfo.java
- type: aosp
  path: https://android.googlesource.com/platform/hardware/interfaces/+/refs/tags/android-17.0.0_r1/memtrack/aidl/android/hardware/memtrack/IMemtrack.aidl
- type: aosp
  path: https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/lmkd.cpp
- type: aosp
  path: https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/libpsi/psi.cpp
- type: aosp
  path: https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/libpsi/include/psi/psi.h
- type: aosp
  path: https://android.googlesource.com/platform/system/memory/libmeminfo/+/refs/tags/android-17.0.0_r1/include/meminfo/procmeminfo.h
- type: kernel
  path: https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/kernel/sched/psi.c
- type: blog
  path: https://juejin.cn/post/7677254638325727242
  note: Android PSI libpsi 源码解析
- type: official
  path: https://developer.android.com/topic/performance/memory-management
- type: official
  path: https://developer.android.com/studio/profile/capture-heap-dump
- type: official
  path: https://perfetto.dev/docs/data-sources/native-heap-profiler
- type: official
  path: https://developer.android.com/ndk/guides/memory-debug
- type: official
  path: https://developer.android.com/ndk/guides/wrap-script
- type: official
  path: https://developer.android.com/guide/practices/page-sizes
- type: blog
  path: Blog/Blog/source/_posts/Android-Jank-Due-To-Low-Memory.md
- type: blog
  path: Cubox/谁动了我的内存，揭秘 OOM 崩溃下降 90% 的秘密-2022-07-25.md
- type: blog
  path: Cubox/抖音renderD128系统级疑难OOM分析与解决-2025-05-06.md
- type: blog
  path: Cubox/MemoryThrashing：抖音直播解决内存抖动实践-2022-07-20.md
- type: blog
  path: Cubox/字节跳动应用性能监控帮助客户Java OOM崩溃率下降80%-2022-01-14.md
- type: official
  path: https://developer.android.com/topic/performance/memory
  note: Android 内存管理官方指南
- type: official
  path: https://source.android.com/docs/core/perf/lmkd
  note: userspace lmkd 与 PSI / vmpressure 机制
- type: aosp
  path: frameworks/base/core/java/android/content/ComponentCallbacks2.java
- type: aosp
  path: frameworks/base/core/java/android/util/LruCache.java@android-17.0.0_r1
- type: official
  path: https://developer.android.com/reference/android/util/LruCache
- type: official
  path: https://developer.android.com/reference/android/content/ComponentCallbacks2
- type: official
  path: https://developer.android.com/reference/android/os/ProfilingManager
- type: official
  path: https://developer.android.com/reference/android/os/ProfilingTrigger
- type: aosp
  path: frameworks/base/libs/hwui/RenderProperties.h
- type: aosp
  path: frameworks/base/libs/hwui/RenderNode.cpp
- type: aosp
  path: packages/modules/Profiling/framework/java/android/os/ProfilingTrigger.java
- type: aosp
  path: system/memory/lmkd/lmkd.cpp
- type: kernel
  path: mm/vmscan.c@android17-6.18-2026-06_r6
- type: kernel
  path: include/trace/events/vmscan.h@android17-6.18-2026-06_r6
tags:
  - memory
  - pss
  - rss
  - mat
  - heapprofd
  - memtrack
  - memory-analysis
  - case-study
related_chapters:
- '4.1'
- '4.2'
- '4.4'
- '14.1'
- '15.3'
- '10.2'
- '10.3'
section: '10.1'
status: finalized
last_consolidated_at: '2026-08-24'
consolidated_from:
- src/part2-performance/ch10-memory-perf/01-app-memory-analysis.md
- src/part2-performance/ch10-memory-perf/05-case-studies.md
- src/part2-performance/ch10-memory-perf/02-memory-leak-growth.md
- src/part2-performance/ch10-memory-perf/03-memory-growth.md
last_body_apply_at: '2026-08-26T19:20:50+08:00'
last_review_finalize_at: '2026-08-26T20:23:27+08:00'
---

# App 内存分析与案例

一条内存曲线能说明什么问题，首先取决于它统计的是哪一块内存。Java 堆（ART 管理的 Java/Kotlin 对象堆）、原生分配器（native allocator，即 C/C++ 默认内存分配器）、RSS、PSS、SwapPss、DMA-BUF（设备间共享缓冲区）和 GPU 私有内存（GPU private memory）各自观察的对象并不相同，数值又往往来自不同的采样时刻，直接相加很容易导致误判。

> 源码基线：AOSP `android-17.0.0_r1`；内核 `android17-6.18-2026-06_r6`（Android 17 / API 37）。涉及 PSI（Pressure Stall Information，压力停顿信息）的内核实现以该内核标签为准。

本文前半部分按实战顺序拆解排查方法：先对齐指标口径，再定位内存域，随后借助对应工具追查内存持有者（owner）与生命周期；后半部分则用四个公开案例走完同一条取证路径。

## 内存域、基线与增长分类

拿到一条上涨的内存曲线，首先要确定它属于哪种内存，再采集可比的快照，随后按域挑选工具。下面按这个顺序依次展开：指标含义、快照采集、Java/Kotlin 堆、Native 堆、图形内存、基线对比与系统压力。

### 1. 先确定问题属于哪种内存

#### 1.1 常用指标的含义

在看曲线之前，先厘清每个指标到底在统计什么。下表列出了常用指标的数据来源、它们各自回答的问题，以及分析时最容易踩的坑：

| 指标 | 主要来源 | 回答的问题 | 容易误用的地方 |
|---|---|---|---|
| Java heap used | ART / `Runtime` / heap dump | 当前 Java/Kotlin 对象占用与引用关系 | 当成整个进程内存 |
| Java heap max | `Runtime.maxMemory()`、`getMemoryClass()` | Java heap 的增长预算 | 与 PSS 或 Graphics 直接相除 |
| Native allocated | bionic allocator / `Debug.getNativeHeapAllocatedSize()` | 分配器仍记为已分配的字节 | 当成 native RSS |
| RSS（Resident Set Size，驻留集大小） | `/proc/<pid>/status`、smaps | 当前驻留在物理内存中的共享页与私有页总和 | 汇总多个进程时重复计算共享页 |
| PSS（Proportional Set Size，按比例分摊集） | smaps / smaps_rollup | 驻留页按内核共享计数分摊；同一进程重复映射与大页近似会影响计数 | 当成硬上限或 LMKD 唯一依据 |
| USS（Unique Set Size，独占集大小） | Private Clean + Private Dirty | 当前进程独占的页面 | 忽略 swap、GPU private 与未映射 DMA-BUF |
| SwapPss | smaps | 按共享计数分摊的换出页面；不等于 ZRAM 压缩后的物理字节数 | 与 resident PSS（仍驻留部分）使用不同采样时刻相加 |
| Graphics / memtrack | `IMemtrack` 与厂商 HAL（硬件抽象层） | smaps 难以覆盖的图形、GL 和 GPU 私有内存 | 假定所有设备记账完整一致 |

<!-- gracker-diagram: ch10-01-02-shared-page-accounting -->
![RSS 与 PSS 的共享页算例](../../assets/diagrams/ch10/ch10-01-02-shared-page-accounting.png)

图：教学算例：一张已驻留的 4 KiB 普通页，由两个进程各映射一次。RSS 各记 4 KiB，PSS 各分摊 2 KiB；这不是测量数据。

选择指标时可以记住一条基本原则：PSS 适合用来比较包含共享映射的进程内存占用，RSS 则适合以更低开销观察驻留内存的实时变化。两者都会受共享库、文件页、内存压缩交换设备（ZRAM）、进程状态和采样时刻的影响。

另外，`ActivityManager.getMemoryClass()` 与 `getLargeMemoryClass()` 返回的单位是 MB，描述的是 Dalvik/ART 堆的近似预算；而 PSS 以 kB 报告，统计范围还包含了 Java 堆之外的原生分配、代码页、线程栈、图形内存和系统共享页分摊。两者的单位与统计范围都不同，直接相除无法得出有效的“PSS 使用率”。

#### 1.2 `Debug.MemoryInfo` 的字段与读法

`Debug.MemoryInfo` 将进程内存划分为 dalvik、native、other 三个域，并通过公开的 `getMemoryStats()` 提供以 kB 为单位的 App Summary。其中摘要里的 `summary.java-heap` 对应 `dalvikPrivateDirty + OTHER_ART` 的 private 部分，`summary.native-heap` 对应 `nativePrivateDirty`，它们的统计口径与 `Runtime` 对象堆用量、分配器（allocator）已分配字节数并不重合。此外，`getTotalPss()` 已经汇总了受支持的 memtrack 统计与 SwapPss，再额外叠加 Graphics 或 SwapPss 会造成重复计算；它和 Linux `smaps` 中的 resident Pss 统计范围也不同，直接对照容易产生误读。

使用这些字段时，还有几处实现细节需要注意：

- `getTotalPss()` 包含 swapped-out PSS，即按共享比例分摊的已换出页面；
- `android-17.0.0_r1` 内部提供了由各域 Private Clean 与 Private Dirty 相加而成的 `getTotalUss()`，但该方法标为 `@hide`；普通 SDK 若需获取这两项数据，直接读取公开的 private clean 与 private dirty 总量即可；
- `getMemoryStats()` 提供 App Summary 分类，在 `android-17.0.0_r1` 中，`summary.total-swap` 实际调用的是 `getTotalSwappedOut()`，与 `SwapPss` 的含义不同，因此阅读统计结果时应以具体 getter 的执行路径为准；
- `Debug.getMemoryInfo()` 直接读取本进程的底层统计，源码注明它可能看不到部分受保护的 graphics 分配；
- 普通应用调用 `ActivityManager.getProcessMemoryInfo()` 时，自 Android 10（API 29）起受到调用 UID 限制，平台特权与跨用户查询也另有权限约束。`android-17.0.0_r1` 会为未获准查询的 PID 保留一个默认值条目，因此返回数组非空或数值为零都可能只是填充了默认值；同时高频调用通常会直接命中服务端缓存，只有由 shell 或 root 发起的 instrumentation 另有例外。

<!-- gracker-diagram: ch10-01-04-am-memory-access -->
![AM 内存查询的权限与缓存](../../assets/diagrams/ch10/ch10-01-04-am-memory-access.png)

图：r1 保留每个请求 PID 的结果位置；普通应用不能依靠非空数组或零值判断已经取得新采样。

源码核对：

- [`Debug.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/os/Debug.java)
- [`ActivityManager.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/app/ActivityManager.java#5115)

### 2. 建立第一份内存快照

确定指标口径后，接下来需要在同一实验阶段采集进程摘要、内存页大小和进程状态，可以通过下面几条命令完成：

```bash
adb shell dumpsys meminfo -d com.example.app
adb shell getconf PAGE_SIZE
adb shell 'pid=$(pidof -s com.example.app); [ -n "$pid" ] && grep -E "VmRSS|RssAnon|RssFile|RssShmem|VmSwap|Threads" "/proc/$pid/status"'
adb shell dumpsys SurfaceFlinger --list
```

由于 `dumpsys meminfo` 的详细列会随平台和厂商实现变化，分析报告中应保留原始输出。`/proc/<pid>/status` 中的 `VmRSS` 只是低成本估算，`libmeminfo` 源码注明它不如逐映射内存统计（smaps）精确。至于 SurfaceFlinger 图层（layer）列表，它只用于核对当前可见的图形对象，若要排查每个图层的 GPU 内存占用，还需借助后续介绍的图形工具。

如果要在应用内采集一次本进程快照，可以使用公开的 `ActivityManager` API：

```kotlin
data class AppMemorySnapshot(
    val observedUptimeMs: Long,
    val androidTotalPssKb: Int?,
    val javaSummaryKb: Int?,
    val nativeSummaryKb: Int?,
    val graphicsSummaryKb: Int?,
    val javaUsedBytes: Long,
    val javaMaxBytes: Long,
    val nativeAllocatedBytes: Long,
)

fun captureAppMemory(
    activityManager: ActivityManager,
): AppMemorySnapshot {
    val info = try {
        activityManager.getProcessMemoryInfo(intArrayOf(Process.myPid()))
            .singleOrNull()
    } catch (_: RuntimeException) {
        null
    }
    val stats = info?.memoryStats.orEmpty()
    val runtime = Runtime.getRuntime()

    return AppMemorySnapshot(
        observedUptimeMs = SystemClock.uptimeMillis(),
        androidTotalPssKb = info?.totalPss,
        javaSummaryKb = stats["summary.java-heap"]?.toIntOrNull(),
        nativeSummaryKb = stats["summary.native-heap"]?.toIntOrNull(),
        graphicsSummaryKb = stats["summary.graphics"]?.toIntOrNull(),
        javaUsedBytes = runtime.totalMemory() - runtime.freeMemory(),
        javaMaxBytes = runtime.maxMemory(),
        nativeAllocatedBytes = Debug.getNativeHeapAllocatedSize(),
    )
}
```

这段示例需导入 `android.app.ActivityManager` 与 `android.os.Debug/Process/SystemClock`，适用于本文覆盖的 API 26 及以上版本。查询失败或键缺失时字段为 `null`，系统返回的零值则保持原样（它仍可能表示没有有效数据）。需要注意，`observedUptimeMs` 只是本地观察时间，服务端缓存的实际采样时刻还需另行确认；AM 摘要、`Runtime` 与原生分配器这三个来源各自独立取值，合看时应当作三次独立采样。为避免引入额外开销，应把采样调用放在实验步骤边界或低频诊断任务中，避开每帧回调和紧循环。

### 3. Java/Kotlin heap：用引用关系证明泄漏

如果内存增长发生在 Java/Kotlin 堆，排查的关键在于梳理引用关系。Heap dump 记录了某一时刻托管堆中的对象与引用信息，具体的 GC 触发、过滤和可达性处理方式取决于采集与分析工具；它能回答“对象由谁引用”以及“哪个对象支配一片子图”，但若要排查原生 `mmap`、GPU 分配或进程为何被系统终止，就需要换用其他工具。

#### 3.1 三个必须分清的概念

- **Shallow Size（对象自身大小）**：对象自身在 managed heap（由 ART 管理的堆）中占用的字节，不含被引用对象；
- **Retained Size（对象不可达后可一并回收的估算大小）**：对象不可达后，预计可随它一起回收的受支配对象总量；
- **GC Root path**：对象通向 GC Root 的引用路径；GC Root 是垃圾回收器判定对象仍可达的起点，例如活跃线程、JNI global reference（JNI 全局引用）、类对象、系统类或活跃栈。

<!-- gracker-diagram: ch10-01-06-references-and-dominators -->
![引用路径与独占支配要分清](../../assets/diagrams/ch10/ch10-01-06-references-and-dominators.png)

图：教学对象图：A、B 都能到 C，只有 A 能到 D。A 不独占支配 C；支配树的边也不必是原始引用边。

对象头、内存对齐、压缩引用和 ART 具体实现都会影响 Shallow Size。哪怕是只包含两个 `int` 字段的简单对象，在不同设备上占用的字节数也并不固定，跨设备时不能按字段大小直接推算。

#### 3.2 可复现的泄漏检查

一次可复现的泄漏检查可以按下面七步推进：

1. 固定初始页面和进程状态；
2. 执行同一生命周期动作多轮，例如进入页面、返回、旋转或替换 Fragment View；
3. 等待异步任务和已知动画结束；
4. 采集 heap dump；
5. 查找应已销毁的 Activity、Fragment View、Compose 状态对象（Compose state）、listener、callback 或缓存条目（cache entry）；
6. 沿 GC Root path 找到生命周期更长的持有者；
7. 修复后重复同一脚本，并比较实例数和保留关系图（retained graph）。

在 dump 中看到单个 Activity 仍存活先别急着判定为泄漏：系统组件、输入法、动画和异步消息都可能短期持有它的引用。要确认泄漏，必须同时满足两个条件：对象已经越过预期生命周期，并且引用链在稳定状态下依然存在。

从 Android 8.0（API 26）起，普通软件 Bitmap 的像素数据位于 native heap，而 `Config.HARDWARE` 的像素由图形内存承载。Java 堆中的 `Bitmap` 包装对象依然是追踪归属关系的入口，Android Studio 的 heap dump 也可能在 Native Size 列展示关联的原生内存。只盯着 Java Shallow Size，很容易低估图片的实际内存成本。

<!-- gracker-diagram: ch10-01-08-bitmap-two-pixel-domains -->
![Bitmap 包装对象与像素域分开](../../assets/diagrams/ch10/ch10-01-08-bitmap-two-pixel-domains.png)

图：API 26+ 的软件像素与 HARDWARE 像素分属不同域；Java 包装对象仍可帮助追踪持有者，Native Size 的可见性也取决于工具。

来源：[Android Studio Heap Dump 指南](https://developer.android.com/studio/profile/capture-heap-dump)

#### 3.3 分配 churn 与 retained leak（对象保留型泄漏）

堆曲线升高可能来自两种不同的机制，排查时需要先加以区分：如果对象创建速率很高但在 GC 后能够回落，这属于频繁短命分配造成的内存抖动（allocation churn）；如果对象沿异常引用链长期存活，则属于对象保留型泄漏（retained leak）。两者的定位工具各不相同：

- churn：记录 Java/Kotlin 分配调用栈（allocation callstack）、GC 和帧时间；
- leak：使用 heap dump、dominator tree 与 GC root；
- 大数组或 Bitmap：同时核对 native size 和图片缓存策略；
- JNI global reference：结合 ART heap 与 native 调用栈检查持有者。

### 4. Native heap 的两类问题：分配归因与非法访问

当内存增长落在 native heap 时，常见的问题通常分为两类：一是分配持续增长，需要查找分配调用栈；二是越界、释放后使用等非法内存访问。我们先看分配归因。

#### 4.1 heapprofd 用于分配调用栈

heapprofd 从 Android 10 开始支持跟踪 `malloc/free` 与 `new/delete` 分配，并通过抽样记录来降低目标进程的运行开销。需要注意，在日常发布版本的系统镜像（user build）上，只能分析声明为 `profileable` 或 `debuggable` 的应用。

下面的命令使用 Perfetto 仓库中的推荐脚本，按进程名启动 native heap profiling：

```bash
tools/heap_profile android -n com.example.app
```

按进程名启动采集时，已经运行的匹配进程和后续新启动的匹配进程都能进入采样范围；需要观察启动期分配时，应先启动分析器（profiler），再启动应用。对于多进程应用，还需分别确认 `com.example.app:worker` 等子进程名。采集结束后，在 Perfetto UI 中打开生成目录里的 `raw-trace` 原始轨迹文件即可分析。

四个常用视图回答不同问题：

| 视图 | 含义 |
|---|---|
| Unreleased malloc size | 采集窗口内已分配但尚未 `free` 的估算字节数 |
| Unreleased malloc count | 采集窗口内尚未 `free` 的估算分配次数 |
| Total malloc size | 窗口内全部分配的估算字节数，包含已经 `free` 的分配 |
| Total malloc count | 窗口内全部估算分配次数，包含已经 `free` 的分配 |


heapprofd 默认只观测采样开始后发生的分配；启动前已有的分配，以及绕过被跟踪分配器的直接 `mmap`、graphics buffer 和 GPU 私有分配，通常都不在这份 native malloc profile 的覆盖范围之内。它也支持通过额外配置启用 ART 分配剖析，两种模式的结果应当分开解读。如果发生 buffer overrun，会话会提前终止，由此留下的覆盖缺口需要如实记录；此外，采样间隔、符号文件以及进程启动方式也应随结果一并保存。

<!-- gracker-diagram: ed10-01-native-profile-window-counters -->
![在实际观测窗口内解释 Total 与 Unreleased](../../assets/diagrams/ch10/ed10-01-native-profile-window-counters.png)

图：默认native malloc profile先核对目标进程名、profileable/debuggable权限与实际区间；需要启动期证据时先启动profiler再启动目标，多进程分别确认。轨道仅示被观测窗口内分配的两种生命周期，无实测时长比例；已free项计入Total而不留Unreleased，样本末尚未free项计入二者，末条在样本末截住不表示发生free。size/count都是采样估算，Unreleased不是全进程所有历史live bytes，更不是RSS。启动前分配、直接mmap、图形与GPU通常不在默认结果内；ART allocation另行配置。保存实际窗口、interval与符号，buffer overrun提前终止造成的缺口不能解释为零占用。

来源：[Perfetto Native Heap Profiler](https://perfetto.dev/docs/data-sources/native-heap-profiler)

#### 4.2 三层统计的覆盖范围

把 heapprofd、分配器（allocator）统计和物理驻留内存（resident memory）并列来看时，它们分别按不同的对象、时机和状态记账，三者之间并不存在严格的包含关系：


```text
heapprofd
  采样到的 malloc/new 请求与 free

malloc_info / allocator statistics
  allocator 管理的 arena、cache 与仍持有的页面

Native Heap RSS / PSS
  已驻留页面，并受 page size、碎片、共享、swap 与采样时刻影响
```

因此，即使统一换算成字节并对齐了观察区间，也不能直接拿 `Native Heap RSS - heapprofd unreleased bytes` 的差值去等价于内存碎片：采样估算误差、启动前分配、allocator 内部缓存、地址对齐、页内空洞、换出或驻留状态变化以及统计分类差异，都会同时影响这两项数据；直接 `mmap` 的内存还需核对是否被工具归入 Native Heap。在部分场景下，heapprofd 统计的存活分配量甚至可能大于该分类的 RSS，两者的差值并没有固定的正负含义。

#### 4.3 用 `wrap.sh` 启用 malloc debug

对于普通应用开发者，可以通过 debuggable APK 中的 `wrap.sh` 来启用 malloc debug。下面的脚本用于记录原生分配调用栈（native allocation backtrace）：

```sh
#!/system/bin/sh
LIBC_DEBUG_MALLOC_OPTIONS=backtrace logwrapper "$@"
```

`wrap.sh` 仅适用于 API 27 及以上的 debuggable 应用；由于它会改变进程启动过程并显著增加分配开销，只适合受控调试，不能带入生产发布包。在 `android-17.0.0_r1` 中，`libc.debug.malloc.program` 按 `strstr(getprogname(), program)` 过滤，而不会经由 PackageManager 查询包名；此外，只要设置了非空的 `LIBC_DEBUG_MALLOC_OPTIONS`，就会覆盖这一属性选择分支。因此，应用侧要确认 malloc debug 真正生效，应当沿可调试 APK 的 `wrap.sh` 启动路径实际验证，仅凭属性里填了包名还无法说明已经启用。

<!-- gracker-diagram: ch10-01-14-wrap-startup -->
![wrap.sh 在受控启动中启用 malloc debug](../../assets/diagrams/ch10/ch10-01-14-wrap-startup.png)

图：wrap.sh 改变目标 App 的启动与分配行为。它是受控诊断入口，命令通过 "$@" 保留参数边界。

来源：[NDK wrap.sh 指南](https://developer.android.com/ndk/guides/wrap-script)

#### 4.4 HWASan、GWP-ASan 与 heapprofd 的职责

| 工具 | 主要目标 | 适用方式 |
|---|---|---|
| heapprofd | 找分配调用栈、增长和 churn | profileable/debuggable App 或平台调试 |
| HWASan | 捕获 C/C++ 越界、use-after-free（释放后使用）和 double free（重复释放） | ARM64 测试构建；Android 14+ 可用 App `wrap.sh` |
| GWP-ASan | 抽样发现 heap use-after-free / overflow（堆越界） | Android 11+ 支持；Android 14+ 默认采用 Recoverable（可恢复）模式策略 |
| Malloc debug | guard（保护区）、backtrace、fill（填充值）等分配器调试 | debuggable App 或 root/userdebug |


ASan 虽然仍可用于旧设备，但当前的 NDK 指南已不再将其作为主动支持的方案；在支持 HWASan 的 ARM64 环境下应优先选择 HWASan。由于内存错误检测器（sanitizer）会显著改变运行耗时和内存开销，其测试数据需要与普通 release 构建的基线分开保存。

来源：[NDK 内存错误调试与缓解](https://developer.android.com/ndk/guides/memory-debug)

### 5. Graphics、DMA-BUF 与 Bitmap

当增长发生在图形内存时，需要换用专门的接口来做归属分析。AIDL 接口 `IMemtrack` 由厂商 HAL 提供，用来上报那些 `smaps` 难以完整追踪的设备相关内存。接口契约明确区分了以下四类统计：

- `GRAPHICS + FLAG_SMAPS_UNACCOUNTED`：CPU/GPU 映射的 DMA-BUF PSS，并去除两组映射的重叠部分；
- `GL + FLAG_SMAPS_UNACCOUNTED`：指定 PID 的 GPU 私有分配；
- `pid = 0, type = GL`：系统级 GPU private memory；
- `OTHER + FLAG_SMAPS_UNACCOUNTED`：其他未进入 `smaps` 的设备内存。

契约要求 HAL 避免在不同 memtrack 记账类别（type）之间重复记账；不过，某项查询设备是否支持、驱动能否将内存准确归属到对应 PID，仍由厂商的产品实现决定。基于这份契约，我们可以得到几条实用的判断规则：

- `dumpsys meminfo` 的 Graphics 显示为 0，并不等同于设备没有分配 GPU 内存，也可能只是 HAL 未覆盖或未上报；
- 当 Graphics 上升时，资源持有者（owner）通常在 Java heap dump 之外，需要转到图形对象或原生资源中查找；
- SurfaceView、TextureView、ImageReader、MediaCodec、Camera 和 Vulkan 各自管理着不同的 buffer 或图层（layer）生命周期；
- Java `Bitmap` 引用释放后，仍需要等待图片库、GPU 缓存（GPU cache）和渲染器（renderer）分别完成各自的释放流程。

源码核对：[`IMemtrack.aidl`](https://android.googlesource.com/platform/hardware/interfaces/+/refs/tags/android-17.0.0_r1/memtrack/aidl/android/hardware/memtrack/IMemtrack.aidl)

GPU 专项工具与图层/缓冲区追踪细节将在 10.4 节展开；本节先聚焦于把 Graphics 从 Java/Native 堆的口径中剥离出来。

### 6. 建立可比较的基线

脱离了可比条件，内存数字就很难说明问题。一份有效的基线至少绑定以下六个维度：

| 维度 | 需要记录的值 |
|---|---|
| App | versionCode、build type（构建类型）、ABI、进程名 |
| 系统 | 设备型号、build fingerprint（系统构建指纹）、Android/API、page size |
| 场景 | 入口、操作脚本、循环次数、前后台状态 |
| 时间 | 进程启动后时长、采样点、采样工具 |
| 负载 | 账号数据量、图片规格、列表长度、网络响应 |
| 指标 | Java used/max、Native allocated、PSS、RSS、SwapPss、Graphics |

一份实用的采样脚本可以设置这些采样点：

1. 冷启动首屏稳定；
2. 目标页面第一次进入；
3. 相同操作完成固定轮数；
4. 返回初始页面并等待异步释放；
5. 进入后台；
6. 进程重新回到前台。


采样收集齐后，可以结合分布与曲线形态来初步判断问题类型：

- 每轮结束后的 retained set（回收后仍保留的对象集合）持续增长：分析持有者与引用链；
- Java used 上下波动但能够稳定回落：更接近正常的 GC 周期或 allocation churn；
- Native allocated 持续上升：使用 heapprofd 定位原生分配调用栈；
- PSS/RSS 上升而 Java/Native allocated 保持稳定：检查 `mmap` 映射、代码页、线程栈、图形内存、DMA-BUF 以及分配器持有的驻留页面（allocator residency）；
- 前台升高、退到后台后回落：多半源自可回收缓存或图形资源的生命周期；
- 进程异常退出：直接读取 `ApplicationExitInfo`，不能仅凭最后一段内存曲线推断死因。

告警阈值应当源自同设备族、同场景的历史分布与产品风险预算。如果简单写成“PSS 增长 5% 即算回归”或“Java heap 超过 85% 就触发 dump”，往往会在不同机型、页面和数据量上制造大量误报。

#### 6.1 4 KB 与 16 KB page size 分组

从 Android 15 起，设备支持采用 16 KB 内存页大小（page size）。页大小会直接影响 ELF 二进制文件的段对齐、`mmap` 粒度、分配器的页跨度（page span）以及驻留内存的计量单位，因此同一份 APK 在 4 KB 与 16 KB 设备上的 PSS/RSS 基线可能存在差异。

制定基线时应遵循以下规则：

- 记录 `getconf PAGE_SIZE` 的实际值；
- 将 4 KB 与 16 KB 设备分开统计；
- 不使用固定百分比试图从 16 KB 数据“还原”4 KB 数值；
- 将 native library 兼容性与内存回归拆开判断；
- 同一分组内仍需固定系统构建版本、ABI 与输入数据。

官方文档给出的总体内存变化幅度来自特定的测试集合，并不适合直接当作所有应用的通用校正系数。

来源：[16 KB page size 支持指南](https://developer.android.com/guide/practices/page-sizes)

#### 6.2 用回落条件区分缓存、积压与泄漏

设计持续增长实验时，不能只在操作峰值抓一次快照，而应比普通峰值测试多设两个采样点：执行完业务释放动作后的状态，以及主动收缩可重建资源后的状态。随后用同一输入再跑一轮，观察波峰、波谷与增长斜率是否可重复。仅凭峰值时抓到的一次 `dumpsys meminfo`，无法区分工作集扩大、缓存保留和生命周期错误。

| 增长来源 | 释放或收缩动作 | 仍需补充的证据 |
| --- | --- | --- |
| 业务 live set（仍在使用的数据集合） | 关闭页面、清空数据集或结束会话 | 对象类型、条目数、字节预算与业务容量是否同步变化 |
| 无上限缓存或队列积压 | 执行缓存裁剪、消费完队列或取消任务 | 缓存 owner、队列长度、命中收益和积压产生速度 |
| Java/Kotlin 对象泄漏 | 结束对象的业务生命周期并等待异步清理 | heap dump 中稳定存在的 GC Root 强引用路径，见上文第 3.2 节 |
| Native 未释放分配 | 关闭会话或执行配对释放 | heapprofd 的 live allocation 差分与符号化调用栈 |
| allocator 保留 | 确认 live allocation 已下降 | allocator 统计、`smaps` 与匿名驻留页；RSS 不立即回落不能单独命名为泄漏 |
| 直接 `mmap`、文件页或线程栈 | 关闭映射、结束线程并再次采样 | mapping 名称、创建者、线程数量和退出条件 |
| Surface、Image、Codec 或 DMA-BUF | 关闭资源并等待 consumer 释放引用 | 图形内存、layer/buffer 生命周期与相关进程的变化 |
| WebView 工作集 | 销毁实例并分别观察宿主与 renderer 进程 | provider 版本、renderer 生命周期、代码页、缓存与图形内存 |


缓存机制需要一份可执行的协议，不能只靠“内存高时清一点”这类模糊约定。设计缓存时至少要明确以下五项：

- 任何输入下的硬上限（hard limit）；
- 页面不可见或进入后台后的收缩目标（shrink target）；
- 统一的计量单位；
- 负责创建与裁剪的持有者（owner）；
- 大小、命中、未命中、淘汰和重建成本（size/hit/miss/eviction/rebuild cost）。

需要注意，`ActivityManager.getMemoryClass()` 只反映 ART 堆的近似上限，整个应用进程的缓存预算需要另外评估。

使用 `LruCache` 时，`sizeOf()` 决定了预算的计量单位，`maxSize` 必须采用相同单位。条目离开 `LruCache` 后，Adapter、View、后台任务或其他集合里仍可能保存着引用，因此缓存计数下降并不意味着对象已经回收。至于能否在 `entryRemoved()` 中直接调用 `Bitmap.recycle()`，还差一个关键前提：所有权协议必须能够证明此时再无其他使用者；只有满足这个条件，才可以在淘汰回调中主动销毁底层资源。

<!-- gracker-diagram: ed10-01-cache-and-resource-owners -->
![缓存淘汰只移除一处持有，资源销毁取决于所有使用者](../../assets/diagrams/ch10/ed10-01-cache-and-resource-owners.png)

图：上半画一个被缓存资源的持有关系示意，下半核对释放条件；并非所有资源都有同一Java包装或consumer。LruCache的sizeOf/maxSize/收缩目标同单位、owner与裁剪条件明确，硬上限只约束cache自身。淘汰只移除cache这一处持有，View/Adapter/任务或图形consumer/renderer仍可按各自协议继续使用；业务close、GC、管线完成和指标回落不是同一时刻。按资源身份追每个持有者和配对释放；只有所有权协议证明没有其他使用者才可选择提前销毁，entryRemoved不是通用Bitmap.recycle开关。随后以layer/buffer/memtrack/映射等对应观测确认，不把缓存计数下降当总内存有界或立即回收证明。

对于长时间运行的音乐、导航、IM、RTC 等场景，还应把运行时长纳入基线考察。环形缓冲区、历史数据、图片、地图瓦片、字幕以及模型缓存应分别设定容量上限；音视频会话中的 Codec、Surface、Image 与原生 session 也应由同一个持有者成对关闭。每轮业务结束后，真正需要验收的是回落后的 live set 本身，单纯以“进程仍在运行”作为验收结论是不够的。

### 7. 系统内存压力与 LMKD

有些内存异常的推手来自系统一侧：在整机内存压力之下，系统会主动回收进程。`lmkd` 可通过 PSI 事件感知内存压力引起的任务停顿（memory stall），并综合可用内存水位（watermark）、swap 状态、工作集页面频繁换入引发的抖动（workingset refault/thrashing）、页面回收（reclaim）状态与产品属性，决定是否终止进程。扫描候选进程时，会按 `oom_score_adj` 的保护级别推进；当配置了 `kill_heaviest_task` 或扫描进入可感知进程等保护级别分支时，会改为优先比较同一 adj 档位中占用更大的进程，这与单纯按全局 PSS 从高到低排序截然不同。

<!-- gracker-diagram: ch10-01-22-lmkd-decision -->
![压力事件与 LMKD 选进程分开](../../assets/diagrams/ch10/ch10-01-22-lmkd-decision.png)

图：r1 扫描顺序和同档选择各有条件，不能仅凭 PSS 高推断下一个 victim。

把这套机制放回实际排查现场，可以得到几条实用的判断规则：

- 即使某个应用的 PSS 较高，下一次也未必轮到它被杀；
- 前台或可感知进程与缓存进程（cached）的保护级别不同；
- 最终被选中回收的进程（victim）并不只由 PSS 决定；
- LMKD kill、kernel OOM、crash、ANR 与用户 force-stop 属于不同的退出原因；
- 设备厂商可以根据产品需求调整 lmkd 属性与内存策略。

源码核对：

- [`lmkd.cpp`](https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/lmkd.cpp)
- [`psi.c`](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/kernel/sched/psi.c)

#### 7.1 libpsi 与 PSI 事件通道

`libpsi` 位于 `system/memory/lmkd/libpsi`。其头文件将监控资源限定为 `PSI_MEMORY`、`PSI_IO` 和 `PSI_CPU`，并暴露 `PSI_SOME` / `PSI_FULL`、`psi_stats` 以及 monitor/parse 相关函数；库本身并不包含 victim 选择、`oom_score_adj` 扫描或查杀策略（kill policy）。`lmkd` 调用 `init_psi_monitor(..., psi_window_size_ms * US_PER_MS)` 时没有显式传入 `resource`，因此默认使用头文件里的 `PSI_MEMORY`。[已验证: system/memory/lmkd/libpsi/include/psi/psi.h@android-17.0.0_r1#25][已验证: system/memory/lmkd/lmkd.cpp@android-17.0.0_r1#3435][来源: https://juejin.cn/post/7677254638325727242]

`init_psi_monitor()` 会先校验资源类型，再以 `O_WRONLY | O_CLOEXEC` 打开 `/proc/pressure/<resource>`，写入 `"some|full threshold_us window_us"`，成功后直接返回该文件描述符（fd）。内核写入路径会将触发器（trigger）绑定到这个已打开的文件；如果对同一个 fd 再写第二个 trigger，内核会以 `-EBUSY` 拒绝。因此，这个 fd 充当的是“何时产生压力”的事件通道，而无法兼作读取 `avg10/avg60/avg300/total` 的统计通道。[已验证: system/memory/lmkd/libpsi/psi.cpp@android-17.0.0_r1#36][已验证: kernel/sched/psi.c@android17-6.18-2026-06_r6#1569][来源: https://juejin.cn/post/7677254638325727242]

`register_psi_monitor()` 只以 `EPOLLPRI` 事件将该 fd 挂入 epoll，并把调用方传入的 `void* data` 放进 `epev.data.ptr`。内核 `psi_trigger_poll()` 会在 trigger 的 `event` 标志从 1 被 `cmpxchg` 消费时附上 `EPOLLPRI`。由于它的基础返回值包含 `DEFAULT_POLLMASK`，`EPOLLIN` 可能一直处于就绪状态，既区分不出新的压力事件，还可能引起轮询空转；因此调用方真正要监听并识别的是 `EPOLLPRI`，同时妥善处理错误和关闭事件。[已验证: system/memory/lmkd/libpsi/psi.cpp@android-17.0.0_r1#86][已验证: kernel/sched/psi.c@android17-6.18-2026-06_r6#1489][来源: https://juejin.cn/post/7677254638325727242]

统计读取则走另一组 fd：`psi_parse_mem()`、`psi_parse_io()` 与 `psi_parse_cpu()` 通过 `reread_file()` 读取 `/proc/pressure/*` 文本，再由 `parse_psi_line()` 解析 `some/full avg10=... total=...`，其中 CPU 只解析 `some` 行。排查 `lmkd` 时，需要将 trigger 唤醒、统计快照与后续的查杀决策（kill decision）拆开来看。[已验证: system/memory/lmkd/lmkd.cpp@android-17.0.0_r1#2093][已验证: system/memory/lmkd/libpsi/psi.cpp@android-17.0.0_r1#109][来源: https://juejin.cn/post/7677254638325727242]

<!-- gracker-diagram: ed10-01-psi-event-stat-and-poll -->
![PSI trigger 唤醒与统计读取分开，后续策略可继续轮询](../../assets/diagrams/ch10/ed10-01-psi-event-stat-and-poll.png)

图：固定r1的libpsi事件fd用O_WRONLY|O_CLOEXEC打开pressure文件并写some/full trigger，一个打开文件只绑定一个，第二次写被EBUSY拒绝。EPOLLPRI指示trigger事件，EPOLLIN可能持续就绪，不能当新事件；void*data交给调用者handler。统计走另一组reread/parse路径读avg10/60/300与total，CPU在此只解析some。事件后lmkd可按状态用10/100ms间隔继续读取并重新评估，默认窗口1000ms，等待死亡可暂停/恢复，超窗结束；内核同trigger至多每窗口通知一次。图下方是后续两个职责，未规定轮询窗口结束后才kill；是否kill、按adj选谁还需水位/回收/swap等策略上下文，libpsi本身不选择victim，参数不是应用SLA。内核参数合法性与权限另见后图。

内核侧的参数边界同样需要按目标内核核对：在 common kernel `android17-6.18-2026-06_r6` 中，内核会拒绝 `window_us == 0` 或超过 10s 的配置，也拒绝 `threshold_us == 0` 或 threshold 大于 window 的配置；源码中的 `privileged` 取决于打开文件的凭据是否具有 `CAP_SYS_RESOURCE`，或者是否编译启用了 `CONFIG_DEFAULT_SECURITY_SELINUX`，只有 `!privileged` 分支才要求 window 为 2s 的倍数。需要注意，这一源码分支判断并不替代 procfs 或 SELinux 对写入操作本身的访问控制。由于同一 trigger 在内核中每个窗口至多通知一次，`lmkd` 默认采用 1000 ms 的 PSI 窗口，并在收到 PSI 事件后以 10 ms 或 100 ms 的间隔持续轮询一个窗口。其他内核分支或资料中提到的窗口下限，不宜直接外推为 Android 17 的通用约束。[已验证: kernel/sched/psi.c@android17-6.18-2026-06_r6#1336][已验证: kernel/sched/psi.c@android17-6.18-2026-06_r6#509][已验证: system/memory/lmkd/lmkd.cpp@android-17.0.0_r1#118][来源: https://juejin.cn/post/7677254638325727242]

<!-- gracker-diagram: ch10-01-24-psi-trigger-gates -->
![固定内核的 PSI 参数条件](../../assets/diagrams/ch10/ch10-01-24-psi-trigger-gates.png)

图：参数合法性、源码内部 privileged 判断与访问权限是不同条件，不能从一个条件推出普通应用一定能注册。

#### 7.2 用 `ApplicationExitInfo` 补齐进程退出上下文

下面的代码读取当前包最近的退出记录：

```kotlin
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
    val exitRecords = activityManager.getHistoricalProcessExitReasons(
        context.packageName,
        0,
        16,
    )

    for (record in exitRecords) {
        Log.i(
            "ExitMemory",
            "reason=${record.reason}, importance=${record.importance}, " +
                "pssKb=${record.pss}, rssKb=${record.rss}, " +
                "timestamp=${record.timestamp}",
        )
    }
}
```

需要注意，`getPss()` 与 `getRss()` 返回的是系统上一次采样的值（单位为 kB）；如果进程在首次采样前就已退出，这两个值可能为 0，它们并不等于进程死亡瞬间的实际内存占用。普通应用分析退出原因时，可以结合公开的 `reason`、`importance`、`description`、可用 trace 以及自定义状态摘要；在 `android-17.0.0_r1` 中，`getSubReason()` 标为 `@hide`，细分原因需要在有权限的平台报告或调试产物中查看。

应用还可以在低频业务状态切换时写入最多 128 bytes 的非敏感摘要：

```kotlin
if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
    val state = "screen=checkout;phase=confirm"
        .toByteArray(StandardCharsets.UTF_8)
    activityManager.setProcessStateSummary(state)
}
```

该 API 的调用频率可能受系统限制，过于频繁地写入会抛出 `RuntimeException`。此外，状态摘要只用于退出原因分析，不能用来恢复界面状态，切勿在其中写入账号、订单、位置等敏感信息。

<!-- gracker-diagram: ed10-01-exit-context-and-old-sample -->
![退出历史把最后内存样本与可选状态摘要作为上下文](../../assets/diagrams/ch10/ed10-01-exit-context-and-old-sample.png)

图：图中箭头表示历史上下文的数据来源，不表示采样导致退出或要求两种来源都存在。公开历史查询/状态摘要API30+，本文26–29跳过相应调用；API门槛不表示系统内存采样本身到API30才存在。系统PSS/RSS是上一次采样、单位kB，可早于死亡且可缺失或为0；可选状态摘要由业务低频写入，UTF8编码后最多128bytes，可能限频抛RuntimeException，仅用于诊断而非恢复UI，不放敏感内容。采样和摘要写入不承诺先后。后续启动代码按当前包最多请求16条历史，不能保证完整历史；公开reason/importance/description/可用trace用于原因分析，getSubReason为隐藏接口，缺失产物保留未知，不能用末次曲线推出死亡原因。

源码核对：[`ApplicationExitInfo.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/app/ApplicationExitInfo.java#912)

### 8. 线上监控的采集范围

线上遥测运行在真实用户设备上，常规做法是只收集轻量级摘要。heap dump、malloc debug 和 sanitizer 各自都有触发前置条件、额外停顿与较高的内存开销，需要单独评估适用性，不宜把它们直接挂成普通告警的无条件同步动作。至于按配置采样的 Hprof 方案，以及受系统策略约束的 `ProfilingManager`，它们属于另一条诊断路径，具体产物要看各自通道的实际执行结果，常规遥测无法保证必然产出。日常轻量记录通常包含以下字段：


- 进程、页面/场景枚举和前后台状态；
- Java used/max；
- 低频采集本进程的 PSS/RSS 与摘要分类；
- native allocated；
- page size、ABI、device/build、App 版本；
- trim callback（内存回收提示回调）、退出原因和最近的非敏感状态摘要；
- OOM、native crash 与 LMKD 相关的聚合事件。

采样时机根据业务选择：

- 场景进入和退出；
- 固定生命周期节点；
- 内存增长速度异常时增加一份低成本快照；
- 进程下次启动时读取历史退出记录；
- 实验组与基线组使用相同采样策略。

采样本身需要排队、读取 `/proc` 文件系统（procfs）或跨进程调用 Binder，因此采样周期应通过实机开销实验来确定，而不宜直接套用“30—60 秒”之类的固定经验值。何况 `getProcessMemoryInfo()` 存在服务端缓存，过短的轮询周期也未必能采集到新数据。

隐私与稳定性要求：

- 不上传 heap 内容、对象字符串、文件路径、图片或业务 payload（载荷数据）；
- state summary 使用枚举或短 ID，不写用户标识；
- 采样失败返回 unknown，不循环重试；
- 单位写进字段名；
- 多进程分别记录 PID、进程名和角色；
- OOM 前末次样本只当上下文，死亡瞬间的证据要从别处找。

### 9. 按现象选工具

下面这张表把前面的方法汇总成一条排查索引：在 trace 或监控里看到某类异常现象时，下一步该选用什么工具、重点要证明什么。

| 现象 | 下一步工具 | 需要证明的事 |
|---|---|---|
| Java used 与实例数持续增长 | Heap dump / dominator / GC root | 哪个长生命周期持有者保留对象 |
| Java used 回落但 GC 很密 | ART allocation profiling / Perfetto | 哪些调用栈制造 churn |
| Native allocated 持续增长 | heapprofd | 哪些 malloc/new 调用栈未释放 |
| Native RSS 高于 allocator 统计 | smaps、malloc_info、mmap trace | 缓存、碎片、直接映射或 swap 哪项成立 |
| Graphics 增长 | memtrack、SurfaceFlinger layer、GPU 专项工具 | 哪个 Surface、buffer 或 GPU 资源持有者未释放 |
| PSS/RSS 增长但 heap 稳定 | meminfo 分类、threads、maps、graphics | 增量属于 code、stack、mmap、共享页还是设备内存 |
| 进程消失 | `ApplicationExitInfo`、系统日志、LMKD 事件 | 退出原因、保护级别与上次采样上下文 |
| Native 非法访问 | HWASan / GWP-ASan / Malloc debug | 越界、use-after-free 或 double free 的访问栈 |


### 10. 交付前检查表

- [ ] 每个指标都标明单位、来源、进程和采样时刻。
- [ ] PSS 没有与 `memoryClass` 或 `largeMemoryClass` 计算比例。
- [ ] Java heap、native allocator、resident pages 和 Graphics 分开。
- [ ] Heap dump 结论包含预期生命周期与 GC root。
- [ ] heapprofd 结论注明采样窗口、interval（采样间隔）、符号和未覆盖的 `mmap`/graphics。
- [ ] Native RSS 与 heapprofd 的差值没有直接写成碎片。
- [ ] malloc debug 只用于 debuggable/root 受控环境。
- [ ] API 26+ 的软件 Bitmap 像素按 native 归属分析，HARDWARE Bitmap 另查图形内存。
- [ ] memtrack 缺失或为 0 时，没有断言 GPU 内存为 0。
- [ ] 4 KB 与 16 KB page size 使用不同基线分组。
- [ ] LMKD 判断包含 PSI、reclaim、swap/thrashing、adj 与设备配置。
- [ ] `ApplicationExitInfo` 的 PSS/RSS 被标为上次采样。
- [ ] 线上数据不含 heap 内容和敏感业务信息。

---

## 从异常曲线到分配责任

基线模型可以帮助我们提出假设，但增长究竟源于泄漏、缓存、抖动、图形资源还是系统共享内存，最终还要靠具体案例里的证据链来回答。

这一节复核四个公开案例。文中的具体数据均来自各自原文所述的实验环境，用来还原取证推理过程，不宜直接照搬为其他产品的阈值或收益目标；平台与内核机制仍以本文开头的版本基线为准，而早期设备案例则保留其原始的系统版本、ABI 与驱动条件。

| 案例 | 主要内存域 | 决定性证据 | 原文公布的结果 |
| --- | --- | --- | --- |
| 低内存导致冷启动退化 | 系统回收、文件页、I/O | 主线程 D 状态（不可中断睡眠）时长、`kswapd0`、进程终止与重启记录 | 原文未公布参数调整后的 A/B 数据 |
| 线上 Hprof 归因 Java OOM | Java 堆 | dominator tree（支配树）、Retained Size、GC Root 路径 | Helo 与美篇均有双月数据，口径见案例二 |
| PowerVR `renderD128` 映射增长 | GPU 用户态驱动、虚拟地址空间 | `syscall(__NR_mmap2)`、`KEGLGetPoolBuffers`、buffer pool（缓冲池）阈值 | 受影响机型实验的 OOM 崩溃率下降近 50% |
| MemoryThrashing 差分采样 | 原案例为 iOS Objective-C 对象 | 连续样本间的 alloc/dealloc（分配/释放）与存活实例差值 | 发布时处于测试环境监控，未公布线上 OOM 降幅 |

### 案例一：低内存导致冷启动等待 Block I/O

#### 现象与数据

我们先看现象。历史文章对比了低内存与正常内存下的冷启动 trace。按原图线程摘要逐行核对，Running 分别为 **682.137 ms** 和 **624.278 ms**；把全部 D 类状态统一相加，分别是 **783.385 ms** 与 **139.417 ms**。D 表示不可中断睡眠；带 Block I/O 标注的行才同时带有这类等待线索，把所有 D 一律写成磁盘读会过度归因。正常截图顶部的启动框选约为 1.223 s。

> ⚠️ 矛盾：原文用约 750/130 ms 概括 D 状态，且低内存 Running 另一处写成约 600 ms，与截图不完全一致。这里按截图全部 D 行重算：低内存为 619.033 + 28.417 + 131.776 + 4.159；正常为 106.320 + 32.428 + 0.669，单位均为 ms。两张线程摘要的选择范围分别为 2053.451/1227.232 ms，与顶部框选的 2.044/1.223 s 略有差别，不能混作同一比例轴。


这些数字只对应那一次采集到的 trace。如果只看总启动耗时，很容易把慢启动归咎于主线程代码本身；线程状态分布却指向了另一条线索：多出来的耗时主要花在等待内核与存储路径上。

#### 证据怎样形成完整链条

要把这段诊断做实，需要把四类证据对齐到同一条时间轴上：

1. 在 Perfetto 中圈出启动区间，比较主线程的 Running、Runnable（可运行但在等待 CPU）、Sleeping 与 D 状态耗时。
2. 展开 D 状态对应的内核调用栈，确认线程是否正在等待文件页、块设备或文件系统锁。
3. 在同一时间窗内检查 `kswapd0`、内存回收 tracepoint（跟踪点）、`meminfo`、`vmstat`、swap/ZRAM 和 PSI。
4. 检查 `lmkd` 与 ActivityManager 事件，确认同一进程是否在短时间内反复被终止，又被业务或系统重新拉起。

`mm/vmscan.c` 中的回收路径标明了 `kswapd` 与直接回收的执行位置，`include/trace/events/vmscan.h` 则定义了相应的回收 tracepoint。`lmkd.cpp` 通过 PSI 监视器感知资源停顿（stall），再结合进程重要性和内存状态选出需要终止的进程。排查时，这两部分证据必须按时间、进程和请求身份逐一对齐；回收繁忙、D 状态与终止记录同时出现只能提供相关性线索，仍需要缺页、回收或 I/O 等待链来证明系统压力是如何进入这一次启动关键路径的。需要注意，历史原文中提到的 QQ 终止—重启记录（日志为 `am_kill`、`empty #3`）其实来自另一段 Monkey 场景，属于那次 Monkey 压力测试下的现象，这次冷启动自身的 LMKD kill 证据仍需单独查找。

#### 根因判断

针对这类现象，原文给出了如下机制解释；在新的分析报告中引用时，仍应逐段补齐现场证据：

<!-- gracker-diagram: ch10-01-31-case-pressure-causality -->
![从相关性补齐请求级因果](../../assets/diagrams/ch10/ch10-01-31-case-pressure-causality.png)

图：回收、D 等待和进程终止共现只是线索。把原文不同样本分离，再补齐这次关键路径的因果证据。

- `[推断]` 低内存可能增加回收与文件页驱逐，需要同窗水位、回收和 refault/缺页记录。
- `[推断]` 若启动依赖的 odex、资源或配置页需从存储补入，等待可能进入关键路径；需调用栈与请求时序佐证，D 状态本身说不清读的是哪个文件。
- `[来源事实]` 另一段 Monkey 记录中有缓存进程反复终止和重启。其资源开销可以作为后续假设，这次冷启动的因果链还要靠本次 trace 内的证据。

主线程与 `kswapd0` 运行在同一个 CPU 核上确实可能加剧资源竞争，但单次 trace 中的同核现象还不足以证明调度策略存在缺陷。分析报告中应当把“trace 直接观察到的事实”与“基于内核机制的推论”分开记录。

#### 修复与验证

原文中曾给出调高 `extra_free_kbytes`（额外预留空闲内存）等历史建议。不过直接照搬到当前产品未必合适：内核回收参数、ZRAM、存储延迟、PSI 阈值和 `lmkd` 策略彼此联动，单项调大往往也会引发更多后台回收，甚至推高后台进程的重启率。

系统侧修复应以同场景下的 A/B 实验为准：

- 对比调优前后的 PSI `some/full`、分配线程同步回收（direct reclaim）、`kswapd` CPU 耗时、需要从存储读取的缺页（major fault）以及块 I/O 延迟。
- 核对 `lmkd` 每次选中的进程、实际释放量与后续重启情况，减少没有实际回收收益的“终止—重启”循环。
- 按设备内存档位分别校准回收、ZRAM 与杀进程策略，并用前台帧时间、启动耗时和后台存活率共同验收。

应用侧可以在 `TRIM_MEMORY_UI_HIDDEN` 或 `TRIM_MEMORY_BACKGROUND` 回调到来时释放可重建缓存。需要注意的是，自 Android 14（API 34）起，`TRIM_MEMORY_RUNNING_*`、`MODERATE`、`COMPLETE` 已不再投递，Android 15（API 35）又将相关常量标为 deprecated。这些旧 trim level 无法推断实时系统压力，大规模的缓存清理也应移出回调的同步路径。

复盘这个案例时，状态对比采用前文按同口径重算的 D 类总量（783.385 ms 与 139.417 ms），并保留各自的截图选区；由于原文并未公布参数调整后的量化 A/B 结果，这里只还原其取证链与调优方向。

### 案例二：用线上 Hprof 找到 Java OOM 的持有者

#### 现象

Java OOM 往往在 Bitmap 分配、字符串拼接或数组扩容等位置触发，但崩溃栈只记录了最后一次分配在哪儿失败，回答不了“此前的堆空间究竟被谁长期占用”。字节跳动 Client Infra 公开的方案采用线上 Hprof（Java 堆快照格式），把排查重心从崩溃点转向了对象持有关系；我们也沿用这一视角，先追查持有者，再回看崩溃栈。

#### 采集与分析

该公开方案由客户端采集、服务端恢复与自动分析三部分组成：

- 原方案默认在 Java OOM 发生时触发 dump，另外提供了可配置高水位阈值的 fork 子进程 dump 入口；这是两条历史实现路径。由于 fork 与 ART 状态协调、写时复制（CoW）以及子进程清理都带有约束条件，今天的普通 SDK 拿不到“绝对无停顿、零额外内存”的通用保证。
- Tailor（该方案的 Hprof 裁剪工具）会在 native 层移除字符串内容、Bitmap 像素等分析引用关系时无需保留的数据。原文公布的头条样本平均文件大小从 355 MB 降至 44 MB。
- 服务端会重建引用图和支配树，计算 Shallow Size、Retained Size 与 GC Root 路径，再按泄漏类、持有业务代码或大对象类进行聚合。
- 混淆后的类名和引用路径经 Retrace（根据映射文件恢复原始符号）还原后，问题即可分派给对应的代码所有者。

<!-- gracker-diagram: ed10-01-historical-hprof-acquisition-and-analysis -->
![历史 Hprof 两条采集入口汇入裁剪与持有关系分析](../../assets/diagrams/ch10/ed10-01-historical-hprof-acquisition-and-analysis.png)

图：仅复述Client Infra历史方案：默认Java OOM现场dump与可配置高水位fork是两入口，成功后汇入Tailor裁剪/压缩上报及服务端分析；OOM现场可失败，fork需要ART状态协调、CoW及子进程清理，不能当作普通SDK无停顿/低额外内存保证。裁剪字符串内容和Bitmap像素等分析不需数据，不证明隐私风险全部消除；355MB到44MB只是原文头条样本平均文件大小。服务端重建引用/支配关系，计算Shallow/Retained/GC Root并聚合，引用路径不是独占支配，更不能按引用数分摊Retained。结合映射文件Retrace后回到代码owner，修复重放同一场景核对实例数、Root与Retained，失败分配栈或单个heap峰值都不能代替历史持有关系。

线上 Hprof 可能包含账号、文本和业务对象，哪怕裁掉了字符串内容，仍可能有漏网的敏感字段。因此采集前必须经过用户授权与合规评审，上传链路也需要具备加密、限流、访问审计和过期删除机制。

#### 根因证据

在原文展示的按类聚合样本中，`ArticleCell` 共有 364 个实例，原文将该聚合大小称为总 Retained Size，截图顶栏标注为“对象大小 **51.29 MiB**”；展开后显示其中 280 个实例存在与 `MainActivity` 相关的引用路径。需要注意，这个聚合值并不意味着 51.29 MiB 全部由 `MainActivity` 独占支配，仍应逐组核对支配关系与其他 GC Root 路径。不过这组数据已经成功把排查重心从孤立的 OOM 崩溃栈移到了 `MainActivity` 的引用所有权上。

后续的修复动作需要遵循对象真实的引用语义：

- 页面退出后仍被异步任务、监听器或全局容器持有时，应及时取消任务、解除注册并清理页面引用。
- 实例数量符合业务预期但单个对象的 Retained Size 过大时，应削减单对象负载或收紧集合容量。
- 缓存需要长期保留时，必须明确容量上限、失效条件与低内存清理策略；`WeakHashMap` 只对 key 采用弱引用，无法替代完整的缓存淘汰策略。
- 从 Android 8.0（API 26）起，软件 Bitmap 像素位于 native heap，HARDWARE 像素归属图形内存。生命周期正常的 Bitmap 通常交给 GC 与运行时登记机制 `NativeAllocationRegistry` 自动清理，切忌把批量调用 `Bitmap.recycle()` 当作通用修复——显式提前回收反而可能让仍在绘制的调用方访问到已释放的像素。

修复完成后，应在相同场景下重放操作并再次 dump，验证实例数量、GC Root 路径与 Retained Size 同步下降。如果只看 Java heap 的峰值回落，很难区分究竟是引用关系修好了，还是采样时机或 GC 调度发生了变化。

#### 原文结果与 Android 17 增量

原文公布了两组接入后的产品数据：

- Helo 在一个双月内处理了 80% 以上的 Java OOM 问题，次日留存增长 2% 以上。
- 美篇在一个双月内 Java OOM 降低 80%，用户卡顿率也下降 80%。

由于原文未披露完整的实验设计与归因细节，这些数字只代表来源文章中特定平台客户在当时周期内的观察结果，不能直接用来推算任意 App 接入 Hprof 后的预期收益。

在系统能力层面，`ProfilingTrigger.TRIGGER_TYPE_OOM` 支持在发生 OOM 时请求采集 Java heap dump；如果应用安装了自定义的 `UncaughtExceptionHandler`，末尾仍须链回默认 handler，否则 OOM 触发器（trigger）不会生效。另一类 `TRIGGER_TYPE_ANOMALY` 则可由系统异常检测触发相应的诊断产物（artifact）。这两类触发都依赖系统版本、功能 flag、注册状态与系统策略；其中部分 anomaly 在同一 UID 下多包注册时还可能拿不到产物。即便 API 本身可用，触发请求也不保证一定能拿到文件——它们提供的只是新的采集入口，后续的引用图分析、隐私脱敏、聚合归因与修复验证，依然要由诊断系统来完成。

<!-- gracker-diagram: ch10-01-37-profiling-trigger-gates -->
![OOM 与 anomaly 触发有不同前置](../../assets/diagrams/ch10/ch10-01-37-profiling-trigger-gates.png)

图：API 37 提供的 trigger 仍受 flag、注册、限流和系统策略约束。OOM 自定义异常处理器需链回默认处理器；部分 anomaly 还有同 UID 多包限制。

### 案例三：PowerVR buffer pool 长期保留 `renderD128` 映射

#### 环境与复现

这个案例主要集中在华为 Android 10、联发科芯片、PowerVR GPU 与 32 位 `armeabi-v7a` 进程上，另有少量样本覆盖 Android 8.1、9、11 和 12。OOM 发生时，GPU 渲染设备节点（render node）`/dev/dri/renderD128` 的内存映射接近 1 GB，大量挤占了 32 位进程的虚拟地址空间。

团队在华为畅享 10e（Android 10）上做了对照实验：新增 10 个普通背景 View 时，映射量没有明显变化；但给新增 View 设置 `alpha=0.5` 后，每个 View 对应的 `renderD128` 虚拟映射大约增加 26,214,400 bytes，即 25 MiB（原文简称 25M）。需要注意，这是特定设备、驱动和复现工程下的测量值，缺乏依据将其外推到其他 GPU 平台。

#### 从缺失的 Hook 记录找到映射入口

排查初期，团队通过运行时拦截（Hook）常规的 `mmap`、`mmap64`、`mremap`、`__mmap2` 函数并未捕获到这批映射，`ioctl` 记录也解释不了增长来源。随后对厂商（vendor）库进行反汇编，才发现 `libsrv_um.so` 直接发起了 `syscall` 调用，系统调用号对应 32 位 ARM 的 `mmap2`。

于是将拦截范围缩小到 `libsrv_um.so` 与 `gralloc.mt6765.so` 对 `syscall` 的调用，增长的映射记录随即现身。这一证据直接推翻了“映射完全发生在内核驱动内部”的早期猜测——实际上是 PowerVR 用户态库绕过了 libc 的 `mmap` 符号，直接进入系统调用。

顺着调用栈继续追查，指向了 `libIMGegl.so` 的 `KEGLGetPoolBuffers`。每次增长会连续触发五次 `PVRSRVAcquireCPUMapping`，五类 buffer 合计约 25 MB，正好与前面 View 实验的增量吻合。绘制结束时，`KEGLReleasePoolBuffers` 只把 buffer 标记为空闲，而没有对称调用 `PVRSRVReleaseCPUMapping`。原文在 EGL surface 或 `CanvasContext` 销毁相关的调用栈中观察到了延迟释放，因此将该问题归类为 buffer pool 长期保留。不过，仅仅找到延迟释放路径还不足以排除生命周期泄漏，仍需验证在预期生命周期内释放是否真正执行、引用是否归零，以及新分配是否受上限约束。

<!-- gracker-diagram: ed10-01-powervr-entry-and-pool-lifetime -->
![直接 syscall 的映射入口与池条目归还后的持有关系](../../assets/diagrams/ch10/ed10-01-powervr-entry-and-pool-lifetime.png)

图：历史已识别PowerVR/ARM32设备和vendor版本中，常规mmap系列符号Hook没看到记录；反汇编发现libsrv_um.so直接syscall进入mmap2，限定libsrv_um.so/gralloc.mt6765.so入口后记录对应增长。因此缺Hook记录不能推出映射全部在内核内部。调用栈到KEGLGetPoolBuffers，可复用条目则复用，不足时该案例一次增长含五次AcquireCPUMapping；View复现的约25MiB增量是特定设备映射量，不是通用每View/RSS/物理成本。绘制后ReleasePoolBuffers只标idle而非立即ReleaseCPUMapping，虚线表示后续可复用。EGL surface/CanvasContext销毁相关调用栈可见迟到释放，仍需验证预期生命周期、引用归零与增长上限，存在释放路径不自动排除泄漏；Android17自动layer路径不能证明此旧pool行为仍存在。

#### 根因与历史修复

进一步反汇编显示，这个缓冲池为每类 buffer 设置了上限参数 `buffer_limits`。测试设备上的原始值为 50，三组对比日志测得的虚拟映射峰值分别为：阈值为 50 时达到 1,318,281,216 bytes，调为 20 时降至 531,849,216 bytes，调为 10 时降至 269,705,216 bytes（原文中分别概括为约 1.3G、530M、269M）。需要明确的是，这些数字属于该复现工程下的虚拟映射量，不能直接当作 RSS 或通用的 GPU 物理内存预算。团队随后针对已识别的 vendor 版本修改了该阈值；来源文章公布的受影响机型实验结果显示，OOM 崩溃率下降了近 50%，观察期间未再因 `renderD128` 问题阻断版本发布。

这属于针对非公开 vendor 实现的历史性干预，不宜当作通用 App 方案直接套用。其他厂商、驱动版本或进程位数可能采用完全不同的 pool 数据结构，贸然 Hook 私有函数也可能破坏正在使用的 GPU 资源。

在产品工程中，更稳妥的处置顺序如下：

- 先按设备型号、SoC、GPU、OS、驱动与 ABI 聚类，确认问题是否只集中在少数设备组合中。
- 监控 `/proc/self/maps` 或 `smaps` 中的 `renderD128` 映射，区分是虚拟地址空间耗尽还是物理驻留内存增长。
- 在受影响设备上减少使用能稳定触发映射增长的渲染组合，必要时仅针对这批设备降级动画或复杂视觉效果。
- 推进 64 位进程迁移可以缓解 32 位虚拟地址空间耗尽，但不会降低 buffer 本身的物理内存成本。
- 将最小复现工程、映射增长曲线与 vendor 调用栈提交给 SoC、GPU 或 ROM 厂商从底层修复。

#### Android 17 源码中的对应路径

在 `android-17.0.0_r1` 的 HWUI 实现中，`promotedToLayer()` 会先要求视图处于 `LayerType::None` 且满足 `fitsOnLayer()`，随后再检查 functor、image filter、stretch 或 alpha 混合等条件。其中的 alpha 分支要求同时满足 `!MathUtils::isZero(alpha)`、`alpha < 1` 以及存在重叠绘制（overlapping rendering），但这只是众多触发入口之一。之后的 `pushLayerUpdate()` 还会继续校验可渲染性与尺寸，再决定创建、更新还是销毁图层。这段源码可以解释为什么带 alpha 的组合可能会走进额外的硬件图层路径，但它本身证明不了 Android 10 时代 PowerVR 缓冲池的遗留行为仍延续到了 Android 17。

<!-- gracker-diagram: ch10-01-41-hwui-promotion-gates -->
![自动图层提升与后续更新条件](../../assets/diagrams/ch10/ch10-01-41-hwui-promotion-gates.png)

图：r1 的 alpha 只是一条触发分支，前置尺寸和后续有效性检查仍存在。这段源码不能证明旧 PowerVR pool 问题延续至新版本。

`hasOverlappingRendering()` 返回 `false` 只适用于内容确实不存在重叠混合的自定义 View，如果误用，可能直接改变画面渲染结果；而 `LAYER_TYPE_NONE` 也关不掉由 alpha 触发的自动图层提升。图形渲染相关的优化，仍应结合 Frame Timeline（帧时间线）、GPU 内存和实机画面对比来共同验收。

### 案例四：保留 MemoryThrashing 的差分思路与平台边界

#### 原案例的 iOS 背景

MemoryThrashing 案例最初来自抖音直播 iOS 团队。其实现借助 Objective-C 运行时拦截（Runtime Hook）`alloc` 与 `dealloc`，按 Class 统计分配、释放与存活实例数，与 Android 侧的 `Runtime.totalMemory()`、Java 堆或 ART 分配接口分属完全不同的运行时体系。

这套工具按多个时间点采样，通过对相邻样本做对象数量差分，主要定位了两类异常：

- **驻留堆积**：原文样本在两个采样周期之间净增 234,024 个对象，样本末仍有 238,800 个 `LivexxxBigDataRead` 实例，截图记录占用 11,462,400 bytes（约 10.93 MiB）。
- **临时对象洪峰**：开播特效在人脸识别后频繁创建轮廓模型。在小于 5 秒的采样周期内，原文称临时对象增量峰值约 60,000、累计分配超过百万次；文中展示的三个累计分配计数分别为 32,616、73,979 和 134,731，后两者之差正好是 60,752 次分配。需要留意的是，这个差值统计的是累计分配次数，不能代表仍然存活对象的净增长；至于“百万次”则是原文另一处概括，从这三行截图本身算不出来。

<!-- gracker-diagram: ed10-01-oc-allocation-and-live-differences -->
![OC 两个历史样本分别计算存活净增与累计分配次数](../../assets/diagrams/ch10/ed10-01-oc-allocation-and-live-differences.png)

图：历史iOS工具Hook OC alloc/dealloc并按Class采样，两支是两个独立样本，不拼同一Class/时间窗。左侧存活从4776到238800净增234024个，末值11462400bytes；右侧相邻累计alloc从73979到134731增加60752次，期间对象可已释放，不能称仍存活60752个。原图另有累计32616，三行不直接推出累计百万，百万为原文另一概括。净存活增长仍需区分业务/缓存/泄漏，差分指出类而不回答持有者，继续查引用关系。工具只覆盖OC对象并可影响方法缓存，Android按ART/malloc/映射/图形另选采集器；原文发布时为测试部署，未提供线上OOM收益。

第二类临时对象虽然很快被释放，却会持续拉高 CPU 与分配器开销；第一类堆积则需要进一步追查引用关系，区分正常业务保留、缓存超限与内存泄漏。对象数量差分解决的是“哪类对象在增长”，要弄清“谁在持有”，最终仍要回到引用关系数据。

原文也明确交代了该方案的局限：只覆盖 Objective-C 对象，无法分析多个内存区域，缺少完整引用图，而且 Hook 会影响方法缓存。文章发布时，工具只部署在测试环境中，线上部署尚在规划阶段，因此并没有可引用的线上 OOM 降幅或定位耗时改善数据。

#### Android 上如何复用

在 Android 上，可以借鉴“连续样本差分 + 异常时触发深度采集”的思路，但具体采集器必须按内存域分别选型：

| 内存域 | 轻量信号 | 深入证据 |
| --- | --- | --- |
| Java/Kotlin 对象 | heap 使用量、GC 次数与停顿、受控场景的对象分配样本 | Java heap dump、实例数差分、GC Root 路径 |
| Native malloc | RSS/PSS 分类、`anon:libc_malloc`、分配速率 | heapprofd 调用栈与分配生命周期 |
| 图形缓冲区 | DMA-BUF、GPU 驱动映射、Surface 数量 | `dmabuf_dump`、smaps、Perfetto graphics 轨道、厂商工具 |
| 文件映射与线程栈 | maps 分类、线程数、地址空间余量 | smaps、线程创建栈、映射调用栈 |


如果业务探针（埋入业务流程的轻量采样代码）只盯着总 PSS 一条曲线，Java 临时对象、native buffer 与 GPU 映射就会混杂在一起。更可靠的告警条件应当由“场景 + 内存域 + 增长速率 + 回落情况”共同构成，具体阈值则应基于目标设备的性能档位与同场景历史分位数来标定，避免直接沿用缺乏依据的固定时间或容量常数。

从系统提供的触发能力看，Android 15（API 35）引入了由应用主动发起的 `ProfilingManager.requestProfiling()`，Android 16（API 36）增加了触发器注册机制，Android 17（API 37）又补齐了 OOM、异常（anomaly）与冷启动（cold-start）等 trigger。需要注意，OOM trigger 是在发生 OOM 时申请采集 Java heap dump，并不能替代 OOM 之前的内存突增探针；而且所有采集结果都受系统限流和策略约束，线上方案仍需妥善处理“触发后未产出诊断文件”的兜底情况。

实战中，当差分指标显示某一类 Java/Kotlin 实例异常增长时，再进一步触发 heap dump 或 allocation profile；当增长落在 native 或 graphics 域时，则切换至 heapprofd、`smaps` 或图形内存工具。这样既能保留 MemoryThrashing 低成本及时发现异常的思路，又能贴合 Android 多内存域的真实机制。

### 四个案例共同说明什么

#### OOM 栈与历史占用的分工

OOM 崩溃栈只记录了最后失败的那次分配点；要追查此前的内存究竟被谁占满，仍需借助 Java Hprof 的 Retained Size、native 分配调用栈、GPU 映射来源以及进程虚拟地址空间分布来还原现场。

#### 内存上涨曲线的机制分类

Java 引用泄漏、短命对象洪峰、malloc 堆积、GPU buffer pool、文件映射与系统回收压力，背后对应着截然不同的机制和证据链。不过排查入口是一致的：先用 `dumpsys meminfo`、`smaps` 和 Perfetto 把增长归入明确的内存域，再切入对应的专用工具深挖。

#### 发布数字的实验上下文

前文提到的 80%、近 50% 以及 355 MB 到 44 MB，都是来源文章在特定产品、统计周期或机型上获得的实测数据。引用这类公开数字时，应一并注明对应的产品背景、测试周期、设备条件与指标口径；对于未公布定量收益的案例，也应如实保留结果空白，不去做无根据的“明显改善”式外推。

#### 驱动与 ROM 问题的设备聚类

当异常集中在特定的 SoC、GPU、OS 与 ABI 组合时，设备聚类特征本身就是关键证据。面对这类故障，大范围修改通用业务代码不仅收益有限，还会放大回归测试范围；更有针对性的做法是在少量目标设备上稳定复现，配合定向规避策略，并将证据交由芯片或 ROM 厂商从底层修复。

### 复盘清单

- 现象对应 Java heap、native heap、graphics、mmap、线程栈还是整机压力？
- 效果数字来自本项目实验、公开案例，还是尚未验证的预期？
- 低内存 trace 是否同时包含线程状态、回收、PSI、I/O 与 `lmkd` 事件？
- Hprof 是否记录 Retained Size、GC Root 路径、版本和场景？
- 32 位 OOM 是否同时检查了地址空间余量与 RSS？
- vendor 故障是否按设备、SoC、GPU、驱动、OS 和 ABI 聚类？
- 突增探针是否按内存域采样，并为缺失 artifact 设计回退路径？
- 修复后是否重放同一场景，比较同口径的峰值、回落速度、帧时间和崩溃率？

### 延伸阅读

- [4.1 Android 与 Linux 内存管理全景](../../part1-fundamentals/ch04-memory/01-android-linux-memory-overview.md)：统计口径、物理页与回收机制。
- [4.2 ART Heap、GC 与后台维护调度](../../part1-fundamentals/ch04-memory/02-art-heap-gc-maintenance.md)：Java 堆、GC 与存活对象的关系。
- [4.3 lmkd、Cached App Freezer 与内存压力治理](../../part1-fundamentals/ch04-memory/03-lmkd-freezer-memory-pressure.md)：系统压力、进程优先级与后台状态。
- [23.2 内存泄漏检测与治理](../../part5-app/ch23-memory-practice/02-memory-leak-governance.md)：引用链与生命周期修复。
- [14.1 Perfetto 入门、Trace 抓取与可靠性](../../part3-tools/ch14-perfetto/01-perfetto-intro-capture-reliability.md)：采集配置、数据源与 trace 完整性。

### 相关章节

- **10.1 本文**：内存域分类、基线、持续增长、`dumpsys meminfo`、smaps、Perfetto 与 heapprofd。
- [23.2 内存泄漏检测与治理](../../part5-app/ch23-memory-practice/02-memory-leak-governance.md)：引用所有权、GC Root 与生命周期修复。
- **10.2 低内存对系统性能的影响**：回收、PSI、`lmkd`、ZRAM 与前台性能。
- **10.3 内存抖动与频繁 GC**：分配速率、GC 停顿和短命对象。
- **10.4 GPU 与图形内存统计、归因与诊断**：DMA-BUF、GPU 映射与图形缓冲区。
- **4.3 Low Memory Killer**：Android 17 userspace `lmkd` 路径。
- **7.2 典型场景分析**：从线程状态和关键路径解释卡顿。

## 参考资料

- [Android 中的卡顿丢帧原因概述——低内存篇](https://www.androidperformance.com/2019/09/18/Android-Jank-Due-To-Low-Memory/)
- [Android-PSI 详解：libpsi 源码解析](https://juejin.cn/post/7677254638325727242)
- [字节跳动应用性能监控帮助客户 Java OOM 崩溃率下降 80%](https://mp.weixin.qq.com/s?__biz=Mzg2NTYyMjYxNg==&mid=2247486007&idx=1)
- [抖音 renderD128 系统级疑难 OOM 分析与解决](https://mp.weixin.qq.com/s?__biz=MzI1MzYzMjE0MQ==&mid=2247514363&idx=1)
- [MemoryThrashing：抖音直播解决内存抖动实践](https://mp.weixin.qq.com/s?__biz=MzI1MzYzMjE0MQ==&mid=2247496677)
- [Android Developers：内存管理概览](https://developer.android.com/topic/performance/memory-overview)
- [Android Developers：ProfilingManager](https://developer.android.com/reference/android/os/ProfilingManager)
- [Android Developers：ProfilingTrigger](https://developer.android.com/reference/android/os/ProfilingTrigger)
- [Perfetto：heapprofd](https://perfetto.dev/docs/data-sources/native-heap-profiler)
- [AOSP `ComponentCallbacks2.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/content/ComponentCallbacks2.java)
- [AOSP `RenderProperties.h`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/hwui/RenderProperties.h)
- [AOSP `RenderNode.cpp`（android-17.0.0_r1）](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/hwui/RenderNode.cpp)
- [AOSP `ProfilingTrigger.java`（android-17.0.0_r1）](https://android.googlesource.com/platform/packages/modules/Profiling/+/refs/tags/android-17.0.0_r1/framework/java/android/os/ProfilingTrigger.java)
- [AOSP `lmkd.cpp`（android-17.0.0_r1）](https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/lmkd.cpp)
- [AOSP `libpsi/psi.cpp`（android-17.0.0_r1）](https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/libpsi/psi.cpp)
- [AOSP `libpsi/include/psi/psi.h`（android-17.0.0_r1）](https://android.googlesource.com/platform/system/memory/lmkd/+/refs/tags/android-17.0.0_r1/libpsi/include/psi/psi.h)
- [Android Common Kernel `mm/vmscan.c`（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/mm/vmscan.c)
- [Android Common Kernel `vmscan.h` tracepoints（android17-6.18-2026-06_r6）](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/include/trace/events/vmscan.h)
- [Eclipse MAT：Shallow 与 Retained Heap](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html)
- [Eclipse MAT：Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html)
- [固定内核：procfs 与 smaps 口径](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/Documentation/filesystems/proc.rst)
- [固定内核：smaps_account 的共享计数](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/fs/proc/task_mmu.c)
- [r1：AM 内存查询的权限与缓存](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/am/ActivityManagerService.java)
- [r1：malloc 调试属性与环境变量选择](https://android.googlesource.com/platform/bionic/+/android-17.0.0_r1/libc/bionic/malloc_common_dynamic.cpp)
- [r1：Bitmap.HARDWARE 与图形内存](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/graphics/java/android/graphics/Bitmap.java)
- [NDK：HWASan](https://developer.android.com/ndk/guides/hwasan)
- [NDK：GWP-ASan](https://developer.android.com/ndk/guides/gwp-asan)

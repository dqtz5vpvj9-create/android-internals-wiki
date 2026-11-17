---
title: 文件系统与 I/O 调度
chapter: '6.2'
section: '6.2'
applicable_versions: Android 10 (API 29) - Android 17 (API 37)
last_verified: '2026-11-09'
last_source_verified_at: '2026-11-09T10:39:35+08:00'
last_idle_audit_at: '2026-11-09T10:39:35+08:00'
last_verified_against: AOSP android-17.0.0_r1 external/sqlite batch atomic write anchors + Android Common Kernel android17-6.18-2026-06_r6 ext4/F2FS/EROFS/GKI anchors + source.android EROFS/16KB page size/Virtual A/B docs + Android Developers SharedPreferences docs + Linux kernel ext4/F2FS/EROFS/VFS docs
confidence: medium-high
sources:
- type: blog
  path: Personal-Knowlodge/source/2026-03-08_wechat_手机Android存储性能优化架构分析_1.md
- type: blog
  path: Personal-Knowlodge/source/2026-03-06_wechat_深入代码细节看f2fs在磁盘上的组织方式.md
- type: blog
  path: Personal-Knowlodge/source/2026-03-07_wechat_性能优化基础_深入理解Linux文件系统.md
- type: official
  path: source.android.com/docs/core/storage
- type: official
  path: developer.android.com/training/data-storage
- type: official
  path: android.googlesource.com/platform/external/sqlite/+/refs/tags/android-17.0.0_r1/
- type: official
  path: android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/
- type: official
  path: source.android.com/docs/core/architecture/kernel/erofs
- type: official
  path: source.android.com/docs/core/architecture/16kb-page-size/16kb
- type: official
  path: source.android.com/docs/core/ota/virtual_ab
- type: official
  path: developer.android.com/reference/android/content/SharedPreferences.Editor
- type: official
  path: www.kernel.org/doc/html/latest/filesystems/f2fs.html
- type: official
  path: www.kernel.org/doc/html/latest/filesystems/ext4/index.html
- type: official
  path: www.kernel.org/doc/html/latest/filesystems/erofs.html
- type: official
  path: www.kernel.org/doc/html/latest/filesystems/vfs.html
- type: material
  path: Cubox/IO调度器详解-2024-03-08.md
- type: material
  path: Personal-Knowlodge/source/2026-03-08_wechat_手机Android存储性能优化架构分析_1.md
- type: material
  path: Personal-Knowlodge/source/2026-03-07_wechat_性能优化基础_深入理解Linux文件系统.md
- type: aosp-kernel
  path: kernel/common block/Kconfig.iosched, block/mq-deadline.c, block/kyber-iosched.c, block/blk-ioprio.c @ android17-6.18-2026-06_r6
- type: aosp-kernel
  path: kernel/common arch/arm64/configs/gki_defconfig, Documentation/admin-guide/cgroup-v2.rst, Documentation/admin-guide/sysctl/vm.rst, include/uapi/linux/stat.h @ android17-6.18-2026-06_r6
- type: aosp
  path: system/core/libprocessgroup/profiles/cgroups.json, task_profiles.json; rootdir/init.rc @ android-17.0.0_r1
- type: aosp
  path: system/core/init/service_parser.cpp, init/service_utils.cpp, libcutils/iosched_policy.cpp @ android-17.0.0_r1
- type: aosp
  path: external/perfetto/src/trace_processor/perfetto_sql/stdlib/linux/block_io.sql @ android-17.0.0_r1
- type: aosp
  path: external/sqlite/dist/Android.bp, dist/sqlite-autoconf-3500600/sqlite3.c @ android-17.0.0_r1
- type: official
  path: https://source.android.com/docs/core/perf/cgroups
- type: official
  path: https://docs.kernel.org/block/ioprio.html
- type: official
  path: https://docs.kernel.org/block/deadline-iosched.html
- type: official
  path: https://docs.kernel.org/block/bfq-iosched.html
- type: official
  path: https://docs.kernel.org/admin-guide/cgroup-v2.html
- type: official
  path: https://docs.kernel.org/admin-guide/sysctl/vm.html
- type: official
  path: https://perfetto.dev/docs/analysis/stdlib-docs
- type: official
  path: https://perfetto.dev/docs/data-sources/cpu-scheduling
tags:
- storage
- filesystem
- ext4
- f2fs
- erofs
- io-scheduling
- perfetto
status: finalized
last_rework_at: '2026-08-19T17:45:17+08:00'
related_chapters:
- '6.1'
- '6.3'
- '6.4'
- '14.10'
last_consolidated_at: '2026-08-24'
consolidated_from:
- src/part1-fundamentals/ch06-storage/02-filesystem.md
- src/part1-fundamentals/ch06-storage/03-io-scheduling.md
---

# 文件系统与 I/O 调度

应用发起的 I/O 会经由系统调用进入 VFS、页缓存和具体文件系统；只有在缓存未能满足请求，或需要回写与同步落盘时，数据才继续穿过块层与设备队列送往存储器件。这一节围绕两个问题展开：文件系统如何组织数据并保证持久化，以及 I/O 调度如何对并发请求排序、合并与限流。

> 源码基线：Android 17 / API 37，AOSP `android-17.0.0_r1`；Android Common Kernel `android17-6.18-2026-06_r6`。

## VFS、页缓存与文件系统语义

### VFS 与 Page Cache（页缓存）：统一接口之下的差异

VFS（Virtual File System，虚拟文件系统）借助 `super_block`、`inode`（索引节点）、`dentry` 和 `file` 等内核对象向上暴露统一的文件操作接口，分别对应已挂载的文件系统、文件本体与元数据、目录项以及单次打开的文件句柄。应用调用同一套 `open()`、`read()`、`write()` 和 `fsync()`，VFS 再把请求分发到具体文件系统的 `file_operations`、`address_space_operations` 等实现上。接口虽然统一，底层行为却随文件系统差异很大，分析 I/O 问题最终都得落回具体文件系统。

<!-- gracker-diagram: ch06-02-vfs-objects -->
![VFS 对象与操作分发](../../assets/diagrams/ch06/ch06-02-vfs-objects.png)

图：dentry 表示名字关系，inode 表示文件本体，file 表示一次打开；VFS 按操作接口分发到具体实现。

在普通缓冲 I/O 中，`write()` 通常只改写 Page Cache 并把页面标为 dirty，由内核回写线程在后台异步提交；而 `fsync()` 要求指定文件在对应范围内达成持久化语义，因此调用线程可能需要等待以下几类工作完成：

- 文件数据写回；
- 影响文件可读性的元数据更新；
- journal（事务日志）、F2FS node 或 checkpoint 等崩溃恢复信息；
- 块设备 cache flush（缓存刷写）。

Page Cache 命中往往会掩盖不同文件系统在底层读取上的差异。分析随机读性能时，只有先分清页缓存命中、page fault（缺页）触发的读取，以及真正落盘的设备读取，才不会把内存访问速度记到文件系统账上。

<!-- gracker-diagram: ch06-02-buffered-persistence -->
![缓存返回与持久化完成](../../assets/diagrams/ch06/ch06-02-buffered-persistence.png)

图：write 返回通常只表示数据进入缓存；fsync 要等待对应持久化工作，flush/FUA 的使用由文件系统与块层条件决定。

### 先把 `fsync` 卡顿放回完整 I/O 路径

在 Perfetto 里，有时会看到主线程进入一段不可中断睡眠，调用栈停在 `fsync()`、`fdatasync()` 或文件关闭附近。这是持久化相关等待的一条线索，仍需结合调用栈与内核事件进一步确认——文件关闭本身并不等同于一次 `fsync()`，不可中断睡眠也可能源自其他内核资源。要把延迟定位到具体层级，需要把这次同步写放回完整的 I/O 路径中考察，它通常会穿过以下五层：

1. 应用或数据库提交修改。
2. VFS 把脏页（即内存中已修改、尚未写回存储的数据页）交给 ext4 或 F2FS。
3. 文件系统写出文件数据、必要元数据以及恢复信息。
4. 块层完成请求合并、调度、加密与 device-mapper（设备映射层）映射。
5. UFS 控制器与器件内部 FTL 完成物理写入与缓存刷新。

此外，`fsync()` 的实际返回语义还受挂载参数与写屏障影响；存储设备如何实现 flush（刷新设备写缓存）与 FUA（Force Unit Access，要求本次写入到达非易失介质），也会直接左右等待时长。文件系统能够优化路径中的一部分环节，但器件尾延迟、温控降频、闪存磨损与队列拥塞本身无法由文件系统消除。

SQLite 一次修改会触发几次同步同样取决于运行条件：事务边界、journal 模式、`PRAGMA synchronous`、是否发生 cache spill（缓存页提前写出），以及文件系统是否具备 SQLite 可识别的原子批写能力，都会改变同步次数，并不是每执行一条 SQL 就固定调用一次 `fsync()`。

至于 `SharedPreferences.apply()`，它会先更新内存映射并把写盘任务排入后台；虽然免去了调用点上的直接阻塞，但排队中的写盘任务依然可能在组件生命周期切换时阻塞主线程，进而引发 ANR（应用无响应）。

### ext4：成熟的通用读写文件系统

#### ext4 解决了哪些问题

ext4 在 arm64 GKI（Generic Kernel Image，通用内核镜像）中仍作为内建文件系统启用（`CONFIG_EXT4_FS=y`），主要依赖以下机制来组织分配与保证一致性：

- **extent（区段）**：用连续区间描述物理块映射，大幅降低大文件的元数据开销。
- **delayed allocation（延迟分配）**：在缓冲写阶段暂缓分配物理块，让多块分配器有机会拼出更连续的磁盘布局。
- **multiblock allocator（多块分配器）**：一次性批量挑选连续空闲块。
- **jbd2 journal**：记录维持文件系统一致性所需的修改。常见的 `data=ordered` 模式主要在日志中记录元数据，并要求对应的数据块先于元数据日志提交完成。
- **fast commit（快速提交）**：在条件允许时仅记录较小的增量提交信息；遇到不支持的操作则会回退到完整 journal commit。

常说的“就地更新”指的是 ext4 在逻辑块分配上的倾向。ext4 直接管理的是逻辑块，底层 NAND 的物理擦除、有效页搬移和磨损均衡都由 UFS/eMMC 内部的 FTL（闪存转换层）接管，固定大小的 NAND erase block（擦除块）也存在于 FTL 内部，因此主机侧的一次小写入并不直接对应器件内固定尺寸的“读—改—擦—写”。

<!-- gracker-diagram: ch06-02-ext4-allocation -->
![ext4 缓冲写分配与有序日志](../../assets/diagrams/ch06/ch06-02-ext4-allocation.png)

图：extent 合并连续逻辑映射，延迟分配为批量布局提供机会；data=ordered 约束相关数据先于元数据日志提交完成。

如今 ext4 依然是 Android 设备的候选方案之一，最终采用与否，取决于产品的分区职责、升级方案、故障恢复经验与性能目标。

#### ext4 `fsync` 的等待路径

下面这段摘自 `fs/ext4/fsync.c` 的代码展示了 ext4 同步文件时的等待对象：

```c
ret = file_write_and_wait_range(file, start, end);
if (ret)
        goto out;

ret = ext4_fsync_journal(inode, datasync, &needs_barrier);

if (needs_barrier)
        err = blkdev_issue_flush(inode->i_sb->s_bdev);
```

可以看到，这条路径先写出并等待目标文件范围的数据，再等待对应的 journal transaction（日志事务）提交；当需要写屏障时，还会下发一次块设备 flush。对于普通文件，`ext4_fsync_journal()` 会尝试走 `ext4_fc_commit()`，最终能否使用 fast commit 取决于文件系统特性与本次修改类型。

<!-- gracker-diagram: ch06-02-ext4-sync-transaction -->
![ext4 fsync 与 journal 等待范围](../../assets/diagrams/ch06/ch06-02-ext4-sync-transaction.png)

图：fsync 先等待目标文件数据，再等待相关 journal/fast commit；同一日志事务可能包含其他工作，最终按需 flush 并报告错误。

因此，ext4 的一次 `fsync()` 有可能捎带等待同一 journal transaction 里的其他写入，但这并不代表它要等全系统所有进程的脏数据，也不会每次都触发完整 checkpoint。诊断这类等待时，应当把 `ext4_sync_file_enter/exit`、jbd2 commit 与块层事件放在同一时间轴上核对。

### F2FS：围绕闪存负载组织写入

#### LFS 思路与 F2FS 的修正

F2FS 借鉴了 LFS（Log-Structured File System，日志结构文件系统）的思路，旨在减少随机覆盖写，同时设法控制经典 LFS 的两大痛点：wandering tree（更新叶节点后逐级向上改写索引节点）与空间清理开销。arm64 GKI 默认启用了以下编译选项：

- `CONFIG_F2FS_FS=y`
- `CONFIG_F2FS_FS_COMPRESSION=y`
- `CONFIG_F2FS_FS_SECURITY=y`

F2FS 以 segment 作为基本空间分配单位（默认包含 512 个 block），一个 section 由一个或多个 segment 组成。它的核心磁盘结构各自承担明确分工：

- **NAT（Node Address Table）**：把 `nid`（节点编号）映射到最新 node block 的物理地址；inode、direct node 和 indirect node 都属于 node。
- **SIT（Segment Information Table）**：记录每个 segment 内的有效块数量、有效位图及类型信息，供空间分配与 GC（垃圾回收）决策使用。
- **SSA（Segment Summary Area）**：保存 segment 内各块的归属摘要，方便 GC 反向核查块是否仍然有效。
- **Checkpoint**：固化一组可恢复的一致状态，并通过双 checkpoint pack 在挂载恢复时选取有效版本。
- **多路 active logs（活跃日志）**：按 node/data 及冷热程度分流写入，尽可能降低后续 GC 搬移有效块的代价。

<!-- gracker-diagram: ch06-02-f2fs-metadata-roles -->
![F2FS 的日志、有效性与恢复结构](../../assets/diagrams/ch06/ch06-02-f2fs-metadata-roles.png)

图：active logs 分流 node/data 与冷热写入；NAT 定位 node，SIT 记录有效块，SSA 提供归属摘要，checkpoint 固化可恢复状态。 箭头表示状态协作，不代表每次 GC 后立即 checkpoint。

这里需要分清 NAT 与数据块地址的职责边界：NAT 只负责 `nid → node block address` 的映射，真正的文件数据块地址则存放在 inode 或其他 node 的地址数组里。正因多出这层间接映射，node 发生搬移时只需更新 NAT 记录，父节点依然可以引用稳定的 `nid`，从而化解了 wandering tree 带来的级联改写。

<!-- gracker-diagram: ch06-02-f2fs-nat-mapping -->
![F2FS 的 NAT、node 与数据地址](../../assets/diagrams/ch06/ch06-02-f2fs-nat-mapping.png)

图：NAT 解析 node 的当前位置，node 的地址数组再解析文件数据块；node 搬移时更新 NAT，父节点仍可引用稳定 nid。

#### SSR 与 IPU：追加式写入的例外

追加式写入虽是 F2FS 的默认策略，但存在两类明确例外。首先是分配模式：默认的 adaptive（自适应）模式会在 LFS 顺序分配与 SSR（Selective Segment Reuse，选择性复用分段）之间动态切换——空间充裕时，out-of-place update（异地更新）保持追加写；空间趋紧时，SSR 会复用已用 segment 中的空闲空洞。如果显式挂载为 `mode=lfs`，主区域将禁用随机覆盖分配，但代价是需要更多连续空闲空间。

其次是写入路径：F2FS 同样具备 IPU（in-place update，就地更新）路径。内核的 `f2fs_do_sync_file()` 会在 `fdatasync()` 或脏页较少时设置 `FI_NEED_IPU`，随后执行范围写回。因此，F2FS 并非每次数据修改都走异地更新或 CoW（写时复制）。

<!-- gracker-diagram: ch06-02-f2fs-opu-ipu-ssr -->
![OPU / IPU 与 LFS / SSR 的两个维度](../../assets/diagrams/ch06/ch06-02-f2fs-opu-ipu-ssr.png)

图：F2FS 既要决定数据地址是否变化，也要决定新地址如何分配；SSR 复用的是 segment 空洞，IPU 则覆盖当前有效数据块地址。

当前内核中 `f2fs_need_SSR()` 的判定条件按顺序依次检查：

- `mode=lfs` 会直接禁用 SSR；
- `GC_URGENT_HIGH` 或 checkpoint disabled 状态下需要启用 SSR；
- 常规模式下则比较 free sections 与 dirty node/dentry/inode metadata、`min_ssr_sections`、reserved sections 所需空间。

这些阈值直接取决于运行时状态与格式化参数，并不存在一个适用于所有设备的固定百分比阈值；排查时直接读取现场状态更可靠。

<!-- gracker-diagram: ch06-02-f2fs-ssr-gates -->
![f2fs_need_SSR 的判断次序](../../assets/diagrams/ch06/ch06-02-f2fs-ssr-gates.png)

图：先检查 mode=lfs；只有未被它排除时，urgent/禁用 checkpoint 或空间阈值才可能要求 SSR。

#### `fsync`、roll-forward 与 checkpoint

在一次普通的 `fsync()` 中，F2FS 会先写回目标文件的数据页，再决定后续的恢复信息策略：对于普通且可 roll-forward（通过重放 fsync node 恢复）的文件，只需写出带 fsync 标记的 node 链并发出必要的 flush；如果涉及非普通文件、压缩文件、硬链接或超级块明确要求 checkpoint，则可能转入完整 checkpoint。

<!-- gracker-diagram: ch06-02-f2fs-fsync-recovery -->
![F2FS fsync 的恢复分支](../../assets/diagrams/ch06/ch06-02-f2fs-fsync-recovery.png)

图：正常启用 checkpoint 的路径先写数据，再按恢复条件选择完整 checkpoint 或 fsync node；没有新增修改时还可能提前结束。

上述分支针对的是正常启用 checkpoint 的可写文件系统；若处于 checkpoint disabled 状态，`f2fs_do_sync_file()` 在完成范围写回后会提前返回，此时便不能沿用常规的 checkpoint/roll-forward 持久化推断。遇到没有新增修改等情况时，系统同样可能跳过恢复信息写入。较短的 roll-forward 路径能缩减恢复信息与等待范围，但仍须守住掉电恢复语义。无论走哪条分支，设备 cache flush、node writeback（节点回写）、checkpoint 以及 GC 都可能推高尾延迟，F2FS 上的 `fsync()` 依然有不容忽视的同步开销。

#### 原子文件写与 Android SQLite

内核在 `include/uapi/linux/f2fs.h` 中暴露了以下原子写控制命令：

- `F2FS_IOC_START_ATOMIC_WRITE`
- `F2FS_IOC_COMMIT_ATOMIC_WRITE`
- `F2FS_IOC_ABORT_ATOMIC_WRITE`
- `F2FS_IOC_START_ATOMIC_REPLACE`

调用 `f2fs_ioc_start_atomic_write()` 时，F2FS 会为普通文件准备一个 COW（写时复制）inode；进入 commit 路径后，由 `f2fs_commit_atomic_write()` 安装修改并按 atomic 语义同步文件，在完成或失败后清理原子写状态。这里的“原子”指的是崩溃恢复时这一批页修改要么全部可见、要么全部不可见，写入操作本身依然伴随 I/O 等待。

<!-- gracker-diagram: ch06-02-f2fs-atomic-cow -->
![F2FS 原子文件写的 COW 生命周期](../../assets/diagrams/ch06/ch06-02-f2fs-atomic-cow.png)

图：START 为普通可写文件准备 COW inode；COMMIT 安装修改并执行 atomic 同步，随后清理原子状态。

在应用层，AOSP SQLite 在 `external/sqlite/dist/Android.bp` 中开启了 `SQLITE_ENABLE_BATCH_ATOMIC_WRITE`，为原子批写留出了编译期开关。但运行时仍要连过几道门槛：Unix VFS（Unix 平台的虚拟文件系统适配层）会先通过 `F2FS_IOC_GET_FEATURES` 查询 `F2FS_FEATURE_ATOMIC_WRITE`，成功且命中该能力位后才向上报告 `SQLITE_IOCAP_BATCH_ATOMIC`；真正执行批写时才会下发 `F2FS_IOC_START_ATOMIC_WRITE`。同时，SQLite pager（页面缓存与事务管理模块）还会核对当前数据库状态与事务条件。

在 r1 的 pager 实现中，WAL 走的是独立分支；能够进入 batch atomic 的候选提交必须同时满足：没有 super-journal、VFS 报告支持该能力、未关闭同步，且 journal 仍保存在内存中。条件全部成立后才会尝试 BEGIN / 写页 / COMMIT，若执行中途出错仍可能回退到普通 journal 或向上报错。换言之，编译宏开启、分区采用 F2FS 与单次事务实际走通 batch atomic 路径之间，必须逐层核对才能确认。

<!-- gracker-diagram: ch06-02-sqlite-batch-decision -->
![SQLite F2FS batch atomic 的实际门槛](../../assets/diagrams/ch06/ch06-02-sqlite-batch-decision.png)

图：编译开关、GET_FEATURES 能力位、非 WAL pager 条件和实际 ioctl 执行逐层成立，才有本次 batch atomic 提交。

#### GC：空间紧张时为什么会抬高尾延迟

F2FS 的异地更新会在原地留下大量无效块，回收这些空间是 GC 的核心任务：选定 victim segment（待回收分段），核查其中仍然有效的数据与 node，将有效块搬移到新位置后释放整个 segment。空闲时可由后台 GC 慢慢消化；一旦可用 section 吃紧，写入路径上的请求线程就可能被迫直接参与回收，或者挂起等待回收释放空间。

6.18 源码对空间紧张的判定已经不同于早期 kernel 6.6 的 lower/upper 阈值写法。下面这段摘自 `fs/f2fs/segment.h` 的代码固定了当前的比较方式：

```c
free_secs = free_sections(sbi) + freed;
required_secs = needed + reserved_sections(sbi) +
                __get_secs_required(sbi);

return free_secs < required_secs;
```

其中 `__get_secs_required()` 会把 dirty node、dentry、inode metadata 以及特定模式下的 dirty data 折算为所需 section。当可用空间充裕时，`f2fs_balance_fs()` 直接返回；一旦不足，它可以唤醒启用了 `gc_merge` 的 GC 线程并等待，或者直接调用 `f2fs_gc()` 腾出 section。默认策略下，后台 GC 采用 cost-benefit（成本收益）或启用 ATGC 时的 age-threshold（年龄阈值），前台 GC 则采用 greedy（贪心）策略；`gc_mode` 下的 idle/urgent 模式还可以覆盖默认选择。

这也解释了为什么设备剩余容量还没有显示为 0，写入就已经明显变慢：文件系统自身必须预留足以完成脏页回写、checkpoint 和 GC 搬移的工作空间，而 UFS 内部同样需要预留块来支撑 FTL 回收。当剩余容量压近边界时，两层空间压力往往会同时显现。

<!-- gracker-diagram: ch06-02-f2fs-gc-pressure -->
![F2FS GC 与前台空间等待](../../assets/diagrams/ch06/ch06-02-f2fs-gc-pressure.png)

图：GC 需要把 victim 中仍有效的块搬到别处，才能释放可复用空间；空闲 section 不足会让前台参与或等待。

#### 4 KB 与 16 KB 页大小

Android 15 开始支持 16 KB page size（页大小），Android 17 继续兼容 4 KB 与 16 KB 设备。分析这一特性时，需要把 ELF（Executable and Linkable Format，可执行与可链接格式）的 16 KB 对齐兼容性和 F2FS 的磁盘格式区分开：

- AOSP 用户空间可以构建为 page-size agnostic（不依赖固定页大小），按 16 KB 对齐编译出的 ELF 二进制文件可以在 4 KB 与 16 KB 内核上通用运行；
- 但在文件系统层面，`android17-6.18-2026-06_r6` 的 `include/linux/f2fs_fs.h` 明确约束 `F2FS_BLKSIZE == PAGE_SIZE`；
- 同一源码下每个默认 segment 仍固定包含 512 个 block，因此 4 KB 页对应的默认 segment 为 2 MiB，16 KB 页下则变为 8 MiB。

这意味着 16 KB 内核所用的 F2FS 分区格式必须按 16 KB block 重新生成。应用的 ELF 兼容性只解决用户态加载问题，磁盘格式的转换以及设备跨页大小升级时能否保留 `/data` 数据，仍取决于 OEM 的分区规划、数据迁移与升级方案。对应用开发者来说，重点是清理 native library 中对页大小的硬编码；分区的格式化与用户数据迁移则由设备厂商负责。

<!-- gracker-diagram: ch06-02-pages-elf-f2fs-format -->
![16 KB：ELF 对齐与 F2FS 格式分别检查](../../assets/diagrams/ch06/ch06-02-pages-elf-f2fs-format.png)

图：16 KB ELF 对齐解决用户空间兼容的一部分；该 r6 的 F2FS block 等于 PAGE_SIZE，磁盘格式与迁移还需设备方案。

#### quota、casefold 与 fscrypt

F2FS 与 ext4 都能承载 Android 所需的配额、大小写无关目录与文件加密能力，但各项能力是否生效，取决于内核配置、文件系统 feature、格式化参数与挂载选项：

- project quota（项目配额）支持按目录项目统计或限制容量；`CONFIG_QUOTA=y`（配额支持）仅表示内核具备该能力，目标分区是否开启 `prjquota`，仍需核对格式化参数与挂载选项。
- casefold 基于 Unicode 规则执行不区分大小写的名称查找，只有在文件系统具备相应 feature 且目标目录设置了 casefold 属性时才会生效。
- fscrypt 提供文件级加密策略，Android 的 FBE 就在其上构建 DE/CE 密钥域。
- inline encryption（内联加密）可以把块加解密卸载给存储控制器，但文件系统仍需负责传递密钥上下文并标记 `bio`（块 I/O 描述结构）。

核查设备实际行为时，应直接读取 superblock feature（超级块特性）、mount options（挂载选项）与内核配置；文件系统名称本身只是一条起点线索。


### EROFS：面向不可变镜像的只读文件系统

#### 适用场景

EROFS（Enhanced Read-Only File System）没有运行时写入、journal 和空闲块分配路径，专为构建期生成、启动后只读的系统镜像设计，常用于 `system`、`vendor`、`product` 和 `system_ext`；需要频繁创建和修改文件的 `/data` 分区，则继续由 ext4 或 F2FS 负责。

AOSP 的 EROFS 文档同时涵盖了 BoardConfig、fstab、压缩选项以及 Virtual A/B 配置。其中 fstab 示例允许为 `/system` 保留 EROFS 与只读 ext4 两种条目，方便测试 ext4 GSI（Generic System Image，通用系统镜像）。这说明平台对两者都提供了完整支持，具体分区采用哪种格式取决于产品构建配置。

EROFS 的核心能力包括：

- compact/extended inode（紧凑/扩展索引节点）布局与 tail packing（尾部数据内联）；
- 可选透明压缩；
- in-place decompression（就地解压），减少额外解压缓冲与 Page Cache 抖动；
- chunk-based 与 rolling-hash（滚动哈希）压缩数据去重；
- 面向随机访问的索引设计。

<!-- gracker-diagram: ch06-02-erofs-compressed-read -->
![EROFS 压缩文件的按需读取](../../assets/diagrams/ch06/ch06-02-erofs-compressed-read.png)

图：EROFS 在构建期生成只读镜像；压缩文件 cache miss 时按索引读取 PCluster，再解压得到文件数据。

AOSP 构建文档默认采用 `lz4hc` 作为 compressor（压缩器），同时允许禁用压缩或调整 PCluster（物理压缩簇）大小。官方文档记录的镜像体积缩减数据为平均约 25%，高压缩配置可达约 45%；这组数值反映的是文档测试场景下的体积压缩效果，并不能用来直接推算任意机型的开机耗时。

6.18 arm64 GKI 已开启 `CONFIG_EROFS_FS=y`、`CONFIG_EROFS_FS_ZIP_ZSTD=y` 与 `CONFIG_EROFS_FS_PCPU_KTHREAD=y`，使内核具备了 ZSTD 解压能力；不过镜像本身是否启用 ZSTD 仍由产品构建配置决定，且 6.18 Kconfig 仍将其标为 experimental（实验性），因此 LZ4HC 目前仍是 AOSP 构建文档的默认选择。

#### EROFS、dm-verity（块设备完整性校验机制） 与 Virtual A/B

在这一栈里，EROFS 负责解释只读文件与压缩数据，`dm-verity` 负责校验块完整性，AVB（Android Verified Boot）/ `vbmeta` 则提供可信的根摘要与签名信息。正常挂载时的简化层次自下而上依次为：

1. `super` 物理分区；
2. `dm-linear` 映射出的动态逻辑分区；
3. `dm-verity` 校验设备；
4. EROFS 或只读 ext4；
5. `/system` 等挂载点。

`dm-verity` 只在读取时按需检索哈希树并做校验，不会在挂载阶段把整棵哈希树重算一遍。它使用的哈希算法、数据块大小与错误处理策略均来自 AVB descriptor（描述符）和设备配置，并不会在所有设备上固定使用 4 KB 块配 SHA-256。

<!-- gracker-diagram: ch06-02-erofs-verity-layers -->
![EROFS、AVB 与 dm-verity 的职责](../../assets/diagrams/ch06/ch06-02-erofs-verity-layers.png)

图：读取从文件系统经 dm-verity、逻辑分区映射到 super；AVB 提供可信校验根，文件系统压缩和 OTA COW 压缩处于不同层。

进入 Virtual A/B OTA 的 snapshot（快照）读取与合并阶段后，下层还可能插入 `snapuserd` 提供的用户态后端；Android 17 r1 支持按条件选择 `dm-user` 或 `ublk`，具体以该次更新状态为准，后端选择逻辑已在 6.1 展开。AOSP 自 Android 13 起完整支持 EROFS 与 Virtual A/B，能够在生成增量 OTA 时直接处理 LZ4 数据流。另外需要注意区分两层“压缩”：EROFS 镜像压缩缩小的是只读文件系统镜像本身，而 Virtual A/B snapshot 压缩缩减的是升级期间暂存的 COW 差异数据，两者互不替代。

### 文件系统如何影响随机 I/O

下表比较的是三类文件系统的工作机制与主要延迟风险点，并非脱离具体硬件和负载的性能排名：

| 场景 | ext4 | F2FS | EROFS |
|---|---|---|---|
| 缓冲随机读 | Page Cache + extent 映射 | Page Cache + node/NAT 映射 | Page Cache + 压缩索引与解压 |
| 随机写 | delayed allocation、extent 分配、journal | OPU（out-of-place update）/IPU、LFS/SSR、node 更新 | 不支持 |
| 同步提交 | 数据写回 + journal/fast commit + 必要 flush | 数据写回 + roll-forward node 或 checkpoint + 必要 flush | 不支持写入 |
| 空间回收 | 空闲 extent 管理、discard（向块设备告知可回收范围） | segment GC、SSR、discard | 构建期生成镜像 |
| 主要尾延迟来源 | journal 竞争、块分配、flush、器件延迟 | GC/checkpoint、flush、器件延迟 | cache miss、压缩块读取与解压、verity、器件延迟 |

随机写的最终代价由多个层次共同塑造：文件系统决定逻辑块怎样分配，块层决定请求怎样合并与派发，FTL 则决定 NAND 页如何搬移与回收。F2FS 试图向 FTL 递交更有规律的写入并分离冷热数据，但文件系统与 FTL 的双层日志式管理在部分负载下也可能叠加写入放大。要对比两套方案在真实产品上的快慢，必须在同机型、同镜像、同挂载参数和同工作集条件下实测 P50/P95/P99（第 50/95/99 百分位）延迟。

### `fsync()` 与 `fdatasync()`：差别在持久化范围

POSIX（可移植操作系统接口）对这两个系统调用的语义区分可以概括为：

- `fsync(fd)`：同步文件数据，以及恢复该文件状态所需的全部元数据。
- `fdatasync(fd)`：允许跳过不影响后续数据读取的元数据（例如单纯修改时间戳），但文件大小等关键变化仍须持久化。


`fdatasync()` 在语义上允许跳过时间戳等不影响后续数据读取的元数据，但两者最终会触发哪些写回与 flush，仍取决于文件修改类型和文件系统实现——例如 F2FS 就可能在 `fdatasync()` 路径设置前文提到的 `FI_NEED_IPU` 标志——仅凭 syscall（系统调用）名称估算不出单次调用的真实成本。

SQLite 在 rollback journal、WAL 和不同 `synchronous` 配置下会发出不同的同步操作。凡是要求断电后能恢复的数据，必须保留相应的同步保证；为了换取性能而调低 PRAGMA 安全级别之前，先要明确业务能容忍丢失多少数据、是否能承受数据库损坏。应用层更稳妥的优化方向是减少事务数量并移出主线程等待，避免直接关闭同步保护。

#### App 侧能做的事

1. **批量提交数据库修改**：将同一业务动作的多条写入合并进一个显式事务中，避免在循环内逐条自动提交；使用 Room 时可以通过 `@Transaction` 或批量 DAO（数据访问对象）方法划定事务边界。
2. **谨慎评估 WAL**：WAL 往往有助于改善读写并发，但自身依然带有 WAL sync、checkpoint 以及文件膨胀的代价。收益必须结合目标 workload（真实工作负载）验证，该保留的同步保证同样不能省略，WAL 换不来“免同步”。
3. **避免主线程等待持久化**：文件写入、数据库事务与 `SharedPreferences.commit()` 都应当避开 UI 关键路径。
4. **认清 `SharedPreferences.apply()` 的限制**：它会先更新内存视图再异步写盘，但连续调用 `apply()` 仍会累积磁盘写入量，且组件生命周期切换时主线程仍可能被迫等待排队任务。
5. **合并小文件更新**：频繁创建、rename（重命名）和删除小文件会放大目录与 inode 元数据更新，应在守住崩溃一致性的前提下降低更新频次。

#### 如何定位

可以用下面几条命令核实目标挂载点的文件系统类型、挂载参数与系统页大小：

```bash
adb shell cat /proc/mounts
adb shell stat -f -c '%T %S' /data
adb shell getconf PAGE_SIZE
```

第一条输出实际的 mount options；第二条利用 Toybox 的 `%T %S` 分别查看 `/data` 的文件系统类型与基本块大小（`%s` 对应最佳传输大小）；第三条确认运行内核的页大小。`stat` 的输出适合作为初筛线索，完整判断还需结合 F2FS on-disk feature（磁盘格式特性）。

在设备支持的前提下，可以通过 Perfetto/ftrace（内核跟踪）采集以下事件：

- `ext4_sync_file_enter` / `ext4_sync_file_exit`
- `f2fs_sync_file_enter` / `f2fs_sync_file_exit`
- F2FS GC 与 checkpoint 事件
- `block_rq_issue` / `block_rq_complete`
- UFS host controller（主机控制器）、device-mapper 与 writeback（回写）事件

分析时先借助 `sync_file` 的 enter/exit 区间锁定文件系统层的总等待范围，再对照内部阶段判断耗时究竟落在写回、journal/checkpoint、GC、块队列排队还是器件完成阶段。评估是否异常时，应与同机型正常场景的分位数做对比，不要生搬硬套统一的 10 ms 阈值。

### 厂商选型：以设备事实为准

AOSP 与 GKI 在底层同时维护了多套能力：`/data` 既可以用 ext4 也可以用 F2FS，只读动态分区同样兼容 EROFS 与只读 ext4。量产设备最终选择哪一种组合，往往是综合以下因素权衡的结果：

- 设备的首发/升级（launch/upgrade）路径与 Virtual A/B 方案；
- UFS 器件特性、容量规格与 FTL 行为；
- 4 KB 或 16 KB 内核选型；
- FBE、metadata encryption、quota 与 casefold 特性需求；
- 故障恢复、量产产线工具与售后升级成本；
- 厂商内核补丁回移植与测试覆盖范围。

同一品牌的不同 SoC、区域版本或产品代际之间也可能切换方案。外部评测或发布会资料只能作参考线索，排查具体问题时应以 `/proc/mounts`、fstab、superblock 与 build config（构建配置）为准。

### 碎片化与长期性能变化

ext4 与 F2FS 都会随着长期使用出现物理布局不连续，只是成因与治理机制有所不同。

在 ext4 上，随着文件频繁创建、追加、截断与删除，空闲空间会逐渐分散。虽然 extent 与 delayed allocation 能缓解碎片，但长时间使用后文件是否还能维持连续，仍取决于设备的实际写入历史。闪存虽然没有机械磁头寻道延迟，布局碎片仍可能增加 `bio` 数量，削弱 readahead（预读）与请求合并的效果。

而在 F2FS 上，更新操作会不断制造失效旧块，再靠 GC 搬移 victim segment 中仍然有效的块。一旦冷热数据混放、空闲 section 偏少或后台 GC 缺少执行窗口，需要搬移的有效块就会增多，前台分配也更容易被迫等待。F2FS 同样可能把单个文件的逻辑块映射到分散的物理位置，异地更新并不会消除文件碎片。

<!-- gracker-diagram: ch06-02-fragmentation-gc-cost -->
![长期布局变化与两类额外成本](../../assets/diagrams/ch06/ch06-02-fragmentation-gc-cost.png)

图：布局不连续可能削弱请求合并与预读；F2FS 还需为 GC 搬移有效块，空闲空间和冷热混放会改变成本。

为设备保留一定的剩余空间通常有利于文件系统与 FTL 顺畅回收；具体阈值应当结合 `/sys/fs/f2fs/<dev>/` 统计、GC trace、块层延迟及产品容量策略来制定，“至少保留 10%”这类跨设备的经验值只适合做粗略参考。普通应用也不应尝试借助 root 工具定期对用户设备执行强制 defrag（碎片整理）。

恢复出厂设置虽然能清空并重建用户数据分区、在短期内改善空间与布局状态，但如果应用层高频小写、无上限缓存或频繁事务提交等写入模式没有改变，时间一长，空间与布局上的收益仍会被逐步消耗掉，恢复出厂设置无法根治这类负载源头。

### 版本脉络：AOSP 能力与设备事实

| 版本阶段 | 可确认的变化 |
|---|---|
| 早期 Android | 设备曾使用 YAFFS2、ext4 等多种格式；“Android 从诞生起所有分区都用 ext4”不成立。 |
| Android 8–12 | F2FS 原子写 ioctl（设备控制命令）与 SQLite 适配进入 Android 设备软件栈；是否使用仍需运行时探测并满足事务条件。 |
| Android 10–12 | F2FS、ext4 继续用于可写分区；动态分区与 Virtual A/B 改变系统镜像的映射和更新方式。 |
| Android 13 | AOSP 文档明确 EROFS 完整支持 Virtual A/B，EROFS 成为只读分区的产品选项。 |
| Android 15 | AOSP 支持 16 KB page size；文件系统格式、kernel page size 与 native ELF 对齐需要分别检查。 |
| Android 16 | AOSP 增加预编译 ELF 最大页大小检查等迁移工具，16 KB 兼容要求继续变严。 |
| Android 17 | 平台锚点为 API 37 / `android-17.0.0_r1`；6.18 arm64 GKI 同时启用 ext4、F2FS、EROFS，并启用 EROFS ZSTD 解压能力。 |

这张时间线总结的是 AOSP 平台演进的能力基线；落实到某一台设备在特定版本究竟跑在什么格式上，仍要结合它是首发还是升级设备，以及 vendor kernel（厂商内核）和产品配置综合判断。

### 文件系统源码锚点

#### Android 17 / kernel 6.18 源码

- `kernel/common/fs/ext4/fsync.c`：`ext4_sync_file()`、fast commit 与 flush。
- `kernel/common/fs/f2fs/file.c`：`f2fs_do_sync_file()`、atomic write ioctls。
- `kernel/common/fs/f2fs/segment.h`：`__get_secs_required()`、`has_not_enough_free_secs()`。
- `kernel/common/fs/f2fs/segment.c`：`f2fs_need_SSR()`、`f2fs_balance_fs()`。
- `kernel/common/fs/f2fs/gc.c`：BG/FG GC 与 victim policy。
- `kernel/common/include/linux/f2fs_fs.h`：F2FS block/page、NAT、SIT 磁盘结构。
- `kernel/common/include/uapi/linux/f2fs.h`：F2FS ioctl ABI。
- `kernel/common/fs/erofs/`、`kernel/common/fs/erofs/Kconfig`：EROFS 与压缩算法支持。
- `kernel/common/arch/arm64/configs/gki_defconfig`：Android 17 arm64 GKI 文件系统配置。
- `external/sqlite/dist/Android.bp` 与 `dist/sqlite-autoconf-*/sqlite3.c`：SQLite batch atomic write 编译选项与 F2FS 探测。

#### 官方文档

- [AOSP EROFS](https://source.android.com/docs/core/architecture/kernel/erofs)
- [AOSP 16 KB page size](https://source.android.com/docs/core/architecture/16kb-page-size/16kb)
- [AOSP Virtual A/B](https://source.android.com/docs/core/ota/virtual_ab)
- [Android SharedPreferences.Editor](https://developer.android.com/reference/android/content/SharedPreferences.Editor)
- [Linux F2FS documentation](https://www.kernel.org/doc/html/latest/filesystems/f2fs.html)
- [Linux ext4 documentation](https://www.kernel.org/doc/html/latest/filesystems/ext4/index.html)
- [Linux EROFS documentation](https://www.kernel.org/doc/html/latest/filesystems/erofs.html)
- [Linux VFS documentation](https://www.kernel.org/doc/html/latest/filesystems/vfs.html)
- [SQLite Atomic Commit](https://www.sqlite.org/atomiccommit.html)

### 文件系统选型的判断依据

定位同步写卡顿时，可以顺着下面四个问题逐层排查：

1. 谁发起了同步操作，事务提交或配置更新是否过于频繁？
2. `/data` 分区采用 ext4 还是 F2FS，内核页大小与挂载参数分别是什么？
3. 等待耗时主要花在数据回写、journal/fast commit、F2FS node/checkpoint/GC，还是块设备 flush？
4. 根因归属应用调用方式、系统服务、文件系统策略，还是 UFS/FTL 尾延迟？

整体而言，ext4 是成熟的通用读写文件系统；F2FS 凭借 segment、NAT/SIT、冷热日志与 GC 适配闪存写入负载；EROFS 则专攻构建期生成的只读镜像。三者各有定位与代价，当前内核基线同时保留了它们的能力，实际分析应当以产品配置与现场观测读数为准。

文件系统生成的 `bio` 如何进一步进入块层转化为设备请求，见下一节「块层队列、调度与延迟分析」。

## 块层队列、调度与延迟分析

文件系统将读写请求提交到块层之后，接下来的核心问题是请求如何合并、按什么优先级派发以及如何进出设备队列。衡量这段路径时的两个核心指标——吞吐与尾延迟——都必须结合请求尺寸、同步语义和底层介质特性来解读。

### D 状态：I/O 排查的起点

当 Perfetto 中主线程出现一段 `D`（uninterruptible sleep，不可中断睡眠）状态时，I/O 往往是第一排查对象，但远没到直接定案的程度：`D` 状态只表明线程睡在了不可中断的内核等待点上，等待对象也可能是驱动、内存回收或其他内核锁与资源。想把范围缩窄，需要接着核对 `thread_state.io_wait=1`、`sched_blocked_reason`、文件系统 tracepoint（内核跟踪点）与块层事件。

哪怕调用栈明确停在 `read()` 或 `fsync()`，延迟依然可能产生在链路上的不同位置：

1. Page Cache miss（页缓存未命中）或脏页回写。
2. ext4 journal（日志）、F2FS checkpoint（检查点）/GC 等文件系统内部工作。
3. request（块层请求）进入块层后等待 scheduler dispatch（调度器派发）。
4. device-mapper、inline crypto（内联加密）、UFS host 与设备内部队列。
5. UFS 固件的 cache flush、FTL GC、磨损控制与温控策略。

I/O scheduler（I/O 调度器）能管到的范围限于请求进入硬件设备之前：它可以调节请求顺序、带宽配额与队列深度，但已经发往设备的命令无法追回，主线程上设计不当的同步写也只能回到应用侧修改。

### blk-mq 与 I/O scheduler 的位置

现代 Linux 块层统一运行在 blk-mq（多队列块层）架构上：软件提交队列先把请求分发到一个或多个硬件队列，再由设备驱动把命令递交给控制器。可选的 elevator（块 I/O 调度器）挂接在 request queue（请求队列）之上，负责对尚未 dispatch 的请求做合并、排序或限流——下文讨论的各类调度器都工作在这个位置。

<!-- gracker-diagram: ch06-02-blk-mq-elevator -->
![blk-mq 中 elevator 的位置](../../assets/diagrams/ch06/ch06-02-blk-mq-elevator.png)

图：elevator 管理尚未派发的请求；none 跳过可选策略，软件上下文、硬件队列、tag 与驱动仍然存在。

虽然 UFS 没有机械磁盘的磁头寻道延迟，调度器在移动设备上依然有其用武之地：

- 交互式读与同步写对延迟极度敏感，而后台顺序写更看重整体吞吐；
- 设备队列过深会拉长单次排队等待，过浅又可能浪费器件内部并行度；
- 多进程或不同 cgroup（控制组）之间需要隔离带宽与服务权重；
- 相邻请求合并能够削减软件栈与设备命令提交的固定开销。

即便闪存没有机械磁头的寻道延迟，请求顺序与队列形态依然直接影响尾延迟：UFS 天然存在读写不对称，加上 SLC cache（单层单元高速缓存）、内部并行通道与 FTL 回收的共同作用，不同的派发策略会带来明显差异。

### CFQ、BFQ、mq-deadline、Kyber 与 `none`

讨论这些调度器时，先把它们各自的位置放准：CFQ 属于早期 single-queue（单队列）块层，BFQ、`mq-deadline` 和 Kyber 则工作在 `blk-mq` 上，而 `none` 表示目标 request queue 未挂载可选 elevator。这些调度器与 Android 版本之间并没有固定的替换对照表，排查时必须将 Android 版本、GKI 编译能力、vendor kernel 配置以及目标块设备的最终选择分开核实。

#### CFQ：历史背景

CFQ（Completely Fair Queuing，完全公平排队）为每个 I/O context（I/O 上下文）管理独立队列，并通过时间片与优先级分配设备服务。它曾是通用 Linux 配置中的主力调度器，但并未进入当前 6.18 的 `blk-mq` scheduler 集合。

CFQ 本身支持 I/O class（优先级类别）与 priority，并非对所有进程一视同仁；它退出当前内核的主要原因是块层全面转向 `blk-mq`，与单个 Android 前后台场景并无直接因果。

#### BFQ：按 budget 分配服务

BFQ（Budget Fair Queueing，预算公平排队）按照权重与 budget（单次获准处理的数据量）为队列分配服务，力求在吞吐、公平性与交互延迟之间取得平衡。开启 `CONFIG_BFQ_GROUP_IOSCHED` 后，它还能执行 cgroup 层级调度。

<!-- gracker-diagram: ch06-02-bfq-budget -->
![BFQ：权重、budget 与服务机会](../../assets/diagrams/ch06/ch06-02-bfq-budget.png)

图：BFQ 为队列分配以数据量计的 budget，并结合权重和交互策略分配服务；组间比例调度还需 GROUP_IOSCHED 支持。

BFQ 的 per-request（逐请求）计算与队列管理比 `mq-deadline` 更复杂。在较慢的存储介质或需要比例带宽、交互保障的负载上，这份调度开销或许值得；但在高 IOPS（每秒 I/O 操作次数）设备上，额外的软件管理成本也可能压低吞吐。两者的延迟差距随设备性能与负载特征而异，并没有固定的倍数关系。

6.18 的 `Kconfig.iosched` 仍保留了 BFQ 作为可选项，但 arm64 GKI defconfig（默认内核配置）并没有显式启用 `CONFIG_IOSCHED_BFQ`。由于 vendor 可以调整内核配置，实机上究竟有没有启用 `bfq`，仍以 sysfs（内核导出的运行时属性接口）读数为准。

#### mq-deadline：位置队列、FIFO（先进先出队列） 与 I/O class

`mq-deadline` 为 RT、BE、IDLE 三种 I/O class 分别维护读队列和写队列。每个请求入队时，会同时进入按 sector（扇区位置）排序的红黑树以及按到期时间排列的 FIFO；调度器通常沿 sector 顺序批量 dispatch，并在批与批之间穿插处理超期请求。

下面这组摘自 `block/mq-deadline.c` 的源码常量给出了内核的默认软期限：

```c
static const int read_expire = HZ / 2;
static const int write_expire = 5 * HZ;
static const int prio_aging_expire = 10 * HZ;
static const int writes_starved = 2;
static const int fifo_batch = 16;
```

其中的 `read_expire=500ms` 与 `write_expire=5s` 是 FIFO 防饥饿检查所用的软到期时间，请求完全可以在到期之前正常派发；它们既不表示最短等待时间，也不是设备完成期限，设备端的完成延迟需要放在另一条时间线上衡量。`writes_starved=2` 则限定连续优先处理一定轮次的读批次后必须照顾一次写队列，控制的是批次交替节奏，与读写 2:1 的带宽比例无关。

<!-- gracker-diagram: ch06-02-mq-deadline-dispatch -->
![mq-deadline 的索引与派发选择](../../assets/diagrams/ch06/ch06-02-mq-deadline-dispatch.png)

图：每个 class 内同时维护位置树与 FIFO；正常批次可在到期前派发，新批次再按方向、超期和位置选择请求。

6.18 的实现会把 `IOPRIO_CLASS_NONE` 映射到 BE，并识别 RT/BE/IDLE 三类 class。优先级 class 能够直接影响派发顺序，但 class 内部 0–7 的 level（等级）是否生效取决于调度器是否消费——这也是 `ionice` 命令返回成功未必马上改变调度效果的中间环节。

#### Kyber：用 token（令牌） 控制队列深度

Kyber 把请求划分为 READ、WRITE、DISCARD 与 OTHER 四个调度域，用 token 限制各域同时在途的请求数量，并根据完成延迟直方图动态调节 token 配额。6.18 源码里的默认 target 为读 2 ms、写 10 ms、discard 5 s；这些数值只是内部反馈控制的目标，并不承诺每个请求都能在这个时限内完成。

<!-- gracker-diagram: ch06-02-kyber-feedback -->
![Kyber 的 token 与延迟反馈](../../assets/diagrams/ch06/ch06-02-kyber-feedback.png)

图：Kyber 用域 token 控制在途深度，再根据完成延迟直方图调整；target 是控制目标，不能当作每个请求的完成保证。

Linux 通用 I/O priority 文档列出的支持者是 BFQ 与 `mq-deadline`；如果业务依赖 `ionice` 或 cgroup I/O class，Kyber 能否产出同等效果需要单独实测确认。

#### `none`：不挂 elevator

选择 `none` 仅表示跳过可选 scheduler 的排序与 QoS（服务质量）策略；`blk-mq` 框架、plugging（暂存请求以便批量提交）、request 构造、硬件 tag（队列槽位标识）以及驱动队列依然照常工作，部分请求合并也可能发生。

#### 平台提供什么，设备选择什么

6.18 的 `Kconfig.iosched` 默认提供 `mq-deadline` 与 Kyber，BFQ 属于可选配置。注意在设备节点上，动态分区往往表现为 `dm-*`，而真正承载底层请求的 UFS LUN（逻辑单元）才对应实际的硬件 request queue；检查调度器时应当沿着 device-mapper 映射找到叶子块设备，再读取它的 `scheduler` 属性。

可以用以下命令列出设备上所有可见 request queue 的当前选择与候选调度器：

```bash
adb shell 'for q in /sys/block/*/queue/scheduler; do
  printf "%s: " "$q"
  cat "$q"
done'
```

输出中被方括号括起的名称即当前启用的调度器。某台设备如果只列出 `[none]`，可能源于驱动能力、队列类型或内核配置裁剪；若要下“Android 17 统一默认用某调度器”的结论，必须先把多台机型的实际读数摆齐。


### I/O priority：先问谁消费它

Linux 的 `ioprio_set()` 与 `ionice` 定义了三种通用 I/O priority class：

- **RT（Real Time）**：优先级高于 BE 与 IDLE，持续高负载下可能让低优先级 class 长期挨饿。
- **BE（Best Effort）**：常规的尽力服务类别，细分为 0–7 共八个等级。
- **IDLE**：仅在设备没有其他竞争工作时延后执行。

下面两条命令仅用于受控进程的调度调试，日常不要把普通前台应用随意设为 RT：

```bash
adb shell su 0 ionice -c 3 -p <pid>
adb shell su 0 ionice -c 2 -n 4 -p <pid>
```

第一条将目标进程设为 IDLE class，第二条设为 BE level 4。执行这类命令通常需要足够权限；更重要的是，如果底层 scheduler 并不消费对应的 class 或 level，即便命令返回成功，请求派发顺序也未必发生改变。

<!-- gracker-diagram: ch06-02-ioprio-consumer -->
![ioprio 的产生、限制与消费](../../assets/diagrams/ch06/ch06-02-ioprio-consumer.png)

图：ionice/init 设置的 class/level 经具体 I/O 路径和 blkcg 策略进入请求；scheduler 是否读取它决定实际效果。

Android `init` service 同样支持通过 `ioprio <rt|be|idle> <0-7>` 语法调用 `SYS_ioprio_set` 配置服务进程，不过 Android 应用的前后台 I/O 保障并不会由 `ActivityManager` 逐一调用 `ionice RT` 来实现。

### AOSP 的 blkio task profile

#### AOSP tag 中的基线

`android-17.0.0_r1` 的 `system/core/libprocessgroup/profiles/cgroups.json` 依然把 `blkio` 配置为 cgroup v1，并挂载于 `/dev/blkio`。同一份文件里的 cgroup v2 基线只包含 freezer（进程冻结控制器）与可选的 memory controller（内存控制器），可见在 Android 17 的这一版本基线中，I/O 控制组仍沿用 cgroup v1，并未全部迁入 cgroup v2。

在 `task_profiles.json` 中，核心 I/O profile 的动作非常明确：

- `LowIoPriority`：加入 `/dev/blkio/background`；
- `NormalIoPriority`、`HighIoPriority`、`MaxIoPriority`：全部加入 `blkio` 根组；
- `SCHED_SP_BACKGROUND`：包含 `LowIoPriority`；
- `SCHED_SP_FOREGROUND`：包含 `HighIoPriority`；
- `SCHED_SP_TOP_APP`：包含 `MaxIoPriority`。

这组命名容易让人产生错觉：AOSP 的 `HighIoPriority` 与 `MaxIoPriority` 其实都只是把任务移回 `blkio` 根组，本身并未设置 RT class；前台进程得到的相对优势，主要来自避开了 `background` 组的降权与 class 限制。

<!-- gracker-diagram: ch06-02-aosp-blkio-profiles -->
![AOSP task profile 的 blkio 分组](../../assets/diagrams/ch06/ch06-02-aosp-blkio-profiles.png)

图：r1 的 Normal/High/MaxIoPriority 都加入根组；LowIoPriority 进入 background，不能按名字推断设置了 RT 或不同前台 I/O 层级。

下面这段摘自 `system/core/rootdir/init.rc` 的配置固定了 AOSP 对后台 `blkio` 组的初始参数：

```rc
write /dev/blkio/blkio.weight 1000
write /dev/blkio/background/blkio.weight 200
write /dev/blkio/background/blkio.bfq.weight 10
write /dev/blkio/background/blkio.prio.class restrict-to-be
```

根组与后台组设置了不同的权重，其中 BFQ 专用权重只有在内核与目标 queue 启用 BFQ 时才会生效。`restrict-to-be` 来自 `blk-cgroup` I/O priority policy，它会把 NONE/RT 请求限制降级到 BE，保留原本更低的 IDLE 等优先级，并且能够作用于支持 cgroup writeback（按控制组归属回写）的缓冲写路径。

#### 从内核能力到产品配置

arm64 GKI 开启了 `CONFIG_BLK_CGROUP`、`CONFIG_BLK_DEV_THROTTLING`、`CONFIG_BLK_CGROUP_IOCOST` 与 `CONFIG_BLK_CGROUP_IOPRIO`。这些编译开关只说明内核具备相应控制器能力；要真正起效，产品端还必须完成控制器挂载、层级创建、参数写入，并选用能够读取这些策略的 scheduler。

Android 允许通过 API 级别配置或 vendor 文件覆盖默认的 `cgroups.json` 与 `task_profiles.json`。因此排查实机 I/O 隔离时，需要核对以下几处运行时状态：

- `/proc/cgroups`、`/proc/<pid>/cgroup` 与 `/proc/mounts`；
- `/system/etc/task_profiles/` 与 `/vendor/etc/task_profiles.json`；
- `/dev/blkio/` 或 `/sys/fs/cgroup/` 下实际存在的控制文件；
- 叶子块设备的 `/sys/block/<dev>/queue/scheduler`。

查看控制文件时也要分清层级版本，避免把 blkio v1 的 `blkio.*` 与 cgroup v2 的 `io.*` 混在一起解读——先确定挂载的是 v1 还是 v2，再去解析 `blkio.weight`、`io.weight`、`io.max`、`io.prio.class` 或 `io.pressure`。


### Buffered I/O、Page Cache 与 cgroup writeback

#### 读路径

普通 `read()` 会优先查询 Page Cache：命中缓存时无需访问存储；未命中时，文件系统读取 folio（由内核管理的一组连续内存页），并可能触发 readahead。应用冷启动期间 DEX、资源与数据库读取是否命中缓存，对耗时影响极大；“同一个文件第二次读取变快”测量的是页缓存命中行为，反映不了 UFS 器件本身的速度。

Page Cache 属于可回收的 file-backed memory（有文件作为后备的数据页）。当系统出现内存压力时，内核会在文件页与匿名页之间权衡回收对象，并把 swap（交换空间）成本纳入考量；6.18 GKI 基线同时启用了 MGLRU（多代 LRU），因此无法仅用经典的活跃/非活跃两条 file LRU 链表来解释所有设备。如果后台执行大范围文件扫描，就可能把前台马上要用的热页挤出缓存，推高 refault（回收后很快再次缺页）。具体的回收决策还受 memcg（内存控制组）保护、访问频次、working set（工作集）检测以及 swap 成本的共同调节。

<!-- gracker-diagram: ch06-02-pagecache-reclaim-refault -->
![Page Cache、MGLRU 与 refault](../../assets/diagrams/ch06/ch06-02-pagecache-reclaim-refault.png)

图：缓存命中无需读盘；内存压力下回收文件页会影响后续命中，refault 与块层延迟需要一起观察。

#### 写路径

Buffered write（缓冲写）会先把 folio 标记为 dirty，随后由 writeback 线程把脏页转化为 `bio`/request 提交下发。脏页控制横跨内存管理与块 I/O 两个子系统：

- memory controller 负责决定脏页在哪个 memory domain（内存记账域）统计与限速；
- I/O controller 负责决定回写生成的 `bio` 归属哪个 blkcg（块 I/O 控制组）；
- 底层文件系统必须支持 cgroup writeback（ext4 与 F2FS 均已支持）；
- inode 的 writeback owner（回写归属者）会随持续写入来源动态切换，不能把所有回写请求都粗暴记到当时正在跑的 flush 内核线程头上。

正因如此，缓冲写转交后台回写线程后，原进程的 cgroup 归属未必会丢失——支持 cgroup writeback 的路径会把生成的 `bio` 关联回 inode owner 所在的 blkcg。

不过当多个 cgroup 并发写同一个 inode 时，仍有相当一部分 I/O 可能被记到其他组；若多个组交叠改写同一批页面，哪怕按页面归属记账也难以拆清。[内核文档](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/Documentation/admin-guide/cgroup-v2.rst)也明确建议避免这种跨组并发写同一文件的模式。分析共享文件负载时，必须结合实际写入方来判断，不能把各组的回写计数直接当成每个写入方的精确写盘量。

<!-- gracker-diagram: ch06-02-cgroup-writeback-owner -->
![缓冲回写的 memory 与 blkcg 归属](../../assets/diagrams/ch06/ch06-02-cgroup-writeback-owner.png)

图：内存按页归属，回写按 inode owner 关联 blkcg；回写线程身份不能直接替代原始写入归属。

#### dirty sysctl 与 swappiness

`dirty_background_ratio`、`dirty_ratio`、对应的 `*_bytes`、`dirty_expire_centisecs` 与 `dirty_writeback_centisecs` 共同调节脏页回写的触发门槛与节奏。它们既可以被产品 init 配置覆盖，也会与 backing device（后备存储设备）及 memcg 阈值联动，因此 Linux 桌面/服务器上的常见默认值不能直接套用到 Android 设备上。

AOSP 仅在 low-RAM（低内存）或 batteryless（无电池）等特定条件下主动写入部分参数，例如 low-RAM 分支会将 `dirty_background_ratio` 设为 5；具体某台设备是否采用 5，取决于它是否命中了对应配置条件。

`swappiness` 用来衡量 swap I/O 与 filesystem paging（文件页换入换出）的相对成本，取值范围为 0–200，其中 100 表示两者成本相当。它调节的是匿名页与 file-backed page 之间的回收倾向，并不代表 Page Cache 的最大占比。Android 普遍使用 zram（内存压缩交换设备），合理的 `swappiness` 取值仍需结合压缩开销、refault 率与产品内存规格实测确定。


可以用下面这组命令读取实机当前的内存回写与 I/O 压力指标：

```bash
adb shell 'for f in \
  dirty_background_bytes dirty_background_ratio \
  dirty_bytes dirty_ratio swappiness; do
  printf "%s=" "$f"
  cat "/proc/sys/vm/$f"
done'
adb shell cat /proc/pressure/io
```

前一组参数需结合设备 init 配置解读；后一条输出的 PSI（Pressure Stall Information，资源压力停顿信息）中，`some` 与 `full` 分别表示部分任务或全部非 idle 任务因等待 I/O 而停顿的时间占比，比孤立的 CPU iowait 百分比更能准确刻画系统级 I/O 压力。

### Direct I/O 与 Buffered I/O

#### Buffered I/O 适合多数 App

Page Cache 能够合并小规模写入、提供预读并复用热点数据，数据库、配置、资源与代码文件都深度依赖这套机制。不过 `write()` 提前返回用户态只说明数据进入了缓存，并不表示已经落盘；崩溃一致性仍需靠事务机制、`fsync()` 与文件系统语义来兜底。

#### `O_DIRECT` 的适用条件

`O_DIRECT` 尝试让文件数据 I/O 绕过 Page Cache，主要服务于自行管理缓存、访问模式明确且能严格满足对齐要求的系统级软件。Linux 6.18 允许通过 `statx(..., STATX_DIOALIGN)` 查询文件系统报告的 direct-I/O 对齐要求；调用方须先检查返回的 `stx_mask` 是否包含该标志位，再解读 `stx_dio_mem_align` 与 `stx_dio_offset_align`——内核提供该接口并不代表每种文件系统都会填回这组字段。


使用 `O_DIRECT` 时需要留意几项约束：

- 内存 buffer 地址、传输长度与文件 offset 通常都有严格的对齐限制；
- 绕过 Page Cache 意味着同时放弃了常规 readahead 与页缓存复用；
- `O_DIRECT` 本身不承诺持久化落盘，需要断电一致性时仍须调用 `fsync()`；
- 对同一个文件混用 buffered 与 direct I/O 会大幅增加缓存一致性与页面失效处理的复杂度；
- inline encryption、device-mapper 或底层驱动仍可能引入 bounce buffer（中转缓冲）、请求拆分等额外代价。

AOSP SQLite 的 Unix VFS 依然以普通缓冲文件 I/O 为基线，SQLite 的 WAL（Write-Ahead Logging，预写式日志）在源码中同样使用缓冲 I/O 而非 Direct I/O；F2FS batch atomic write（批量原子写）则属于另一套独立的 ioctl 能力。

### Perfetto：从线程等待走到块设备

#### 录制数据要够

要走通整条排查链路，trace 至少得包含 scheduler 调度数据；为了进一步把等待归因到具体层级，还可以按设备支持情况加上以下数据源：

- `sched_switch`、`sched_wakeup`、`sched_blocked_reason`；
- `block_rq_insert`、`block_rq_issue`、`block_rq_complete`；
- `writeback:*`；
- `ext4:*` 或 `f2fs:*` 中的 sync、writeback、checkpoint、GC 事件；
- UFS、device-mapper 与 PSI 数据。

`sched_blocked_reason` 的可用性随 build type（系统构建类型）和内核配置而异。一旦缺失该事件，`thread_state.io_wait` 就可能为 NULL，难以把普通内核睡眠从 I/O 等待中筛出来，排查范围随之扩大。

<!-- gracker-diagram: ch06-02-perfetto-d-iowait -->
![从 D 状态确认 I/O 等待线索](../../assets/diagrams/ch06/ch06-02-perfetto-d-iowait.png)

图：D 只说明不可中断等待；io_wait=1 缩小到 I/O 等待线索，仍需调用栈、文件系统与 block 事件定位具体对象。

#### 第一问：哪些线程在 I/O sleep（睡眠等待）

下面这段兼容当前 `thread_state` schema（表结构）的 PerfettoSQL，用于聚合明确标记为 `io_wait=1` 的 D 状态等待：

```sql
SELECT
  COALESCE(process.name, '[kernel]') AS process_name,
  thread.name AS thread_name,
  ROUND(SUM(thread_state.dur) / 1e6, 2) AS iowait_ms,
  ROUND(MAX(thread_state.dur) / 1e6, 2) AS max_wait_ms
FROM thread_state
JOIN thread USING (utid)
LEFT JOIN process USING (upid)
WHERE thread_state.state = 'D'
  AND thread_state.io_wait = 1
  AND thread_state.dur > 0
GROUP BY thread.utid, process.name, thread.name
ORDER BY iowait_ms DESC
LIMIT 20;
```

查询只统计已结束的正时长区间，自动排除了 `dur=-1` 等未闭合状态，从而得出录制窗内可确认的线程总等待时长与单次峰值。至于线程究竟卡在哪个文件、哪块设备上，仍要回到对应时间窗核查调用栈、文件系统 slice（事件区间）与块请求。

#### 第二问：块设备队列是否积压

下面的查询用于统计 trace 期间各 block device 上在队列或设备中的最大及时间加权平均操作数：

```sql
INCLUDE PERFETTO MODULE linux.block_io;

WITH io_intervals AS (
  SELECT
    dev,
    ops_in_queue_or_device,
    LEAD(ts, 1, (SELECT end_ts FROM trace_bounds)) OVER (
      PARTITION BY dev ORDER BY ts
    ) - ts AS dur
  FROM linux_active_block_io_operations_by_device
)
SELECT
  dev,
  MAX(ops_in_queue_or_device) AS max_ops,
  ROUND(
    SUM(1.0 * ops_in_queue_or_device * dur) /
    NULLIF((SELECT end_ts - start_ts FROM trace_bounds), 0),
    2
  ) AS time_avg_ops
FROM io_intervals
WHERE dur > 0
GROUP BY dev
ORDER BY max_ops DESC;
```

这个 stdlib view（Perfetto 标准库视图）只在计数发生变化的时间点输出记录，并非等间隔采样，因此查询先用 `LEAD` 算出每个计数状态持续了多久，再按整段 trace 时间窗求时间加权均值（无 I/O 的时段自然按零贡献计入），直接对变化点取 `AVG` 会算错。由于它依赖 `track.type='block_io'` 的 slice，若块事件缺失或截断，队列深度统计也会随之失真；录制中若没有 block issue/complete 数据，查询不会凭空给出结果。另外，输出中的 `dev` 编号仍需对照实机的 major:minor（主/次设备号）和 device-mapper 映射才能定位物理器件。

<!-- gracker-diagram: ch06-02-perfetto-time-weighted-depth -->
![变化点队列计数要按时间加权](../../assets/diagrams/ch06/ch06-02-perfetto-time-weighted-depth.png)

图：示例 trace 共 100 ms，只有 20–50 ms 处于 2 个在途操作；时间均值是 0.6，变化点数值均值会得到 1.0。

#### 第三问：等待发生在哪一层

接下来把同一时间窗内的多层线索对齐起来对照：

- `sync_file_enter/exit` 区间很长，但 block queue 并不深：重点排查 journal/checkpoint、内部锁、writeback 或设备 flush。
- 请求从 issue 到 complete 的耗时很长：重点核查设备排队、UFS 控制器、加密、dm 映射层和器件健康状态。
- `D` 状态持续很长，但 `io_wait` 未标明且没有显著的 block 活动：转向排查 blocked function（阻塞函数）、reclaim（内存回收）以及 Binder/驱动等待。
- 后台 `wbytes/wios`（写入字节数/写操作数）攀升，同时前台 refault/major fault（需要读盘的缺页）增多：同步核查 blkio、memcg 与 Page Cache 竞争。
- I/O PSI 的 `full` 指标持续走高：说明在对应统计窗内出现了所有非 idle 任务集体因 I/O 停顿的时段；注意 `/proc/pressure/io` 统计整机系统，cgroup 下的 `io.pressure` 仅统计该控制组，仍需结合 CPU、内存与块层判断源头。

<!-- gracker-diagram: ch06-02-perfetto-latency-windows -->
![调用、文件系统与块请求的不同区间](../../assets/diagrams/ch06/ch06-02-perfetto-latency-windows.png)

图：先对齐同一时间窗，再区分调用区间、文件系统同步区间与单个 block 请求区间；相邻或重叠不能单独证明归因。

分析时不要套用跨设备统一的“fsync 超过 5 ms”“随机读超过 1 ms”“iowait 超过 5%”等硬性红线。UFS 代际、容量规格、温度、文件系统类型、队列深度乃至 trace 自身开销都会改变延迟分布；更有参考价值的基线，是在同机型、同镜像、同电量与温度以及相同 workload（工作负载）下测得的 P50/P95/P99 分位数。

#### CPU iowait 的含义

CPU iowait 属于 CPU idle 记账状态的一种，统计口径是 CPU 的空闲等待时间，既叠加不出各个线程的 I/O 等待时长，也拆不到单个应用头上。异步 writeback 可能把存储器件打满而 CPU iowait 却很低；反过来，当一条线程在等 I/O 时，只要还有其他 runnable（可运行）线程在跑，CPU 就不会记为 iowait。

<!-- gracker-diagram: ch06-02-cpu-thread-psi-scopes -->
![CPU iowait、线程等待与 I/O PSI](../../assets/diagrams/ch06/ch06-02-cpu-thread-psi-scopes.png)

图：CPU 时间、单线程等待和任务群体停顿属于不同统计口径；结合使用才能解释系统与交互压力。

因此 CPU iowait 只适合当成宏观系统线索，真正定位时仍要回到线程 `io_wait`、I/O PSI、block queue、文件系统事件与应用调用栈。

### SQLite、Room 与 SharedPreferences：优先减少同步工作

底层调度策略可以缓解资源竞争，但本就不该落在主线程上的多余事务，依然得回到应用侧解决。工程上建议优先检查五处：

1. **事务边界**：把同一次业务动作的多条数据库修改放进同一个显式事务中，避免循环内自动逐条提交。
2. **线程边界**：Room 默认禁止主线程访问数据库；应使用 `suspend`、Flow、RxJava 或 executor（任务执行器）等异步 DAO，不要为了省事开启 `allowMainThreadQueries()`。
3. **WAL 条件**：WAL 通常有助于改善读写并发，但自身依然有 WAL sync、checkpoint、文件增长和多进程边界成本，仍需结合真实 workload 实测收益。
4. **SharedPreferences**：`apply()` 把磁盘写排往后台，但连续高频调用仍会产生大量写盘，且组件生命周期切换时主线程仍可能等待排队任务。
5. **开发期检查**：开发阶段可以借助 StrictMode 揪出主线程磁盘访问；至于 release（发布版本）的实际表现，仍要依赖 Perfetto、数据库统计和线上分位数来验证。


AOSP SQLite 虽然在编译期加入了 F2FS batch atomic write 支持，但运行时仍需由 Unix VFS 探测文件系统 ioctl 并满足 pager 的前置条件。即便走通了批写，它也只能削减部分 journal 开销；剩余的同步等待和块层竞争，终究要靠合理编排事务本身来压低。

### `io_uring`（Linux 异步 I/O 接口） 与 FUSE：能力与实际使用

6.18 Kconfig 默认启用了 `IO_URING`，GKI 同时也开启了 FUSE（Filesystem in Userspace，用户空间文件系统）和 FUSE BPF（借助内核可编程机制处理部分 FUSE 操作）。不过，内核编译选项只证明底层具备这些能力；要判断 Android 17 的某条 `MediaProvider`、外部存储或 OTA 路径是否真的用上了 `io_uring`，必须对照具体的 AOSP 调用点、进程权限、设备配置与 trace 事件来核实。


像“io_uring 让 FUSE 快 40%”“dm-verity 并行哈希让冷读快 35%”这类脱离具体前提的数字，无法直接推广为全平台的通用结论。

### 现场检查清单

| 问题 | 证据 |
|---|---|
| 请求落到哪个叶子块设备？ | `/proc/mounts`、`ls -l /sys/dev/block/<major>:<minor>`、dm 映射 |
| 当前 elevator 是什么？ | `/sys/block/<dev>/queue/scheduler` |
| 线程在哪个 I/O cgroup？ | `/proc/<tid>/cgroup` |
| v1 还是 v2，参数是否存在？ | `/proc/cgroups`、`/proc/mounts`、`/dev/blkio`、`/sys/fs/cgroup` |
| Page Cache 是否反复失效？ | major fault、`workingset_refault_file`、memcg `memory.stat` |
| 脏页是否在回写或限速？ | `file_dirty`、`file_writeback`、`writeback:*` |
| 系统是否普遍被 I/O 阻塞？ | `/proc/pressure/io` 或 cgroup `io.pressure` |
| 延迟在文件系统还是设备？ | `*_sync_file_*`、checkpoint/GC、`block_rq_*`、UFS trace |

### 块层与调度源码锚点

#### Android 17 / kernel 6.18 源码

- `kernel/common/block/Kconfig.iosched`：mq-deadline、Kyber、BFQ 配置边界。
- `kernel/common/block/mq-deadline.c`：deadline 队列、软期限与 I/O class。
- `kernel/common/block/kyber-iosched.c`：调度域、token 与 latency target。
- `kernel/common/block/blk-ioprio.c`：cgroup I/O priority policy 与 `prio.class`。
- `kernel/common/Documentation/admin-guide/cgroup-v2.rst`：I/O controller 与 cgroup writeback。
- `kernel/common/arch/arm64/configs/gki_defconfig`：Android 17 arm64 GKI blk-cgroup 能力。
- `system/core/libprocessgroup/profiles/cgroups.json`：Android 17 controller 基线。
- `system/core/libprocessgroup/profiles/task_profiles.json`：前后台 I/O profiles。
- `system/core/rootdir/init.rc`：blkio 根组与 background 组参数。
- `system/core/init/service_parser.cpp`：init service 的 `ioprio` 解析。
- `external/perfetto/src/trace_processor/perfetto_sql/stdlib/linux/block_io.sql`：block I/O stdlib view。

#### 官方文档

- [AOSP cgroup abstraction layer](https://source.android.com/docs/core/perf/cgroups)
- [Linux block I/O priorities](https://docs.kernel.org/block/ioprio.html)
- [Linux mq-deadline](https://docs.kernel.org/block/deadline-iosched.html)
- [Linux BFQ](https://docs.kernel.org/block/bfq-iosched.html)
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
- [Linux VM sysctl](https://docs.kernel.org/admin-guide/sysctl/vm.html)
- [PerfettoSQL standard library](https://perfetto.dev/docs/analysis/stdlib-docs)
- [Perfetto CPU scheduling events](https://perfetto.dev/docs/data-sources/cpu-scheduling)

### 块层诊断的四个问题

排查 Android I/O 卡顿时，可以按顺序回答下面四个问题：

1. 线程是处于明确的 I/O sleep，还是其他类型的不可中断等待？
2. 延迟主要落在 Page Cache/回写、文件系统、块层 scheduler，还是设备完成阶段？
3. 实机当前启用了哪一个 scheduler，目标线程又落在哪个 task profile 与 blkio/io cgroup 中？
4. 应用侧能否通过合并事务、移出主线程磁盘访问和减少无效小写来降低同步压力？

GKI 提供了 `mq-deadline`、Kyber 与多种 `blk-cgroup` QoS 能力，BFQ 仍是可选项；AOSP task profile 基线也继续借助 `blkio` v1 区分 `background` 与根组。但厂商可以覆盖这些默认配置，每台设备最终采用哪一个 scheduler，都要回到目标实机上核实。

关于应用配置持久化的同步边界详见 6.3，MediaProvider 与 FUSE 的共享存储路径则放在 6.4。

## 常见误区

### “F2FS 一定比 ext4 快”

F2FS 确实针对闪存随机更新做了专门优化，但在可用空间紧张时也可能付出更高的 GC 与 checkpoint 成本；而 ext4 的 journal 虽然可能拉高同步提交延迟，fast commit、工作集特征与设备 flush 行为同样会左右最终结果。文件系统名称只能用来建立初步假设，快慢结论必须来自相同测试条件下的实测。

### “EROFS 自带 dm-verity”

EROFS 负责提供只读文件系统语义与压缩访问，`dm-verity` 则是独立的 device-mapper 完整性校验层。Android 确实经常把两者叠加使用，但 EROFS 镜像完全可以在没有 `dm-verity` 的其他 Linux 环境中单独挂载。

### “`apply()` 已经消除了 SharedPreferences I/O”

`apply()` 只是把写盘阶段从当前调用点移到了后台队列，实际的磁盘写入依然会发生。Android 官方 API 文档也明确提醒，积压的写入任务可能在组件生命周期切换时引发 ANR，高频配置更新仍须先行合并并控制频次。

### “`fsync()` 慢就换文件系统”

把 `/data` 从 ext4 换成 F2FS 属于设备级的分区格式化、系统升级与数据迁移工程，运行时的普通应用既改不了也无权决定。发现同步操作耗时过长时，先查清调用发起方、事务边界、文件系统内部等待与块层设备延迟，再判断应该从应用代码、framework、内核还是产品分区配置入手解决。

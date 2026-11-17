---
title: Android 存储架构
chapter: '6.1'
section: '6.1'
status: finalized
applicable_versions: Android 9 - Android 17 (API 37)
last_verified: '2026-11-09'
last_verified_against: Android 17 (android-17.0.0_r1), AOSP cgroups/task_profiles/init/vold/MediaProvider source, Android Common Kernel android17-6.18 UFS/blk-crypto source & config, dynamic partitions / metadata encryption / file-based encryption / hardware-wrapped keys / system-as-root / scoped storage / FUSE passthrough / Virtual A/B docs, SQLite compile & WAL docs
confidence: medium
sources:
- type: reference
  path: 手机Android存储性能优化架构分析（Linux阅码场）
- type: reference
  path: 手机主流存储器件的分析与发展（OPPO内核工匠）
- type: reference
  path: Android分区挂载原理介绍（OPPO内核工匠）
- type: reference
  path: Android Storage | Android Open Source Project
- type: reference
  path: Scoped Storage | Android Developers
- type: reference
  path: Access media files from shared storage | Android Developers
- type: reference
  path: File-based encryption | Android Open Source Project
- type: reference
  path: Metadata encryption | Android Open Source Project
- type: reference
  path: Hardware-wrapped keys | Android Open Source Project
- type: reference
  path: Android Common Kernel android17-6.18-2026-06_r6 block/blk-crypto.c / Documentation/block/inline-encryption.rst
- type: reference
  path: Scoped storage | Android Open Source Project
- type: reference
  path: System-as-root | Android Open Source Project
- type: reference
  path: Implement dynamic partitions | Android Open Source Project
- type: reference
  path: SQLite Compile-time Options / WAL | sqlite.org
- type: reference
  path: JEDEC UFS 4.0 Standard (JESD220F)
tags:
  - storage
  - ufs
  - emmc
  - partition
  - scoped-storage
  - mediastore
  - fuse
  - fbe
related_chapters:
- '6.2'
- '4.1'
- '7.2'
last_source_verified_at: '2026-11-09T14:39:34+08:00'
last_idle_audit_at: '2026-11-09T14:39:34+08:00'
---

# Android 存储架构

一次应用 I/O 可能自上而下穿过 API、文件系统、页缓存、块层直到存储器件，也可能命中页缓存后直接返回；一旦缓存未命中，路径上的等待又可能把短请求拖成长尾。这一节我们把整条链路拆开走一遍，把笼统的“磁盘慢”还原为可观测的缓存命中、脏页回写、队列排队、同步刷盘和介质延迟。

> 源码基线：AOSP `android-17.0.0_r1`，Android 17 / API 37；内核 Android Common Kernel `android17-6.18-2026-06_r6`。

设备厂商可以定制分区表、文件系统、UFS（Universal Flash Storage）控制器和 vendor kernel（厂商内核），涉及具体机型的性能结论仍要以设备运行时的实际配置为准。

## 从一个卡顿现象说起

在 Perfetto 里追主线程卡顿时，常会看到这样的片段：线程调用 SQLite、`SharedPreferences` 或普通文件 API 后进入睡眠，直到数据回写、日志提交或块设备请求完成才重新运行。SQLite 事务和 `SharedPreferences` 写盘走的是两条独立的实现路径，要判断一次卡顿的 `fsync()` 来自哪一条，必须把调用栈、目标文件名、文件系统事件和 block trace（块 I/O 跟踪记录）合在一起定位。

这类问题有时伴随较高的 CPU 开销，有时则主要耗在 I/O wait（等待输入/输出完成）上。在 Android 上，一次文件访问可能依次经过 VFS（统一文件系统接口）、具体文件系统、fscrypt（文件级加密框架）、device-mapper（块设备映射层）、块层、主机控制器和闪存器件；若是共享存储，前方还会多出 MediaProvider 与 FUSE（用户态文件系统）。分析时，需要先把等待时间对应到具体层级，再判断延迟究竟来自同步点设计、文件系统回写、设备排队、加密准备，还是共享存储的权限检查路径。


## 存储栈全景：从闪存芯片到应用 API

Android 存储栈按职责可以划分为应用与 framework、VFS 与文件系统、块设备映射与调度、主机控制器以及闪存器件几层。ext4、f2fs、FUSE、fscrypt 和 device-mapper 各自处在不同的位置，分析 I/O 问题时需要将它们逐层拆开，才能把笼统的“文件系统开销”落到具体环节上。

下面的简图标出了常见的读写路径；括号中的层级只在相应场景下出现。

```text
Application / native library
    ↓  Java File API、SQLite、MediaStore 或 POSIX I/O
Android framework / ContentProvider（按 API 路径）
    ↓
MediaProvider + FUSE（共享外部存储路径）
    ↓
VFS → ext4 / f2fs（集成 fscrypt；buffered I/O 使用 page cache）
    ↓
device-mapper（dm-linear、dm-verity、dm-default-key、snapshot，按卷配置）
    ↓
Block multi-queue / I/O scheduler
    ↓
UFS 或 eMMC host controller → storage device
```

同一次访问通常只经过图中的一部分路径：应用内部文件不走 MediaProvider/FUSE；只读动态分区一般经过 `dm-linear` 与 `dm-verity`；`/data` 则可能叠加 `dm-default-key` 和 `fscrypt`。具体设备采用哪些映射组合，仍要以该机的实际运行时配置为准。

<!-- gracker-diagram: ch06-01-storage-path-optional-frontends -->
![存储路径中的可选入口与公共底层](../../assets/diagrams/ch06/ch06-01-storage-path-optional-frontends.png)

图：本图按职责压缩层级，不是每次 I/O 都经过所有节点。内部文件不经共享存储 FUSE；授权 fd、直接路径、passthrough 可能不同，缓存命中也可能提前返回。dm 目标及叠加顺序按卷和更新状态核对。

我们先从最底层的物理存储器件看起。

## 物理存储器件：UFS 与 eMMC（embedded MultiMediaCard） 的差异

### 总线、并发和软件栈

eMMC 和 UFS 都属于管理型闪存器件，封装内部集成 NAND 闪存、控制器和 FTL（Flash Translation Layer，闪存转换层）。FTL 负责把主机看到的逻辑块地址映射到 NAND 物理位置。两类器件都向 Linux 暴露块设备接口，主要差异集中在主机总线和并发能力上。

eMMC 采用并行总线和半双工传输。早期 eMMC 请求模型的并发能力很有限，到了 eMMC 5.1 才定义了 Command Queuing（命令排队）；控制器同一时刻能排队多少命令，取决于主机驱动、器件是否支持 CQE（Command Queue Engine）、队列深度以及固件质量。

UFS 则采用 MIPI M-PHY 差分串行链路与 UniPro 协议，由 UTP 承载 UFS Command Set。链路本身全双工，协议和主机控制器也支持同时挂载多个 outstanding request（尚未完成的请求）。更高的链路速率、队列并发度和控制器并行度有助于改善吞吐与尾延迟，但应用实际感受到的性能，依然受 NAND 类型、SLC cache（单层单元高速缓存）、温度、容量占用与固件策略制约。

下面的分层图列出了 UFS 协议栈及各层承载的规范：

```text
┌─────────────────────────┐
│     Application Layer    │  ← UCS（基于 SCSI 的命令集）
├─────────────────────────┤
│     Transport Layer      │  ← UTP (UFS Transport Protocol)
├─────────────────────────┤
│     Interconnect Layer   │  ← UniPro（含传输、网络与数据链路）
├─────────────────────────┤
│     Physical Layer       │  ← M-PHY (差分串行)
└─────────────────────────┘
```

应用调用 `read()` 时，请求并不会直接变成 UFS Command Set 命令：文件系统与块层会先把文件偏移翻译成块请求，按需合并或拆分，最终由 UFS host driver（主机驱动）映射为 UTP transfer request。


### 版本号与实际性能

JEDEC 版本规定的是接口能力，同一标准的量产器件在实际 MB/s 和 IOPS（每秒输入/输出操作次数）上往往相差悬殊。建立性能基线应以目标设备的实测数据为准，横向比较时可以从以下维度拆解：

| 维度 | eMMC 5.1 | UFS 3.x / 4.x |
|---|---|---|
| 主机链路 | 并行、半双工 | M-PHY 串行、全双工 |
| 多请求能力 | 可有 CQE，设备实现差异大 | 原生支持多个 transfer request |
| Linux 驱动栈 | MMC block / CQHCI（命令队列主机控制器接口，按设备能力） | SCSI/UFSHCD（UFS 主机控制器驱动） |
| 多硬件队列 | 取决于主控和 CQE | 支持 MCQ 的 UFSHCI 主控可建立多组 submission/completion queue（提交/完成队列） |
| 常见性能特征 | 链路与并发上限较低 | 更高带宽与并发潜力，尾延迟仍由器件和负载决定 |

**MCQ（Multi-Circular Queue，多循环队列）是 UFS Host Controller Interface 的能力**，位于主机控制器一侧；而设备标称的“UFS 4.0”指的则是存储器件接口，两者需要分开看待。`android17-6.18-2026-06_r6` 的 `drivers/ufs/core/ufs-mcq.c` 会根据主控能力配置读写队列、专用读队列和 polling queue（轮询队列），默认读写队列数还会参考 CPU 数量。要确认一台设备是否启用了 MCQ，还需结合 host controller capability（主机控制器能力）、驱动日志和 `/sys` 队列信息核实。


### 验证器件差异

遇到 I/O 延迟异常时，先记录器件型号、UFS/eMMC 版本、文件系统、可用空间、设备温度和当前后台负载，再在这台设备上建立冷启动、随机读写和 `fsync()` 基线。Perfetto 的 block request 延迟可以直观反映请求在块设备路径上的等待时长，但是否属于异常，仍要对照同设备自身的基线来判断。


## 块设备层：设备映射与 I/O 调度

请求离开文件系统之后、到达存储器件之前，还要经过映射与调度两站。文件系统把一段或多段内存页组织成 `bio`（描述一组块 I/O 的内核结构）提交给块层；device-mapper 可以先行改写目标设备和扇区，块层再合并或拆分 `bio`，形成 request 交给 blk-mq（多队列块层）与设备驱动。映射和调度的先后顺序取决于 device-mapper 的叠加方式，配置不同，同一段 I/O 经过的路径也不同。

<!-- gracker-diagram: ch06-01-bio-dm-blkmq -->
![bio、映射与 request 的职责](../../assets/diagrams/ch06/ch06-01-bio-dm-blkmq.png)

图：本图是职责顺序示意，不保证每个 dm target 都是相同的 bio-based 实现；映射层可以多次重入底层块路径，合并、拆分和下发也不是简单一对一。

### device-mapper：虚拟块设备映射层

device-mapper（简称 dm）是 Linux 内核提供的通用块设备映射框架，可以把一个或多个底层块设备映射成新的虚拟块设备。Android 用它实现分区管理、完整性校验和加密等功能。

device-mapper 有三个基本概念：

1. **映射设备（Mapped Device）**：对上层可见的虚拟块设备，例如 `/dev/block/dm-0`；
2. **映射表（Mapping Table）**：定义虚拟设备的每段扇区范围对应哪个底层设备的哪些扇区；
3. **目标设备（Target Device）**：映射表指向的底层块设备。

Android 常用的 dm target（映射目标类型）包括：

- **dm-linear**：把一个连续扇区范围线性映射到另一个设备的连续扇区。它是 Dynamic Partition 的基础，`system`、`vendor` 等逻辑分区就是通过 `dm-linear` 从 `super` 物理分区中映射出来的。
- **dm-verity**：通过预先计算的 hash tree（哈希树）校验只读分区（如 `system`）的完整性，检测数据是否遭到篡改。
- **dm-snapshot / dm-user**：用于 Virtual A/B 的快照路径，具体职责随 Android 版本演进：Android 11 使用 `dm-snapshot` 和 kernel COW；Android 12 compressed snapshots 引入了 Android COW format 与 `snapuserd`，但仍需转换到 kernel COW / `dm-snapshot`；直到 Android 13+ 的 userspace merge 才移除对 kernel COW 和 `dm-snapshot` 的依赖。
- **dm-default-key**：用于 metadata encryption，在 `data` 分区的块设备层执行加密。

这些 dm 目标可以按需叠加，共同组成 Android 的分区布局，各分区的职责、挂载方式与性能影响也需要分开分析。


### I/O 调度器

I/O 调度器负责块 request 的排序、合并与派发。Android 设备可能选择 `mq-deadline`、BFQ（Budget Fair Queueing）或 `none`，具体取舍受 UFS MCQ 与设备厂商配置共同影响。`mq-deadline` 同时维护排序队列和 FIFO（先进先出）到期约束；BFQ 则依据预算和权重分配设备服务时间，在启用相应 cgroup（控制组）支持时还能体现组级权重。不过，调度器名称只是分析的起点，前台请求能否真正优先，还要看后续的分组配置。

手机上常出现前台随机读与后台顺序写互相争抢带宽的情况。AOSP `android-17.0.0_r1` 的 `libprocessgroup/profiles/cgroups.json` 仍把 v1 `blkio`（块 I/O 控制组）挂载到 `/dev/blkio`；在 `task_profiles.json` 中，`LowIoPriority` 进入 `blkio/background`，`SCHED_SP_FOREGROUND` 与 `SCHED_SP_TOP_APP` 则分别组合 `HighIoPriority` 与 `MaxIoPriority`。但在这个基线里，`HighIoPriority` 与 `MaxIoPriority` 最终都加入同一个 blkio 根组，单凭名字划分不出两个实际的 I/O 优先级档位。这些 profile 本质上只代表用户空间的分组意图；能否转化为设备侧的服务差异，还要取决于 active scheduler（当前启用的调度器）、内核 cgroup 支持以及厂商对 blkio 属性的配置。

核对实机配置时，可以结合 `/sys/block/<dev>/queue/scheduler`、`/proc/cgroups`、`/dev/blkio` 与设备配置一起查看。

<!-- gracker-diagram: ch06-01-io-task-profile-scheduler-gates -->
![I/O 分组意图到实际设备服务的条件](../../assets/diagrams/ch06/ch06-01-io-task-profile-scheduler-gates.png)

图：r1 的 High/MaxIoPriority 组路径相同，单看名字证明不了两个设备优先级档位。mq-deadline、BFQ 或 none 的选择要落到前台是否更快，还需核对内核与设备配置。

## 分区布局：system、vendor、data 与 metadata

### 传统分区与 Dynamic Partition

早期 Android 采用固定大小的分区：`system`、`vendor`、`cache` 等分区在出厂写入分区表时容量就已定死。即便 `system` 空间告急而 `vendor` 仍有富余，多出的空间也无法挪给 `system` 使用。

Android 10 引入了 **Dynamic Partition（动态分区）**。设备把 `system`、`vendor`、`product`、`odm` 等适合动态调整的只读分区统一放进 `super` 容器，再通过 `dm-linear` 映射成逻辑分区；至于 `boot`、`dtbo`、`vbmeta` 等 bootloader（引导加载程序）需要直接读取的分区，则通常保留为物理分区，位于 `super` 之外。

下面的简图示意了 `super` 与逻辑分区的映射关系，实际介质上的分区排列以具体设备为准：

```text
Physical Partition: super
┌──────────┬──────────┬──────────┬──────────┐
│  system  │  vendor  │ product  │   odm    │
│ (logical)│ (logical)│ (logical)│ (logical)│
└──────────┴──────────┴──────────┴──────────┘
         mapped via dm-linear
```

借助这种布局，OTA 升级可以动态调整各逻辑分区的大小，不再完全受固定分区表约束。

<!-- gracker-diagram: ch06-01-super-logical-extents -->
![super 容器与逻辑分区的 extent 映射](../../assets/diagrams/ch06/ch06-01-super-logical-extents.png)

图：super 本身是分区容器，挂载的是映射后设备上的文件系统。逻辑分区可以有多个 extent，具体排列、空闲区和 OTA 期间的 COW 占用以本机 metadata 为准。

### 各分区的职责

**system 分区**：包含 Android framework、系统库和系统应用，在正常 Verified Boot（验证启动）流程中以只读方式挂载。Android 9 首发设备曾采用当时的 system-as-root 方案，将 rootfs（根文件系统）内容合入 `system.img`，由内核直接挂载为根。到了 Android 10，分区布局仍保留 system-as-root，但启动方式改为强制携带 ramdisk：由 `first-stage init` 解析 `super` metadata、创建 `dm-linear` 逻辑设备并挂载 `system`、`vendor`、`product` 等分区，不再沿用 Android 9 的 no-ramdisk、kernel-direct-mount（内核直接挂载）路径。受保护的只读分区继续由 AVB（Android Verified Boot）/ `dm-verity` 验证。

**vendor 分区**：包含 HAL（硬件抽象层）实现、固件和厂商定制配置。Project Treble 借助这道分区界线把 vendor 实现与 Android framework 分离开来，使 framework 升级不必等待全部厂商实现同步更新。`vendor` 分区同样以只读方式使用，并受 `dm-verity` 保护。

**data 分区**：这是整机最主要的大容量可写分区，承载安装包（`/data/app/`）、应用私有数据（`/data/user/<user_id>/`）、共享媒体的底层存储（`/data/media/`）以及系统数据库等。设备上通常还另有 `metadata`、`persist` 等小型可写分区。应用日常的持久化流量几乎都落在这里，因此 I/O 性能分析的重点也在 `/data`。

**metadata 分区**：这是一个在启动早期即可使用的独立小分区，AOSP metadata encryption 文档建议容量为 16 MB，通常挂载到 `/metadata`。它保存用于保护 metadata encryption key 的 KeyMint blobs（由 KeyMint 保护的密钥数据），也可能承载 `vold`（Volume Daemon，存储卷守护进程）、checkpoint（检查点）、Virtual A/B 等功能在 `/data` 挂载前必须访问的少量状态。启动过程中，系统先挂载 `/metadata` 取得 key material（密钥材料），随后再建立 `/data` 的 metadata-encrypted block device（元数据加密块设备）——取密钥和建加密设备是先后两步，分析启动挂载依赖时需要分开追踪。


### 挂载流程：从 bootloader 到用户空间

Android 10+ 设备的启动链需要 bootloader、ramdisk 和用户空间多阶段接力完成。bootloader 完成 Verified Boot 和硬件初始化后，负责加载内核与启动所需的 ramdisk；其中，首发 Android 13+ 的 GKI 设备把 generic ramdisk 放进独立的 `init_boot`，而 vendor ramdisk 来自 `vendor_boot`，核对 ramdisk 位置时需要一并查看，不能只盯着 `boot.img`。

内核启动后会进入 ramdisk 中的 `first-stage init`，由它解析 `super` 分区 metadata、创建 `dm-linear` 逻辑设备，并挂载 `system`、`vendor`、`product` 等 `first_stage_mount` 分区。

进入 `early-fs` 阶段后，系统先拉起 `vold` 完成 metadata encryption 的前置准备；到了 `late-fs` 阶段，`init` 先执行 `wait_for_keymaster`，再通过 `mount_all` 挂载 `/data`。可见从解析 `super`、建立逻辑设备到挂载 `/data`，全过程都依赖内核与用户空间的接力协作，`vold` 在其中专门承担 `/data` 挂载前的密钥准备与设备映射。

<!-- gracker-diagram: ch06-01-boot-mount-key-preparation -->
![从启动镜像到 /data 可用的依赖](../../assets/diagrams/ch06/ch06-01-boot-mount-key-preparation.png)

图：这是常见配置的依赖链，init 具体动作由设备 rc/fstab 决定。Android 13+ 首发 GKI 的 generic ramdisk 位于 init_boot；super 是映射容器，不是 bootloader 直接挂载的文件系统。

## 文件系统：ext4 与 f2fs

### ext4 的同步写成本

ext4 和 f2fs 都是 Android 17 GKI（Generic Kernel Image，通用内核镜像）支持的文件系统，量产设备可以选择其中之一作为 `userdata`。ext4 在 Android 上仍是现役方案，分析它的延迟时，需要把日志策略、一致性保证和同步写时机放进应用的事务模型里一起看。

应用的普通 buffered I/O（缓冲 I/O）会先写入 page cache（页缓存），真正落盘的时机则常由 SQLite、`SharedPreferences`、文件下载器或系统服务调用 `fsync()` / `fdatasync()` 触发。移动设备同时面临进程频繁启停、后台脏页回写、掉电保护、热节流以及共享闪存队列竞争，这些因素都可能放大单次同步写的尾延迟。

<!-- gracker-diagram: ch06-01-buffered-cache-and-writeback -->
![缓存命中、脏页与实际块 I/O](../../assets/diagrams/ch06/ch06-01-buffered-cache-and-writeback.png)

图：图示普通 buffered 文件 I/O，省略 readahead、mmap 与错误路径。write 返回可仅表示数据进入缓存；fsync/数据库提交的持久化要求还受日志模式、文件系统、flush/FUA 与设备语义影响。

SQLite 可以使用 rollback journal（回滚日志）或 WAL（Write-Ahead Logging，预写日志）。一次事务提交究竟会触发哪些同步操作，取决于 journal mode、`synchronous` 级别、checkpoint 状态以及 Android SQLite 配置。以 WAL 为例，事务记录通常追加到 `-wal` 文件，再由 checkpoint 回写主库；估算一次事务的同步成本，就从这两段入手。

<!-- gracker-diagram: ch06-01-sqlite-rollback-wal-sync -->
![SQLite 两种日志模型与同步点](../../assets/diagrams/ch06/ch06-01-sqlite-rollback-wal-sync.png)

图：这是机制对照，不是每次事务固定发相同数量的 fsync。WAL commit 与 checkpoint 是不同阶段；实际同步由 synchronous、自动 checkpoint、文件系统和 Android 配置共同决定。

在 ext4 常见的 `data=ordered` 配置下，`fsync()` 需要协调目标文件的脏数据、必要的 `jbd2` metadata transaction（文件系统日志事务）以及设备 flush。由于延迟分配（delayed allocation）可能把块分配推迟到回写或同步阶段，后台写入也可能占据设备队列，因此要靠具体 trace 判断耗时落在哪一步。

<!-- gracker-diagram: ch06-01-ext4-fsync-data-journal-flush -->
![ext4 fsync 的数据、日志与条件 flush](../../assets/diagrams/ch06/ch06-01-ext4-fsync-data-journal-flush.png)

图：图限定常见有 journal、非 data=journal 的路径；无 journal、错误和特殊模式另有分支。journal 同步是否伴随额外设备 flush，要按这条路径的实际条件确认；延迟分配与后台写入也可能影响等待。

### f2fs：为闪存优化的文件系统

f2fs（Flash-Friendly File System）是 Android 设备可选的 `userdata` 文件系统。它采用 log-structured（日志结构） 设计，把主机侧更新写入新的逻辑块，再通过 segment（分段）、checkpoint 和 GC（垃圾回收） 管理空间。Android 也没有统一要求把 `/data` 从 ext4 迁移到 f2fs。

f2fs 的关键设计包括：

**Out-of-place update（异地更新）**：f2fs 通常把修改后的数据写入新逻辑块，再更新元数据。它可以把主机侧的随机更新整理到 segment 中，降低文件系统层的覆盖写与碎片压力。不过 NAND 的物理擦除、有效页搬移和写入放大仍有器件 FTL 参与，一次 4 KiB 更新在闪存内部产生多少写入，要由 FTL 的实际行为决定。

**冷热数据分离**：f2fs 会根据更新模式给数据与 node 标记不同温度，尽量把更新频率相近的数据放入相应 segment。这样可以降低 GC 搬移仍然有效的冷数据的概率。这种分类属于启发式策略，热写入仍有可能影响冷数据。

**SQLite batch atomic write（批量原子写）**：`android-17.0.0_r1` 的 `external/sqlite/dist/Android.bp` 明确定义了 `SQLITE_ENABLE_BATCH_ATOMIC_WRITE`。只有当 VFS 与文件系统报告相应能力、事务满足限制且采用 rollback-journal 相关路径时，SQLite 才可能通过 batch atomic write 减少 journal 工作。WAL 有自己的追加与 checkpoint 语义，用不上这项优化；设备文件系统和运行时 journal mode 都需要单独确认。

<!-- gracker-diagram: ch06-01-sqlite-batch-atomic-gates -->
![SQLite 批量原子写的启用条件](../../assets/diagrams/ch06/ch06-01-sqlite-batch-atomic-gates.png)

图：编译选项不代表每笔 SQLite 事务都减少日志。先确认运行时 journal mode、VFS/device characteristics 和实际原子写支持，再比较同步次数、延迟与写入量。

在 Perfetto 里看到 `data` 分区出现大量 `fsync()` 延迟时，第一步应先确认 filesystem type（文件系统类型）。针对 ext4，重点关注 `jbd2`（ext4 日志线程）和 `ext4_sync_file_*` 等同步写路径；针对 f2fs，则需要检查 writeback（脏页回写）、checkpoint 或 GC 是否正在与 foreground I/O 争用 device queue（设备队列）。f2fs 的 GC 多数时候在后台运行，但当可用空间吃紧时，回收也会直接拖慢前台读写。

<!-- gracker-diagram: ch06-01-f2fs-vs-ftl-gc -->
![f2fs GC 与 FTL GC 的不同边界](../../assets/diagrams/ch06/ch06-01-f2fs-vs-ftl-gc.png)

图：f2fs 的异地更新和冷热分离作用于主机逻辑块，NAND 页怎么搬移、何时擦除由器件 FTL 决定。两个 GC 层都可能有成本；空间紧张与后台写入影响尾延迟，需要分别观测。

## Scoped Storage：权限模型与 I/O 路径变化

### 为什么需要 Scoped Storage

Android 10 前后，共享存储的权限模型经历了一次彻底重构。在此之前，应用只要拿到 `READ_EXTERNAL_STORAGE` 或 `WRITE_EXTERNAL_STORAGE`，就能读取或修改共享存储（`/sdcard`）中的绝大部分内容，用户的照片、文档和下载文件缺少按媒体集合与创建者划分的细粒度隔离，暴露了过多隐私数据。

为此，Android 10 引入了 Scoped Storage（分区存储），并允许应用借助兼容开关暂缓迁移；从 Android 11 起，target API（应用声明的目标 API 级别）达到 30 及以上的应用必须遵循这套模型。主要变化有四条：

1. 应用可以直接读写自己的专属目录（`Android/data/<package_name>/` 和 `Android/media/<package_name>/`），无需申请存储权限；
2. 访问共享媒体通常先通过 `MediaStore` 查询和定位，再按 Android 版本申请媒体权限或由用户选择授权；Android 11+ 在获得访问权后，也支持使用直接路径的 `File` / `fopen()` 访问媒体；
3. 访问用户的 PDF、文档等任意文件时，一般通过 Storage Access Framework（SAF，存储访问框架）交由用户选择；应用自身的专属目录以及自己通过 `MediaStore.Downloads` 创建的文件，则按对应规则访问；
4. 遵循 scoped storage 的普通应用写共享存储时，应通过相应媒体集合、SAF 或自身专属目录完成，`/sdcard` 根路径不再开放任意直接写入入口；确有全局文件管理需求的应用，则对应专门的 All Files access 权限边界。


### FUSE 层的性能开销

新的权限模型需要在每次文件访问时落地执行。Android 11 重新引入了 FUSE 来承担这道关口：由 `MediaProvider` 充当 userspace FUSE handler（用户态 FUSE 处理程序），负责放行、拒绝或按策略脱敏文件访问结果。首发搭载 Android 11 且采用 5.4 及以上内核的设备全面转向 FUSE 路径，不再使用 SDCardFS；从旧版本升级上来的设备，则可能在 SDCardFS 之上叠加 FUSE。至于应用内部目录 `/data/user/<user_id>/<package>/`，走的是独立路径，完全绕开共享存储的 FUSE 挂载。

为了让大量第三方媒体库无需彻底重写，Android 11 新增了 shared media 的 direct file paths（直接文件路径）访问方式：拿到对应权限后，应用仍可用 `File` API 或 `fopen()` 读写媒体文件。需要分清的是，这一能力解决的是 API 兼容性，本身并没有承诺绕过 FUSE。官方文档在 Android 11 针对 Pixel 2 的性能对比中，曾记录下 direct file path 与 `MediaStore` 顺序读取性能接近、随机读写耗时可能接近后者 2 倍的结果。这一倍率强依赖具体设备与访问模式，不能直接外推为 Android 12–17 的统一规律；存在重度随机读写时，仍应优先评估 `MediaStore`。

从 Android 12 开始，平台引入了 FUSE passthrough（直通路径），但需要匹配的官方内核、`MediaProvider` 实现与产品属性同时到位。文件在 `open()` 阶段通过权限和 redaction（内容脱敏）检查后，FUSE 驱动可以把后续读写直接转发至 lower file system（底层文件系统）。在 `android-17.0.0_r1` 中，`MediaProvider/jni/FuseDaemon.cpp` 仍会检查 `persist.sys.fuse.passthrough.enable`、内核 capability（能力支持）以及文件是否需要 redaction/transform，再决定能否启用 passthrough；源码里同时存在 FUSE BPF 路径，由内核 BPF 程序接管部分 FUSE 操作。`MediaStore` API、Android 11 direct file path、FUSE passthrough 和 FUSE BPF 分属四个不同层次，定位共享存储性能问题时，第一步就是看清请求实际落在了哪一层。

<!-- gracker-diagram: ch06-01-fuse-open-and-passthrough -->
![FUSE open 检查与后续数据直通](../../assets/diagrams/ch06/ch06-01-fuse-open-and-passthrough.png)

图：r1 create_handle_for_node 要求无需 redaction 且 transform 已完成，才能在允许的路径上启用 passthrough；首次读才做转码时不能直接返回尚未转换的数据。MediaStore API、直接路径、passthrough 与 FUSE BPF 不是同一开关。 未获授权的 open 会失败，不进入这两条数据读写分支。

### 对 App I/O 行为的实际影响

落到应用开发与性能排查上，核心是理清三件事：接口怎么选、数据放哪里、版本差异怎么判。

**访问共享媒体时，先按访问模式选接口**：目录扫描、批量查询和随机读写场景，优先通过 `MediaStore` 完成索引与权限判定；只有在需要兼容旧库或 native 媒体栈时，再考虑 Android 11 的 direct file paths。

**应用私有数据优先放内部存储**：仅在应用内部使用的数据放在 `/data/user/0/<package>/` 最直接。如果确实需要写入 external app-specific directory（外部存储中的应用专属目录），做性能建模和排查时也要把它与共享媒体访问拆开，按两条独立路径评估。

**先核对版本再下结论**：同样是“共享媒体访问慢”，Android 10 需要区分 `MediaProvider` API 与当时的 SDCardFS/设备存储模拟路径；Android 11 才由 `MediaProvider` FUSE 支持 direct file path；Android 12+ 设备则可能启用了 passthrough。排查时务必先确认设备的首发版本、`MediaProvider` 模块版本、内核版本与产品属性。

在 Perfetto trace 中，未走 passthrough 的 FUSE 请求通常会表现为应用线程等待与 `MediaProvider` 的 FUSE worker（工作线程）活动在时间轴上对齐；启用 passthrough 后，后续数据读写可能不再唤醒用户态处理线程。因此，确认某次请求是否经过 FUSE，需要综合 `MediaProvider` 日志、产品属性、内核 capability 与实际调用路径，应用侧的 I/O wait 只是指向问题的线索。

### 版本断点速查

| Android 版本 | system / 挂载模型 | shared storage 入口 | FUSE 行为 | App 侧建议 |
| --- | --- | --- | --- | --- |
| Android 9 | `system-as-root` 成为首发设备基线，rootfs 合入 `system.img` | 传统 external storage 模型 | 设备存储模拟常用 SDCardFS，也存在升级和厂商差异 | 旧项目以路径访问为主，但要为后续访问权限减少做准备 |
| Android 10 | dynamic partitions + `first-stage init` 成为新设备主路径 | Scoped Storage 引入，可通过兼容机制暂缓 | MediaProvider 执行 scoped policy；设备存储模拟仍常见 SDCardFS，direct file path 受限 | 新代码优先 MediaStore / SAF，少依赖裸路径 |
| Android 11 | `/data` 挂载流程继续沿用 Android 10 | shared media 支持 direct file paths、`File` API、`fopen()` | MediaProvider 成为 FUSE handler；升级设备可叠加 SDCardFS | 媒体库兼容可以用 direct file paths，重度随机访问优先比较 MediaStore |
| Android 12 | 挂载模型基本稳定 | API 入口与 Android 11 接近 | 首发设备配合 official kernel 可启用 FUSE passthrough | 先确认设备是否支持 passthrough，再判断瓶颈位置 |
| Android 15-17 | 挂载与共享存储主要模型延续 Android 12+ | MediaStore / direct file path 共存 | FUSE passthrough 仍取决于内核与 MediaProvider 模块版本 | 大量枚举和跨媒体库访问仍优先使用 MediaStore，模块侧优化按设备实测确认 |

## FBE：文件级加密的存储影响

### 从全盘加密到文件级加密

Android 的存储加密经历了从全盘加密（Full-Disk Encryption，FDE）到文件级加密（File-Based Encryption，FBE）的演进。FDE 在块设备层用一套 volume key（卷密钥）保护 `userdata`，早期密码启动流程会将整卷解锁与用户凭据绑定。FBE 则借助 fscrypt policy（文件系统加密策略）把不同目录树划分到可独立解锁的加密类中，从而区分出 DE（Device Encrypted，设备加密）与 CE（Credential Encrypted，凭据加密）存储；至于内容密钥是否按文件派生，则取决于 policy 版本与 inlinecrypt 优化模式。

**DE 存储**：class key（加密类密钥）不依赖用户凭据解锁，但仍受 KeyMint、Verified Boot 与硬件信任根保护。系统完成 Direct Boot（用户解锁前启动）的准备工作后，direct-boot-aware 组件就能直接访问 DE 数据。

**CE 存储**：class key 受用户解锁凭据和 Android 密钥保护机制双重约束，必须在用户解锁后才能安装。应用默认存储、用户媒体和绝大多数隐私数据都归属 CE。

所有首发搭载 Android 10 及以上版本的设备都必须启用 FBE。

### metadata encryption、FBE 与 `/metadata` 的分工

讨论“存储加密”时，可以把三个容易混淆的层级拆开来看。`/metadata` 是一个独立小分区，用来存放保护 metadata encryption key 的 KeyMint blobs。

metadata encryption 工作在 userdata 块设备层，负责保护目录项、inode（索引节点）、文件长度等文件系统 metadata；现代设备上常见的实现是 `dm-default-key` 配合 inline crypto / blk-crypto。

FBE 则由 ext4/f2fs 集成的 `fscrypt` 实现，负责保护文件内容与文件名。在 `/data` 挂载之后，`vold` 才开始管理和安装对应的 FBE 密钥，并为目录设置加密策略。其中 System DE、User DE 与 User CE 密钥的准备时机各不相同，梳理启动和解锁时序时必须将它们分开。

顺着启动顺序能看得更清楚：系统先挂载 `/metadata`，让 `vold` 取出保护 metadata encryption key 的 key material；接着 `wait_for_keymaster` 与 `mount_all` 协作，使 `/data` 得以挂载；等到文件系统就绪后，`vold` 才会继续安装 System DE、User DE 和 User CE key。`dm-default-key` 保护的是 `/data` 块设备的元数据，与文件级加密 FBE 分属上下两层。

<!-- gracker-diagram: ch06-01-metadata-fbe-keymount-separation -->
![metadata 加密、FBE 与 /metadata 的依赖](../../assets/diagrams/ch06/ch06-01-metadata-fbe-keymount-separation.png)

图：dm-default-key 工作在块设备层；fscrypt 集成于文件系统，按目录策略使用 DE/CE 等密钥。/metadata 存放早期密钥材料，不是把 userdata 的全部文件系统 metadata 搬到另一个分区。

### FBE 的密钥层次

FBE 的密钥管理由 `vold` 负责。密钥层次如下：

1. **System DE Key**：系统级 DE key 在启动早期安装，保护 `/data/app`、`/data/misc`、`/data/system`、`/data/vendor` 等不属于某个用户 DE/CE 类的顶层数据。
2. **User DE Key**：每个用户各有 User DE class key，用于 Direct Boot 数据，对应 `/data/misc_de/<user_id>/`、`/data/system_de/<user_id>/`、`/data/user_de/<user_id>/`、`/data/vendor_de/<user_id>/` 等。
3. **User CE Key**：每个用户的 CE class key 在用户解锁认证成功后解封并安装，用于绝大多数 App 数据，对应 `/data/user/<user_id>/`，也包括 `/data/misc_ce/`、`/data/system_ce/`、`/data/vendor_ce/` 等。

AOSP `android-17.0.0_r1` 中的关键实现路径如下：

- `system/vold/FsCrypt.cpp`：`fscrypt_prepare_user_storage()` 准备 DE/CE 目录并应用 fscrypt policy；
- `system/vold/Utils.cpp`：`BuildDataSystemDePath()`、`BuildDataMiscDePath()`、`BuildDataUserDePath()` 生成 `/data/system_de/<user>`、`/data/misc_de/<user>`、`/data/user_de/<user>` 等路径。

fscrypt policy 设置在加密目录上，并写入文件系统 metadata。新建的子文件或子目录会继承父目录的加密上下文，内核再从已安装的 master key（主密钥）派生或选取对应的内容密钥与文件名密钥。应用层看到的仍是普通文件 API，至于一份文件此刻能否访问，取决于相应的 DE/CE class key 是否已经安装到位。

<!-- gracker-diagram: ch06-01-fbe-system-user-key-classes -->
![System DE、User DE 与 User CE 存储类](../../assets/diagrams/ch06/ch06-01-fbe-system-user-key-classes.png)

图：图不是密码学派生树，也不把 /data/user 父目录本身当某个用户的 CE。各类 key 的落盘保护和安装时机不同；文件内容密钥是否按文件派生，还受 policy、inlinecrypt 优化模式与 key 类型影响。

### 加密的 I/O 性能影响

加密路径引入的额外开销覆盖密钥准备、crypto mapping（加密映射）以及数据加解密本身，实际成本取决于设备是否具备 CPU crypto acceleration（加密指令加速）、inline crypto、hardware-wrapped key（硬件封装密钥）与匹配的底层驱动。

inline encryption hardware（内联加密硬件）通常集成在 UFS 或 eMMC host controller 中，在数据往返存储器件的路径上直接完成块加解密。`android17-6.18-2026-06_r6` 的 arm64 GKI 开启了 `CONFIG_BLK_INLINE_ENCRYPTION`、`CONFIG_FS_ENCRYPTION_INLINE_CRYPT`、`CONFIG_DM_DEFAULT_KEY`、`CONFIG_SCSI_UFS_CRYPTO`，同时也开启了 `CONFIG_BLK_INLINE_ENCRYPTION_FALLBACK`。这组配置说明内核具备内联加密接口与软件 fallback（回退实现），但具体设备能否走硬件路径，还要看密钥类型、算法、设备驱动以及 fstab（文件系统挂载配置）。需要特别留意的是，`blk-crypto-fallback` 仅支持 raw key（原始密钥），不支持 hardware-wrapped keys；在该内核基线下，`blk_crypto_start_using_key()` 遇到设备不支持的 wrapped key 配置时会直接返回 `-EOPNOTSUPP`，不会把同一密钥交回 CPU 做软件回退。

Android 17 还将新版 hardware-wrapped keys 命名为 `wrappedkey`，以区别于旧版 `wrappedkey_v0`。前者使用 android17 内核的 `blk-crypto` key generate/import/prepare 接口，与 mainline Linux 方向兼容。首发 Android 17 的设备可优先选用 `wrappedkey`；已经以 `wrappedkey_v0` 出货的设备则应继续沿用旧格式以兼容既有数据，因为决定磁盘格式的 `fileencryption=` 选项无法通过 OTA 更改。设备最终启用了哪种格式，可以从 `userdata` 的 fstab `fileencryption=` 选项、内核日志与加密测试中确认。

做性能分析时，最好先把加密路径核对清楚：软件 fallback 会拉高 CPU 耗时，而 inline crypto 也会受 keyslot（硬件密钥槽）编程、host reset、队列调度与内存带宽的影响。最小验证清单应覆盖 fstab、`dmctl table userdata`、内核配置与 `vts_kernel_encryption_test`，随后再把 CPU 活动与 block trace 对齐观察。查看 VTS 日志时，还需要确认 hardware-wrapped key 用例没有因为未检测到支持而被跳过——整体测试通过本身并不足以证明该能力已实际启用。

<!-- gracker-diagram: ch06-01-inlinecrypto-hardware-fallback -->
![Inline crypto 与软件路径的能力边界](../../assets/diagrams/ch06/ch06-01-inlinecrypto-hardware-fallback.png)

图：r6 GKI 同时启用 inline 接口与 fallback；实际路径还要看 fstab 和驱动。blk-crypto-fallback 不支持 hardware-wrapped keys；设备不支持相应 wrapped key 配置时，内核会拒绝使用该密钥，不能回退到 CPU 解密文件内容。dm-default-key 单独证明不了 FBE 已硬件卸载。

## Dynamic Partition 与 Virtual A/B 的存储布局

Dynamic Partition 借助 `super` 物理分区与 `dm-linear` 解决了运行时“逻辑分区如何划分”的问题；与之配套的 **Virtual A/B** 则负责 OTA 升级期间如何安全更新这些逻辑分区、差异数据存放在哪里，以及由谁来执行合并。

传统 A/B 方案会为每个需要无缝升级的分区保留完整的 A/B slot（槽位）。Virtual A/B 依然会复制 bootloader 必须直接读取的物理分区，但动态分区不再常驻一套完整副本，而是在 OTA 期间仅为变更部分创建 snapshot（快照），等新系统确认成功启动后再执行 merge（合并）。随着版本演进，snapshot 的格式、存放位置与 merge 执行者经历了三个主要阶段：

### Android 11：kernel COW

Android 11 引入了 Virtual A/B 的早期形态。升级差异采用 kernel COW（Copy-on-Write，写时复制）format，并由 `dm-snapshot` 对外提供 base partition（基础分区）与 COW 数据的组合视图。COW 数据在 OTA 期间会占用临时空间：Android 11 的 `PartitionCowCreator` 会优先利用当前与目标分区布局中都空闲的 `super` 区间，超出部分再由 `/data` 上的 COW image 补足；r1 的分配器至今仍区分 `cow_partition_size` 与 `cow_file_size`。因此，统计或追踪 COW 空间占用时，必须同时把 `super` 和 `/data` 两侧算进来；作为交换，动态分区无须常驻一套完整的 B 槽副本。新 slot 确认启动成功后，系统再把变化合并进 base device。至于单次请求是否产生额外读写，取决于具体操作以及当前所处的 merge 阶段，需要按阶段实测。

<!-- gracker-diagram: ch06-01-vab-cow-allocation -->
![COW 在 super 与 /data 之间如何分配](../../assets/diagrams/ch06/ch06-01-vab-cow-allocation.png)

图：Android 11 与 r1 分配器都区分 cow_partition_size 和 cow_file_size。图概括空间分配，两处是否同时占用、压缩 COW 以哪侧为主，都以本次 update metadata 和 backing image 为准。

### Android 12：compressed snapshots 与 dm-snapshot 过渡期

从 Android 12 起，Virtual A/B 支持启用 **compressed snapshots（压缩快照）**。这一版本引入了 Android COW format 与 `snapuserd`，压缩后的 COW 同样可能分布在 `super` 空闲区与 `/data` backing image 上，实际比例取决于剩余空间与更新布局；`dm-user` 则让用户态组件能够接手处理块设备读写。不过，Android 12 尚未实现纯 userspace merge：Android COW 仍需转换成 kernel COW format，snapshot merge 依然依赖 `dm-snapshot`。分析 Android 12 设备上的 OTA I/O 时，需要把 `snapuserd`、`dm-user` 和 `dm-snapshot` 串在一起看。

### Android 13+：userspace merge

Android 13 将 compressed snapshot 的 mount 与 merge 迁入用户态的 `snapuserd`，移除对 kernel COW format 与 `dm-snapshot` 的依赖。首发搭载 Android 13 及以上版本的设备默认启用 userspace merge，由旧版本升级而来的设备则需显式开启。Android 17 延续这一架构，同时 r1 提供了 `dm-user` 与 `ublk` 两种 snapshot 后端，`snapuserd` 挂在哪一侧由运行条件决定：`IsUblkEnabled()` 会依次检查 `ro.virtual_ab.ublk.enabled`、`vabc_with_ublk_support` flag 以及内核版本门槛（6.6+），测试模式下可通过参数覆盖属性，更新 manifest 也可禁用 ublk；真正落到设备上，还需具备相应的内核驱动与设备节点。新 slot 确认成功后才会启动合并；一旦进入 merge，就无法再回退到未修改的旧系统，若合并中途被打断，系统会在后续重启时继续恢复合并。

<!-- gracker-diagram: ch06-01-android17-ublk-selection -->
![Android 17 r1 的快照后端选择](../../assets/diagrams/ch06/ch06-01-android17-ublk-selection.png)

图：IsUblkEnabled 的测试 force_mode 可覆盖属性；真正映射 ublk 还需内核驱动、/dev/ublk-control 等节点就绪，节点缺失可使建立失败，自动回退与否取决于具体条件。此图限定已经采用 userspace snapshot 的更新。

下面的简图用于对比三个关键版本的 COW 与 merge 路径。

```text
Virtual A/B 存储模型演进:

Android 11(kernel COW):
  snapshot delta → dm-snapshot COW → super 空闲区 + 按需 /data backing image

Android 12(compressed snapshots 过渡期):
  snapshot delta → Android COW（super / /data）→ dm-user + snapuserd → kernel COW / dm-snapshot merge

Android 13+(userspace merge):
  snapshot mount / merge 由 snapuserd 执行，移除 kernel COW / dm-snapshot 依赖
  Android 17 r1 后端按条件选择 dm-user 或 ublk
```

上图中 Android 12 这一行处于格式转换的过渡期，运行时走的仍是混合路径，尚未实现 Android 13+ 才具备的纯用户态 merge。compressed snapshots 占用的 `/data` 临时空间会在升级合并完成后释放回收；而在升级安装阶段的 COW 写入以及后续 merge 期间的底层设备流量，都可能与前台应用的 I/O 发生竞争。


在 Perfetto trace 中，OTA 升级期间的 Virtual A/B 活动主要分布在三组进程上：

| 进程 | 角色 | Trace 特征 |
| --- | --- | --- |
| `update_engine` | 下载/应用更新、协调 COW 与 merge 状态 | 安装期间有下载与 COW 写入；不能由守护进程存在与否判断 merge 是否活跃 |
| `snapuserd` | Android 12 compressed snapshots 的 COW 处理；Android 13+ 的 userspace merge | 按 snapshot 读视图与 merge 阶段产生 CPU、COW 和 base device I/O；r1 后端可能为 dm-user 或 ublk |
| 前台 App | 受影响方 | 主线程 `fsync()` / `read()` 延迟明显增加，时间与 `snapuserd` / `update_engine` 活动对齐 |

Android 13+ 的 userspace merge 大多在后台执行；Android 12 设备则仍需单独留意 `dm-snapshot` 的 merge 路径。当可用空间紧张或后台写入密集时，`snapuserd` 产生的 COW/base I/O 与应用数据 I/O 可能落到同一块物理存储器件上，争用带宽、设备队列与 CPU；即使它们分属不同的逻辑分区，也可能相互影响。前台等待是否被它拉长，仍要对照实际 trace 与对照组负载才能确认。

<!-- gracker-diagram: ch06-01-snapshot-view-and-merge -->
![快照读取视图与后续 merge 阶段](../../assets/diagrams/ch06/ch06-01-snapshot-view-and-merge.png)

图：实线概括读视图依赖，虚线表示后续合并阶段，并不是每次读都立刻 merge。进入 merge 后 base 已开始改变，完整回滚的承诺就此失效；中断后会恢复合并。不同逻辑分区也可能争用同一存储器件。

## 存储寿命与写入放大

评估存储寿命，关键在于追问“一次应用写入最终在 NAND 闪存上落下了多少字节”。NAND 闪存单元只能承受有限次数的 program/erase cycle（编程/擦除循环）。SLC、MLC、TLC、QLC 每个单元存储的比特数不同，耐久度趋势各异；即便同属一类颗粒，也会因制程工艺、纠错能力、预留空间与厂商分级拉开明显差距。此外，手机存储器件普遍引入了动态 SLC cache（以单层单元模式工作的高速缓存）、磨损均衡和 over-provisioning（预留空间），估算器件寿命必须落实到具体型号的规格上。

**写入放大（Write Amplification Factor，WAF）**的测量需要先切分两段路径。器件 WAF 等于 NAND 实际写入字节数除以主机提交给器件的写入字节数：数据库日志、文件系统 metadata 与 F2FS GC 放大的是前一段“应用有效写入 → 主机块写入”，这些额外写入量已经包含在器件 WAF 的分母里；FTL GC、磨损均衡以及 SLC 数据搬移影响的则是后一段“主机块写入 → NAND program”。因此计算器件 WAF 时，必须分别采集主机侧与 NAND 侧的字节计数——应用发起的 4 KiB 写入还处在主机侧放大之前，凭固定 erase block（擦除块）大小同样推算不出设备 WAF。

<!-- gracker-diagram: ch06-01-write-amplification-boundaries -->
![应用、主机与 NAND 的写入放大边界](../../assets/diagrams/ch06/ch06-01-write-amplification-boundaries.png)

图：公式适用于相同且非零的工作量对比，需处理缓存延迟、后台写入和计数窗口。减少应用重写可减少总写入，器件 N/H 比值是否随之下降要另行测量；一次应用 4 KiB 只覆盖主机侧，单独当设备 WAF 分母会把比值算错。

写入放大主要源自以下三类活动：

- **垃圾回收（GC）**：NAND 无法就地覆盖写，必须先擦除整块再重新写入。当空闲 block 不足时，控制器需要先把仍有效的数据搬移到其他 block，再擦除旧 block，这些内部搬移都会带来额外写入。
- **磨损均衡（Wear Leveling）**：控制器会尽量拉平各个 block 的擦写次数，防止局部热点过早损毁，数据重分布同样会产生搬移写入。
- **文件系统与应用写入模式**：小事务、频繁 checkpoint、临时文件反复重写以及文件系统 GC 会重塑主机提交的请求形态，FTL 再把这些逻辑写入映射到物理 NAND 上。

随着可用空间下降，文件系统与 FTL 可调度的空闲区域同步收窄，GC 更容易进入前台路径，尾延迟与 WAF 都可能上升。同时，设备使用时长本身只是一个伴随变量，应用数据膨胀、机身温度、后台任务、OTA merge、器件固件以及电池策略都会改变表现。遇到“手机用久了变慢”，需要把这些因素逐项过一遍，再下判断。

在应用层，开发者可以通过合并状态更新、避免无实质变化的重写、控制日志与缓存体积，把持久化移出关键交互路径。以 `SharedPreferences.apply()` 为例，它先更新内存再排队写盘，并不保证每次调用都对应一次完整的 XML 写盘：r1 的 `writeToFile()` 会跳过磁盘上已有的代次，也会略过已被更新状态覆盖的异步中间代次；不过最新状态真正持久化时，依然需要执行 XML 序列化和同步落盘，组件生命周期切换时也可能反过来等待 queued work（排队写入）。如果优化目标是压低总写入量与闪存磨损，应当先减少逻辑层的无效重写，再分别测量主机侧写入量与器件 WAF——异步 API 本身并不自动带来更少的写入量。

<!-- gracker-diagram: ch06-01-sharedprefs-async-generations -->
![SharedPreferences 异步写入的代次跳过](../../assets/diagrams/ch06/ch06-01-sharedprefs-async-generations.png)

图：图限定 r1 的 apply 异步路径与已有文件代次检查。磁盘已有此代次、过时异步中间状态可被跳过；最新需持久状态仍会写 XML 并同步。新文件创建等路径按各自条件判断是否跳过。

## 常见问题与误区

**“手机变慢是因为闪存老化了吗？”**

判断闪存是否拖慢整机，需要结合剩余可用空间、器件寿命健康指标、后台写入量、温度、文件系统 GC、I/O 错误计数以及同机型健康基线一起来看。闪存磨损确实可能拉长延迟，但也常常只是随着使用积累，应用数据体积与并发负载本身同步增长的结果。

**“f2fs 一定比 ext4 快吗？”**

快慢必须回到具体的负载特征与机型配置上验证。f2fs 的 out-of-place update、冷热分离和 segment 管理契合不少闪存写入场景，而 ext4 成熟的日志与块分配策略也可能在另一类负载下更稳健。两者的实际表现都受 mount option（挂载选项）、内核版本、剩余空间、GC、checkpoint、设备 cache 与 flush 语义影响。选型与对比应当依据目标机型实测的 p50/p95/p99（第 50/95/99 百分位）延迟、吞吐、CPU 占用和写入量，所谓“低于 80%”之类的统一阈值并没有源码依据。

**“FBE 加密会拖慢存储性能吗？”**

在具备 inline encryption 硬件的设备上，FBE 增加的 CPU 负担通常不大；如果设备缺少这类硬件支持，软件加解密才会明显占用 CPU。确认 FBE 的实际路径时，应核对 fstab 中的 `fileencryption=` 与 `inlinecrypt` 参数、fscrypt/blk-crypto 能力以及驱动是否走通硬件路径——仅看到 `dm-default-key` 只能证明 metadata encryption 已启用，无法说明 FBE 已经走上硬件加密。再将 `vold` 与内核日志、CPU 活动和块层等待结合分析，才能评估具体成本。

## 存储问题观测地图

开展 I/O 诊断时，至少需要覆盖下面五个观测面，才能把结论从“感觉像 I/O 慢”推进到具体层次：

| 关注面 | 推荐抓取点 | 重点看什么 | 异常形态 |
| --- | --- | --- | --- |
| Block layer | Perfetto 的 `ftrace`（内核跟踪）事件 `block_rq_issue`、`block_rq_complete` | 单次请求从 issue 到 complete 的时延、队列是否堆积 | 前台线程卡在 `fsync()` / `read()`，同时块请求完成时延持续增加 |
| ext4 / f2fs | `ext4_sync_file_*`、`f2fs_sync_file_*`、内核回写线程 | 同步写是否集中出现在事务提交或 checkpoint 前后 | `fsync()` 时间长，并伴随 `jbd2`、f2fs checkpoint 或 GC 活动 |
| Shared storage / FUSE | App 线程、`MediaProvider`、`fuse` 相关进程或线程 | App I/O wait 是否与用户态转发、权限检查同时发生 | 目录扫描或批量访问媒体时，App 与 `MediaProvider` 的 CPU 和 I/O 等待同时增加 |
| Mount / encryption | 开机阶段的 `init`、`vold`、`wait_for_keymaster` 日志与 trace slice（事件区间） | `/metadata` 是否已挂载、`vold` 是否提前启动、`mount_all` 是否卡住 | 开机早期反复重试 KeyMint，`/data` 长时间无法挂载，后续 I/O 全部受到影响 |
| OTA merge | `update_engine`、`snapuserd`、Virtual A/B merge 相关后台写入 | OTA 后台 merge 是否仍在持续、前台 I/O 是否受到挤压 | 重启后长时间存在稳定写入流量，前台 App 随机 I/O 延迟异常 |

需要注意的是，`block_rq_issue` 到 `block_rq_complete` 只覆盖请求下发给设备驱动之后的耗时，并未计入用户态调用、文件系统处理以及下发前的排队等待，统计一次 `fsync()` 或 `read()` 的总耗时必须把上层调用区间一并算上。此外，命中页缓存的读请求可能不产生 block 事件；若要观察调度器内部的排队情况，还需配合 insert/requeue 等事件和上层调用区间一起看。

除了 Perfetto，排查时还应结合 `logcat`、`dmesg`、`mount` 和 `getprop` 做交叉印证。存储问题常常横跨内核、`init`、`vold`、`MediaProvider` 与应用线程，把这几层证据链串起来，定位才稳固。

## 从存储架构定位性能问题

当主线程卡在 `fsync()` 上时，可以按下面六个步骤自上而下收敛范围：


1. **调用层**：确认是谁发起了 `fsync()`、同步的是哪个文件，以及这个同步点是否必须放在主线程。
2. **文件系统层**：确认采用 ext4 还是 f2fs、挂载参数是什么，并核对 `jbd2`、checkpoint、writeback 或 GC 是否与等待区间重合。
3. **块设备层**：检查 active I/O scheduler、request issue-to-complete（请求下发到完成）延迟、队列堆积以及并发的后台写入。
4. **映射与加密层**：读取 device-mapper table 与 fstab，确认是否涉及 `dm-default-key`、snapshot、inline crypto 或软件 fallback。
5. **共享存储层**：若路径落在 `/storage/emulated` 下，核对 `MediaProvider`/FUSE、passthrough、权限检查与 redaction 行为。
6. **器件层**：记录 UFS/eMMC 型号、MCQ 状态、剩余空间、温度与设备健康信息，对照同机型基线解读数值。

顺着这套顺序排查下来，Perfetto 里原本模糊的“I/O wait”就能逐步收敛到同步点、文件系统、块队列、共享存储或存储器件上的可验证根因。

第 6.2 节将继续深入文件系统选择、I/O 调度与具体调优手段；存储等待与内存压力共同放大卡顿的案例则放在第 7.2 节。

## 参考资料

- **手机 Android 存储性能优化架构分析** - Linux 阅码场，系统梳理了 Android 存储 I/O 路径和 ext4/f2fs 的性能差异
- **手机主流存储器件的分析与发展** - OPPO 内核工匠，介绍 eMMC/UFS 架构对比与 UFS 4.0 MCQ 特性
- **Android 分区挂载原理介绍** - OPPO 内核工匠，介绍 Dynamic Partition、dm-linear 与 FBE 密钥层次
- **[Partition layout | AOSP](https://source.android.com/docs/core/architecture/partitions/system-as-root)** - Android 9/10 system-as-root 语义与 first-stage init 的分工
- **[Scoped storage | AOSP](https://source.android.com/docs/core/storage/scoped)** - Android 11 MediaProvider/FUSE、direct file path 与性能特征
- **[FUSE passthrough | AOSP](https://source.android.com/docs/core/storage/fuse-passthrough)** - Android 12+ passthrough 的内核、产品属性和验证方式
- **JEDEC UFS 4.0 Standard (JESD220F)** - UFS 设备接口与协议能力；MCQ 还需结合 UFS Host Controller Interface 规范和主控实现
- **Android Common Kernel `android17-6.18-2026-06_r6`** - `drivers/ufs/core/ufs-mcq.c`、arm64 GKI defconfig、ext4/f2fs、blk-crypto 与 dm-default-key 实现
- **AOSP `android-17.0.0_r1`** - `system/core/libprocessgroup/profiles/`、`system/vold/FsCrypt.cpp`、`packages/providers/MediaProvider/jni/FuseDaemon.cpp`、`external/sqlite/dist/Android.bp`
- **[Virtual A/B overview | AOSP](https://source.android.com/docs/core/ota/virtual_ab)** - Android 11 kernel COW、Android 12 格式转换、Android 13+ userspace merge 的官方版本划分
- **[File-based encryption | AOSP](https://source.android.com/docs/security/features/encryption/file-based)** / **[Metadata encryption | AOSP](https://source.android.com/docs/security/features/encryption/metadata)** - DE/CE、KeyMint、`dm-default-key`、inline encryption 与 `/metadata` 启动依赖
- **[Hardware-wrapped keys | AOSP](https://source.android.com/docs/security/features/encryption/hw-wrapped-keys)** - `wrappedkey` / `wrappedkey_v0` 的版本与兼容边界，以及 VTS 用例跳过时的验证限制
- **[r6 blk-crypto.c](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/block/blk-crypto.c)** / **[Inline encryption 文档](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-06_r6/Documentation/block/inline-encryption.rst)** - raw key 软件回退与不支持 wrapped key 时的拒绝路径
- [KIOXIA managed flash protocol analysis](https://americas.kioxia.com/content/dam/kioxia/en-us/business/memory/mlc-nand/asset/KIOXIA_Protocol_Analysis_Tech_Brief.pdf)：UFS 3.1/4.0/4.1 与 JEDEC 规范编号对应表。
- [MIPI UniPro](https://www.mipi.org/specifications/unipro-specifications)：UFS 互连层与 M-PHY 的分工。
- [Android 17 snapshot.cpp](https://android.googlesource.com/platform/system/fs/fs_mgr/+/refs/tags/android-17.0.0_r1/libsnapshot/snapshot.cpp) / [capabilities.cpp](https://android.googlesource.com/platform/system/fs/fs_mgr/+/refs/tags/android-17.0.0_r1/libsnapshot/capabilities.cpp)：dm-user/ublk 选择、更新 manifest 与 merge 状态。
- [Android 11 COW 分配](https://android.googlesource.com/platform/system/core/+/refs/tags/android-11.0.0_r1/fs_mgr/libsnapshot/partition_cow_creator.cpp) / [Android 17 COW 分配](https://android.googlesource.com/platform/system/fs/fs_mgr/+/refs/tags/android-17.0.0_r1/libsnapshot/partition_cow_creator.cpp)：super 空闲区与 data backing image。
- [Android 17 SharedPreferencesImpl](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/app/SharedPreferencesImpl.java)：异步中间代次跳过与实际持久化。
- [KIOXIA logical-to-physical address translation](https://www.kioxia.com/content/dam/kioxia/shared/business/memory/mlc-nand/asset/productbrief/KIOXIA_Understanding_Logical_Block_Address_Tech_Brief.pdf)：器件 WAF 的 NAND/host 字节边界。

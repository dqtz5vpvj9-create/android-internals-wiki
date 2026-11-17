# 第 6 章：存储与 I/O

> 平台源码统一锚定 AOSP `android-17.0.0_r1` / Android 17（API 37）；涉及内核机制时，以 `android17-6.18-2026-06_r6` 为核对基线。量产设备的文件系统、块设备、调度器和厂商补丁以产品配置为准。

Android 上的 I/O（输入/输出）问题常常显得很偶发：主线程某次读取被 page fault（缺页）拉长，`fsync()` 等待文件系统提交并按存储栈协议落盘，后台任务与前台启动争用块设备，或者共享存储请求经过 MediaProvider 与 FUSE（用户态文件系统）后多出一截延迟。如果只看 Java 调用栈，很容易把这些存储等待误判成业务计算慢。

分析存储延迟时，应先理清请求经过了哪些层、耗时具体落在哪一段等待上，再结合上层接口语义和底层设备条件判断优化方向，避免预先假定哪种文件系统一定更快：

<!-- gracker-diagram: ch06-overview-storage-layers -->
![存储访问入口与共同下层](../../assets/diagrams/ch06/ch06-overview-storage-layers.png)

图：直接私有路径与共享存储入口不同；下层的文件系统、缓存、加密和块设备仍共同影响延迟。图为概念分层，具体产品可能没有 device-mapper 或采用不同配置。

- 应用私有目录通常经由 VFS（统一文件系统接口）、ext4/F2FS、device-mapper（块设备映射层）和块 I/O 层到达存储设备；
- 共享存储还要考虑 MediaProvider、FUSE、passthrough（绕过部分用户态数据转发）、FUSE BPF（让部分 FUSE 操作在内核侧处理）和 scoped storage（分区存储）权限检查；
- SharedPreferences 的 `commit()`、`apply()` 与 `QueuedWork` 决定 XML 何时写盘，以及积压的写入何时反过来阻塞调用线程；
- DataStore 解决的是异步、一致性和结构化存储问题，不会消除底层 I/O 延迟；
- 文件级加密、闪存回收、热节流、内存回写和并发负载，都可能改变同一段代码的长尾延迟。

eMMC、UFS 和 NVMe 是不同的存储接口，并发队列能力各异；ext4 与 F2FS 在写入、回收和一致性策略上也有各自取舍。由于 Android 允许产品按需组合底层方案，单看系统版本既不能默认设备已经换装 UFS，也不能直接断定 F2FS 的随机写一定快过 ext4。动手调试前，先记录挂载表、文件系统、块设备、内核配置和当前测试负载，后续数据才有对照基础。

## 内容索引

<!-- gracker-diagram: ch06-overview-reading-map -->
![第6章按问题选择阅读入口](../../assets/diagrams/ch06/ch06-overview-reading-map.png)

图：四个入口按问题选择，也可从架构到具体机制顺序阅读；图中的连接表示知识关系。


- [6.1 Android 存储架构](01-storage-architecture.md)
- [6.2 文件系统与 I/O 调度](02-filesystem-io-scheduling.md)
- [6.3 SharedPreferences 与 DataStore：I/O、ANR 与多进程一致性](03-sharedpreferences-datastore.md)
- [6.4 vold、MediaProvider 与 FUSE：共享存储 I/O 路径](04-vold-mediaprovider-fuse.md)

## 阅读建议

遇到主线程处于 `D` 状态时，先看它正在等待的内核栈、调度事件和 I/O 区间。`D` 状态只代表线程处在不可中断睡眠中，背后可能是驱动、内存回收或其他内核等待；同样，Trace 里单独出现 `block_io`、page fault 或 `io_uring`（Linux 异步 I/O 接口）事件，也还不足以证明卡顿正是由它引发的。

推荐的排查顺序是：

1. 明确文件路径、文件系统、挂载选项和调用线程；
2. 用 Perfetto 和 ftrace（内核跟踪工具）对齐应用延迟、调度、page fault、writeback（脏页回写）和块 I/O；
3. 区分同步语义、队列拥塞、闪存长尾、文件系统回收和权限路径成本；
4. 在同一设备、同一构建和同一温度条件下做单变量复测。

<!-- gracker-diagram: ch06-overview-investigation-flow -->
![存储延迟的调查顺序](../../assets/diagrams/ch06/ch06-overview-investigation-flow.png)

图：先证明延迟发生在哪段等待，再做单变量复测。单独看到 D 状态、page fault 或 block 事件，只是线索，仍需与目标请求的时间和调用链关联。

应用启动阶段的 I/O 问题可以结合启动章节分析；如果同时出现 reclaim（内存回收）、PSI（资源压力停顿指标）或 page fault，还应查看内存管理章节。

# 第 12 章：网络性能

本章围绕 Android 应用网络请求的端到端耗时展开，覆盖业务排队、必要的路由与 DNS 解析、新传输连接与 TLS 握手、HTTP 交换，以及响应消费和应用处理。实际执行时，缓存命中、连接复用、并行尝试和流式处理会让部分阶段跳过或彼此交叠，各阶段耗时并不会简单地串行累加。在系统侧，还需要将负责网络与路由管理的 netd，与维护每网络配置、缓存和 Private DNS 的 DNS Resolver 区分开来；至于系统如何选网及 `NetworkCallback` 的具体语义，请参阅 [1.22](../../part1-fundamentals/ch01-architecture/22-connectivity-service.md)。

排查网络问题时，建议先将单次请求按阶段拆解，再顺着耗时或报错证据进入 TLS 或 DNS 专项。状态栏的 Wi-Fi 图标、系统网络验证结果、DNS 可用性与目标服务可达性分别反映不同层面的状态，排查时应各自核实，不宜笼统归结为“网络正常”或“网络异常”。

<!-- gracker-diagram: ch12-index-01-request-stage-map -->
![请求阶段、复用与业务内容可用](../../assets/diagrams/ch12/ch12-index-01-request-stage-map.png)

图：先看请求实际经历的阶段，再区分系统状态与业务端点可用性。 箭头表示依赖，非固定串行时长；连接复用与缓存可跳过新建阶段，流式处理可交叠，示意不声称性能收益。

## 章节地图

- [12.1 Android 网络与 TLS 性能优化](01-android-network-tls-performance.md)
- [12.2 netd 与 DnsResolver：DNS 解析性能和故障诊断](02-netd-dnsresolver-network-diagnostics.md)

## 阅读路径

### 应用网络性能排查

建议先读 12.1，建立请求阶段模型并确认连接复用情况，再排查 TLS 握手、证书链与信任配置；若问题集中在域名解析、Private DNS 或特定网络环境，继续阅读 12.2。

### 系统网络栈排查

先读 [1.22 Connectivity 服务、网络选择与回调](../../part1-fundamentals/ch01-architecture/22-connectivity-service.md)，理清 NetworkRequest、NetworkCallback、网络排序、rematch 和 linger 的语义，再结合 12.2 检查 netd 路由与每网络 DNS。业务连接恢复与容灾可参考 [24.5](../../part5-app/ch24-io-network/05-mobile-network-connection-resilience.md)，Wi-Fi 网络选择与切换性能可参考 [24.8](../../part5-app/ch24-io-network/08-wifi-connectivity-selection.md)。

<!-- gracker-diagram: ch12-index-02-chapter-reading-map -->
![按应用阶段与系统网络问题选择专项](../../assets/diagrams/ch12/ch12-index-02-chapter-reading-map.png)

图：应用请求先在12.1分段，系统选择先读1.22，再按证据进入DNS或恢复专项。 阅读分支不是故障根因断言；DNS、TLS与系统Network可能共同影响同一请求。

## 版本边界

本章各节均以 Android 17 / API 37 / AOSP `android-17.0.0_r1` 作为当前的源码核验锚点，并在文中各自说明了适用版本范围。由于实际行为受应用的 targetSdk、设备运行系统及服务端配置共同影响，排查时仍需单独记录 HTTP 客户端、TLS provider 与 Mainline 模块的版本。对于实现细节与公开文档存在出入的地方，12.1 分别说明了 ECH 当前文档与固定 `r1` 源码默认策略的差异，12.2 则区分了普通查询与组合查询超时后的不同回调路径。分析具体设备时，仍应以实测的模块信息与连接证据为准，避免直接套用旧版网络分数或已退出主路径的 API 来推导当前行为。

<!-- gracker-diagram: ch12-index-03-network-version-boundaries -->
![系统、模块与实际连接的版本边界](../../assets/diagrams/ch12/ch12-index-03-network-version-boundaries.png)

图：把系统与target、网络库和模块、DNS与服务端一起纳入证据。 固定r1用于源码核验，不能概括所有更新设备；ECH默认与组合查询线程差异见各专项，不凭版本号推断启用与成功。
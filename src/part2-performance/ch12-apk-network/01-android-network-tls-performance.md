---
title: Android 网络与 TLS 性能优化
chapter: '12.1'
section: '12.1'
status: finalized
applicable_versions: Android 8 (API 26) - Android 17 (API 37)
last_verified: '2026-10-24'
last_verified_against: AOSP android-17.0.0_r1；Android 公开 API 文档；OkHttp 5.3.0 提交0960b47ec28a02e893499d2a7e53bf462a62875e；Cronet Play services 18.0.1 接入文档；HTTP/TLS/QUIC RFC；当前文档与固定r1的ECH默认值分别披露
confidence: high
sources:
- type: official
  path: https://developer.android.com/develop/connectivity/network-ops/reading-network-state
- type: official
  path: https://developer.android.com/reference/android/net/ConnectivityManager
- type: official
  path: https://developer.android.com/reference/android/net/ConnectivityManager.NetworkCallback
- type: official
  path: https://developer.android.com/reference/android/net/NetworkCapabilities
- type: official
  path: https://developer.android.com/develop/connectivity/cronet
- type: official
  path: https://developer.android.com/develop/connectivity/cronet/start
- type: official
  path: https://developer.android.com/develop/connectivity/cronet/reference/org/chromium/net/CronetEngine.Builder
- type: official
  path: https://developer.android.com/reference/android/net/http/HttpEngine.Builder
- type: official
  path: https://developer.android.com/reference/androidx/tracing/Trace
- type: official
  path: https://developer.android.com/reference/android/telephony/SubscriptionInfo
- type: official
  path: https://developer.android.com/privacy-and-security/local-network-permission
- type: source
  path: https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/README.md
- type: source
  path: https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/OkHttpClient.kt
- type: source
  path: https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/ConnectionPool.kt
- type: source
  path: https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/EventListener.kt
- type: rfc
  path: https://www.rfc-editor.org/rfc/rfc9113
- type: rfc
  path: https://www.rfc-editor.org/rfc/rfc9114
- type: rfc
  path: https://www.rfc-editor.org/rfc/rfc9000
- type: rfc
  path: https://www.rfc-editor.org/rfc/rfc9001
- type: aosp
  path: packages/modules/Connectivity/framework/src/android/net/ConnectivityManager.java
- type: aosp
  path: packages/modules/Connectivity/framework/src/android/net/NetworkCapabilities.java
- type: aosp
  path: packages/modules/Connectivity/service/src/com/android/server/ConnectivityService.java
- type: aosp
  path: packages/modules/NetworkStack/src/com/android/server/connectivity/NetworkMonitor.java
- type: aosp
  path: frameworks/base/telephony/java/android/telephony/SubscriptionInfo.java
- type: aosp
  path: libcore/luni/src/main/java/libcore/io/BlockGuardOs.java
- type: official
  path: https://developer.android.com/about/versions/17/behavior-changes-17
- type: official
  path: https://developer.android.com/privacy-and-security/security-config
- type: official
  path: https://developer.android.com/privacy-and-security/certificate-transparency-policy
- type: official
  path: https://developer.android.com/about/versions/10/features#tls-1.3
- type: official
  path: https://developer.android.com/reference/android/crypto/hpke/package-summary
- type: official
  path: https://developer.android.com/reference/android/crypto/hpke/Hpke
- type: official
  path: https://developer.android.com/reference/android/crypto/hpke/HpkeSpi
- type: official
  path: https://android.googlesource.com/platform/external/conscrypt/+/android-17.0.0_r1/common/src/main/java/org/conscrypt/SSLParametersImpl.java
- type: official
  path: https://android.googlesource.com/platform/external/conscrypt/+/android-17.0.0_r1/platform/src/main/java/org/conscrypt/Platform.java
- type: official
  path: https://android.googlesource.com/platform/packages/modules/DnsResolver/+/android-17.0.0_r1/PrivateDnsConfiguration.cpp
- type: official
  path: https://www.rfc-editor.org/rfc/rfc8446
- type: official
  path: https://www.rfc-editor.org/rfc/rfc9180
- type: official
  path: https://www.rfc-editor.org/rfc/rfc9849
- type: official
  path: https://github.com/square/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/ConnectionPool.kt
- type: official
  path: https://github.com/square/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/EventListener.kt
- type: official
  path: https://developer.android.com/develop/connectivity/cronet/reference/org/chromium/net/QuicOptions.Builder.html
tags:
  - network
  - okhttp
  - http/2
  - http/3
  - quic
  - weak-network
  - network-security
  - tls
related_chapters:
- '12.2'
- '1.22'
- '24.5'
- '24.6'
- '8.1'
- '1.2'
last_consolidated_at: '2026-08-24'
consolidated_from:
- src/part2-performance/ch12-apk-network/03-network-performance-deep.md
- src/part2-performance/ch12-apk-network/01-network-performance.md
- src/part2-performance/ch12-apk-network/02-network-security-tls-performance.md
---

# Android 网络与 TLS（传输层安全） 性能优化

一次接口调用的等待时间，分散在客户端排队、DNS（域名系统）解析、路由尝试、建连与拥塞控制、加密握手、上传、边缘节点、服务端、响应传输、解析和界面更新里。只拿到“接口耗时 2 秒”这个总结果，还定位不出时间具体花在哪一段。

移动网络环境持续波动，而客户端真正能控制的始终是请求时机、连接复用、总期限、缓存、重试和内容降级这几件事。因此，优化工作的第一步是统一各阶段的计时口径，再据此按协议、请求组织和网络状态制定策略——下文也正是按这条线索展开。

> 源码基线：Android 17 / API 37、AOSP `android-17.0.0_r1`、OkHttp 5.3.0、Play services Cronet 18.0.1；实际设备的内核、Conscrypt/Mainline 模块和网络 provider 都可能与该源码快照存在差异。其中 OkHttp 5.3.0 tag 对应提交 `0960b47ec28a02e893499d2a7e53bf462a62875e`；旧 `square` 仓库链接目前会重定向至 `lysine-dev`，排查时注意核对 tag 提交，勿将重定向后的 `main` 分支当作 5.3.0。

`netd`（Android 网络管理守护进程）与 DNS Resolver（解析器）的内部细节见 12.2，系统选网与 `NetworkAgent` 见 1.22。

## DNS、连接、传输与应用处理

### 应用网络栈和主线程边界

动手优化之前，先看清应用的 HTTP 请求实际走哪条路径——不同网络栈的底层落点各不相同：OkHttp 自己管理连接池，TCP 通常经由 `java.net.Socket`，TLS 走平台 JSSE/Conscrypt（Java 与 Android 的 TLS 实现）；Cronet 使用 Chromium native（原生代码）网络栈；API 34 起的 `HttpEngine` 则交给设备提供的系统实现。请求走哪条路，决定了哪些环节由应用掌控，也是排查主线程卡顿的前提。

协议栈位置也随路径而异：HTTP/3/QUIC 的状态机运行在 Cronet 或 `HttpEngine` 的用户空间 provider（实现提供方）里，内核只负责底层的 UDP/IP/socket；OkHttp 5.3.0 的内置实现不支持 QUIC/HTTP/3，源码中虽然预留了 `Protocol.HTTP_3` 和 `QUIC` 枚举，但枚举本身并不包含对应的传输实现。

<!-- gracker-diagram: ch12-01-01-network-stack-layers -->
![Android 应用 HTTP 栈的实现落点](../../assets/diagrams/ch12/ch12-01-01-network-stack-layers.png)

图：先确定由哪个网络实现管理连接、TLS 与协议状态。 内核接口是概念共用层，省略JNI/Binder细节；OkHttp枚举h3只是预留枚举，说明不了内置已有HTTP/3实现。

主线程上的网络阻塞需要区分“直接发起网络 I/O”和“同步等待后台网络”两种情况。在直接发起路径中，`Inet6AddressImpl` 会在检查 DNS 缓存前调用 `BlockGuard.getThreadPolicy().onNetwork()`，BlockGuard 依赖这类钩子来拦截主线程违规 I/O；`BlockGuardOs` 也会在非 UDP 的 connect、超时不为 0 的 poll 以及 recvmsg 等入口触发检查。由于 UDP connect 属于明确例外，且 JNI 层的直接 I/O 也可能绕过部分 Java 检测，因此主线程上“没抛异常”并不足以证明网络风险已排除。

第二种情况则是用 `Future.get()`、`CountDownLatch.await()` 或 `runBlocking` 同步等待后台请求：它们虽不会触发 `NetworkOnMainThreadException`，却会直接卡住 UI 线程，造成掉帧甚至 ANR（应用无响应）。定位主线程卡顿时，先分清问题落在直接 I/O 还是跨线程等待上，后续才好顺藤摸瓜。


### 一次请求应当怎样计时

对于普通的顺序请求，可以先按下面这条概念链路来拆解各阶段耗时。需要注意的是，同步 `execute()` 不会经过异步 Dispatcher 的并发排队；而双工请求、`Expect: 100-continue`、提前响应以及升级连接则会产生交错事件，需单独记录：

```text
enqueue / execute
  → 异步 Dispatcher 排队（execute 不走此队列）
  → 代理选择与 DNS
  → 路由尝试
  → TCP + TLS，或 QUIC + TLS
  → 请求头与请求体
  → 响应头
  → 响应体
  → 反序列化、业务处理与界面更新（流式解析可与读取重叠）
```

在实际请求中，缓存命中或连接复用会跳过部分阶段，重定向、认证、路由回退和重试则会让同一阶段反复出现，双工请求还允许请求体与响应数据交错收发。因此，监控埋点应当保留完整的事件序列，某段计时从何处起止、各阶段实际发生过几次，都要以序列中的真实事件为准。

<!-- gracker-diagram: ch12-01-03-call-event-sequence -->
![Call 事件序列与可跳过、重复的阶段](../../assets/diagrams/ch12/ch12-01-03-call-event-sequence.png)

图：保留实际事件序列，区分缺席、重试和交错。 上方是普通顺序路径；新鲜缓存可跳过网络，连接合并仍可能有DNS，双工与100-continue另记。条长没有时长含义。

#### 需要分开的指标

| 指标 | 建议边界 | 能回答的疑问 |
|---|---|---|
| Call 总耗时 | `callStart` 到 `callEnd` / `callFailed` | 用户发起的单次 `Call` 在网络库内停留多久 |
| Dispatcher 异步排队 | 对应 `dispatcherQueueStart` 到 `dispatcherQueueEnd` | `maxRequests` / `maxRequestsPerHost` 是否造成等待；自定义 Executor 内部排队需另测 |
| DNS | 每组 `dnsStart` 到 `dnsEnd` | 域名解析、缓存和重定向域名是否消耗时间 |
| 建连前置阶段 | HTTPS 的 `connectStart` 到 `secureConnectStart`；明文到 `connectEnd` | 新路由、TCP 及可能的代理 CONNECT 隧道准备，不能一律命名为纯 TCP RTT |
| TLS | `secureConnectStart` 到 `secureConnectEnd` | 加密握手与证书处理消耗多少时间 |
| 请求发送 | `requestHeadersStart` 到 `requestBodyEnd`，无请求体时到 `requestHeadersEnd` | 上传或请求体生产是否缓慢 |
| 响应头等待近似值 | 普通顺序请求发送结束到首个 `responseHeadersStart`；若要最终头部就绪，另看 `responseHeadersEnd` | 事件发生在库读到响应头后，并非精确的线上首字节；100-continue/1xx 需另分组 |
| 响应体交付 / 消费 | `responseBodyStart` 到 `responseBodyEnd`，同时保存字节数与关闭方式 | 包含应用读取节奏；空体或提前关闭也可能触发事件，不能等同完整资源下载成功 |
| 内容可用时间 | 业务发起到数据可展示 | 网络、解析、数据库和 UI 的整体结果 |

<!-- gracker-diagram: ed12-01-call-consumption-and-content -->
![Call 终态、响应消费和内容可展示分别计时](../../assets/diagrams/ch12/ed12-01-call-consumption-and-content.png)

图：普通顺序HTTP路径的职责与数据依赖合图：业务发起、Call事件、响应消费、解析/存储和UI可展示分别计时。execute返回响应头不等callEnd；读取可受消费背压影响，提前关闭也能结束这次调用，完整下载与业务成功要另行确认。流式解析可与读取重叠，两轨无测量时长含义，Call终态与UI可见不强制固定先后。HTTP状态/解析成功不能仅靠failed布尔识别；过期业务取消传到Call，响应体或升级流仍由owner关闭，cancel不替代关闭。双工、100continue、升级需另存实际交错事件。

在 OkHttp 5.3.0 中，`callStart` 会在调用 `enqueue()` 或 `execute()` 后立即触发，而 `dispatcherQueueStart`/`dispatcherQueueEnd` 这对排队事件只记录异步 Dispatcher 的并发名额等待：若请求入队时直接获准执行，就不会触发这对事件；同步 `execute()` 也不受异步 Dispatcher 的并发上限约束。至于 HTTP/2 stream 容量、连接分配以及自定义 Executor 内部的排队等待，则需单独测量，不能混算进 Dispatcher 排队耗时。相关约束详见同版本的 [`EventListener.kt`](https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/EventListener.kt)。

#### TTFB 的两种起点

严格意义上的 TTFB（Time to First Byte）指收到线上首字节的时间，而 `EventListener` 回调提供的是网络库层面的近似值。因此统计前需要先统一起点与终点的口径：

- 从 `callStart` 到首个 `responseHeadersStart`：涵盖排队、DNS、建连、握手、上传与服务端等待；在普通顺序请求中接近等待响应头的总耗时，但与真正的线上首字节仍有差距。
- 从请求发送结束到响应头事件：排除了前端建连与发送阶段，主要反映网络往返、代理、CDN 与服务端处理耗时。遇到 `100-continue` 或提前响应时，响应头事件可能早于上传结束触发，此时直接相减会产生错误结果；若要度量最终响应头就绪时间，则需单独取 `responseHeadersEnd`。

单靠一个偏高的 TTFB 数值，还不足以把问题归因到服务端。要进一步缩小排查范围，需要把服务端 trace（性能跟踪）、`Server-Timing`、CDN cache（节点/缓存）状态和客户端分段计时放在一起对照，并固定好响应头与响应体的切分边界。在固定的 OkHttp 5.3.0 版本中，`responseHeadersStart` 是在 `readResponseHeaders()` 返回后才触发的（在开始读取前触发属于 4.3 之前的旧行为），与内核收到首字节的时刻仍有偏差；而且遇到 `Expect: 100-continue` 或其他 1xx 中间响应时，该事件还可能早于请求体发送结束，统计时应当将中间响应单独列出，并用 `responseHeadersEnd` 标记最终响应头就绪。如果同时接入了 Cronet，还需注意 `getTtfbMs()`（首字节耗时）与 `getResponseStart()`（响应头接收结束时间）的语义差异，跨网络库合并指标时必须先按定义对齐字段。

<!-- gracker-diagram: ch12-01-05-ttfb-endpoints -->
![TTFB 起点、响应事件与中间响应](../../assets/diagrams/ch12/ch12-01-05-ttfb-endpoints.png)

图：给每个响应等待指标写清起点、终点和中间响应规则。 固定5.3.0的responseHeadersStart在库读到头后触发，不是wire首字节；100-continue可早于上传结束。

#### 传输速率怎么算

传输速率适合用在大响应、上传和媒体流上。计算时至少记录：

- 有效载荷字节数与计时起止点；
- 内容编码，例如 gzip、Brotli；
- 是否命中 HTTP cache；
- 应用是否因读取响应过慢产生 backpressure（上游被迫等待的背压）；
- 协议、网络 transport（传输类型）、是否 metered（按流量计费）、是否 roaming（漫游）；
- 中断、续传和重试字节。

`NetworkCapabilities.getLinkDownstreamBandwidthKbps()` 返回的是系统估计的**第一跳传输链路带宽**，反映的是设备到当前接入网络的能力；这个值只能作为策略参考，若直接当作实际请求吞吐量来使用，往往会产生很大偏差。


### HTTP/1.1、HTTP/2 与 HTTP/3

| 能力 | HTTP/1.1 | HTTP/2 | HTTP/3 |
|---|---|---|---|
| 传输 | TCP | TCP | QUIC over UDP（基于 UDP 的 QUIC） |
| 加密 | 可选；Android 业务通常使用 TLS | HTTPS 场景使用 TLS | TLS 1.3 集成在 QUIC 握手中 |
| 同连接并发 | 常规实现中一条连接一次处理一个请求 | 多个 stream（请求流）复用一条连接 | 多个 QUIC stream 复用一条连接 |
| 头部压缩 | 无协议级动态压缩 | HPACK（HTTP/2 头部压缩） | QPACK（HTTP/3 头部压缩） |
| 丢包影响 | 该 TCP 连接等待缺失字节 | 同一 TCP 连接上的 stream 都受传输层顺序约束 | 丢失数据所属 stream 等待重传；共享拥塞控制仍会影响整条连接 |
| 网络迁移 | 通常重建连接 | 通常重建连接 | 协议具备 Connection ID（连接标识）与路径验证能力，能否迁移取决于实现和服务端 |


横向对比三代协议，HTTP/2 借助多路复用（multiplexing）和 HPACK 头部压缩降低了应用层并发对多条 TCP 连接的依赖，也减少了重复的握手与头部开销。不过底层 TCP 依然严格按字节序交付，一旦其中一段数据丢包，同一连接上其他 stream 的后续数据都得等待重传；此外，服务端允许的最大并发 stream 数、流优先级调度以及单连接拥塞控制，同样会制约实际并发表现。

HTTP/3 将请求映射到相互独立的 QUIC stream 上，某条流的数据丢包时，其他无依赖的请求流不必再受限于同一条 TCP 字节序列。尽管如此，HTTP/3 也只消除了传输层的队头阻塞：QPACK 动态表更新依赖、关键控制流以及连接级流量控制依然可能引发跨流等待；同时，连接级拥塞窗口、设备 CPU、服务端调度和 UDP 转发路径仍是共享资源，在存在丢包的网络环境下，HTTP/3 的实际表现也未必一定更快。

<!-- gracker-diagram: ch12-01-08-loss-and-qpack -->
![HTTP/3 避开 TCP 队头阻塞后的共享约束](../../assets/diagrams/ch12/ch12-01-08-loss-and-qpack.png)

图：丢失数据不再要求独立请求流等待同一 TCP 字节序列，但依赖仍需单独检查。 轨道是机制示意；QUIC共享拥塞/连接流控，QPACK动态表依赖和关键控制流仍可能阻塞多个请求。

#### 0-RTT 的边界

QUIC 在恢复连接时允许携带 TLS early data（握手确认前的早期数据），从而省去一次网络往返，即 0-RTT。这一机制需要客户端保有之前的会话状态、双方配置均允许，且服务端实际接受该早期数据才能成立；若服务端拒绝 early data，客户端会退回正常握手流程。因此，业务功能必须按 0-RTT 可能失败的路径来保证正确性，只能把它视作一项未必每次都能命中的延迟优化。

Early data 面临重放风险——攻击者可能截获并重复发送同一份请求数据，其安全属性弱于完整握手后的 1-RTT 数据。因此，只有能容忍重复执行的请求才适合放入 0-RTT；像支付、发帖、创建订单这类有副作用的操作，要么等待握手完成再发送，要么依靠服务端幂等键、去重记录和明确的重放防护策略来兜底。HTTP 方法名本身只能作为初筛线索，能否容忍重放最终仍取决于业务语义。

在 Cronet 中，可以通过实验性接口 `QuicOptions.Builder.enableTlsZeroRtt()` 开启 TLS 0-RTT；但使用前需确认设备上实际的 provider 版本支持该选项（Play services 的接入依赖版本号只是引入坐标，具体能力仍取决于运行时加载的 provider），而 `addAllowedQuicHost()` 仅用于配置允许启用 QUIC 的目标主机白名单。此外，跨进程场景下的会话恢复能否生效，还受磁盘缓存、provider 实现以及服务端会话状态的共同影响。

#### QUIC 连接迁移的条件

QUIC 借助 Connection ID，允许连接在客户端 IP 或端口变化后继续沿新路径传输，Cronet 也相应提供了 `ConnectionMigrationOptions` 配置项。不过，连接迁移能否顺利完成，取决于 provider 配置、服务端支持、新路径验证，以及 NAT（网络地址转换）、VPN 和中间网络设备的兼容情况，在 Wi‑Fi 与蜂窝网络切换时请求依然可能中断失败。另外，如果允许迁移使用非默认网络或在握手前跨网重试，还可能意外消耗用户原本未选中的计费流量，因此需要同步约束计费网络（metered）的使用、迁移次数与驻留时间。综合来看，连接迁移是一项依赖多项条件同时满足的优化手段，业务层仍需保留取消、重试与幂等保障来兜底。

<!-- gracker-diagram: ch12-01-10-quic-migration -->
![QUIC 切网迁移与业务恢复](../../assets/diagrams/ch12/ch12-01-10-quic-migration.png)

图：网络变化后先验证新路径，迁移失败仍由业务恢复保证正确性。 CID只是机制前提；provider、服务端、NAT/VPN及计费网络规则均影响结果。轨道无真实时长。

#### Android 上怎样使用 HTTP/3

OkHttp 5.3.0 的稳定协议栈覆盖 HTTP/1.1 与 HTTP/2，需要 HTTP/3 时可以评估 Cronet。当前 Android 官方接入使用下面的 Play services 依赖：

```kotlin
dependencies {
    implementation("com.google.android.gms:play-services-cronet:18.0.1")
}
```

构造 `CronetEngine` 前应先调用 `CronetProviderInstaller.installProvider(Context)`，并妥善处理 Play services 缺失、版本过旧或安装失败的情况。如果设备退回到功能较弱的官方 Java 备用实现 `cronet-fallback`，它的 HTTP/3 支持、性能表现与连接迁移能力都需要单独实测验证，不能直接套用 native（C/C++ 层）Cronet 的测试结论。

通常一个进程只需维护一个 `CronetEngine` 实例，若存在多个实例，应避免并发读写同一个存储目录（storage directory）。如果应用选择自行打包 native Cronet provider，还需参照 [25.10 应用体积分析与优化：DEX、Native SO 与资源](../../part5-app/ch25-power-size/10-apk-r8-resource-optimization.md) 检查 ABI（应用二进制接口）、符号导出及 16 KB 内存页大小（page size）的兼容性；至于页大小调整对初始化耗时的影响，目前并无通用的固定收益比例，需以目标设备实测为准。

<!-- gracker-diagram: ch12-01-11-cronet-provider -->
![Cronet provider 安装与运行时能力](../../assets/diagrams/ch12/ch12-01-11-cronet-provider.png)

图：先确认 provider 可加载，再复用 engine 并观察实际协商协议。 Play services18.0.1只是接入坐标，设备内provider版本与HTTP/3成败要看运行时；Java fallback的能力要先单独验证，再决定是否沿用native结论。

#### 协议选择的线上分组

HTTP/3 发布至少要按这些维度分组：

- 实际协商生效的协议（以防客户端配置了“启用 QUIC”但实际仍回退到 HTTP/2）；
- 首次连接、会话恢复和已有连接复用；
- Wi‑Fi、蜂窝、VPN、漫游与 metered 状态；
- 地区、运营商、CDN POP（边缘节点）和服务端版本；
- P50、P95、P99 延迟（50/95/99 分位数），以及失败率、回退率和重试率；
- 请求大小、响应大小与电量成本。

上线 HTTP/3 需要客户端、服务端与中间网络路径协同就绪：服务端正确宣告支持能力，CDN 与防火墙放行对应的 UDP 流量，客户端则保留向 HTTP/2 回退的路径。建议先小比例放量；一旦发现尾部延迟或失败率恶化，应按网络类型与地区逐组排查，避免被整体均值掩盖局部异常。


### 请求组织：复用、并发、合并与预热

协议之外，客户端能直接下手的是请求组织。这一节按连接复用、并发与聚合、预连接预热的顺序展开，它们共同决定一次请求要重复付出多少建连和调度成本。

#### 共享 OkHttpClient

OkHttp 官方建议在进程内全局复用同一个 `OkHttpClient` 实例：每个独立创建的 client 都会自带连接池与后台线程池，若按请求反复新建，不仅会丧失连接复用机会，还会导致线程和空闲连接资源持续堆积。

下面的代码创建一个共享 client，并从它派生不同超时策略：

```kotlin
data class TimeoutPolicy(
    val callMs: Long,
    val connectMs: Long,
    val readMs: Long,
    val writeMs: Long,
)

val sharedClient = OkHttpClient()

fun clientFor(
    base: OkHttpClient,
    policy: TimeoutPolicy,
): OkHttpClient = base.newBuilder()
    .callTimeout(policy.callMs, TimeUnit.MILLISECONDS)
    .connectTimeout(policy.connectMs, TimeUnit.MILLISECONDS)
    .readTimeout(policy.readMs, TimeUnit.MILLISECONDS)
    .writeTimeout(policy.writeMs, TimeUnit.MILLISECONDS)
    .build()
```


通过 `newBuilder()` 派生的 client 会与基础实例共享连接池和线程资源。因此我们可以用它为交互请求、文件上传、流式读取等场景分别定制超时策略；只有当代理、信任管理器、证书固定、自定义 DNS 或协议配置存在无法调和的冲突时，才需要考虑创建独立 client。

OkHttp 5.3.0 默认最多保留 5 条**空闲**连接、最长保持 5 分钟——注意这个数字约束的是空闲连接的缓存与回收，并非总连接数上限，也不限制每域名只能建 5 条连接。正在承载 HTTP/2 stream 的活跃连接不会被计入空闲池；至于总并发度，异步请求受 Dispatcher 队列上限控制，同步 `execute()` 的并发则由业务自行约束，同时还要受限于服务端的 stream 上限、系统 socket 配额及文件描述符资源。要判断默认连接池参数是否够用，应当先观测新建连接率、空闲连接回收频率以及服务端的 keep-alive（保持连接）策略，再决定是否调优。


连接能否被后续请求复用，取决于 scheme（协议）、port、代理、DNS、socket/TLS 配置、hostname verifier（主机名校验器）和 certificate pinner（证书固定器）等完整的 `Address` 匹配条件。在固定的 OkHttp 5.3.0 版本中，如果想让不同域名复用同一条 HTTP/2 连接（跨主机合并），还必须同时满足：双方均采用 DIRECT 直连路由、解析出的 socket 地址与端口一致、使用内置主机名校验器、现有连接证书覆盖新域名、证书 pin 检查通过且连接仍允许开启新 stream；走代理的连接则不适用这套直连合并规则。两个域名最终能否共享连接，需逐一对照这些条件核实。

<!-- gracker-diagram: ch12-01-15-connection-eligibility -->
![连接复用与跨主机合并的筛选](../../assets/diagrams/ch12/ch12-01-15-connection-eligibility.png)

图：先检查连接与Address资格，同主机复用和跨主机合并走不同后续条件。 固定5.3.0概念分支，省略内部对象锁；跨主机需要H2、直连路由相同socket地址、端口/证书/校验器/pin和容量均满足。

OkHttp 5 默认启用了 fast fallback（快速回退），通过交错并行地尝试多个可用路由来缩短 IPv6/IPv4 建连等待。其默认算法按时间间隔交错发起 TCP 建连，一旦某条路由率先连通，便会取消或延后其余落败的 TCP 尝试，再仅对胜出路由执行 TLS 握手等后续流程，而不会让所有地址同时跑完完整握手。由于并发建连会导致多个 `connect` 事件在时间上重叠，埋点时必须按单次路由 attempt 分别记录，不能把各路由的耗时直接相加当作墙钟等待时间。

<!-- gracker-diagram: ch12-01-16-fast-fallback -->
![Fast fallback 的 TCP 竞速与 TLS 后续](../../assets/diagrams/ch12/ch12-01-16-fast-fallback.png)

图：交错尝试TCP路由，选出胜者后再完成TLS等连接准备。 阶段轨道只示意并行关系；固定算法的250ms只是调度参考间隔，实际连接时间以每次为准，TLS不与所有地址同时竞速。

#### 并行请求与聚合接口的取舍

聚合接口能减少网络往返、重复 header（请求头） 和客户端调度，但也会放大响应体、缓存失效范围和单次失败的影响。反过来，HTTP/2 / HTTP/3 的并行请求允许各数据块独立缓存、独立失败和按优先级展示。

具体选用哪种组织方式，可以对照以下几项指标来权衡：

- 页面最早可展示时间与全部数据完成时间；
- 每个接口的缓存周期和权限范围；
- 部分失败是否允许展示；
- 聚合服务的超时与下游 fan-out（一次请求扇出为多个下游调用）；
- header、序列化和重复字段占比；
- 取消页面后还有多少无用请求继续执行。

同一页面每次打开都发出相同请求时，缓存或状态复用通常比单纯增加并发更有效。而搜索联想、滚动图片和页面切换，要及时取消过期请求，把 Dispatcher、stream 和带宽资源让给当前可见的内容。


#### 预连接的真实成本

OkHttp 没有提供可直接保证任意业务请求都能复用的公开 `preconnect()` API；如果通过发送 HEAD 或空 GET 请求来实现连接预热（warmup），依然会消耗实际的 DNS、建连、TLS、服务端计算、流量及电量开销。而且即便提前建好了连接，后续业务请求仍可能因为网络切换、authority（URL 中的主机与端口）不一致、证书策略差异、空闲超时回收或服务端主动断连而无法命中复用。

若冷启动指标证明预热有收益，可设置无副作用、低成本、允许失败的专用 endpoint（服务端接口），并满足这些条件：

- 与后续请求使用同一 authority 和网络栈；
- 不触发鉴权刷新、业务统计、昂贵后端或 WAF（Web Application Firewall）规则；
- 只在很快会使用该域名时执行；
- 不阻塞首屏，也不把失败展示给用户；
- 记录复用命中率、额外字节和电量变化。

另外，DNS 预解析只能分摊域名解析阶段的耗时，TCP、TLS 或 QUIC 握手仍会在后续请求时照常发生；Cronet 提供的 QUIC hint（提示）和会话元数据也只起到辅助提示和状态复用的作用，实际能否快速建连仍需以运行时为准。

<!-- gracker-diagram: ch12-01-18-warmup-costs -->
![预热的复用机会与真实代价](../../assets/diagrams/ch12/ch12-01-18-warmup-costs.png)

图：只有很快需要的同authority、同栈请求才值得验证预热复用收益。 HEAD/GET预热是真实请求，会消耗网络、服务端和电量；DNS预解析只覆盖解析这一步，TCP/TLS仍要另行建立，hint也只是提示，建连结果以运行时为准。

### CDN、DNS 与图片

请求组织之外，CDN、DNS 和图片体量同样影响每一段耗时。这一节看客户端在这三处分别能观察到什么、能改动什么。

#### 客户端如何观察 CDN

CDN 会改变 DNS 答案、边缘节点距离、TLS 会话、协议协商、缓存命中和回源（边缘节点访问源站）路径。客户端可在不泄露敏感信息的前提下记录：

- 业务域名的匿名分组；
- 协议与 IP family；
- CDN 提供的 POP / cache 状态响应头白名单；
- DNS、connect、TLS、响应头等待和传输耗时；
- 响应码、重试、回退和字节数。

仅凭客户端测得的 TTFB，很难区分耗时究竟来自边缘节点排队、cache miss（缓存未命中）还是源站处理，需要结合 CDN 日志与服务端 trace ID 来补齐归因链。出于安全与隐私考虑，这些关联字段应通过白名单筛选后传递，切勿将完整 URL、query（查询参数）、Cookie、Authorization 头或用户标识直接写入 APM（应用性能监控系统）。


#### 自定义 DNS 与系统边界

OkHttp 通过 `Dns` 接口支持自定义域名解析。无论是通过 HTTP 协议获取地址的 HTTPDNS，还是将查询封装进 HTTPS 通道的 DoH（DNS over HTTPS），接入这类自定义解析服务时都必须妥善处理 TTL（解析结果有效期）、IPv6 兼容、多地址排序、负缓存（缓存解析失败结果）、请求取消、故障回退以及按网络隔离缓存。同时，请求 URL 仍应保留原始域名，确保 HTTP `Host` 头、TLS 握手的 SNI（服务器名称指示）以及证书主机名校验能正常工作——直接将 HTTPS URL 替换为裸 IP 会破坏这套身份校验语义（后文证书小节还会详述这一点）。

<!-- gracker-diagram: ch12-01-21-domain-and-ip -->
![连接地址与 HTTPS 域名身份分开处理](../../assets/diagrams/ch12/ch12-01-21-domain-and-ip.png)

图：解析结果决定连接地址，原始URL域名继续用于HTTP与TLS身份语义。 仅把URL改成裸IP再补Host头，SNI和主机名验证是否保持原样要单独核对；专门设计的IP证书服务须单独处理。

还需要权衡的是，自定义解析可能不使用 Android Private DNS、VPN 或企业 split DNS 提供的命名空间与解析策略，有时还会破坏局域网域名访问和强制门户（captive portal）认证流程；而业务流量最终是否走 VPN 隧道，依然取决于 socket、Network 绑定以及系统路由表。因此上线前应同时核查域名解析合规与数据路由两方面要求。即使怀疑系统 DNS 偏慢，也应基于按网络环境分组的统计数据来决策，不宜因零星超时就全量切换至自定义解析。


#### 图片网络优化

图片请求优化的主要手段，仍是减少无用字节和无用工作：

- 按显示尺寸、密度和裁剪方式请求合适分辨率；
- 列表优先缩略图，进入详情后再请求大图；
- 使用内存与磁盘 cache，服务端提供稳定 cache key（缓存键）、`ETag` 或合理的 `Cache-Control`；
- 页面离开后取消不再可见的请求；
- 根据请求观测和用户设置选择画质，Wi‑Fi / 蜂窝标签只作参考信号；
- 渐进式图片仅在编码格式、解码器和渲染组件均支持时采用。

缩略图和原图要使用可推导或可关联的 cache key，防止列表滚动时重复下载。渐进式传输如果需要多次解码，还会增加 CPU 和内存成本，这时必须同时测量首个可用画面出现时间与完整解码时间。


### 弱网策略：期限、重试、缓存与降级

弱网下的体验，取决于期限、重试、缓存与降级这四件事怎么配置，这一节按这个顺序展开。

#### 各层超时的含义

OkHttp 5.3.0 为 connect、read 和 write 均设置了 10 秒的默认超时，但默认并未配置覆盖整次 `Call` 的总超时（`callTimeout`）。这四项超时各自约束不同的阶段：

- `callTimeout` 在已开始执行的调用内覆盖 DNS、建连、写入、服务端处理、读取和内部恢复。**固定 5.3.0 的异步超时在 `AsyncCall.run()` 才启动，Dispatcher 和 Executor 此前的排队不计入这段 timeout**；`callStart` 总耗时则包含它们。同步 `execute()` 在执行入口启动 timeout。WebSocket 和双工调用只在初始建立阶段应用此总超时。
- `connectTimeout` 只约束新 TCP socket 的连接阶段，DNS 和完整调用在它之外。
- `readTimeout` 约束 socket 与单次读取操作，覆盖不了整个响应体的时间。
- `writeTimeout` 约束写入操作，上传业务的完整截止时间要另行设定。

合理的超时阈值应当依据接口 SLO（服务目标）、用户可容忍的等待上限、请求体大小以及恢复机制来设定。对于交互型接口，需要从业务发起那一刻起计算端到端的总期限，一并约束排队、执行与重试退避——既然 `callTimeout` 只覆盖执行阶段，端到端期限就必须在业务编排层独立控制。此外，调用取消也未必能让底层的同步 DNS 查询等不可中断操作立刻返回；因此，大文件上传更宜采用分片、进度控制与断点续传，长连接与流媒体需围绕心跳或媒体分段（segment）设计超时，而后台同步则应交给 WorkManager 配合网络约束与重试调度。

把弱网 timeout 一律调大，会延长用户等待并占用并发资源；一律调小，则会放大尾部网络上的失败与重试。每类请求都先记录超时发生在哪一段，我们再据此调整对应的那一项。

<!-- gracker-diagram: ch12-01-23-timeout-and-deadline -->
![业务期限、排队与执行期 callTimeout](../../assets/diagrams/ch12/ch12-01-23-timeout-and-deadline.png)

图：从业务发起计算总期限，分别约束排队、执行和退避。 固定5.3.0异步callTimeout在AsyncCall.run才启动，排队不计入；取消不保证同步DNS立刻返回，长连接初始建立另有范围。

#### 失败分类与重试决策

请求失败可以分成几类：

| 失败位置 | 风险 | 处理方向 |
|---|---|---|
| DNS 或尚未发送请求的连接失败 | 服务端大多尚未收到业务请求 | 允许网络库尝试其他地址或路由，并受总期限限制 |
| TLS 证书、主机名或协议校验失败 | 安全配置或中间网络异常 | 停止盲目重试，保留错误分类 |
| 请求体发送后连接中断 | 客户端不知道服务端是否已经执行 | 查询业务状态，或依赖幂等键去重 |
| HTTP 408、429、503 | 服务端可能允许稍后尝试 | 按接口契约和 `Retry-After` 决定 |
| 其他 4xx | 请求、权限或业务状态通常需要修改 | 按响应语义处理 |
| 响应体中途失败 | 已接收部分数据 | 支持 Range / ETag 的下载可续传，其他请求按业务语义恢复 |


执行指数退避时应加入随机抖动（随机延迟），并严格受最大尝试次数、端到端总期限、应用前后台状态以及用户取消动作的约束。若服务端返回了 `Retry-After`（建议的重试时间），应优先遵守；网络恢复瞬间，挂起的请求也需错峰调度，避免并发齐发。

OkHttp 默认开启了 `retryOnConnectionFailure`，会在单次 `Call` 内部自动尝试路由与连接层的故障恢复；此外，重定向、认证和部分特殊响应也会触发库内的后续请求（follow-up）。如果应用层在此之上再叠加业务重试，务必将网络库层的 attempt 与业务层的 attempt 分开计数，防止实际总请求数成倍放大。另外，不要在 Interceptor（拦截器）内部通过线程阻塞来实现退避等待，这会持续占用调度资源；重试编排更适合放在上层请求调度逻辑或 WorkManager 中。

<!-- gracker-diagram: ed12-01-retry-classification-and-attempts -->
![失败先分类，库内尝试与业务重试分别计数](../../assets/diagrams/ch12/ed12-01-retry-classification-and-attempts.png)

图：概念重试编排合图，不是OkHttp内部完整状态机。每次业务attempt中的Call可已有多个route/认证/重定向followup，内外分别计数。按失败位置与业务语义处理：安全校验不盲重试，发送后断链先查结果或服务端幂等；发送前连接失败和408/429/503也需按契约判断。仅确需恢复且允许时，在次数/总期限/幂等/前后台/用户取消约束下遵守RetryAfter并抖动，再发新的Call；不在Interceptor阻塞退避。双轨仅示分层，非时长或次数上限；其他4xx/响应体中断仍按上表恢复。

HTTP 方法的规范语义只是初筛线索：一个声明为 PUT 或 DELETE 的接口，仍可能包含审计、通知或外部系统副作用。支付、订单和发帖等写操作，应由服务端提供幂等键和可查询结果。

#### HTTP cache 与业务离线数据

OkHttp cache 遵守 HTTP 缓存语义。每个磁盘目录只能由一个 `Cache` 实例独占；该实例可由派生 client 共享。目录与容量由拥有者配置，下面函数接收已创建的实例，避免每次调用都对同一目录创建新 cache：

```kotlin
fun withHttpCache(
    base: OkHttpClient,
    sharedCache: Cache,
): OkHttpClient = base.newBuilder()
    .cache(sharedCache)
    .build()
```

<!-- gracker-diagram: ed12-01-shared-client-cache-owner -->
![派生 client 共享连接资源，磁盘 Cache 由唯一 owner 管理](../../assets/diagrams/ch12/ed12-01-shared-client-cache-owner.png)

图：共享资源与磁盘目录所有权合图：固定5.3的newBuilder派生client沿用连接池/Dispatcher，按请求类别配置超时。一个目录只由一个Cache实例独占；派生client可配置同一sharedCache，或继承base已配置实例，并不表示任意独立client自动共享缓存。容量/清理/关闭由owner统一管理，页面只管理自己的Call；共享池不替代完整Address资格、同步并发或服务端stream资源约束。

服务端应正确返回 `Cache-Control`、`ETag`、`Last-Modified` 和 `Vary`。客户端 cache 只保存符合规则的 HTTP 响应；Room、SQLite 或文件层的业务离线数据，要在对应的层里另建。

离线时若产品允许使用已经过期但仍在可接受时限内的 stale 响应，我们可以显式构造只读 cache 请求：

```kotlin
fun offlineRequest(
    url: HttpUrl,
    maxStaleSeconds: Int,
): Request {
    val policy = CacheControl.Builder()
        .onlyIfCached()
        .maxStale(maxStaleSeconds, TimeUnit.SECONDS)
        .build()

    return Request.Builder()
        .url(url)
        .cacheControl(policy)
        .build()
}
```

当本地没有满足条件的缓存时，`onlyIfCached()` 会直接返回由客户端本地生成的 504 响应，不会触发任何网络请求。同时要注意，`maxStale` 并不能绕过服务端下发的 `must-revalidate` 或 `no-cache` 等强制校验指令；而且单凭一个 504 状态码，也无法分辨究竟是“从未缓存”“过期太久”还是“受限于强制重验证”，排查或降级时需借助额外元数据来区分。至于界面上常见的“先展示旧数据、同时后台刷新”交互，则需要另行发起显式网络刷新或依赖业务层离线数据策略，无法靠单次只读缓存请求实现。

<!-- gracker-diagram: ch12-01-27-http-cache-decision -->
![只读缓存、重新验证与本地 504](../../assets/diagrams/ch12/ch12-01-27-http-cache-decision.png)

图：先按HTTP策略判断缓存能否使用，再决定验证或本地失败。 onlyIfCached禁止网络；maxStale不越过must-revalidate/no-cache，单个504分辨不出不存在、过旧或需验证。

#### 弱网降级的依据

弱网降级通常包括回退缓存、降低分辨率、缩小分页大小、暂停自动播放以及延后非交互式同步等。需要明确的是，网络传输类型（transport）本身只是一项提示：同一 Wi‑Fi 可能经过拥塞链路，而蜂窝网络也未必吞吐不佳。因此，降级策略应当综合用户设置、metered、roaming、系统估计以及近期的实际请求观测来做判断，并引入滞回机制——为降级和恢复分别设定不同阈值，避免状态边界抖动导致画质频繁来回切换。


### 平台提供的策略输入

平台侧还提供了两项容易被误用的策略信号。其一是 `SubscriptionInfo.getStreamingAppMaxDownlinkKbps()` 和 `getStreamingAppMaxUplinkKbps()`，它们返回的是运营商为流媒体应用分配的速率上限（未知时返回 `SubscriptionPlan.BITRATE_UNKNOWN`），反映的是分配值而非实时链路测速，直接拿来当测速结果会导致误判。其二是 targetSdk 37 起对局域网访问的权限收敛，相关功能需适配 `ACCESS_LOCAL_NETWORK` 或系统 picker（由系统展示的设备选择器）；一旦权限被拒，应当按授权问题处理，若归入普通弱网故障来排查就会走错方向。局域网权限与网络切换的完整规则见 [1.22 Connectivity 服务、网络选择与回调](../../part1-fundamentals/ch01-architecture/22-connectivity-service.md)。


### 长连接、解析与后台流量

WebSocket 适合高频双向消息，但长连接不会自动省电。固定 ping/pong（心跳请求/响应）、代理或 NAT 空闲超时、网络切换后的重复重连，都可能让蜂窝 radio（无线基带）频繁保持活跃；低频通知优先复用 FCM（Firebase Cloud Messaging）等系统通道，高频业务则要和服务端共同定义心跳、退避、会话恢复和消息去重。

<!-- gracker-diagram: ch12-01-30-heartbeat-radio -->
![长连接心跳、重连与基带活跃](../../assets/diagrams/ch12/ch12-01-30-heartbeat-radio.png)

图：心跳与反复重连会改变无线活跃窗口，应和服务端共同设计恢复。 轨道仅示意可能阶段；tail依RAT、信号、设备与运营商变化，WebSocket不自动保证省电。

使用 Retrofit 的 `suspend` 协程适配器（suspend adapter）不会加快底层协议传输。当 `EventListener` 已显示网络请求结束、业务层却迟迟拿不到数据时，需要继续区分 Converter/JSON 解析、数据库写入和 UI 映射的耗时，并确认协程取消能正确传到 `Call.cancel()`。网络传输、CPU 解析和界面提交应当分别记录 trace，避免把网络完成后的 CPU 时间错算进 TTFB。


日志、遥测和可延迟同步应在应用内合批，交给 WorkManager/JobScheduler 设置网络、电量和充电约束。蜂窝 tail time（请求结束后基带继续活跃的时长）会受设备、RAT（无线接入技术）、信号和运营商配置影响，写死一个固定时长会出错；是否节能要比较唤醒次数、radio 活跃窗口、字节量和任务完成率。

### 监控：EventListener 与 NetworkCallback

前面的策略都要靠数据支撑。这一节我们看客户端的两条观测通道——OkHttp 的 EventListener 与系统的 NetworkCallback——以及怎样用 Perfetto 把网络事件和线程对齐。

#### OkHttp EventListener

当需要维护单次调用内部的阶段状态时，应通过 `EventListener.Factory` 为每个 `Call` 创建独立的 listener 实例。由于事件可能从不同线程回调，且路由竞速事件在时间上可能重叠，回调实现须快速返回、不抛异常、不做阻塞 I/O，也不要重入调用 client。推荐先用非阻塞 `offer` 将事件写入有界队列（队列满时计数丢弃），再由后台消费，防止遥测积压占满内存。

下面的示例记录总耗时与 Dispatcher 排队时间，不采集 URL 或 header：

```kotlin
data class CallMetric(
    val totalMs: Long,
    val queueMs: Long?,
    val failed: Boolean,
)

class CallTimingListener(
    // 必须快速、不阻塞且不抛异常；下面用有界队列的 offer。
    private val emit: (CallMetric) -> Unit,
) : EventListener() {
    private val stateLock = Any()
    private var callStartNs: Long? = null
    private var queueStartNs: Long? = null
    private var queueTotalNs = 0L
    private var queueSeen = false
    private var finished = false

    override fun callStart(call: Call) {
        synchronized(stateLock) { callStartNs = System.nanoTime() }
    }

    override fun dispatcherQueueStart(call: Call, dispatcher: Dispatcher) {
        synchronized(stateLock) {
            queueSeen = true
            queueStartNs = System.nanoTime()
        }
    }

    override fun dispatcherQueueEnd(call: Call, dispatcher: Dispatcher) {
        synchronized(stateLock) {
            queueStartNs?.let { queueTotalNs += System.nanoTime() - it }
            queueStartNs = null
        }
    }

    override fun callEnd(call: Call) = finish(failed = false)

    override fun callFailed(call: Call, ioe: IOException) = finish(failed = true)

    private fun finish(failed: Boolean) {
        val metric = synchronized(stateLock) {
            if (finished) return
            val startNs = callStartNs ?: return
            finished = true
            val endNs = System.nanoTime()
            val activeQueueNs = queueStartNs?.let { endNs - it } ?: 0L
            CallMetric(
                totalMs = TimeUnit.NANOSECONDS.toMillis(endNs - startNs),
                // 观察到的短排队可舍入为 0 ms；没有 queue 事件才是 null。
                queueMs = if (queueSeen) {
                    TimeUnit.NANOSECONDS.toMillis(queueTotalNs + activeQueueNs)
                } else null,
                failed = failed,
            )
        }
        emit(metric)
    }
}

val metricQueue = ArrayBlockingQueue<CallMetric>(1024)
val droppedMetricCount = AtomicLong()
val monitoredClient = OkHttpClient.Builder()
    .eventListenerFactory {
        CallTimingListener { metric ->
            if (!metricQueue.offer(metric)) droppedMetricCount.incrementAndGet()
        }
    }
    .build()
```

<!-- gracker-diagram: ch12-01-32-event-listener-pipeline -->
![每 Call 计时状态与有界遥测队列](../../assets/diagrams/ch12/ch12-01-32-event-listener-pipeline.png)

图：用独立listener维护调用状态，快速入队后由后台批量消费。 事件可跨线程或并行；短排队可舍入0ms，没有事件才为null。队列满时丢弃计数，回调须快速返回，阻塞与抛异常都要避免。

生产环境监控可按同样的方式扩展出 DNS、connect、secure connect、request、response 与 `connectionAcquired`（取得可用连接）等阶段区间（span）。由于重定向和连接恢复会导致 DNS、建连、请求与响应事件重复触发，埋点结构应将它们追加到 attempt 列表中保存；复用现有连接时通常不会产生新的 connect/TLS 事件，不过在 HTTP/2 跨主机连接合并场景下，仍可能先做 DNS 来核对路由。因此，判断请求究竟命中了缓存、复用了连接还是触发了重试，必须靠多个事件联合判断，仅凭某一阶段缺席反推不出唯一原因。此外，`callEnd` 还包含调用方延迟消费响应体的时间，而 HTTP 状态错误、提前关闭和业务解析失败，也无法仅靠示例中的 `failed` 布尔值来识别；业务方仍须按所有权及时关闭返回的响应体或升级流，单纯调用 `Call.cancel()` 并不能替代资源关闭。

指标上传要限制基数——控制字段不同取值的数量——并保护隐私。建议记录经过白名单映射的接口模板、协议、状态码、错误类别和时间分段；完整 URL、query、header、请求体、响应体、Cookie 与 token 都要留在网络性能日志之外。

#### 用 Perfetto 对齐网络与线程

Perfetto 不会自动将 OkHttp 的 `Call` 拆解为 DNS、TLS 和 TTFB 等子阶段。我们可以用 AndroidX Tracing 的异步 slice（时间片段）标出整次逻辑调用，并借助唯一 cookie（关联编号）区分并发的同名请求；各子阶段仍由 `EventListener` 使用单调时钟记录差值，避免受系统墙钟校时影响。需要注意 `System.nanoTime()` 的起点是任意值，0 或负数照样可能是真实读数，未启动状态需另行标记，之后再按 Call、route（路由）和 attempt 关联事件。trace 名称沿用同一套低基数与隐私约束，不写完整 URL、用户 ID、token 或查询参数。

在 Perfetto 中看到主线程处于 `nativePollOnce`，通常仅表明 Looper 正在空闲等待消息。只有当调用栈、线程状态与时间重叠共同指向 `Future.get()`、锁、socket 或协程桥接点时，才能判断 UI 正在等待网络。网络异步 slice 与主线程慢区间重叠只能建立相关性，要补足因果依据，还得依靠贯穿两端的业务 request ID 和同步阻塞对象的调用栈。

<!-- gracker-diagram: ch12-01-33-trace-causality -->
![Perfetto 时间相关性与 UI 等待因果](../../assets/diagrams/ch12/ch12-01-33-trace-causality.png)

图：用Call关联号、异步slice和线程证据一起判断UI为何等待。 网络slice重叠只说明相关；nativePollOnce常是Looper空闲，单独拿来定性网络卡顿会出错。轨道非真实trace。

#### NetworkCallback 的职责范围

`NetworkCallback` 测不了业务 host 的 DNS、TLS 或响应延迟。`INTERNET` 是网络能力声明，`VALIDATED` 是系统公网探测结果，业务请求成功仍取决于目标域名、路由、证书、CDN 和服务端。应用只需把 capability（网络能力）、metered、blocked（是否被系统阻止）、VPN 与网络切换作为请求策略的参考输入；至于回调顺序、每 UID 100 个共享 request/callback 配额、注册生命周期、FullScore（系统内部用于选网的完整评分）和 linger（旧网络短暂保留期）的完整语义，统一见 [1.22 Connectivity 服务、网络选择与回调](../../part1-fundamentals/ch01-architecture/22-connectivity-service.md)。

后台任务若只关心“有网”或“非计费网络”，优先使用 WorkManager/JobScheduler constraint（约束条件）。网络切换后不要统一清空连接池或立即重放全部失败请求；先让网络库处理连接状态，再由业务幂等和退避策略决定恢复。

<!-- gracker-diagram: ed12-01-platform-inputs-and-request-quality -->
![平台状态、速率字段、局域网授权与实际请求质量分开](../../assets/diagrams/ch12/ed12-01-platform-inputs-and-request-quality.png)

图：三类平台输入与真实请求证据合图：NetworkCallback只报告能力/计费/blocked/VPN/切网等状态，INTERNET和VALIDATED不保证目标host成功；第一跳带宽是估计，carrier cap是运营商分配，BITRATEUNKNOWN保留未知，均非请求实时吞吐。仅局域网业务检查target37权限或picker限定范围，拒权按授权问题处理。业务用DNS/TLS/等待与所选层有效字节/明确时间窗验证质量，另记编码/缓存/背压/续传/重试。注册按生命周期注销；切网先由库处理连接，业务恢复再核幂等/期限/抖动，不统一清池或齐发全部失败请求。

### 排查清单

#### 指标

- [ ] 总耗时、排队、DNS、connect、TLS、响应头等待和响应体传输已分开
- [ ] 计时使用单调时钟
- [ ] 重定向、路由回退和重试按 attempt 保存
- [ ] 协议、cache、network、metered 与失败类别进入低基数分组
- [ ] APM 没有记录完整 URL、query、凭证或正文

#### 协议与请求组织

- [ ] OkHttpClient 或 CronetEngine 在进程内复用
- [ ] HTTP/3 指标按协商协议统计，并保留 HTTP/2 回退
- [ ] 0-RTT 只用于可容忍重放的业务
- [ ] 聚合接口与并行请求比较了缓存、部分失败和最早展示时间
- [ ] warmup 有专用 endpoint、命中率和额外流量数据
- [ ] 页面离开后会取消失效请求

#### 弱网

- [ ] 每类接口有总期限和阶段 timeout
- [ ] 重试受幂等、结果未知、`Retry-After`、尝试次数和总期限约束
- [ ] 网络恢复采用抖动，避免请求同步重发
- [ ] HTTP cache 与业务离线数据职责清楚
- [ ] 降级策略结合近期请求观测，带有滞回

#### Android 平台

- [ ] default network callback 在不再使用时注销
- [ ] `INTERNET`、`VALIDATED`、metered、transport 与请求结果没有混用
- [ ] 第一跳带宽估计没有写成实时吞吐
- [ ] Android 17 流媒体 carrier cap（运营商速率上限） 正确处理 `BITRATE_UNKNOWN`
- [ ] target 37 的局域网功能已适配权限或系统 picker


## TLS 握手、证书与安全边界

在基础传输通道之上，TLS 额外引入了密钥协商、证书校验和会话恢复流程。一个 HTTPS 请求在真正发出业务数据前，往往要依次走完 DNS 解析、传输层建连、TLS 握手与证书校验；对于载荷极小的短请求，这些前置准备甚至会占据绝大部分等待时间。因此，优化前必须先把耗时拆分到具体环节，切忌笼统归为“TLS 慢”，更不能靠放宽安全校验来换取表面的延迟下降。

后文会反复出现几个缩写：Encrypted Client Hello（ECH）、Certificate Transparency（CT，证书透明度）；它们与明文流量策略、HPKE 的版本差异都按前文基线核对，版本迭代只保留会影响迁移判断的节点。

### 先把一次安全连接分段

RTT（Round-Trip Time）指报文在网络上往返一次所需的时间。由于网络制式、无线信号质量、运营商路由及服务端部署地域的差异极大，直接用固定毫秒数估算握手耗时并不准确，建议按如下阶段拆解记录一次新建 HTTPS 连接的开销：

| 阶段 | 常见工作 | 观测重点 |
|:---|:---|:---|
| DNS | A/AAAA 查询，分别获取 IPv4/IPv6 地址；ECH 场景还可能读取 DNS HTTPS 资源记录 | 缓存命中、解析器类型、查询并发 |
| 传输层 | TCP 三次握手；QUIC 则把传输参数协商与 TLS 1.3 握手结合 | 新连接比例、IPv4/IPv6 竞速、丢包 |
| TLS | ClientHello（客户端提出的能力与参数）、密钥协商、证书和 Finished（握手完整性确认）消息 | TLS 版本、完整握手或恢复、ECH |
| 证书验证 | 信任链、主机名、有效期、CT 等检查 | 失败类型、证书链、SCT（证书透明度时间戳） |
| HTTP | 发送请求并等待响应头与响应体 | 协议、连接复用、服务端处理 |


HTTP/2 或 HTTP/3 可以让多个请求复用一条连接。复用命中时前四段不会为每个请求重新执行，收益通常大于调整加密算法参数——这也是后面反复出现的主线：先争取复用，再谈参数。

### TLS 1.3 减少了哪些等待

#### 完整握手

在常见的 TLS 1.2 完整握手中，客户端必须先收到服务端的第一轮握手响应，才能发出密钥交换与 Finished 消息，待服务端最终确认后才可发送应用数据，协议层开销通常需要两个网络往返。而在 TLS 1.3 的常见完整握手中，客户端在首个 ClientHello 中便携带了 key share，仅需等待一个 TLS 往返即可发送应用数据。注意这一对比仅度量协议消息往返本身，未计入 TCP 建连、`HelloRetryRequest` 追加的额外往返、丢包重传、客户端排队及服务端处理耗时，因此不宜将其直接折算为固定的百分比或毫秒级收益。

<!-- gracker-diagram: ch12-01-36-tls-full-handshake -->
![TLS 1.2 与 1.3 的常见完整握手等待](../../assets/diagrams/ch12/ch12-01-36-tls-full-handshake.png)

图：比较完整握手中客户端何时能够发送应用数据。 仅常见协议路径：TLS1.2约2个TLS往返、1.3约1个；不含TCP、HRR、丢包或业务处理，固定性能百分比推不出来。

Android 10（API 29）起，平台 TLS 实现默认启用 TLS 1.3；同一版本的 Android 文档也明确，基于 socket 的平台 TLS 1.3 API 不支持 0-RTT。到了 Android 17，应用通过 `SSLSocket`、`SSLEngine` 或依赖平台 provider 的网络库使用 TLS 1.3，仍要以网络库公开的能力和服务端协商结果为准。

#### 连接复用和会话恢复

这三个概念容易混淆：

| 机制 | 是否新建传输层连接 | 是否重新进行 TLS 握手 | 适用时机 |
|:---|:---:|:---:|:---|
| HTTP 连接复用 | 否 | 否 | 原连接仍可用 |
| TLS 会话恢复 | 是 | 是，但使用 PSK（预共享密钥）或缓存的 session state（会话状态）缩短协商 | 原连接已关闭，双方仍保留恢复状态 |
| TLS 1.3 0-RTT | 是 | 恢复握手中提前发送 early data（握手确认前的早期数据） | 网络栈、服务端和业务语义均允许 |


连接复用能否命中，取决于池内是否还有可用连接；池容量与 keep-alive 的默认值见前文「共享 OkHttpClient」。要判断复用有没有发生，我们先统计 `connectionAcquired` 回调、新建连接率、域名数量和服务端空闲超时，再调整 `maxIdleConnections` 与 keep-alive。

TLS 会话恢复则发生在新建传输连接时。即便客户端持有一份看似有效的 session ticket（会话票据），服务端依然可能因为进程重启、用于保护票据的 ticket key 轮换、负载均衡调度到其他节点，或票据本身过期而回退到完整握手。单看客户端 `secureConnectStart`/`secureConnectEnd` 耗时并不能区分是否成功恢复，排查时应结合客户端 TLS 库的连接日志与服务端的 full/resumed handshake（完整/恢复握手）指标共同印证。

<!-- gracker-diagram: ch12-01-38-session-ticket-lifetime -->
![会话票据可用性与完整握手回退](../../assets/diagrams/ch12/ch12-01-38-session-ticket-lifetime.png)

图：客户端持有票据与服务端实际接受恢复是两个条件。 过期、重启、密钥轮换或负载均衡可能使恢复不可用；secureConnect时长本身证明不了是否恢复。

#### 0-RTT 与可重放风险

前文提到过 early data 存在重放风险，从安全边界上还需要进一步明确判断标准。RFC 8446 要求由应用层协议来评估请求被重复执行的后果，HTTP 方法名本身不足以充当准入依据：一个 GET 请求同样可能消耗一次性令牌、修改服务端计数器或读取具有时序约束的敏感数据，而某些 POST 请求如果携带了业务幂等键，反而在服务端具备去重能力。因此，0-RTT 的安全准入条件应界定为“该请求即便被重放也不会带来不可接受的业务后果”，仅靠一份简单的 GET/HEAD 白名单并不可靠。

<!-- gracker-diagram: ed12-01-zero-rtt-eligibility-and-rejection -->
![0-RTT 先审业务资格，再记录接受或拒绝后的恢复](../../assets/diagrams/ch12/ed12-01-zero-rtt-eligibility-and-rejection.png)

图：恢复机制与安全门槛合图：需具体provider/协议/服务端支持及可用PSK/恢复状态，且重复执行后果、鉴权材料和服务器保护允许，才发送earlydata。不满足则等正常握手；发送后服务端仍可接受或拒绝，接受不等握手已完成或业务成功，拒绝后按栈/业务语义恢复并受总期限约束。GET/HEAD或客户端幂等键不是重放安全证明，去重须服务端实现；仅PSK保护的0RTT无前向保密，后续握手的安全保证要在握好后另算。

OkHttp 5.3 的稳定公开协议配置没有 HTTP/3 或 TLS early-data 开关；平台 `HttpEngine` 的 QUIC hint（提示某个主机可尝试 QUIC） 也证明不了某个请求已经用上 early data。Cronet 侧 `QuicOptions.Builder.enableTlsZeroRtt()` 与跨进程会话恢复的配置面，已在前文「0-RTT 的边界」列出。启用前应确认以下事项：

- 网络库版本和具体传输协议支持 0-RTT；
- 服务端具备重放（replay）防护，并能区分 early data；
- 请求语义允许重放，鉴权材料也允许在 early data 中发送；
- 指标能区分普通恢复、0-RTT 被接受和 0-RTT 被拒绝后重发。

### 网络安全能力的版本演进

| 版本 | 已核对的平台变化 | 迁移含义 |
|:---|:---|:---|
| Android 6.0 / API 23 | `android:usesCleartextTraffic` 与 `NetworkSecurityPolicy` 进入平台 | 应用可声明和查询明文策略 |
| Android 7.0 / API 24 | Network Security Configuration（网络安全配置）上线 | 可按域名配置明文、信任锚（证书验证的信任起点）、调试证书和证书固定 |
| Android 9 / API 28 | targetSdk 28 及以上默认不允许明文流量 | 旧应用升级 targetSdk 时要检查 HTTP 端点 |
| Android 10 / API 29 | 平台 TLS 1.3 默认启用；平台 TLS socket 不支持 0-RTT | TLS 版本与 early data 能力要分别判断 |
| Android 15 / API 35 | 新增 `android.crypto.hpke.HpkeSpi` | provider 实现层获得标准 SPI（Service Provider Interface，服务提供者接口） |
| Android 16 / API 36 | 应用可在 Network Security Configuration 中选择启用 CT | 升级 targetSdk 37 前可先做兼容性验证 |
| Android 17 / API 37 | ECH 进入平台网络安全配置；targetSdk 37 及以上默认启用 CT；新增应用层 HPKE API | 同时核对运行系统、targetSdk、网络库和服务端 |

Android 的 Java TLS 路径由 Conscrypt 等安全 provider 实现，底层使用 BoringSSL。模块化更新能让部分实现随 Google Play 系统更新交付，但设备、模块版本和厂商支持仍存在差异；因此定位问题时不能只笼统记录“Android 17”，诊断报告应同时写明设备的 build fingerprint（用于定位系统镜像版本的构建指纹）、安全 provider 名称及其实际版本。


### Android 17 的 Encrypted Client Hello（ECH，加密客户端问候）

在常规 TLS 握手中，明文发送的 ClientHello 会暴露 SNI（Server Name Indication，通常即目标主机名）等元数据。ECH（RFC 9849）将这些敏感参数封装进加密的内层 ClientHello（inner ClientHello）中，外层仅保留完成路由转发和协议兼容协商所需的信息，从而对链路上的被动观察者隐藏真实连接参数。不过，最终终止 TLS 握手的服务器依然能解密读取真实参数；同时链路观察者仍可通过目标 IP、流量形态以及 DNS 查询推断部分元数据——ECH 保护的是 ClientHello 载荷本身，并不能抹去整个访问行为的痕迹。

#### 四个生效条件

当前官方文档公开的 `<domainEncryption>` 模式仅列出 `enabled` 与 `disabled`，并把 Android 17 上 `targetSdk >= 37` 的默认值写成 `enabled`。但在固定 `r1` 源码快照中，默认策略存在如下差异：

在固定 `r1` 源码中，`NetworkSecurityConfig.defaultDomainEncryptionMode()` 仅在对应兼容性变更与 feature flag 同时开启时才返回内部状态 `OPPORTUNISTIC`，否则返回 `DISABLED`；而 `SSLParametersImpl` 对 `OPPORTUNISTIC` 模式会设置 `enableGrease=false`。只有当应用在 XML 中显式声明 `mode="enabled"` 时，才会映射为内部 `ENABLED` 模式，从而在缺乏 ECHConfig 时发送 GREASE 占位扩展。因此，仅凭“Android 17 且 targetSdk 37”尚不能保证设备默认一定会发送 GREASE，实际行为需结合 Conscrypt 模块版本、生效策略与连接日志核实；同时也要区分这些内部枚举值与 XML 公开属性值的对应关系。[来源：固定 r1 默认策略](https://android.googlesource.com/platform/external/conscrypt/+/refs/tags/android-17.0.0_r1/nsc/src/android/security/net/config/NetworkSecurityConfig.java)、[当前配置文档](https://developer.android.com/privacy-and-security/security-config)。

<!-- gracker-diagram: ch12-01-42-ech-default-version-difference -->
![ECH 当前文档与固定 r1 默认策略差异](../../assets/diagrams/ch12/ch12-01-42-ech-default-version-difference.png)

图：明确记录文档默认enabled与r1内部OPPORTUNISTIC的不同分支。 固定源码默认需兼容性变更和flag开启；OPPORTUNISTIC不发GREASE，显式XML enabled才映射ENABLED，两者要分开承诺。

一次连接真正使用 ECH，还要同时满足：

1. 应用使用的网络库已经接入 Android ECH 能力；
2. DNS 或网络库获得了服务端可用的 ECHConfig，即包含服务端公钥和算法参数的 ECH 配置；
3. 负责终止 TLS、实际完成握手的 CDN、代理或服务节点支持对应配置；
4. 当前连接路径没有绕过平台网络安全策略，例如没有改用完全自管且不读取该策略的网络栈。

<!-- gracker-diagram: ch12-01-41-ech-inner-outer -->
![ECH 配置、内外 ClientHello 与可见信息](../../assets/diagrams/ch12/ch12-01-41-ech-inner-outer.png)

图：可用配置、已接入的库和实际TLS终止点共同完成ECH。 ECH保护路径观察者看到的敏感Hello内容；终止TLS的服务端可解密，目标IP与流量形态仍可见。

按照官方文档对 `enabled` 模式的定义，若获取到可用的 ECHConfig 则要求使用 ECH，若无可用配置则会发送 ECH GREASE 占位扩展（用于促使中间网络设备适应 ECH 报文格式，防止因协议字段僵化而阻碍后续升级）；`disabled` 模式则既不启用 ECH，也不发送 GREASE。抓包或统计时要留意：GREASE 仅仅是占位扩展，证明不了真实 SNI 已被 ECH 加密，因此应将无配置下的“携带 ECH 扩展”单独归类，切勿统计成真实的 ECH 成功。日常开发中，应用通常无需手动解析或安装 ECHConfig，交给已集成平台 ECH 能力的网络库处理即可。

AOSP `android-17.0.0_r1` 中，Conscrypt 的接法是：`SSLParametersImpl.getEchOptions()` 根据网络安全策略生成 ECH 选项，`Platform` 把配置不匹配包装为 `android.net.ssl.EchConfigMismatchException`，其中可携带服务端返回的重试配置。所以 ECH 失败后会不会静默改用普通 TLS 并没有统一答案：网络库可能按重试配置重连，也可能直接把异常交给调用者。

<!-- gracker-diagram: ch12-01-43-ech-grease-and-retry -->
![ECH、GREASE 与配置不匹配后的处理](../../assets/diagrams/ch12/ch12-01-43-ech-grease-and-retry.png)

图：区分真实ECH、无配置占位与失败后的库层处理。 图以显式enabled语义为例；GREASE不加密真实SNI，异常可能携带retry配置，但不承诺静默普通TLS回退。

#### ECH 性能的分段测量

ECHConfig 通常通过 DNS 的 HTTPS 资源记录（携带服务端配置参数的一类记录）分发。引入这类查询是否会额外增加网络等待，取决于 DNS 缓存命中情况、解析器是否并行发送 A/AAAA 与 HTTPS 查询、加密 DNS 连接能否复用以及网络库自身的解析流程，因此必须分段实测，简单按“ECH 增加一次 DNS RTT”来估算往往会失真。

ClientHello 加密使用 HPKE。客户端只在新 TLS 握手中执行相关密码运算，已建立连接上的 HTTP 请求不会重复执行。评估时把下面几项分开记：

- HTTPS 资源记录的缓存命中和查询时长；
- 有 ECHConfig、仅 GREASE、配置不匹配三类连接；
- 完整握手、会话恢复和连接复用比例；
- 同一设备、同一网络条件下的 CPU 时间与握手墙钟时间，即用户实际等待的经过时间。


### Android 17 的 Certificate Transparency（CT，证书透明度）

再来看证书这一侧。CA（Certificate Authority，证书颁发机构）签名和系统信任链只能证明证书能追溯到受信任根。CT 通过公开日志和 Signed Certificate Timestamp（SCT，签名证书时间戳）留下可供审计的签发记录，用于发现误签或恶意签发。

#### CT 默认值的决定条件

Android 16（API 36）开始支持应用在配置中选择启用 CT；而当应用运行在 Android 17 且 `targetSdk >= 37` 时，平台会默认启用 CT 验证。排查时需同时核对系统版本与 `targetSdk` 两个条件：同一个 APK 跑在旧系统上拿不到 Android 17 提供的平台 CT 校验，而 `targetSdk` 低于 37 的应用即便运行在 Android 17 上，默认也并未开启 CT。

Network Security Configuration 的规则还包含一个容易遗漏的分支：

1. 当前配置显式设置 CT `true` 或 `false` 时，采用该值；
2. 否则，当前配置的任一信任锚条目为 `user` 或应用资源证书（如 `@raw/...`）时，关闭该配置的 CT 要求；
3. 否则递归继承上层；没有上层时再根据运行实现、flag 与 targetSdk 兼容性规则取默认值。

私有 PKI 与抓包调试配置常常落入第二种情况。这里要注意，平台判定是否关闭 CT 的单位是“域名匹配到的整条配置”，而不仅仅是本次证书链最后选中的那张根证书。如果同一条配置里同时列出了 `system` 与 `user`/资源证书，它仍可能整体关闭 CT 要求；只有把公网与私网配置彻底隔离并实测验证后，才能确定哪类连接执行了 CT。若业务确需让自定义信任锚也执行 CT，应显式配置并验证证书签发流程，公网证书的经验在这里替代不了测试。

<!-- gracker-diagram: ch12-01-45-ct-config-precedence -->
![CT 要求的配置优先级](../../assets/diagrams/ch12/ch12-01-45-ct-config-precedence.png)

图：逐层计算当前匹配配置是否要求CT，包含显式false与自定义锚。 判断单位是配置，不是本次选中的链根；任一user/资源锚可关闭未显式设置的当前配置CT。

#### Android CT Policy 的判定条件

策略会按 SCT 交付方式、证书有效期、日志状态和日志运营者判断：

| SCT 交付方式 | Android CT Policy 的检查要点 |
|:---|:---|
| 嵌入证书 | 至少 1 个来自检查时 Qualified / Usable / ReadOnly 日志；计数集合可包含检查时 Qualified / Usable / ReadOnly / Retired 的不同日志，有效期≤180天需要2个，>180天需要3个；计数集合至少覆盖2个运营者。Retired 日志的 SCT 还须满足退休时间约束 |
| OCSP stapling（服务端在握手中附带证书状态响应）或 TLS 扩展 | 至少 2 个 SCT 来自检查时合格的不同日志，并覆盖至少 2 个日志运营者 |


需要注意的是，日志状态与 Android CT log list 会随时间变化。按照当前 Android CT Policy，如果设备没有可用日志表，或现有日志表的时间戳距今超过 70 天，系统将暂停 CT 强制执行（基础的证书链与主机名验证仍照常执行）。因此，“配置要求 CT”只是前提，长期离线设备当下有没有实际执行验证还需单独确认；此外，日志运营者按 SCT 签发时的归属判断，当前名称作不得准。证书部署流程应以当前 Android CT Policy 和预发布设备测试为准，避免把上表中的数字固化成多年不变的服务端规则。

<!-- gracker-diagram: ch12-01-46-ct-enforcement-loglist -->
![CT 配置要求与实际强制执行](../../assets/diagrams/ch12/ch12-01-46-ct-enforcement-loglist.png)

图：把配置要求、可用日志表与证书政策检查分开。 当前Android政策：日志表不可用或时间戳超过70天暂停CT强制；基础信任链与主机名校验继续。

CT 校验通常直接利用握手携带的证书、OCSP 响应或 TLS 扩展在本地完成，因此它一般不会带来额外的实时网络请求。在向 `targetSdk 37` 迁移放量的过程中，线上更常见的风险反而是握手直接失败——例如 SCT 缺失、日志状态不满足政策或证书链发送错误；这时客户端要保留异常类型、域名、系统版本和证书摘要，服务端则要密切监控 `targetSdk 37` 分批放量期间的 TLS 失败率。

### 明文策略、信任锚和证书链

#### 明文默认值

从 Android 7.0 开始，应用可以通过 Network Security Configuration 按域名管理明文流量和信任锚。对于普通的远端目标域名，`targetSdk >= 28` 时 `cleartextTrafficPermitted` 的默认值为 `false`，`targetSdk <= 27` 时则默认为 `true`。到了 Android 17，平台还为未显式配置的 `localhost` / loopback 地址补充了一条隐式配置（在固定 `r1` 中受相应实现 flag 约束）：默认允许明文传输、不执行 CT/pinning，信任锚继承 `base-config`；不过这条隐式配置的范围就到 `localhost` / loopback 为止，换到其他局域网主机仍要另行判断。此外，第三方或 native 网络实现未必会遵守平台明文策略，网络库是否查询 `NetworkSecurityPolicy` 还需核对对应源码。

从 HTTP 迁移时，客户端应直接配置 HTTPS URL。先访问 HTTP 再跟随 301/302 会多一次明文请求、一次服务端响应和一条新的 HTTPS 连接路径，还会在重定向前暴露请求元数据。WebView 的 mixed content（HTTPS 页面加载 HTTP 资源） 策略是另一组配置，不要拿普通 API 客户端的明文策略去推 WebView 行为。


#### 证书链与证书固定

TLS 服务端应发送叶子证书（直接签发给目标域名的证书）和客户端建立信任链所需的中间证书，通常不发送根证书，也不发送无关中间证书。证书数据会进入握手字节数；在带宽低、丢包高的网络上，过大的握手更容易跨越多个传输包并触发重传。判断“过长”要看实际链路字节和兼容性，没有固定的层数标准。

Network Security Configuration 支持 certificate pinning（证书公钥固定），但 Android 官方文档不建议一般应用把 pinning 当作默认方案：服务端证书或 CA 轮换处理不当会使应用失联。如果威胁模型（需要防范的攻击和采用的信任假设）要求使用 pinning，就要准备 backup pin（备用公钥摘要）、合理的失效时间、证书轮换演练和可用的轮换与恢复渠道；如果恢复配置也只能从已经被错误 pin 拦住的同一入口下载，远端开关就救不回来。删除证书校验、信任所有证书或放宽主机名校验，都不属于性能优化。


### API 35 与 API 37 的 HPKE 位于不同接口层

Hybrid Public Key Encryption（HPKE，混合公钥加密，RFC 9180）把 KEM（密钥封装机制）、KDF（密钥派生函数） 和 AEAD（带关联数据的认证加密） 组合成标准公钥加密方案。它适合用接收方公钥加密较短的消息或会话材料，但不替代 HTTPS 的身份验证、连接管理和传输协议。

Android 的 API 演进分为两步：

- Android 15 / API 35 新增 `android.crypto.hpke.HpkeSpi`。它是安全 provider 实现 HPKE 引擎的 SPI，供加密服务实现者接入平台；对应用开发者来说它不是日常加密入口。
- Android 17 / API 37 新增 `Hpke`、`Sender`、`Recipient`、`Message` 及参数规范。`Hpke.getInstance()` 用于获取实例，`seal()`/`open()` 是 one-shot（单次调用完成一次加密或解密） 操作；`Sender`/`Recipient` 面向需要在同一上下文中处理多条消息的场景。

当前 Android 文档标明平台 HPKE 只支持 RFC 9180 的 base mode（基本模式）：它用接收方公钥建立加密上下文，发送方身份则不在认证范围内。业务要求发送方认证时，应在协议层增加经过审计的签名或身份绑定设计——“使用接收方公钥加密”本身当不了双向身份认证。

ECH 协议内部也使用 HPKE 加密 inner ClientHello，但应用不需要调用 `android.crypto.hpke.Hpke` 来实现 ECH；自行用应用层 HPKE 包裹 HTTP payload（业务载荷），也得不到 ECH 对 ClientHello 元数据的保护。

<!-- gracker-diagram: ch12-01-50-hpke-api-layers -->
![HPKE 组成、API 层与 ECH 的分工](../../assets/diagrams/ch12/ch12-01-50-hpke-api-layers.png)

图：区分provider SPI、应用加密入口与TLS内部ECH。 Android当前只支持base mode：接收方公钥加密不认证发送方；应用payload加密保护的是业务载荷，覆盖不到ClientHello，也顶替不了HTTPS。

### 加密 DNS 与 ECH 的关系

Android 9 引入 Private DNS 的 DNS over TLS（DoT）设置。AOSP `android-17.0.0_r1` 的 DnsResolver `PrivateDnsConfiguration.cpp` 同时包含 DoT 与 DoH（DNS over HTTPS，通过 HTTPS 加密传输的 DNS）的配置和查询路径。DoT/DoH 保护客户端到解析器之间的 DNS 传输，ECH 保护 TLS ClientHello 中的敏感字段，两者处理的是不同的泄露面：

- 只有 DoT/DoH：能够观察链路流量的第三方不易读取 DNS 查询内容，但普通 TLS SNI（Server Name Indication，服务器名称指示，通常包含目标主机名） 仍可能暴露目标域名；
- 只有 ECH：ClientHello 的敏感字段被保护，但明文 DNS 仍可能暴露查询；
- 两者均启用：目标 IP、包长、时序和连接频率仍然可见。

DoH 首次查询的成本取决于已有 HTTP/2/HTTP/3 连接、DNS 缓存、连接竞速（并行尝试多个地址或协议）和解析器实现，并不固定增加一个 RTT。应用层自定义 DNS 还可能绕过系统 Private DNS、HTTPS 记录处理，以及网络切换后的缓存和重新解析规则，采用前要评估这些副作用。

<!-- gracker-diagram: ch12-01-51-dns-ech-privacy -->
![加密 DNS 与 ECH 的隐私边界](../../assets/diagrams/ch12/ch12-01-51-dns-ech-privacy.png)

图：按DNS传输、Hello内容和流量元数据分别说明保护范围。 DoT/DoH只保护客户端到解析器的传输；两者都有仍可见IP、包长和时序，DoH成本不固定增加一次RTT。

### 客户端与服务端的性能证据

#### 客户端事件

OkHttp `EventListener` 可记录 `dnsStart`/`dnsEnd`、`connectStart`、`secureConnectStart`/`secureConnectEnd`、`connectionAcquired`、库读到响应头后触发的 `responseHeadersStart` 和失败回调。这些时间点能回答“时间花在哪一段”；至于会话有没有恢复、ECH 有没有被接受、CT 的某条规则有没有命中，还要靠更多信号。

前文已经说明 Perfetto 不会自动生成 OkHttp 的阶段轨道。要把网络阶段与线程、CPU、蜂窝 radio 和进程状态对齐，仍应在网络回调中加入应用 trace slice（表示一段持续时间的追踪区间）；协议层的情况要靠 Cronet NetLog（Cronet 网络事件日志）、平台网络日志和服务端 TLS 指标补齐。生产日志不要记录会话密钥、完整证书、鉴权头或用户请求内容。

#### 服务端指标

服务端至少应能按应用版本和灰度发布批次（分批放量的用户组）观察：

- TLS 版本、cipher suite（加密套件）、ALPN（Application-Layer Protocol Negotiation，应用层协议协商）与完整/恢复握手比例；
- HTTP/2、HTTP/3 连接比例和 0-RTT 接受/拒绝情况；
- ECH 接受、GREASE、配置不匹配和重试；
- 证书链版本、SCT 交付方式与 TLS alert（TLS 协议错误通知）；
- 新连接率、连接寿命、空闲超时和负载均衡节点切换。

客户端和服务端的时间基准可能不同。分析单次请求时，我们用贯穿两端的 request ID 关联两端事件；比较分布时，使用同一网络类型、同一设备组和同一发布阶段，避免把用户构成变化误判为协议收益。

<!-- gracker-diagram: ed12-01-cdn-protocol-joint-evidence -->
![关联客户端、CDN 与服务端证据后再解释性能](../../assets/diagrams/ch12/ed12-01-cdn-protocol-joint-evidence.png)

图：CDN与TLS协议诊断共用同一关联方法：客户端单调事件、CDN白名单POP/cache/回源与服务端trace/协议日志按requestID关联，再在同网络/地区/设备/发布组比较延迟和失败分布。单个TTFB分摊不了CDN与源站，secureConnect耗时也证明不了会话恢复、ECH或CT结果；跨端不同墙钟不直接相减。字段保持低基数和白名单，不记录完整URLquery、凭证、正文、密钥或用户标识。

#### 排查对照表

| 现象 | 优先核对 | 常见误判 |
|:---|:---|:---|
| 同一域名频繁出现 `secureConnectStart` | 客户端实例是否复用、服务端 keep-alive、网络切换、连接失败 | 直接增大空闲连接上限 |
| 首次请求慢，后续请求正常 | DNS 缓存、新连接、完整 TLS 握手，以及首次访问触发的服务端初始化或缓存未命中 | 把整段都归为证书验证 |
| targetSdk 37 分批发布后 TLS 失败增加 | Android 17 设备占比、CT Policy、SCT 与自定义信任锚 | 关闭全部证书校验 |
| Android 17 上 ECH 连接失败 | 网络库是否接入、HTTPS 记录、ECHConfig 更新、`EchConfigMismatchException` | 假定平台总会静默降级 |
| 开启 DoH 后解析变慢 | DoH 连接复用、缓存、解析器地域、网络切换 | 固定认为多一个 RTT |
| HPKE 解密失败 | suite（算法组合）、info（上下文信息）、AAD（参与认证但不加密的附加数据）、密钥格式和 base mode 边界 | 把 HPKE 当作 TLS 会话 |


## 版本与实现基线

| 版本 | 相关变化 |
|---|---|
| Android 8 / API 26 | 范围下界；`onAvailable()` 后的 capabilities（网络能力）与 link properties（链路属性）callback 顺序得到公开保证 |
| Android 11 / API 30 | 平台改进 5G 场景的带宽估计；返回值仍是第一跳估计 |
| Android 17 / API 37 | `SubscriptionInfo` 增加流媒体分配速率；target 37 的局域网访问受 `ACCESS_LOCAL_NETWORK` 约束 |
| OkHttp 5.3.0 | 客户端锚点；共享 client、fast fallback、EventListener 排队事件与默认 timeout（超时）口径以此版本为准 |
| Cronet 18.0.1 | Play services Cronet 接入锚点；provider 可用性和协议协商需要在运行时观测 |


## 与其他部分的关联

- **前文「DNS、连接、传输与应用处理」**：连接池、缓存、HTTP/2、HTTP/3 与 OkHttp 事件决定新连接出现的频率并提供分段指标。
- **§12.2 netd 与 DnsResolver**：系统 DNS、Private DNS、HTTPS 资源记录与每网络解析状态。
- **§1.2 版本演进**：适合核对 targetSdk 与运行系统共同改变行为的案例。


## 参考资料

- [Read network state](https://developer.android.com/develop/connectivity/network-ops/reading-network-state)
- [`ConnectivityManager`](https://developer.android.com/reference/android/net/ConnectivityManager)
- [`ConnectivityManager.NetworkCallback`](https://developer.android.com/reference/android/net/ConnectivityManager.NetworkCallback)
- [`NetworkCapabilities`](https://developer.android.com/reference/android/net/NetworkCapabilities)
- [OkHttp 5.3.0 README](https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/README.md)
- [OkHttp 5.3.0 `OkHttpClient.kt`](https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/OkHttpClient.kt)
- [OkHttp 5.3.0 `EventListener.kt`](https://github.com/lysine-dev/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/EventListener.kt)
- [Perform network operations using Cronet](https://developer.android.com/develop/connectivity/cronet)
- [Send a simple Cronet request](https://developer.android.com/develop/connectivity/cronet/start)
- [`CronetEngine.Builder`](https://developer.android.com/develop/connectivity/cronet/reference/org/chromium/net/CronetEngine.Builder)
- [`QuicOptions.Builder`](https://developer.android.com/develop/connectivity/cronet/reference/org/chromium/net/QuicOptions.Builder)
- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)
- [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114)
- [RFC 9000: QUIC](https://www.rfc-editor.org/rfc/rfc9000)
- [RFC 9001: Using TLS to Secure QUIC](https://www.rfc-editor.org/rfc/rfc9001)
- [`SubscriptionInfo`](https://developer.android.com/reference/android/telephony/SubscriptionInfo)
- [Android 17 local network permission](https://developer.android.com/privacy-and-security/local-network-permission)

- [Android 17 behavior changes](https://developer.android.com/about/versions/17/behavior-changes-17)：ECH 与 targetSdk 37 的 CT 默认行为。
- [Network Security Configuration](https://developer.android.com/privacy-and-security/security-config)：明文、信任锚、CT、ECH 和证书固定配置。
- [Android Certificate Transparency Policy](https://developer.android.com/privacy-and-security/certificate-transparency-policy)：SCT 数量、日志状态和运营者要求。
- [Android 10 TLS 1.3](https://developer.android.com/about/versions/10/features#tls-1.3)：TLS 1.3 默认启用及平台 0-RTT 边界。
- [Android HPKE package](https://developer.android.com/reference/android/crypto/hpke/package-summary)、[Hpke](https://developer.android.com/reference/android/crypto/hpke/Hpke) 与 [HpkeSpi](https://developer.android.com/reference/android/crypto/hpke/HpkeSpi)：API 35/37 的接口层次与 base mode 限制。
- [AOSP Conscrypt `SSLParametersImpl.java`](https://android.googlesource.com/platform/external/conscrypt/+/android-17.0.0_r1/common/src/main/java/org/conscrypt/SSLParametersImpl.java) 与 [`Platform.java`](https://android.googlesource.com/platform/external/conscrypt/+/android-17.0.0_r1/platform/src/main/java/org/conscrypt/Platform.java)：Android 17 ECH 策略映射与配置不匹配异常。
- [AOSP DnsResolver `PrivateDnsConfiguration.cpp`](https://android.googlesource.com/platform/packages/modules/DnsResolver/+/android-17.0.0_r1/PrivateDnsConfiguration.cpp)：Android 17 DoT/DoH 实现锚点。
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)、[RFC 9180: HPKE](https://www.rfc-editor.org/rfc/rfc9180)、[RFC 9849: ECH](https://www.rfc-editor.org/rfc/rfc9849)。
- [OkHttp 5.3 `ConnectionPool.kt`](https://github.com/square/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/ConnectionPool.kt) 与 [`EventListener.kt`](https://github.com/square/okhttp/blob/parent-5.3.0/okhttp/src/commonJvmAndroid/kotlin/okhttp3/EventListener.kt)：连接池默认值和客户端事件边界。
- [Cronet `QuicOptions.Builder`](https://developer.android.com/develop/connectivity/cronet/reference/org/chromium/net/QuicOptions.Builder.html)：QUIC/TLS 0-RTT 的实验性配置面。
- [固定5.3.0 RealCall](https://github.com/lysine-dev/okhttp/blob/0960b47ec28a02e893499d2a7e53bf462a62875e/okhttp/src/commonJvmAndroid/kotlin/okhttp3/internal/connection/RealCall.kt)、[Dispatcher](https://github.com/lysine-dev/okhttp/blob/0960b47ec28a02e893499d2a7e53bf462a62875e/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Dispatcher.kt)、[Cache](https://github.com/lysine-dev/okhttp/blob/0960b47ec28a02e893499d2a7e53bf462a62875e/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Cache.kt)：[来源] 异步超时起点、排队与缓存目录所有权。
- [固定r1 NetworkSecurityConfig](https://android.googlesource.com/platform/external/conscrypt/+/refs/tags/android-17.0.0_r1/nsc/src/android/security/net/config/NetworkSecurityConfig.java)、[XmlConfigSource](https://android.googlesource.com/platform/external/conscrypt/+/refs/tags/android-17.0.0_r1/nsc/src/android/security/net/config/XmlConfigSource.java)：[来源] ECH默认值差异和CT配置优先级。
- [RFC 9204：QPACK](https://www.rfc-editor.org/rfc/rfc9204)、[RFC 9111：HTTP缓存](https://www.rfc-editor.org/rfc/rfc9111)：[来源] 跨流头部阻塞与缓存验证规则。

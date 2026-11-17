---
title: SystemUI 性能分析
chapter: '7.4'
section: '7.4'
status: finalized
applicable_versions: Android 12 (API 31) - Android 17 (API 37)
tags:
- systemui
- jank
- launcher
- statusbar
- navigationbar
- notification-shade
- perfetto
related_chapters:
- '2.3'
- '2.4'
- '7.1'
- '7.2'
- '14.2'
confidence: medium-high
last_verified: '2026-10-23'
last_verified_against: 'AOSP android-17.0.0_r1 SystemUI/WM Shell/Launcher3 anchors: systemui.aconfig; super_notification_shade.xml / scene_window_root.xml; ShadeViewProviderModule / ShadeWindowLayoutParams / NotificationShadeWindowView; SceneContainerFlag / SceneContainerFrameworkModule / SceneWindowRootViewBinder; NotificationStackScrollLayout / NotificationRowContentBinderImpl / BigPictureIconManager / notification icon binder; StatusBarWindowControllerImpl / NavigationBar / NavigationBarView / DisplayBackGestureHandler / EdgeBackGestureHandler / SysUIConcurrencyModule / DisplayContent; Transitions / StartingWindowController / RecentsView; Android notification, SplashScreen and aconfig official docs checked 2026-08-19. Additional diagram/source audit rechecked 2026-10-23: RemoteViews/AsyncTask/SceneTransitionLatencyMonitor and SQL wall-clock boundaries.'
last_rework_at: '2026-08-19T13:51:21+08:00'
sources:
- type: aosp
  path: frameworks/base/packages/SystemUI/aconfig/systemui.aconfig
- type: aosp
  path: frameworks/base/packages/SystemUI/res/layout/super_notification_shade.xml
- type: aosp
  path: frameworks/base/packages/SystemUI/res/layout/scene_window_root.xml
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/shade/ShadeViewProviderModule.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/shade/ShadeWindowLayoutParams.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/shade/NotificationShadeWindowView.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/stack/NotificationStackScrollLayout.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/collection/NotifInflaterImpl.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/collection/inflation/NotificationRowBinderImpl.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/row/NotificationRowContentBinderImpl.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/row/BigPictureIconManager.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/icon/ui/viewmodel/NotificationIconContainerStatusBarViewModel.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/notification/icon/ui/viewbinder/NotificationIconContainerStatusBarViewBinder.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/phone/ui/StatusBarIconControllerImpl.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/statusbar/window/StatusBarWindowControllerImpl.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/views/NavigationBar.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/views/NavigationBarView.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/DisplayBackGestureHandler.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/EdgeBackGestureHandler.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/util/concurrency/SysUIConcurrencyModule.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/scene/shared/flag/SceneContainerFlag.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/scene/SceneContainerFrameworkModule.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/scene/ui/view/SceneWindowRootViewBinder.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/compose/features/src/com/android/systemui/scene/ui/composable/SceneContainer.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/compose/scene/src/com/android/compose/animation/scene/SceneTransitionLayout.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/compose/scene/src/com/android/compose/animation/scene/reveal/ContainerReveal.kt
- type: aosp
  path: frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java
- type: aosp
  path: frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/startingsurface/StartingWindowController.java
- type: aosp
  path: frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/transition/Transitions.java
- type: aosp
  path: packages/apps/Launcher3/quickstep/src/com/android/quickstep/views/RecentsView.java
- type: official
  path: https://source.android.com/docs/setup/build/feature-flagging/flip-a-flag
- type: official
  path: https://developer.android.com/develop/ui/views/notifications
- type: official
  path: https://developer.android.com/develop/ui/views/launch/splash-screen
---

# SystemUI 性能分析

普通 App 卡顿时，受影响的画面往往局限在单个任务窗口内；而 SystemUI 负责的状态栏、通知抽屉、锁屏和导航栏覆盖面大得多，同一段阻塞还经常与 Launcher（桌面与最近任务组件）、WM Shell（窗口管理的交互与动画组件）以及目标 App 自身的动画交织在一起。如果只盯着 `com.android.systemui` 的主线程，很容易分不清窗口由谁创建、工作落在哪条线程、最终画面何时呈现。要理清这些归属，需要把版本开关、窗口拓扑、通知绑定管线以及整屏合成逐层拆开来看。

> 源码基线：AOSP `android-17.0.0_r1`；内核 `android17-6.18-2026-06_r6`。版本差异的讨论以 Android 12—16 的演进为参照，现行结论统一取 Android 17 / API 37。

同一份 SystemUI 代码中，legacy shade（传统通知面板）与 SceneContainer（基于场景切换的新容器）两条路径并存，状态栏、通知抽屉、返回手势还各自配有专用 UI 线程开关。动手分析前，应先把目标构建的 flag（功能开关）、窗口列表与线程列表记录下来——设备实际跑在哪条路径上由这些运行时记录决定，仅凭系统版本号无法判断。

## 版本、flag、窗口和线程

分析 SystemUI 的第一步是确认目标设备实际启用了哪条实现路径，它的运行时结构无法用单一固定架构图概括：`scene_container`、`dual_shade`、`status_bar_for_desktop`、`status_bar_root_modernization`、`status_bar_system_status_icons_in_compose`、`status_bar_ui_thread`、`notification_shade_ui_thread` 与 `edge_back_gesture_handler_thread` 这些开关，每一个都可能改变需要观察的窗口、线程或 UI 框架。AOSP tag（源码版本标签）只能说明对应代码存在，产品是否真的执行那条分支，取决于构建配置与运行时 flag。

先运行以下只读命令，把设备身份、aconfig（Android 平台功能开关系统）状态、线程名与窗口名采集存档：

```bash
adb shell getprop ro.build.fingerprint
adb shell aflags list | grep -E 'com\.android\.systemui\.(scene_container|dual_shade|status_bar_for_desktop|status_bar_root_modernization|status_bar_system_status_icons_in_compose|status_bar_ui_thread|notification_shade_ui_thread|edge_back_gesture_handler_thread)'
adb shell ps -A -T | grep -E 'systemui|launcher|ShellMain|ShellAnimation|Splashscreen|BackPanelUiThread|NotifInflation|RenderThread'
adb shell dumpsys window windows | grep -E 'NotificationShade|StatusBar|NavigationBar'
```

这组输出应与 Perfetto trace（系统跟踪）一起留档。`aflags list` 仅给出开关状态，窗口列表和线程列表才能证明对应实现确实已经创建。部分量产设备会隐藏调试信息，必要时可结合 userdebug（可调试系统构建）或厂商内部符号补齐上下文。


### 组件边界

| 画面或工作 | Android 17 的主要实现 | 分析时要确认的窗口或线程 |
| --- | --- | --- |
| 状态栏窗口 | <code>Status<wbr>Bar<wbr>Window<wbr>Controller<wbr>Impl</code>、状态栏 View/Compose root（根节点）、通知与系统图标绑定 | <code>Status<wbr>Bar</code> 或 <code>Status<wbr>Bar(display<wbr>Id=N)</code> 窗口；主线程或专用 UI 线程 |
| 通知抽屉与锁屏主窗口 | legacy <code>Notification<wbr>Shade<wbr>Window<wbr>View</code>，或 <code>Scene<wbr>Window<wbr>Root<wbr>View</code> 承载的 View/Compose 混合树 | <code>Notification<wbr>Shade</code> 窗口；主线程或专用 UI 线程 |
| 通知列表 | <code>Shared<wbr>Notification<wbr>Container</code> 与 <code>Notification<wbr>Stack<wbr>Scroll<wbr>Layout</code>（简称 NSSL，通知列表容器） | Scene 与 legacy 两条路径都可能出现 NSSL |
| 三按钮导航 | <code>Navigation<wbr>Bar</code>、<code>Navigation<wbr>Bar<wbr>View</code> | <code>Navigation<wbr>Bar<wbr>N</code> 窗口及其 ViewRoot |
| 边缘返回 | <code>Edge<wbr>Back<wbr>Gesture<wbr>Handler</code>、<code>Display<wbr>Back<wbr>Gesture<wbr>Handler<wbr>Impl</code>、Back Panel（返回手势箭头面板） | <code>edge-swipe</code> input monitor（输入监听器）；<code>Back<wbr>Panel<wbr>Ui<wbr>Thread</code> 或主线程 |
| Overview / Recents | Launcher3 Quickstep 的 <code>Recents<wbr>View</code> 等组件 | 设备当前 Launcher 进程，包名不必然是 <code>com.<wbr>android.<wbr>launcher3</code> |
| 窗口转场与起始窗口 | WM Shell <code>Transitions</code>、<code>Starting<wbr>Window<wbr>Controller</code> | Shell main/animation/splashscreen executor（主逻辑/动画/启动画面执行器）所在线程及宿主进程 |
| 最终合成与显示 | SurfaceFlinger、HWC（Hardware Composer，硬件合成器）、显示驱动 | SurfaceFlinger、FrameTimeline（逐帧时间线）、fence（同步栅栏）与显示时序 |

另外需要注意，WM Shell 本身是一组功能组件，未必以独立进程形态运行——目标产品既可以将 Shell 组件装入 SystemUI 进程，也可以另设宿主。因此在 Perfetto 中，应通过进程的 `cmdline`（命令行标识）与线程名来定位，不要假定系统中必然存在单独的“WM Shell 进程”。

## 三个系统栏窗口的拓扑

先看布局结构：`super_notification_shade.xml` 的根节点是 `NotificationShadeWindowView`，并通过 `<include>` 引入 `status_bar_expanded`。注意 `status_bar_expanded` 是展开面板的布局名称，与屏幕顶部的状态栏窗口属于不同窗口。状态栏、通知抽屉/锁屏主窗口以及三按钮导航栏均通过 `WindowManager.addView()` 创建，三个入口都能与 `WindowManager.LayoutParams` 直接对应：

| 窗口 | 类型 | AOSP 标题 | 源码入口 |
| --- | --- | --- | --- |
| 顶部状态栏 | <code>TYPE_<wbr>STATUS_<wbr>BAR</code> | 默认屏为 <code>Status<wbr>Bar</code>，辅助屏为 <code>Status<wbr>Bar(display<wbr>Id=N)</code> | <code>Status<wbr>Bar<wbr>Window<wbr>Controller<wbr>Impl.<wbr>get<wbr>Bar<wbr>Layout<wbr>Params<wbr>For<wbr>Rotation()</code> |
| 通知抽屉/锁屏主窗口 | <code>TYPE_<wbr>NOTIFICATION_<wbr>SHADE</code> | <code>Notification<wbr>Shade</code> | <code>Shade<wbr>Window<wbr>Layout<wbr>Params.<wbr>create()</code> |
| 三按钮导航栏 | <code>TYPE_<wbr>NAVIGATION_<wbr>BAR</code> | <code>Navigation<wbr>Bar<wbr>N</code> | <code>Navigation<wbr>Bar.<wbr>get<wbr>Bar<wbr>Layout<wbr>Params()</code> |

窗口名与 Layer（图层）之间也未必是一一对应关系，单个窗口在 SurfaceFlinger 中完全可能产生多个图层。窗口归属由 `dumpsys window` 确认，进入合成阶段后再按名称与时间去 SurfaceFlinger Layers 中查找对应图层。


### Legacy shade 的树

当 `SceneContainerFlag.isEnabled == false` 时，`ShadeViewProviderModule` 直接 inflate（按布局资源创建 View）`super_notification_shade.xml`。这棵视图树包含：

- 背景、通知区与前景 Scrim（半透明遮罩）；
- `status_bar_expanded`；
- `KeyguardRootView`；
- `SharedNotificationContainer`；
- bouncer（锁屏认证界面）、light reveal（亮屏揭示动画）等兼容内容。

<!-- gracker-diagram: ch07-04-legacy-shade-tree -->
![Legacy Shade 的视图职责](../../assets/diagrams/ch07/ch07-04-legacy-shade-tree.png)

图：Legacy Shade 的 XML 根直接包含展开面板、Scrim、锁屏与共享通知容器等区域；共享容器并非 status_bar_expanded 的子节点，NSSL 还可能由运行时 section 移入共享容器。

`NotificationShadeWindowView` 会在 `onMeasure()` 中写入 `NotificationShadeWindowView#onMeasure` slice（时间区间），并在 `requestLayout()` 时写入 instant event（瞬时事件）。其类注释也明确提醒：该 View 可以担任主 SystemUI 窗口的根节点，但调用方不应假定它永远位于根节点位置。

### Scene shade 是 Compose 与 View 的混合树

开启 Scene flag 后，`ShadeViewProviderModule` 改为 inflate `scene_window_root.xml`。该布局以 `SceneWindowRootView` 为根，内部仍通过 include 保留完整的 `super_notification_shade.xml`。随后 `SceneWindowRootViewBinder` 会执行三项直接影响性能观察的操作：

1. 创建承载 `SceneContainer` 的 `ComposeView`。
2. 将 `legacy_window_root`（传统窗口根节点）设为不可见。
3. 把包含 NSSL 的 `SharedNotificationContainer` 从旧父节点移出，挂载到 `Scene ComposeView` 之后，作为同一窗口下的兄弟 View。

因此即便开启了 Scene，NSSL 相关的观察点依然要保留：锁屏、Shade、QS（Quick Settings，快捷设置）等场景切换进了 Compose，但通知列表行仍然可以运行在 View 体系上。一次面板展开，往往同时交织着 Compose 的 recomposition/layout/draw（重组/布局/绘制）、NSSL 的 View 测量与状态计算、UI 线程的绘制记录、RenderThread 的渲染执行与提交，以及 SurfaceFlinger 合成。

<!-- gracker-diagram: ch07-04-scene-view-hybrid -->
![Scene Shade 的 Compose 与 View 混合树](../../assets/diagrams/ch07/ch07-04-scene-view-hybrid.png)

图：SceneWindowRootViewBinder 添加 ComposeView、隐藏 legacy root，并把共享通知容器移到根下。省略教育提示、Bouncer 专用 ComposeView 和认证涟漪等附加兄弟节点。

## SceneContainer 的开关与场景

判断 Scene 路径是否生效，首先要看 `SceneContainerFlag.isEnabled`：在 `android-17.0.0_r1` 中它等于 `Flags.sceneContainer() && isEnabledOnVariant`，并不要求一组 secondary flags（辅助开关）同时打开。Automotive 等 SystemUI variant（产品变体）可通过 `isEnabledOnVariant` 强制关闭该路径，常规产品则以目标构建的 aconfig 值为准。

开关启用后，`SceneContainerFrameworkModule` 注册的场景包括 `Gone`、`Communal`、`Dream`、`Occluded`、`Lockscreen`、`QuickSettings` 和 `Shade`；overlay（覆盖层）包括通知 Shade、QS Shade 与 Bouncer；Quick Actions 仅在 `StatusBarPopupChips.isEnabled` 为真时加入。当 Dual Shade（双面板通知/快捷设置）生效时，部分大屏配置会省去 Shade/QS scene 而改用两类 overlay——这一结构差异会直接改变 Compose 节点规模、过渡路径与 trace 名称。

<!-- gracker-diagram: ch07-04-scene-configuration-branches -->
![Scene 内容集合的条件分支](../../assets/diagrams/ch07/ch07-04-scene-configuration-branches.png)

图：Dual Shade 开启并且资源配置不要求保留时，才省去 Shade/QS 两个 scene。通知与 QS overlay 仍在配置中；Quick Actions 另有条件。

### 性能观察点

> 注（Android 17 r1）：`SceneTransitionLatencyMonitor` 只在目标为 Shade 或 QS 内容时开启 `ACTION_EXPAND_PANEL`，并以主线程队首回调结束；它度量的是首帧相关区间，不能替代整段转场或实际呈现测量。

- `SceneWindowRootViewBinder` 会将 `traceName` 传入 `view.viewModel()`，用于根节点生命周期绑定相关的跟踪；至于每次 scene transition 的耗时与目标帧是否按时呈现，仍需通过以下监控与 FrameTimeline 另行确认。
- `SceneJankMonitor` 将特定 scene transition（场景过渡）映射到 `InteractionJankMonitor` 的 CUJ（Critical User Journey，关键用户操作流程）。
- `SceneTransitionLatencyMonitor.onTransitionStart()` 在目标为 Shade/QS scene 或相应 overlay 时启动 `ACTION_EXPAND_PANEL`，再向 `@Main Handler` 的队首投递结束回调。源码注释将其明确限定为首帧相关区间：以符合条件的转场开始通知启动，主线程队首回调结束，既不等待整段转场完成，也不以 present fence 作为结束条件。
- `SceneTransitionBlurViewModel.requestWindowBackgroundBlur()` 根据 transition state（过渡状态）和进度请求窗口背景模糊，`WindowBackgroundBlur` log buffer（日志缓冲区）会记录请求值与支持状态。
- `status_bar_root_modernization` 与 `status_bar_system_status_icons_in_compose` 分别控制状态栏向新架构的迁移，不能只由 `scene_container` 的值反推，需在目标构建中逐项核对。

<!-- gracker-diagram: ch07-04-scene-monitor-boundaries -->
![Scene 监控的区间与呈现边界](../../assets/diagrams/ch07/ch07-04-scene-monitor-boundaries.png)

图：CUJ、LatencyTracker 与 FrameTimeline 的结束条件不同；绑定 trace 用于根节点生命周期相关的绑定跟踪，不能直接代表每次转场。模糊成本需在目标设备上对照验证。

模糊渲染的开销必须结合目标设备的 RenderThread、GPU 与 SurfaceFlinger 数据来评估。`debug.hwui.disable_blur_visual_feedback` 在参考源码中并未形成稳定的 SystemUI 诊断接口，不宜将其视为通用排障开关。做工程验证时，可以在可控分支中关闭对应的 blur flag，或将模糊半径设为零进行对照实验，并保持同一设备、同一场景与同一热状态下的 trace 可比性。

Compose 路径的 PSS（按比例分摊的进程内存）同样没有固定增幅：Scene 数量、always-compose（始终保持组合）策略、状态对象、缓存与 OEM 定制内容都会左右基线。建议按 flag 组合分别记录冷启动后、稳定待机、展开 Shade 以及通知集中到达后的内存快照，再进一步定位增量落在哪些对象或 native/GPU（原生/GPU）分配上。

## 通知从入库到显示的路径

排查通知列表性能时，至少应拆开四段工作：集合变化、通知行内容绑定、列表状态计算和窗口绘制。主要调用链路如下：

1. `NotifInflaterImpl.inflateViews()` 或 `rebindViews()` 将 entry（一条通知记录）交给 `NotificationRowBinderImpl`。
2. `NotificationRowBinderImpl` 创建或复用 `ExpandableNotificationRow`（可展开的通知行 View），更新图标，并通过 `RowContentBindStage` 请求所需的 contracted、expanded、public、single-line（折叠、展开、隐私、单行）等内容形态。
3. `NotificationRowContentBinderImpl` 创建 `AsyncInflationTask`；正常异步路径先在 `@NotifInflation Executor` 上恢复 Builder、生成模板与部分 View，加载所需图片并等待预加载任务。该阶段结果经 `onPostExecute()` 回到 SystemUI 主线程后，再发起 RemoteViews apply。
4. 新建 RemoteViews 内容走 `applyAsync()`，复用现有内容走 `reapplyAsync()`，两者显式共用同一个 `inflationExecutor`。RemoteViews 的 worker 阶段负责 inflate 与 `initActionAsync` 等准备；剩余 Action 应用及 `onViewApplied/onError` 回调则会切回其 Context 的主 looper，不能把整个 apply 耗时都归到 worker 上。
5. 异步 apply 失败时，`OnViewAppliedListener.onError()` 会在 UI 回调路径尝试同步 `apply()` 或 `reapply()`，以区分异步框架异常与通知内容自身的 inflate 失败。
6. 所需内容全部就绪后，更新后的 row 进入 View 树，进而触发后续测量、布局、动画与绘制。

<!-- gracker-diagram: ed07-04-notification-binding-handoffs -->
![通知绑定的执行器交接、图片等待预算与呈现边界](../../assets/diagrams/ch07/ed07-04-notification-binding-handoffs.png)

图：限定 Android 17 r1 的正常异步内容绑定：entry/row 请求所需形态，模板与图片准备、RemoteViews 准备共用同一 NotifInflation 执行器，中间经 SystemUI 主 looper 发起 apply，剩余 Action 与结果回调回到 RemoteViews Context 的主 looper。1000 ms 仅为该批 URI 预加载等待的共享预算，无 cache 或目标 URI 时可跳过；其他阶段另计。reapply 可在整批完成前修改已有 View；实际 ViewRoot 线程及窗口呈现仍须另查，异步失败的同步回退见下文。

搜 trace 时需留意一个历史兼容命名：Android 17 源码中已移除旧版的 `NotificationContentInflater.java`，实现类迁移为 Kotlin 的 `NotificationRowContentBinderImpl.kt`，但 `doInBackground()` 依然保留了旧 trace 名称 `NotificationContentInflater.AsyncInflationTask#doInBackground`。

### 异步绑定后的线程分工

在参考实现中，`NotifInflation` 是单个后台优先级的 `HandlerThread`，由 `ExecutorImpl` 投递任务；Builder/模板阶段与后续 RemoteViews 准备阶段共享这一执行器，高并发时可能互相排队。`AsyncInflationTask.onPostExecute()` 运行在默认主 looper 上，而 RemoteViews 回调使用其 Context 的主 looper，完成部分 Action、wrapper 更新与内容挂接等收尾。至于窗口 traversal，仍需回到该 ViewRoot 实际所属的 UI 线程核对——窗口线程 flag 决定的是窗口自身的宿主，具体哪些通知回调迁到了新线程需逐一确认。当大量通知在短时间内密集到达时，trace 中常会连续出现以下现象：

- `NotifInflation` 队列持续繁忙；
- 多个异步绑定结果在相近时刻集中完成；
- UI 线程集中将通知 row 挂载进 View 树；
- NSSL 与状态栏图标容器在随后几帧反复触发更新；
- RenderThread 或 SurfaceFlinger 在同一时段承受更大的绘制与合成压力。

同步 fallback（后备路径）同样需要单独盯防。一旦在 trace 或日志中发现 `applyAsync()` 失败并频繁回退到同步处理，耗时就会从 worker（工作线程）转移到 UI 回调路径。此时单纯降低通知更新频率只能减少触发次数，真正要查清的是究竟由自定义 `RemoteViews`、异常资源、URI 权限还是厂商控件触发了异步失败。

<!-- gracker-diagram: ch07-04-async-apply-fallback -->
![异步 apply 失败后的同步回退](../../assets/diagrams/ch07/ch07-04-async-apply-fallback.png)

图：异步失败会在 UI 回调里尝试同步 apply/reapply；即使成功，这段同步路径的耗时也留在 UI 回调里。应定位失败原因，并核对同步回退是否拖延目标帧。

### NSSL 的测量成本由什么决定

`NotificationStackScrollLayout#onMeasure` 先调用父类测量，当 `mSuppressChildrenMeasureAndLayout` 为真时直接提前返回。在未抑制的常规分支中，它会显式遍历全部直接 child（子 View），包括处于 `GONE` 状态的节点也一样调用 `measureChild`，因为堆叠算法需要借助这些高度估算面板可容纳的通知条数。也就是说，即使通知行在视觉上处于隐藏状态，测量开销仍可能照常发生。单帧内的测量工作量主要取决于以下五个因素：

<!-- gracker-diagram: ch07-04-nssl-measure-branches -->
![NSSL 显式测量的抑制与 GONE 分支](../../assets/diagrams/ch07/ch07-04-nssl-measure-branches.png)

图：NSSL 通常显式测量所有直接 child，包括 GONE；但抑制标志为真会提前返回。图不把一次 measureChild 调用等同于整棵子树必然重新完整计算。

- entry（SystemUI 中的一条通知记录）与 row 总数；
- 分组展开/折叠和 heads-up（悬浮通知）状态；
- public、contracted、expanded、single-line 等内容变体是否已绑定；
- OEM 增加的包装层与装饰 View；
- 配置变化、字体缩放、屏幕形态切换触发的全量重测。

NSSL 的状态更新在两条路径中入口不同：legacy 路径通过 pre-draw listener（绘制前监听器）调用 `updateChildren()`，Scene 路径则在 `onDraw()` 起始处调用 `onJustBeforeDraw()`，且仅在 `mChildrenUpdateRequested` 为真时处理待更新状态；两条路径都保留了 `NSSL#updateChildren` slice，内部负责执行 stack algorithm（通知堆叠布局算法）、应用当前状态或启动状态动画，并处理通知间的重叠计算。

<!-- gracker-diagram: ch07-04-nssl-update-entry-points -->
![Legacy 与 Scene 的 NSSL 更新入口](../../assets/diagrams/ch07/ch07-04-nssl-update-entry-points.png)

图：Legacy 使用 pre-draw listener；Scene 在 onDraw 开始且有待更新请求时进入。两条路径共用 NSSL#updateChildren，随后选择直接应用状态或启动状态动画。

### 普通模板、自定义 RemoteViews 与大图

| 负载 | 主要风险 | 证据入口 |
| --- | --- | --- |
| 标准模板高频更新 | entry 反复 rebind（重新绑定）、图标变化、多个完成回调集中到达 | <code>Notif<wbr>Inflation</code> 队列、row bind 日志、NSSL requestLayout |
| 自定义 <code>Remote<wbr>Views</code> | 层级复杂、资源异常、异步 apply fallback、内存校验失败 | <code>apply<wbr>Async/reapply<wbr>Async</code>、<code>on<wbr>Error</code>、<code>Custom<wbr>View<wbr>Memory<wbr>Size<wbr>Exceeded<wbr>Exception</code> |
| 大图通知 | 解码与缩放、像素常驻、异步预加载等待、纹理上传 | worker CPU、bitmap/native（位图/原生）内存、RenderThread 与 GPU |
| 分组通知 | summary/child（摘要/子通知）内容形态、展开状态与动画、更多 row 参与测量 | group 状态变化、NSSL measure/updateChildren |

`BigPictureIconManager` 对部分 URI/resource（资源）类型支持延迟加载；而 bitmap（位图）、adaptive bitmap（自适应位图）和 data 类型会跳过这套延迟策略，其像素数据会继续常驻内存。

<!-- gracker-diagram: ch07-04-big-picture-loading-types -->
![大图通知的类型与延迟加载边界](../../assets/diagrams/ch07/ch07-04-big-picture-loading-types.png)

图：BigPictureIconManager 对 bitmap、adaptive bitmap 和 data 类型跳过这套延迟策略；URI/resource 等类型能否延迟，还要结合功能开关、可见性和消费方状态。

`NotificationRowContentBinderImpl` 在正常异步任务中为 `waitForPreloadedImages()` 传入 1000 ms 参数；resolver 会为这一批目标 URI 共用同一个截止时间，并逐张递减剩余等待预算。因此这 1000 ms 是整批共享的预算（并非每张图各一秒），且仅约束预加载等待这一段，不对整个绑定任务设统一总时限，其他阶段的耗时需另外测量。虽然这段等待发生在 worker 中、UI 线程未必同步卡住一秒，但队列积压、完成回调集中到达以及后续纹理上传，依然可能拖慢可见帧。


从优化分工上看，App 侧往往更容易见效：合并高频进度更新、保持通知 ID 与模板稳定、减少内容未变时的无效 `notify()`、避免每秒替换大图、控制自定义 RemoteViews 树深，并利用通知分组减少频繁结构变动。SystemUI 侧则应保住异步路径、消除触发 fallback 的异常源、限制单帧内的状态更新量，并通过实机数据验证缓存策略的收益。

## 状态栏图标：通知图标与系统状态图标分开看

左侧通知图标在 Android 12—14 的资料中常从 presenter/controller 追起；在当前实现里已经移到 `statusbar/notification/icon/ui`，主要由三个组件串联：

- `NotificationIconContainerStatusBarViewModel.icons` 从 `iconsInteractor.statusBarNotifs` 生成 `NotificationIconsViewData`；map 转换在后台 context（协程执行上下文）中执行，上游更新随后经过 `conflate()` 与 `distinctUntilChanged()` 控制——前者在下游来不及处理时仅保留最新值，后者过滤相邻相等结果。至于实际更新频率是否压到了“每帧最多一次”，仍要到具体帧里统计确认。
- `NotificationIconContainerStatusBarViewBinder.bindWhileAttached()` 按 `displayId` 选用图标 View store，再绑定到 `NotificationIconContainer`。
- 默认屏复用通知处理流程保存的 status bar icon；辅助屏则使用 `ConnectedDisplaysStatusBarNotificationIconViewStore`，按通知 key 缓存为目标 display context 创建的 `StatusBarIconView`。

<!-- gracker-diagram: ch07-04-notification-icon-flow -->
![通知图标 Flow 的合并与去重](../../assets/diagrams/ch07/ch07-04-notification-icon-flow.png)

图：图标集合在后台映射，再合并积压值和过滤相邻相等值；算子之后的更新频率与最终呈现，仍要靠后续 View 与帧时间线分析。

`NICStatusBar#bindWhileAttached` 只覆盖绑定关系建立的时刻；每次通知变化引发的实际帧耗时，还要沿着 Flow（异步数据流）更新、View 容器变化、ViewRoot traversal 与 FrameTimeline 继续追踪。

<!-- gracker-diagram: ch07-04-icon-store-by-display -->
![通知图标 View 的 per-display 选择](../../assets/diagrams/ch07/ch07-04-icon-store-by-display.png)

图：同一条通知数据可以对应不同的 View 实例：默认屏复用 pipeline 中的图标，辅助屏按 display context 创建并缓存 View。绑定入口的 trace 只到绑定为止，每次通知更新的完整帧要另行跟踪。

右侧网络、电池、时钟等系统状态图标仍由状态图标处理流程与 `StatusBarIconControllerImpl` 等组件管理；受 `status_bar_system_status_icons_in_compose` 开关控制，目标产品也可能已将部分区域迁至 Compose。排查大量通知集中到达的场景时，应把两侧输入源分开统计：

- 左侧压力源于通知集合与图标 View 的增删；
- 右侧压力源于网络、电话、热点、隐私指示以及 OEM 扩展等状态更新；
- 两侧更新可以在同一个状态栏窗口帧内叠加，但各自的诱因与节流位置完全不同。


## 导航输入的两条路径

三按钮导航和边缘返回走的是两条截然不同的输入路径：三按钮经 `NavigationBarView` 接收触摸，边缘返回经对应的 input monitor 进入；此外，手势导航中的主页与最近任务手势还会经由 Launcher/Quickstep 等组件参与，不能全部归入边缘返回这一入口。

### 三按钮导航

`NavigationBarView.onInterceptTouchEvent()` 与 `onTouchEvent()` 将触摸事件交给 `mTouchHandler`，再由按钮触发 back、home、recents（返回、主页、最近任务）等动作。定位三按钮响应延迟时，时间线应覆盖：

`InputDispatcher` 投递 → `NavigationBarN` 窗口 UI 线程 → 事件与按钮处理。此后需分开记录两条结果路径：一是导航栏自身的 pressed/动画反馈帧，二是按钮动作触发的 WM/Launcher 或目标 App 状态变化与转场；两者可以交叠，反馈帧无需等待目标窗口切换完毕。

<!-- gracker-diagram: ch07-04-three-button-parallel-results -->
![三按钮导航的反馈与行为分支](../../assets/diagrams/ch07/ch07-04-three-button-parallel-results.png)

图：从导航栏事件处理处分开跟踪反馈帧与目标窗口行为。底部只是可交叠的阶段示意，具体先后与耗时应读取设备 trace。

如果 Input 已经送达而按钮 pressed（按下状态）或反馈动画迟到，优先排查该导航栏窗口的 UI 线程与 ViewRoot；反之，若按钮反馈及时而窗口切换迟缓，则应转向 WM Shell、Launcher 或目标 App，不能把整段延迟都记在 `NavigationBarView` 头上。

### 边缘返回手势

边缘返回手势把 per-display（每块显示屏独立）的资源放进 `DisplayBackGestureHandlerImpl`：它为每个 display 创建 `InputMonitorCompat("edge-swipe", displayId)`，利用 `UiThreadContext` 的 looper（消息循环）与 Choreographer 建立 input receiver（输入接收器），并注册 system gesture exclusion listener（系统手势排除区域监听器）。跨 display 的共享状态与回调集中管理在 `EdgeBackGestureHandler` 中，由它持有多个 `DisplayBackGestureHandler`。

当 `edge_back_gesture_handler_thread` 开启时，`SysUIConcurrencyModule` 会创建具有显示相关优先级的 `BackPanelUiThread`；关闭时，同一个 `UiThreadContext` 改用 SystemUI 主线程。由此衍生出两个线程排查分支，以及一条后续的窗口转场检查：

<!-- gracker-diagram: ch07-04-edge-back-thread-branches -->
![边缘返回的 per-display 输入与线程分支](../../assets/diagrams/ch07/ch07-04-edge-back-thread-branches.png)

图：边缘返回不依赖三按钮窗口的触摸入口；它使用 per-display input monitor。线程开关决定 UiThreadContext 使用专用 BackPanelUiThread 还是主线程。

- trace 中存在 `BackPanelUiThread`：检查 input receiver、手势判定、Back Panel 绘制以及该线程的 Choreographer；
- trace 中没有该线程：核对 aconfig 值，并在 SystemUI 主线程中寻找同一套处理路径；
- 手势进入 back animation 后：继续追踪 WM Shell back transition、目标窗口与 SurfaceFlinger。

三按钮路径与边缘返回虽然共享部分窗口管理结果，但输入入口完全不同：在 gesture mode（手势导航模式）下，边缘返回走 `edge-swipe` input monitor 与 Back Panel，只搜索 `NavigationBarView` 会漏掉整条链路。

## 多显示、折叠屏与桌面窗口模式

per-display status bar（每块显示屏独立状态栏）的基础设施已经就位：`StatusBarWindowControllerImpl` 持有 `mDisplayId`，辅助屏窗口标题带有 display id（显示屏标识）；`MultiDisplayStatusBarWindowControllerStore` 按 display 提供 controller；通知图标 binder（绑定器）也接受 `displayId`。面对折叠屏和外接屏形态，“全局只有一个 StatusBar 实例”的假设已经不再成立。

不过，具备多屏基础设施并不等于每块 display 都会创建状态栏。`DisplayContent.isSystemDecorationsSupported()` 会先排除 VR 2D display 与不可信 display，再检查 display window settings（显示窗口设置）、`FLAG_SHOULD_SHOW_SYSTEM_DECORATIONS`，以及旧 display-content-mode 管理路径下的强制桌面条件。最终是否创建，由产品 flag、display 类型、信任属性与系统策略共同决定。

<!-- gracker-diagram: ch07-04-display-decor-policy -->
![Display 系统装饰的策略判断](../../assets/diagrams/ch07/ch07-04-display-decor-policy.png)

图：系统装饰支持先经过安全排除，再看设置/flag 与特定旧桌面条件。要证明每块屏真的建起了系统栏，还要回到运行时窗口列表。

多屏分析中还有三处细节容易混淆：

- `NavigationBarControllerImpl` 用 `SparseArray<NavigationBar>` 按 display 管理导航栏，并通过 WMS（WindowManagerService，窗口管理服务）查询该 display 是否存在 navigation bar 或 taskbar（导航栏/任务栏）。外接屏的 Taskbar 可能由 Launcher 管理，SystemUI 的 `TaskbarDelegate` 负责协调状态与回调。
- AOSP Shade 仍是 display-aware（能够识别不同显示屏）的单例主窗口，可以在 display 之间迁移，或在 display 移除时重新挂回默认屏；因此“每块屏都有一套 NotificationShade”的说法需从窗口列表单独核实，不可直接假定。
- 桌面任务布局、窗口装饰与转场主要属于 WM Shell desktop mode；分析桌面模式卡顿时，应把任务应用的 View、Shell 的窗口装饰与输入系统的光标按实际宿主拆开排查，不能笼统归入 desktop mode 渲染。


测量多显示场景性能时，至少需要分别固定以下状态：单屏折叠态、单屏展开态、外屏连接但休眠、双屏点亮、桌面窗口模式，以及导航栏与 Taskbar 两种形态。实验记录还应包含分辨率、刷新率、Layer 数、状态栏实例数与通知 Shade 所在 display；CPU、GPU、显存或 PSS 的增量，也只能基于同一设备上的对照数据得出。

## App 启动与 Overview 的参与者

从桌面或 Overview 启动 App 时，以下多个参与者经常并发交叠（starting window、目标 App 生产 buffer、系统栏更新与转场未必按编号串行）：

1. Launcher/Quickstep 接收点击或手势，更新 workspace（桌面工作区）、任务卡片或 Overview 状态。
2. `system_server` 的窗口管理核心创建并推进 transition（窗口过渡）。
3. WM Shell `Transitions` 接收 request/ready（请求/就绪）回调，选定 transition handler（过渡处理器），由 Shell main executor 调度；动画执行线程取决于所选 handler，既可能在 Shell animation executor，也可能委托给 Launcher 等 remote transition 宿主。
4. `StartingWindowController` 调用 `StartingWindowTypeAlgorithm`，在 splashscreen executor 中决定采用 snapshot（任务快照）、solid-color splash（纯色启动画面）、SplashScreen、windowless starting surface（无独立窗口的起始 Surface）还是不创建起始窗口，并执行创建；移除请求则先由 Shell main 上的 observer 协调，再把实际移除动作提交给 splashscreen executor。
5. 目标 App 提交首批 buffer。
6. SystemUI 同步更新状态栏、导航栏、锁屏或 Shade 的相关状态。
7. SurfaceFlinger 合成 Launcher、starting window、目标 App 与系统栏，交给 HWC 与显示设备呈现。

<!-- gracker-diagram: ch07-04-launch-participants-overlap -->
![启动与 Overview 的多方参与](../../assets/diagrams/ch07/ch07-04-launch-participants-overlap.png)

图：启动职责按交叠关系排布，Shell handler、起始画面、目标 App 与系统栏可能同时在场；示意条长不表示真实耗时，生产者也未画全。

`Transitions.java` 保留了 `dispatchRequest: <type>`、`playTransition: <type>` 与 `<Handler>#startAnimation animated <type>` 等 WM trace。`StartingWindowController` 同时用到 Shell main executor 与 splashscreen executor，排查起始窗口耗时时要按执行器分开看：Shell main 承担状态协调，创建与移除的实际执行落在 splashscreen executor。

<!-- gracker-diagram: ch07-04-starting-surface-executors -->
![起始 Surface 的创建与移除执行器](../../assets/diagrams/ch07/ch07-04-starting-surface-executors.png)

图：添加请求分别提交 Shell main 状态协调与 splashscreen 创建工作；类型选择含 windowless/none。移除请求先协调，再派发实际移除。

Overview 的 `RecentsView.applyLoadPlan()` 负责增删、复用并绑定任务卡片，但该方法名并未成为稳定的 trace slice；因此源码里的方法边界与设备上实际采到的 trace 事件应分开核对。


Launcher 的包名与进程名同样随产品定制变化：AOSP 参考实现是 Launcher3 Quickstep，Pixel 或 OEM 构建常使用其他包名。定位时应通过默认 HOME activity、进程 `cmdline` 和窗口 owner（所有者）来确认当前宿主，避免只搜固定的 `com.android.launcher3`。

## 把 SystemUI 放回标准渲染管线

SystemUI 特殊在窗口数量多、状态来源杂，且可以通过开关启用专用线程，但单个窗口内部走完 HWUI 主路径依然遵循标准渲染时序：

`VSync` 驱动对应窗口 UI 线程的 Choreographer；`doFrame()` 按 `INPUT`、`ANIMATION`、`INSETS_ANIMATION`、`TRAVERSAL`、`COMMIT` 顺序分发回调。输入与动画更新发生在对应阶段，ViewRoot 的 traversal、绘制记录及向 RenderThread 同步通常落在 `TRAVERSAL`，早于 `COMMIT`。随后 RenderThread/HWUI 经 BLAST buffer queue（窗口缓冲队列）向 SurfaceFlinger 提交 buffer，再由 HWC/present 链路完成呈现。各阶段可流水交叠，`COMMIT` 本身不等待 GPU 或显示呈现结束，后两者的完成时刻必须回到各自时间线上确认。

<!-- gracker-diagram: ch07-04-ui-callback-render-pipeline -->
![SystemUI 的回调阶段与渲染流水](../../assets/diagrams/ch07/ch07-04-ui-callback-render-pipeline.png)

图：ViewRoot traversal 通常在 TRAVERSAL 回调中记录绘制并与 RenderThread 同步；COMMIT 在其后，GPU 或屏幕呈现的完成点要另找 fence 与 present。底部只表示可能流水交叠，不按时长比例绘制。

沿这条路径读 trace 时，有五个关键边界需要注意：

- `doFrame` 较长只表示墙钟区间长，里面可能混有 CPU 执行、Runnable 排队和阻塞等待；应先结合 sched 分解，再看输入、动画、measure/layout、绘制记录或同步等待哪一段变长。
- `Traversal` 覆盖 measure/layout、绘制记录以及向 RenderThread 同步。尾部的 `syncAndDrawFrame()` 可能等待 RenderThread 状态同步，下游处理不及时造成的 backpressure（反压）同样会拉长 traversal。
- Compose 的 recomposition、layout 与 draw 记录仍发生在对应窗口的 UI 线程；GPU 执行与 display 合成则需到 RenderThread、SurfaceFlinger 与 HWC 中继续确认。
- `requestLayout` instant event 仅表示发出了布局请求，当场是否真正执行 layout 要看后续是否出现 measure/layout。
- App `SurfaceFrame` 使用 `surface_frame_token`，Display `DisplayFrame` 使用 `display_frame_token`；两者分属不同命名空间，数值碰巧相等不构成关联，必须依据 FrameTimeline 的对应关系配对。


### Perfetto 中的观察顺序

| 步骤 | 要回答的问题 | 主要轨道或证据 |
| --- | --- | --- |
| 确认呈现异常 | 哪个 display frame missed（错过截止时间），异常在 deadline 还是 present 环节 | FrameTimeline <code>Display<wbr>Frame</code>、VSYNC、HWC |
| 找到受影响 Surface | 是 NotificationShade、StatusBar、NavigationBar、Launcher 还是目标 App | <code>Surface<wbr>Frame</code>、SurfaceFlinger Layers、窗口 owner |
| 确认生产者线程 | 哪个进程和 ViewRoot 产生该 buffer | 目标进程 UI 线程、RenderThread、BLAST |
| 细分应用或系统 UI 工作 | 输入、动画、绑定、measure/layout、绘制记录中哪段变长 | slice、sched（调度）、binder、CPU frequency（频率） |
| 检查后续阶段的反压 | UI 是否等待 RenderThread，RenderThread 是否等待 GPU/buffer，SurfaceFlinger 是否错过合成 | <code>sync<wbr>And<wbr>Draw<wbr>Frame</code>、dequeue/queue（出队/入队）、fence、SurfaceFlinger/HWC |
| 回到源码 | trace 名对应哪个 Android 17 方法，目标 flag 是否选择该实现 | <code>android-17.<wbr>0.<wbr>0_<wbr>r1</code> 源码、aflags、产品差异 |

下面的 Trace Processor SQL 用于列出 SystemUI 中三个已核对的通知列表 slice：

```sql
SELECT
  s.id AS slice_id,
  p.upid,
  p.pid,
  p.name AS process_name,
  t.utid,
  t.tid,
  t.name AS thread_name,
  s.ts,
  s.dur,
  s.dur / 1e6 AS wall_dur_ms,
  s.name
FROM slice AS s
JOIN thread_track AS tt ON s.track_id = tt.id
JOIN thread AS t USING (utid)
JOIN process AS p USING (upid)
WHERE p.name GLOB '*systemui*'
  AND s.dur >= 0 -- 排除尚未结束的 slice；空结果不证明该工作没有发生
  AND s.name IN (
    'NotificationShadeWindowView#onMeasure',
    'NotificationStackScrollLayout#onMeasure',
    'NSSL#updateChildren'
  )
ORDER BY s.ts;
```

该查询返回已完成 slice 的墙钟时长，其中包含运行、调度等待与阻塞时间，与线程纯 CPU 执行时间属于不同统计量。进程名与这三个 slice 名仅适用于相应实现及已覆盖的采集配置，空结果也可能源自 OEM 改名、未采集对应类别或 slice 尚未结束。查出候选区间后，还应结合实际进程/线程身份、Surface 与逐帧关联，在同一时间窗口内核对 `SurfaceFrame`、`DisplayFrame`、RenderThread、SurfaceFlinger 与调度状态；时间重叠只构成线索，认定用户可见卡顿仍须依靠逐帧证据。


## 四类常见现场

把上述窗口、线程与绑定边界落到具体排障中，最常见的是四类现场：Shade 展开、通知集中到达、返回手势和启动动画。每一类都应从用户可见的异常帧出发，再回溯到对应的生产者线程。

### Shade 展开掉帧

首先在 FrameTimeline 中选中 missed display frame，定位关联的 `NotificationShade` SurfaceFrame，随后检查该窗口的 UI 线程：

- legacy 路径重点观察 `NotificationShadeWindowView#onMeasure`、NSSL measure 与 `NSSL#updateChildren`；
- Scene 路径则需同时纳入 Compose recomposition/layout/draw、scene transition/CUJ 与 blur 请求；
- 两条路径都必须检查 NSSL，因为 Scene 架构下通知行容器仍保留在 View 树中；
- 若 UI 线程并未超出该帧预算，则继续下钻 RenderThread、buffer queue、SurfaceFlinger 与 GPU。

接着按信号位置收窄优化方向：若 NSSL measure 随通知总数线性放大，应减少参与测量的 row、已绑定内容形态和嵌套层级；若 `NSSL#updateChildren` 耗时变长，重点排查分组展开、heads-up、动画状态及同帧更新次数；若 UI 与 RenderThread 均正常而 display frame 依然 miss，则转向排查 SurfaceFlinger/HWC、其他高层 Surface 或显示模式切换。


### 通知集中到达

这类现场需要同时核对三组信号：`NotifInflation` worker、SystemUI 窗口 UI 线程以及状态栏/NotificationShade 的 FrameTimeline。常见诱因包括 worker 排队、图片预加载、异步 apply fallback、完成回调集中抵达、row 批量挂接、图标批量更新与 NSSL 连续重算。

由于异步绑定的主体工作原本就在 worker 线程执行，在主线程上看不到 `RemoteViews.apply()` 并不能排除通知绑定问题——真正触发卡顿的往往是任务集中完成后的主线程 View 树更新阶段。反过来，若只是 worker 队列变长而可见帧并未受到拖延，也只能将其记为候选因素，需补充下游证据才能定性。


### 返回手势反馈迟缓

分析时以 input event 送达 `edge-swipe` receiver 为起点，以 Back Panel 首帧或目标窗口 transition 为终点。当 `BackPanelUiThread` 启用时，主线程上的通知绑定未必直接阻塞返回箭头绘制，但两条线程仍可能通过共享状态、WM 调用与合成资源相互干扰。若 input receiver 响应迅速且 Back Panel 按时出帧，仅窗口切换阶段迟缓，则问题重点在 WM Shell 与目标 App 侧。


### 启动动画不连贯

在同一个时间窗口内，同时比对 Launcher、Shell、starting window、目标 App、SystemUI 与 SurfaceFlinger 的轨道，拆清以下六种可能：

- Launcher 任务卡片或 workspace 自身掉帧；
- Shell handler 选择或动画执行延迟；
- starting window 创建过慢或移除时机不当；
- 目标 App 首批 buffer 提交偏晚；
- StatusBar/NavigationBar 同期状态更新超出帧预算；
- SurfaceFlinger/HWC 合成或 present 延迟。

完整归因需走完三步：先确认受影响系统栏的 SurfaceFrame 与对应 UI/RenderThread 工作在时间上吻合，建立候选；再找出最早拖延该帧的依赖项，分清是本地计算还是外部等待；最后通过同场景对照实验验证。单纯的时间重叠和 CPU 峰值只完成了第一步，还不足以将根因归咎于 SystemUI。

## OEM 差异的处理方式

厂商往往会对状态栏层级、QS、锁屏、通知模板、插件、模糊效果、动画以及线程开关做深度定制。AOSP 源码提供了稳定的排查基准，但具体类名与 trace slice 在量产 ROM 上仍可能变化。审查 OEM 实现时，建议同步保留三份材料：

- AOSP Android 17 的基准源码与 flag；
- 产品分支相对于 AOSP 的 diff；
- 目标设备的窗口、线程、Layer、Perfetto trace 与日志。

编写结论时也应明确标注适用边界。例如，“Scene 路径下 NSSL 仍参与通知行布局”可直接由 AOSP Android 17 源码佐证；“某机型在 120 Hz 下展开通知面板时 blur 构成瓶颈”需要该机型的对照 trace 支撑；而“外接显示器后会创建第二个 StatusBar”则需结合 display policy（显示策略）与运行时窗口列表共同证明。


## 实战检查清单

采集前：

- 记录 build fingerprint（系统构建指纹）、刷新率、分辨率、导航模式、折叠状态和外接屏状态。
- 保存相关 aconfig 值。
- 保存 `dumpsys window` 中三个系统栏窗口及 display id。
- 保存 SystemUI、Launcher、Shell 相关线程分别属于哪个进程。
- 固定通知集合、分组、图片和更新频率，控制温度与电源状态。

读 trace 时：

- 从 missed `DisplayFrame` 开始，找到对应的 Surface 和 owner。
- 区分 MainThread、专用窗口 UI 线程、`NotifInflation`、RenderThread 和 Shell executor。
- 将 `requestLayout` 当成触发信号，将 measure/layout/draw 与 `syncAndDrawFrame` 分开。
- 对照 legacy/Scene、View/Compose、三按钮/手势、单屏/多屏分支。
- 检查 CPU 调度、频率、binder、GPU、buffer queue、SurfaceFlinger/HWC，避免只凭一条 slice 判断责任。

形成结论时：

- 写明 Android 17 tag、产品分支、flag 和 display 条件。
- 给出 FrameTimeline 与线程 slice 的时间关系。
- 标明直接源码事实、trace 观察和工程推断。
- 优化后复测同一场景，并报告分位数、missed frame 类型和 thermal（温控）状态。

## 与其他章节的关系

- **§2.4 MainThread 与 RenderThread 协作**：介绍标准 HWUI、BLAST 与 SurfaceFlinger 的分工；SystemUI 还需检查专用 UI 线程。
- **§7.1 卡顿的定义与分类**：SystemUI 仍需从 FrameTimeline 的用户可见帧开始判断责任。
- **§7.2 典型卡顿场景**：Shade、导航、启动和 Overview 的现象，需要结合这里的窗口与组件边界进一步分析。
- **§14.2 Perfetto View 解读**：线程、FrameTimeline、Layer 和 SQL 操作可参考该章。

## Android 17 源码与官方资料

- AOSP [`systemui.aconfig`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/aconfig/systemui.aconfig)
- AOSP [`super_notification_shade.xml`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/res/layout/super_notification_shade.xml)
- AOSP [`scene_window_root.xml`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/res/layout/scene_window_root.xml)
- AOSP [`ShadeViewProviderModule.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/shade/ShadeViewProviderModule.kt)
- AOSP [`ShadeWindowLayoutParams.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/shade/ShadeWindowLayoutParams.kt)
- AOSP [`NotificationShadeWindowView.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/shade/NotificationShadeWindowView.java)
- AOSP [`SceneContainerFlag.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/scene/shared/flag/SceneContainerFlag.kt)
- AOSP [`SceneContainerFrameworkModule.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/scene/SceneContainerFrameworkModule.kt)
- AOSP [`SceneWindowRootViewBinder.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/scene/ui/view/SceneWindowRootViewBinder.kt)
- AOSP [`NotificationStackScrollLayout.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/statusbar/notification/stack/NotificationStackScrollLayout.java)
- AOSP [`NotificationRowContentBinderImpl.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/statusbar/notification/row/NotificationRowContentBinderImpl.kt)
- AOSP [`NotificationIconContainerStatusBarViewBinder.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/statusbar/notification/icon/ui/viewbinder/NotificationIconContainerStatusBarViewBinder.kt)
- AOSP [`StatusBarWindowControllerImpl.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/statusbar/window/StatusBarWindowControllerImpl.java)
- AOSP [`NavigationBarControllerImpl.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/navigationbar/NavigationBarControllerImpl.java)
- AOSP [`DisplayBackGestureHandler.kt`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/DisplayBackGestureHandler.kt)
- AOSP [`DisplayContent.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/services/core/java/com/android/server/wm/DisplayContent.java)
- AOSP [`Transitions.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/transition/Transitions.java)
- AOSP [`StartingWindowController.java`](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/startingsurface/StartingWindowController.java)
- AOSP Launcher3 [`RecentsView.java`](https://android.googlesource.com/platform/packages/apps/Launcher3/+/android-17.0.0_r1/quickstep/src/com/android/quickstep/views/RecentsView.java)
- Android Open Source Project：[读取和修改 aconfig flag](https://source.android.com/docs/setup/build/feature-flagging/flip-a-flag)
- Android Developers：[通知概览](https://developer.android.com/develop/ui/views/notifications)
- Android Developers：[SplashScreen API](https://developer.android.com/develop/ui/views/launch/splash-screen)

- [NotificationInlineImageResolver.java](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/statusbar/notification/row/NotificationInlineImageResolver.java)
- [RemoteViews.java](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/core/java/android/widget/RemoteViews.java)
- [AsyncTask.java](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/core/java/android/os/AsyncTask.java)
- [SceneTransitionLatencyMonitor.kt](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/scene/ui/view/SceneTransitionLatencyMonitor.kt)
- [StatusBarWindowControllerStore.kt](https://android.googlesource.com/platform/frameworks/base/+/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/statusbar/window/StatusBarWindowControllerStore.kt)
- [Perfetto FrameTimeline](https://perfetto.dev/docs/data-sources/frametimeline)
- [Perfetto slice 表与线程时间字段](https://perfetto.dev/docs/analysis/sql-tables#slice)

- [Launcher3 TouchInteractionService：主页/最近任务手势的输入监控与 consumer（固定提交）](https://android.googlesource.com/platform/packages/apps/Launcher3/+/4e7411c54cf4dbb92764d275bc8dcf6d6ed73a0e/quickstep/src/com/android/quickstep/TouchInteractionService.java)
- [PointerChoreographer：输入系统光标控制（Android 17 r1）](https://android.googlesource.com/platform/frameworks/native/+/android-17.0.0_r1/services/inputflinger/PointerChoreographer.cpp)

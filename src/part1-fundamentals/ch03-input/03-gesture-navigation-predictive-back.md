---
title: 系统手势导航与 Predictive Back
chapter: '3.3'
section: '3.3'
status: finalized
applicable_versions: Android 13 (API 33) - Android 17 (API 37)
last_verified: '2026-10-26'
last_source_verified_at: '2026-10-26'
last_idle_audit_at: '2026-10-26'
last_verified_against: AOSP android-17.0.0_r1 / Android Developers predictive back docs
confidence: medium-high
sources:
- type: blog
  path: TechMerger - 深入理解 Android 系统 Back Gesture 的实现 (微信)
- type: blog
  path: 郭霖 - Android 15 新特性：预测性返回手势 (微信)
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/EdgeBackGestureHandler.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/DisplayBackGestureHandler.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/BackPanelController.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/BackPanel.kt
- type: aosp
  path: frameworks/base/packages/SystemUI/shared/src/com/android/systemui/shared/system/InputMonitorCompat.java
- type: aosp
  path: frameworks/base/packages/SystemUI/src/com/android/systemui/util/concurrency/SysUIConcurrencyModule.kt
- type: aosp
  path: frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/back/BackAnimationController.java
- type: aosp
  path: frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp
- type: aosp
  path: frameworks/base/core/java/android/view/ViewRootImpl.java
- type: aosp
  path: frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java
- type: aosp
  path: frameworks/base/services/core/java/com/android/server/wm/WindowState.java
- type: aosp
  path: frameworks/base/services/core/java/com/android/server/wm/WindowManagerConstants.java
- type: aosp
  path: frameworks/base/core/java/android/view/WindowInsets.java
- type: aosp
  path: frameworks/base/core/java/android/window/OnBackInvokedCallback.java
- type: aosp
  path: frameworks/base/core/java/android/window/OnBackAnimationCallback.java
- type: aosp
  path: frameworks/base/core/java/android/window/OnBackInvokedDispatcher.java
- type: aosp
  path: frameworks/base/core/java/android/window/WindowOnBackInvokedDispatcher.java
- type: aosp
  path: frameworks/native/services/inputflinger/include/InputTracingPerfettoBackend.h
- type: official
  path: https://developer.android.com/develop/ui/views/touch-and-input/gestures/gesturenav
- type: official
  path: https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture
- type: official
  path: https://developer.android.com/about/versions/16/behavior-changes-16
- type: official
  path: https://developer.android.com/reference/android/window/OnBackInvokedDispatcher
- type: official
  path: https://developer.android.com/reference/android/window/OnBackInvokedCallback
- type: official
  path: https://developer.android.com/reference/android/window/OnBackAnimationCallback
- type: official
  path: https://developer.android.com/reference/android/view/WindowInsets
- type: official
  path: https://developer.android.com/reference/androidx/activity/OnBackPressedCallback
- type: official
  path: https://perfetto.dev/docs/getting-started/system-tracing
- type: official
  path: https://perfetto.dev/docs/data-sources/frametimeline
- type: aosp
  path: frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/back/ShellBackAnimationRegistry.java
- type: aosp
  path: frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/back/BackAnimationRunner.java
- type: aosp
  path: frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/dagger/back/ShellBackAnimationModule.java
- type: aosp
  path: frameworks/base/services/core/java/com/android/server/wm/BackNavigationController.java
- type: aosp
  path: frameworks/base/core/java/android/window/BackNavigationInfo.java
- type: aosp
  path: frameworks/base/core/java/android/app/Activity.java
- type: aosp
  path: frameworks/base/core/java/android/view/ImeBackAnimationController.java
- type: aosp
  path: frameworks/base/core/java/android/window/ImeBackCallbackSender.java
- type: aosp
  path: frameworks/base/core/java/android/window/ImeBackCallbackProxy.java
tags:
  - gesture-navigation
  - input-monitor
  - back-gesture
  - predictive-back
  - edge-swipe
  - systemui
  - windowinsets
  - input
related_chapters:
- '3.1'
- '3.2'
- '2.3'
- '1.1'
- '22.6'
- '1.19'
- '8.1'
last_consolidated_at: '2026-08-24'
consolidated_from:
- src/part1-fundamentals/ch03-input/03-gesture-navigation.md
- src/part1-fundamentals/ch03-input/07-predictive-back-system-architecture.md
---

# 系统手势导航与 Predictive Back

一个返回手势从屏幕边缘滑入开始，需要依次经过边缘区域识别、导航策略裁决，才会转变为窗口转场或应用回调；而 Predictive Back（预测性返回）进一步将返回流程拆分为开始、进度、取消与提交四个阶段，使系统动画与应用导航状态保持同步。

> 源码基线：AOSP `android-17.0.0_r1`。

## 系统手势识别与窗口路由

### 为什么要了解手势导航

在 Perfetto 跟踪中，当看到应用窗口的触摸事件流突然以 `ACTION_CANCEL` 中断，或者从某一时刻起不再收到后续 `MOVE` 事件时，这未必是应用自身的问题。左右边缘的返回手势启动时，SystemUI（系统界面进程）的手势监视通道（gesture monitor）与应用窗口会并行接收同一条指针事件流（pointer stream）。一旦系统确认当前滑动符合返回手势条件，便会调用 `pilferPointers()` 抢占后续指针，将事件流转交给手势处理方，同时向原目标窗口下发取消事件。下文将这一接管动作简称为“指针抢占”。

从 Android 10（API 29）引入全手势导航开始，从左右边缘向内滑动对应返回操作，底部上滑及横向滑动则负责回到主屏（Home）、进入最近任务或快速切换应用。由于边缘返回采用“并行观察、达标后接管”的模式，在 `ACTION_DOWN` 到来之前，系统并不会预先把边缘触摸挡在应用之外。排查手势冲突与返回输入延迟时，都需要从这一时序机制出发。

自 Android 13（API 33）起引入的预测性返回（Predictive Back）API 则增加了一个预提交阶段：手指滑动过程中，系统先解析返回目的地、分发进度并驱动预览动画，直到松手时才决定提交或取消。Android 15 将返回主屏（back-to-home）、跨任务（cross-task）和跨 Activity（cross-activity）三类系统动画移出了开发者选项；Android 16 进一步将它们设为 `targetSdkVersion >= 36` 应用的默认行为。

### Android 10+ 手势导航的系统实现

#### 组件分工

边缘手势的入口依然位于 SystemUI 的 `EdgeBackGestureHandler`，具体职责拆分给以下几个协作组件：

- `EdgeBackGestureHandler` 维护导航模式、主屏排除区域、边缘宽度、方向与阈值状态，并把事件送往反馈插件和 WM Shell。WM Shell 是窗口管理组件中承载系统级任务动画和窗口转场（Transition）的部分。
- `DisplayBackGestureHandlerImpl` 为每块显示屏持有输入监视器、`InputEventReceiver`、排除区域监听器和一个 `BackPanelController`。
- `InputMonitorCompat("edge-swipe", displayId)` 调用 `InputManagerGlobal.monitorGestureInput()`，取得手势监视器使用的 `InputChannel`。
- `BackPanelController` 和 `BackPanel.kt` 负责边缘箭头和面板动画；它们使用不可触摸的 `TYPE_NAVIGATION_BAR_PANEL` 受信任叠加层（trusted overlay），不靠这个窗口接收触摸。
- `BackAnimationController` 位于 WM Shell，负责 `startBackNavigation()`、目标解析、指针抢占、进度回调以及提交后的系统动画。

在初始化时，`updateIsEnabledInner()` 会注册主屏的 `ISystemGestureExclusionListener`，再遍历当前显示屏创建 `DisplayBackGestureHandlerImpl`。不过 Android 17 仍将边缘返回识别限定在主显示屏：`isWithinTouchRegion()` 对 `ev.getDisplayId() != mMainDisplayId` 直接返回 `false`，源码旁仍保留着 `TODO(b/382130680)`。因此，排查外接显示屏的返回手势时，不能只看监视器生命周期，还需对照这条主屏判定条件。

早期版本中的 `InputMonitorResource`、`resetEdgeBackPlugin()` 与 `NavigationBarEdgePanel` 均已退出主路径。

#### 从并行观察到指针抢占

`InputMonitorCompat` 负责建立监视通道，`DisplayBackGestureHandlerImpl` 再使用指定的 `Looper` 和 `Choreographer` 创建 `InputEventReceiver`。这两个组件只负责接入事件流，返回手势能否成立以及何时接管则由上层状态机决定。

按事件到达的时间顺序，触摸判定依次经过以下步骤：

1. `ACTION_DOWN` 到来时，检查导航模式、SystemUI 状态、底部手势区、画中画（PiP）和桌面模式排除区、应用排除区、左右边缘宽度及设备类型。
2. 资格成立后，事件才会送入 `BackPanelController`；如果启用了提前返回分发（ahead-of-time back dispatch），还会送入 WM Shell 的 `BackAnimation.onBackMotion()`。这里的“提前”是指在松手提交前就开始解析返回目标并产生手势进度。
3. 阈值之前，以下任一情况都会取消候选返回手势：纵向位移先超过 `mTouchSlop`、停留超时或出现第二根触点。
4. 横向位移大于纵向位移并超过 `mTouchSlop` 后，`mThresholdCrossed` 变为 `true`。
5. 旧式分支此时由 `EdgeBackGestureHandler` 直接调用 `pilferPointers()`；提前分发分支调用 `BackAnimation.onThresholdCrossed()`，由 `BackAnimationController` 决定何时抢占指针，判断依据包括描述返回目标和动画能力的 `BackNavigationInfo`、系统动画是否可用以及应用如何生成进度。

`pilferPointers()` 最终在 `InputDispatcher`（输入分发器）中生效：原目标窗口会收到由分发器合成的 `ACTION_CANCEL`，手势监视器则继续接收后续事件。因此，监视器拿到事件副本并不意味着应用还能收到完整手势，两者之间隔着一次指针抢占。

#### 旧式与提前分发两条提交路径

下面的流程图展示了两条提交路径的分叉点：

<!-- gracker-diagram: ch03-03-legacy-and-ahead-routing -->
![提前解析返回目标可以早于手势识别阈值](../../assets/diagrams/ch03/ch03-03-legacy-and-ahead-routing.png)

图：SystemUI 与应用先并行观察指针流，候选成立后按是否连接 BackAnimation 分流。legacy 越过阈值后直接 pilfer，提交时注入 BACK；提前分发可在首次 MOVE 就解析 BackNavigationInfo，之后根据阈值、目标和进度生成能力决定抢占与预览。两条路径都可能让原应用收到 CANCEL。

左侧的旧式（legacy）分支在 Android 17 源码中依然是明确的回退路径，并未随 Android 10–12 退役。当 `mBackAnimation == null` 时，手势越过阈值后由 SystemUI 抢占指针，待 `BackPanelController` 判定提交后，`triggerBack()` 会注入 `KEYCODE_BACK` 的按下与抬起事件。

右侧走的是提前分发路径：`ACTION_DOWN` 与 `MOVE` 经 `dispatchToBackAnimation()` 切到 Shell 执行器，`BackAnimationController` 调用 `IActivityTaskManager.startBackNavigation()` 获取 `BackNavigationInfo`，据此决定启用系统动画控制器还是应用回调。其中的 `setTriggerBack(true)` 仅记录“松手后提交”的状态；直到收到 `ACTION_UP`，Shell 才会执行 `onBackInvoked()` 或启动提交后动画，若手势取消则执行 `onBackCancelled()`。一旦未能取得有效的 `BackNavigationInfo`，源码同样保留了注入返回键的兜底逻辑。

预测性返回（Predictive Back）分支也会触发指针抢占，具体时机由 `BackAnimationController.tryPilferPointers()` 控制：使用系统动画控制器、应用侧无法生成进度、焦点发生变化或导航信息为空等情况，均可能触发抢占。因此，在系统跟踪中区分旧式返回与预测性返回时，单看 `ACTION_CANCEL` 并不足够，还需要结合 WM Shell 的返回动画与回调轨道共同确认。


### 手势冲突处理：系统手势优先区域与应用的 WindowInsets

当应用将交互控件布置在屏幕边缘时，便会与系统手势争夺触摸区域，冲突主要集中在左右返回边缘以及底部主屏、快速切换区域。应用可以通过 `View.setSystemGestureExclusionRects()` 声明需要优先响应的区域，但可排除的范围存在配额上限，而强制系统手势区域（mandatory system gesture）则始终保留给系统。

#### 系统手势排除区域

应用在屏幕边缘放置侧滑抽屉、滑块或画布手势时，可以调用 `View.setSystemGestureExclusionRects()` 上报局部矩形。矩形坐标以该 View 布局后的局部坐标为准，View 发生移动或尺寸变化时需要重新计算。

下面的示例仅排除抽屉把手实际占用的左侧区域：

```kotlin
override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
    super.onLayout(changed, l, t, r, b)
    val exclusionRect = Rect(0, drawerHandleTop, drawerHandleWidth, drawerHandleBottom)
    setSystemGestureExclusionRects(listOf(exclusionRect))
}
```

这些矩形随后会进入系统侧的收集与裁剪链路：`ViewRootImpl` 中的 `ViewRootRectTracker` 收集各 `View` 的矩形，将其转换到窗口坐标后通过 `WindowSession.reportSystemGestureExclusionChanged()` 上报。WindowManagerService（WMS，窗口管理服务）的 `DisplayContent.calculateSystemGestureExclusion()` 会结合窗口 Z 序、可触摸区域与显示坐标进行汇总，再经 `ISystemGestureExclusionListener` 将受限后的 `Region` 通知 SystemUI。也就是说，应用上报成功只代表 WMS 收到了请求，最终生效范围还要经过可触摸区域相交与高度配额裁剪。

#### 系统手势区域限制

高度配额由 `mSystemGestureExclusionLimit` 控制，它限制的是左右边缘各自可排除的**纵向总高度**，矩形的横向宽度不受此限。`WindowManagerConstants` 保证该限值至少为 200 dp，设备也可以通过 `system_gesture_exclusion_limit_dp` 配置更大的额度。`addToGlobalAndConsumeLimit()` 会对与边缘相交的矩形逐个扣除高度预算，超出部分将被裁掉。

WMS 会同时保留受限区域（restricted `Region`）与原始未受限区域（unrestricted `Region`）。SystemUI 依据受限区域决定是否让出手势；如果触点只命中未受限区域，说明应用虽然申请过排除，但该段区域未能获得配额，系统依然会识别返回手势，并将此次请求记为被拒绝的排除请求（rejected exclusion）。遇到“同一条侧边上部分区域不触发返回、另一部分却依然触发”的情况时，需要联合检查纵向高度预算、窗口遮挡与最终获批区域。

<!-- gracker-diagram: ch03-03-exclusion-request-to-grant -->
![排除矩形先转换坐标，再经过相交与每侧高度预算](../../assets/diagrams/ch03/ch03-03-exclusion-request-to-grant.png)

图：应用提供 View 局部矩形，ViewRootImpl 收集并转换到窗口坐标，上报 WMS。DisplayContent 再按窗口 Z 序、可触摸区域和显示坐标汇总，消耗左右边缘各自的纵向总高度配额。SystemUI 使用最终受限 Region；仅申请过但未批准的片段仍可触发系统返回。

部分系统窗口可以豁免排除区域的高度配额，第三方应用窗口在特定条件下也能获得豁免：`DisplayContent.needsGestureExclusionRestrictions()` 对请求隐藏导航栏且采用 `BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE` 的窗口不施加高度限制。不过这类窗口仍需主动上报排除矩形，且获批范围依旧受限于可触摸区域与窗口遮挡裁剪。这一条件对应的正是粘性沉浸模式（sticky immersive），即系统栏短暂滑出后会自动重新隐藏。

此外，`WindowState.isImplicitlyExcludingAllSystemGestures()` 还保留了一条隐式排除兼容分支：当窗口满足上述粘性沉浸条件、应用 `targetSdkVersion < 29` 且 `mSystemGestureExcludedByPreQStickyImmersive` 配置开启时，WMS 会直接将窗口可触摸区域作为排除区域。当导航栏处于临时显示状态时，`EdgeBackGestureHandler` 会优先允许返回边缘内的候选手势，不再受应用排除区阻挡。

#### WindowInsets 与手势区域

Android 将系统手势区分为常规手势区域与强制手势区域两层：

- `WindowInsets.Type.systemGestures()` 描述系统手势具有优先级的区域，通常包含左右返回边缘和底部手势区。应用可以在非强制部分申请有限排除。
- `WindowInsets.Type.mandatorySystemGestures()` 标出的是其中系统必须保留的子集，`setSystemGestureExclusionRects()` 覆盖不到。旧方法 `getMandatorySystemGestureInsets()` 自 API 30 起由 `getInsets(Type.mandatorySystemGestures())` 取代。

与侧边返回不同，底部主屏和快速切换手势不支持通过局部矩形申请排除。若游戏确实需要全屏边缘交互，可以在游玩期间切入沉浸模式（immersive mode），此时用户依然能通过系统规定的边缘手势重新呼出系统栏；而对于普通应用页面，更稳妥的做法是将横向滑动控件移出 `systemGestures()` 区域，把有限的排除配额留给无法避开边缘的关键交互。

### 从返回手势到预测性返回动画

#### 传统返回手势的问题

在早期返回手势模型中，用户在松手前只能看到屏幕边缘的箭头提示，无法提前感知返回后的目标界面；系统通常直到松手提交的瞬间才派发返回信号，应用也因此习惯把所有返回逻辑集中在 `onBackPressed()` 或 `KEYCODE_BACK` 中一次性处理。

预测性返回补上了松手前的预提交阶段：WM Shell 在手势滑动过程中就会调用 `startBackNavigation()` 获取目标类型与回调，并按实时进度驱动当前窗口、目标窗口或应用自定义动画。对应用而言，这意味着需要把“跟随手势的视觉预览”和“确认提交后的导航状态变更”拆分成两个独立步骤。

#### 预测性返回的回调模型

预测性返回回调分为平台原生 API 与 AndroidX 兼容层两套接口：

| 层级 | 接口 | 引入版本 | 可直接确认的方法 | 作用 |
| --- | --- | --- | --- | --- |
| 平台提交回调 | `OnBackInvokedCallback` | API 33 | `onBackInvoked()` | 返回提交后收到通知，没有进度方法。 |
| 平台进度回调 | `OnBackAnimationCallback` | API 34 | `onBackStarted()`、`onBackProgressed()`、`onBackCancelled()`、`onBackInvoked()` | 可接收开始、进度、取消和提交事件。 |
| AndroidX 兼容层 | `OnBackPressedCallback` | `androidx.activity:activity` 1.0.0；进度方法在 1.8.0 增加 | `handleOnBackPressed()`；`handleOnBackStarted()`、`handleOnBackProgressed()`、`handleOnBackCancelled()` | 提供向下兼容入口。只有框架 API 34+ 才会由系统驱动后三个进度相关方法。 |

平台回调通过 `OnBackInvokedDispatcher` 注册，AndroidX 回调则由 `OnBackPressedDispatcher` 管理。由于 `OnBackInvokedCallback` 仅提供提交通知，需要响应开始、进度与取消事件时，应实现 `OnBackAnimationCallback`，或使用 AndroidX、Navigation、Compose 对应的封装 API。

同时，`android:enableOnBackInvokedCallback` 的语义会随目标 SDK 版本变化。在 Android 15 及更早版本中，该属性用于显式声明加入提前分发模型；从 Android 16 起，运行在 Android 16+ 且 `targetSdkVersion >= 36` 的应用会默认启用该模型，不过仍可通过设为 `false` 临时退出。该属性与 AndroidX `OnBackPressedCallback.enabled` 控制的是不同层级的开关，回调的生命周期注册与注销仍需单独维护。

#### 版本演进的时间线

| Android 版本 | API | 系统动画状态 | 清单与 Activity 条件 | `targetSdkVersion` 与兼容边界 | 回调与预览范围 |
| --- | --- | --- | --- | --- | --- |
| Android 13 | 33 | 通过开发者选项测试预测性返回动画。 | 应用或 Activity 通过 `android:enableOnBackInvokedCallback` 显式加入。 | `OnBackInvokedCallback` 从 API 33 可用。 | 返回主屏是主要测试入口；提交回调没有进度信息。 |
| Android 14 | 34 | 系统动画测试仍依赖开发者选项。 | 延续显式加入模型。 | `OnBackAnimationCallback` 从 API 34 可用；AndroidX 1.8.0 可转发进度。 | 应用能收到开始、进度和取消事件。 |
| Android 15 | 35 | 开发者选项移除；已加入的应用或 Activity 可以显示返回主屏、跨任务和跨 Activity 动画。 | 仍需迁移到受支持的返回 API；根 Activity 的消费型回调会阻止返回主屏预览。 | 目标 SDK 版本不是唯一条件。 | 系统预览范围扩展到三类系统转场。 |
| Android 16 | 36 | 在 Android 16+ 设备上，目标版本为 36+ 的应用默认启用三类系统动画。 | 可暂时用 `android:enableOnBackInvokedCallback="false"` 退出。 | 目标版本为 36+ 时，旧 `onBackPressed()` 不再调用，`KEYCODE_BACK` 不再分发给应用；三键导航也可接入预测性返回。 | 新增 `PRIORITY_SYSTEM_NAVIGATION_OBSERVER`；API 36 只允许注册一个观察者回调。 |
| Android 17 | 37 | 延续目标版本为 36+ 时的默认模型与三类系统动画。 | 退出开关仍应只作迁移缓冲，业务返回使用 AndroidX 或平台返回 API。 | `PRIORITY_SYSTEM_NAVIGATION_OBSERVER` 已是没有 `@FlaggedApi` 标记的公共常量。 | 观察者回调数量不再受 API 36 的单实例限制，多个回调的调用顺序未定义。 |

API 37 中观察者优先级的值为 `-2`。虽然普通注册参数声明了非负范围约束，但 `WindowOnBackInvokedDispatcher.Checker` 对该常量作了专门放行。观察者仅在系统即将执行默认导航时接收通知，本身不会消费返回事件，适合用于记录日志与埋点统计；由于多个观察者之间的调用顺序未作定义，业务代码应避免依赖其执行顺序。

#### 预测性返回对性能的影响

1. 进度回调每帧都可能执行。优先更新 `translationX`、`alpha`、缩放比例或已准备好的动画状态，避免在 `onBackProgressed()` 中做 I/O、Binder 同步调用、复杂布局或创建大量对象。
2. 跨 Activity、跨任务和返回主屏（back-to-home）会同时涉及当前层、目标层和 Shell 动画。掉帧时要检查当前应用、目标 Activity 或 Launcher、WM Shell、SurfaceFlinger，单看当前 Activity 的 RenderThread 是不够的。
3. 只在提交时改变导航状态。若在进度阶段就执行 `popBackStack()` 或 `finish()`，取消手势时很难恢复一致状态。
4. 观察者回调适合记录轻量日志。它不消费返回事件，但仍运行在应用回调环境中，耗时工作应异步化。

### 边缘滑动检测的性能敏感点

#### 先找对 SystemUI 线程

分析边缘手势的耗时时，第一步是找对手势判定所在的线程。`DisplayBackGestureHandlerImpl` 和 `EdgeBackGestureHandler` 使用带有 `@BackPanelUiThread`（采用 `THREAD_PRIORITY_DISPLAY` 对应的显示相关线程优先级）的 `UiThreadContext`，`SysUIConcurrencyModule` 再根据 `Flags.edgeBackGestureHandlerThread()` 将其映射到独立的 `BackPanelUiThread` 或 SystemUI 主线程。因此，在分析性能跟踪时需先核实当前设备将手势判定调度到了哪条线程，而不能直接假定所有判定都落在 SystemUI 主线程上。

在跟踪中，可以先根据线程名以及 `InputConsumer processing on...` 等接收器轨迹区段确认事件所在线程，再检查该线程从 `ACTION_DOWN` 到阈值越过期间是否被长任务、锁等待或 Binder 调用阻塞。由于 `EdgeBackGestureHandler` 没有为每个输入事件打上固定的同名区段，必要时可在可控调试构建中添加自定义跟踪点。

在越过阈值之前，代码还需先后校验排除区、SystemUI 状态标志、PiP、桌面模式角区、手势阻塞 Activity 以及可选的机器学习（ML）分类等逻辑。这些路径均处于交互热路径上，必须保持轻量，避免混入同步 I/O。

#### 长按超时的影响

手势判定中还设有一个长按超时限制：`mLongPressTimeout` 取 `min(gestures.back_timeout, ViewConfiguration long-press timeout)`。只有在尚未越过横向阈值时，若某个 `ACTION_MOVE` 的 `eventTime - downTime` 超过该上限，候选返回手势才会被取消。`gestures.back_timeout` 的 AOSP 默认值为 250 ms（有别于常见的 400–500 ms 估算），设备厂商可通过系统属性调整该上限，现场排查时应以 `dumpsys` 与设备配置为准。

#### 多指触控的取消

`ACTION_POINTER_DOWN` 仅在 `mThresholdCrossed == false` 且输入非三指触控板返回时才会取消候选手势；一旦越过横向阈值，该取消分支便不再触发。复现“第二根手指取消返回”的问题时，需要准确记录第二指落下与阈值越过的先后时序。

#### 方向、阈值与 ML 分类

方向识别阈值计算为 `scaledTouchSlop * back_gesture_slop_multiplier`，其中 `back_gesture_slop_multiplier` 的 AOSP 默认值为 `0.75f`。在越过阈值前，若 `dy > dx` 且 `dy > mTouchSlop`，手势会因纵向滑动而取消；若 `dx > dy` 且 `dx > mTouchSlop`，才会正式进入返回流程。

部分设备在边缘命中判定中还会启用 `BackGestureTfClassifierProvider`。该模型仅在系统配置与 DeviceConfig 均允许时加载，推理特征包括屏宽、距边缘距离、左右侧、前台包词表索引与 y 坐标。因此，排查边缘“同一位置偶发不响应”时，需要同步记录灵敏度设置、内边距、排除区、前台应用包名与 ML 开关状态，仅对比手指物理位移并不足以定位根因。

#### 动画渲染的开销

边缘箭头反馈由 `BackPanelController` 和 `BackPanel.kt` 负责绘制，窗口类型为 `TYPE_NAVIGATION_BAR_PANEL`。它与 WM Shell 驱动的目标页面预览分属两层不同的动画：前者是贴近手指边缘的指示箭头，后者是当前任务与返回目的地的窗口转场。边缘箭头动画流畅只说明第一层绘制正常，预测性返回的目标预览仍需单独核查。

### 在 Perfetto 中的表现

在边缘手势与返回动画链路上，Perfetto 主要用于还原事件何时被读入、发往哪些窗口、由哪条线程消费以及哪些渲染帧错过了截止时间；而手势排除矩形最终获批的几何范围无法直接从通用 atrace 轨迹还原，这部分需要结合 `dumpsys window` 或 Winscope 状态补充核对。

#### 最小抓取配置

在量产版 `user` 构建上，可以使用官方快速入门文档支持的 atrace 类别抓取线程调度、输入、窗口与图形基线：

```bash
adb shell perfetto -o /data/misc/perfetto-traces/back-gesture.perfetto-trace -t 15s \
  sched freq idle am wm gfx view binder_driver input
adb pull /data/misc/perfetto-traces/back-gesture.perfetto-trace
```

这种简写命令适合快速确认线程调度是否繁忙以及动画是否掉帧，但不会记录完整的逐事件指针分发明细。

在 `userdebug` 或 `eng` 设备上，如果需要逐事件确认应用与 `edge-swipe` 监视器之间的分发关系，可以启用结构化输入数据源并配合 FrameTimeline：

```protobuf
buffers {
  size_kb: 32768
  fill_policy: RING_BUFFER
}
duration_ms: 15000

data_sources {
  config {
    name: "linux.ftrace"
    ftrace_config {
      ftrace_events: "sched/sched_switch"
      ftrace_events: "sched/sched_waking"
      atrace_categories: "input"
      atrace_categories: "wm"
      atrace_categories: "gfx"
      atrace_categories: "view"
      atrace_apps: "com.android.systemui"
      atrace_apps: "your.package.name"
    }
  }
}
data_sources {
  config {
    name: "android.surfaceflinger.frametimeline"
  }
}
data_sources {
  config {
    name: "android.input.inputevent"
    android_input_event_config {
      mode: TRACE_MODE_TRACE_ALL
    }
  }
}
```

将该配置保存为 `back-gesture.pbtxt` 后，通过 `adb shell perfetto --txt -c - -o ... < back-gesture.pbtxt` 执行录制。由于 `TRACE_MODE_TRACE_ALL` 会绕过调试构建上的隐私裁剪并记录完整坐标与按键内容，仅适用于本地受控复现；现场或用户数据采集必须改用 `TRACE_MODE_USE_RULES` 配置脱敏级别。

Perfetto 的查询引擎 Trace Processor 在 `android.input` 模块中提供了 `android_motion_events` 与 `android_input_event_dispatch` 视图，可通过 `event_id` 将 `MotionEvent` 与窗口分发目标关联起来。此外，`InputMonitorCompat` 自身还会写入 `InputMonitorCompat-edge-swipe-dispN created/receiver created/disposed` 瞬时事件，用于记录监视器的生命周期，单次手势未必存在同名的持续区段。

#### 1. 旧式返回手势：检查取消事件和按键注入链

1. 用结构化输入事件的 `event_id` 确认初始触摸同时分发到前台窗口和手势监视器。
2. 在阈值附近寻找原窗口的 `ACTION_CANCEL`，并检查 SystemUI 对应线程是否正在处理该手势。
3. 提交后查找注入的 `KEYCODE_BACK` 及其后续窗口分发。
4. 若原窗口收到完整指针事件流且没有 `ACTION_CANCEL`，检查是否未命中返回边缘、命中了最终获批的排除区域，或未达到方向阈值。仅命中未获批的排除申请不会阻止系统返回。

#### 2. 预测性返回：检查进度回调和目标层预览

1. 先梳理 `ACTION_DOWN`、`MOVE` 到 Shell `startBackNavigation()` 的时序，再确认阈值越过点。
2. 通过 FrameTimeline 和 SurfaceFlinger 轨迹区分当前 Activity、目标 Activity 或 Launcher。不同返回类型不保证出现相同数量的 Surface。
3. 应用自定义进度回调没有系统统一的轨迹区段名，可为 `onBackStarted()`、`onBackProgressed()`、`onBackCancelled()` 添加应用自己的 `Trace.beginSection()`，再与 Shell 和帧时间线对齐。
4. `ACTION_CANCEL` 单独出现不足以说明走的是旧式路径，Shell 分支同样可能抢占指针。
5. 提交后通常走 `onBackInvoked()` 和系统转场；只有导航信息为空等兜底条件才可能再次看到注入的返回键。

#### 3. 排除区冲突的三组对照

排查排除区冲突时，需要将以下三组证据放到同一次复现中交叉核对：

- 应用记录的矩形与 `WindowInsets.Type.systemGestures()`、`mandatorySystemGestures()`；
- 应用日志中的请求矩形、`dumpsys window` 的 `mSystemGestureExclusion` 最终显示区域，以及 SystemUI 转储中的受限与未受限区域；
- Perfetto 中该指针事件流是否被抢占，以及 SystemUI 判定线程是否及时运行。

由于应用传给 `setSystemGestureExclusionRects()` 的列表只是申请请求，WMS 最终批准的区域大小仍需通过窗口转储确认，而 Perfetto 本身也无法还原所有矩形的布局坐标，因此必须将系统状态转储与性能跟踪结合验证。

### 与其他章节的关系

- **3.1 Input 事件分发全流程**：这里的手势监视器、监视窗口（spy window）、指针抢占和取消事件，都建立在 InputDispatcher 的窗口目标模型上。
- **3.2 触摸响应的性能分析**：结构化输入事件可把 `InputReader` 读取、`InputDispatcher` 分发、窗口投递与应用消费时刻放在同一条链上。
- **2.3 VSync 机制**、**2.3 Choreographer 与渲染流水线**：边缘反馈和预测性预览都受帧节拍约束，FrameTimeline 用来确认帧是否错过截止时间。
- **1.1 线程模型**：Android 17 的边缘判定线程可能是 `BackPanelUiThread`，也可能回退到 SystemUI 主线程；WM Shell 和应用回调还有各自的执行上下文。


## Predictive Back 生命周期与动画同步

预测性返回将一次返回操作拆分为“手势预览”与“提交导航”两个阶段，后续的生命周期时序与动画同步问题都围绕这一拆分展开。手指滑动期间，系统与应用只更新可撤销的视觉状态；直到手势确认提交，返回回调才会执行 `finish()`、弹出返回栈（pop back stack）或隐藏输入法等不可逆操作。由于预测性返回需要持续传递进度并支持中途取消，应用导航栈与系统窗口动画必须对齐到同一个提交时点。

这一模型让系统得以提前感知返回目的地，但也衍生出三条容易混淆的执行路径：

- 应用回调处理页面内部返回；
- WM Shell 在系统目标可预测且产品提供对应动画执行器时，对关闭对话框（dialog）、跨 Activity、跨任务和返回主屏执行系统动画；
- 条件不足时回退到应用回调，极端情况下再回退到 `KEYCODE_BACK`。

应用侧的具体接入方式见 22.11，边缘手势识别逻辑见本节前文。

### 1. 先建立正确的阶段模型

#### 1.1 预提交与提交后

`OnBackAnimationCallback` 的四个回调方法对应两类性质截然不同的工作：

| 回调 | 所属阶段 | 合适的工作 |
|---|---|---|
| `onBackStarted()` | 预提交 | 保存起始状态，准备轻量动画对象 |
| `onBackProgressed()` | 预提交 | 根据手势进度更新可撤销的属性 |
| `onBackCancelled()` | 取消 | 把视觉状态恢复到起点 |
| `onBackInvoked()` | 已提交 | 执行导航、关闭容器或提交业务状态 |

这条阶段界线非常关键：如果在 `onBackProgressed()` 中提前结束 Activity、弹出 Fragment 或写入数据库，一旦用户取消手势，状态就难以恢复一致。系统动画同样遵循这一约束：手势滑动阶段仅通过 SurfaceControl 动画控制柄（leash）变换图层几何属性，直到松手提交后才触发真实回调，并将预览无缝接入正式的窗口转场。leash 允许动画执行者控制窗口图层变换，但不会移交窗口 Surface 本身的所有权。


#### 1.2 返回目的地与动画执行者

`BackNavigationInfo` 是 `system_server` 返回给 WM Shell 的目的地与动画能力描述，定义了以下主要类型：

| 类型 | 含义 | 常见动画执行者 |
|---|---|---|
| `TYPE_CALLBACK` | 应用或输入法回调接管 | 应用进程的回调 |
| `TYPE_DIALOG_CLOSE` | 关闭当前 Activity 上方的窗口 | 取决于产品是否注册动画执行器（runner） |
| `TYPE_CROSS_ACTIVITY` | 返回同一 Task 中的前一个 Activity | WM Shell |
| `TYPE_CROSS_TASK` | 返回前一个 Task | WM Shell |
| `TYPE_RETURN_TO_HOME` | 返回主屏 | Launcher 或产品注册的动画执行器 |
| `TYPE_IN_TRANSITION` | 当前已有窗口转场，暂不能准备 | 等转场空闲后重试 |
| `TYPE_TASK_ROOT_INTERCEPTION` | 根任务（Root Task）拦截返回 | 按系统覆盖规则处理 |

手势进度最终由谁来驱动，由上述类型与 `isPrepareRemoteAnimation()` 共同决定：当应用回调获胜时，系统不会叠加跨 Activity 系统动画；当系统转场获胜时，逐帧的 Surface 图层变换主要在 WM Shell 中执行。

### 2. 端到端架构

下面的流程图展示了 SystemUI、WM Shell、`system_server` 与应用之间的决策与动画分工。为表述简洁，下文将 ActivityTaskManagerService 简称为 ATMS，将 InputMethodManagerService 简称为 IMMS。

<!-- gracker-diagram: ch03-03-navigation-target-and-executor -->
![WMS 预测目的地，Shell 按能力选择动画执行者](../../assets/diagrams/ch03/ch03-03-navigation-target-and-executor.png)

图：SystemUI 把手势交给 Shell，Shell 经 ATMS 请求 WMS 的 BackNavigationController。WMS 读取焦点窗口 top callback，判断应用回调或系统目标；满足准备条件且产品有动画执行者时交付 RemoteAnimationTarget 与 leash。应用回调、系统 leash 动画和无有效信息时的按键兜底应分别取证。

图中的 `RemoteAnimationTarget` 是交付给 Shell 的窗口图层描述，携带了图层几何信息以及用于执行变换的 leash。整条链路中的核心协调职责由以下两个类承担：

- `BackNavigationController` 位于 `system_server`，负责确定焦点窗口、最高优先级回调、返回目标和可动画性，并准备 WindowContainer 与 Transition 侧资源；
- `BackAnimationController` 位于 WM Shell，负责手势状态、指针抢占、远程动画就绪状态、进度分发以及提交后的收尾。

此外，Android 17 的 WMS 中并不存在 `TaskAnimationCoordinator` 类，上述跨 Activity、跨任务及任务快照协调均由这两个控制器直接衔接完成。


### 3. 输入事件怎样到达返回动画

#### 3.1 InputDispatcher 与分流决策

`EdgeBackGestureHandler` 借助系统输入监视通道观察边缘指针事件流，判断手势是否符合起点、方向、排除区域与阈值条件。在这条路径中，`InputDispatcher` 承担的是事件路由与旁路输入监视职责，至于当前手势究竟属于旧式返回还是预测性返回进度，则交由下游的返回处理逻辑裁决。

当 SystemUI 已经连接 WM Shell 的 `BackAnimation` 时，事件会按以下顺序流转：

1. `ACTION_DOWN`、`ACTION_MOVE`、`ACTION_UP` 或 `ACTION_CANCEL` 被转给 `BackAnimationController.onBackMotion()`；
2. Shell 在第一次 `ACTION_MOVE` 时启动返回导航，让按下指针导致的焦点变化有机会先完成；
3. 手势越过阈值后，Shell 按配置调用 `pilferPointers()`，从原接收者接管后续指针；
4. 松手时根据 `triggerBack` 进入提交或取消。

需要留意的是，`EdgeBackGestureHandler.mBackAnimation` 是否为空反映的是 SystemUI 与 WM Shell 的功能连接状态，与当前应用是否在清单中显式声明开启新模型属于两码事；判断应用本身是否启用新返回模型，主要看窗口是否向 WMS 注册了相应回调。

#### 3.2 仍然存在 KEYCODE_BACK 回退

提前返回分发（ahead-of-time）路径同样保留了异常兜底。例如，`startBackNavigation()` 因找不到有效焦点窗口、当前状态无法构建 `BackNavigationInfo` 或系统正处于不兼容状态而返回 `null` 时，Shell 仍可在手势提交后异步注入 `KEYCODE_BACK`。

这是一条兜底分支。对于 `targetSdkVersion >= 36` 且未显式退出新模型的应用，常规返回已全部经由回调分发；官方文档也明确说明，在这类应用上 `Activity.onBackPressed()` 与返回 `KEYCODE_BACK` 不再作为正常分发入口。

### 4. 窗口回调如何进入 WMS

#### 4.1 每个窗口只向 WMS 暴露最高优先级回调

`WindowOnBackInvokedDispatcher` 在应用进程内维护注册的回调集合。每当最高优先级回调发生变化时，它便将 `OnBackInvokedCallbackInfo` 通过 `IWindowSession.setOnBackInvokedCallbackInfo()` 同步给对应的 `WindowState`。该结构包含以下核心信息：

- 回调的 Binder 接口；
- 优先级；
- 是否实现 `OnBackAnimationCallback`；
- 是否请求系统覆盖行为。

借助这层本地收敛，WMS 无需遍历应用内的全部回调列表，只需读取当前窗口已经选出的最高优先级回调即可。

#### 4.2 优先级与同级顺序

关键优先级常量共有四个：

| 常量 | 值 | 用途 |
|---|---:|---|
| `PRIORITY_OVERLAY` | `1_000_000` | 菜单、抽屉等应先关闭的覆盖层 |
| `PRIORITY_DEFAULT` | `0` | 普通应用回调 |
| `PRIORITY_SYSTEM` | `-1` | 框架内部默认导航回调 |
| `PRIORITY_SYSTEM_NAVIGATION_OBSERVER` | `-2` | 只观察系统导航，不消费 |

分发时高优先级优先执行，同一优先级内则按注册顺序逆序匹配。普通应用无法注册负优先级的常规回调，仅 `PRIORITY_SYSTEM_NAVIGATION_OBSERVER` 是专门开放的例外：API 36 对观察者数量仍有限制，从 API 37 起则允许注册多个，且观察者均不会拦截或改变系统返回结果。

启用新模型后，`Activity` 会以 `PRIORITY_SYSTEM` 注册默认回调。只要应用注册了 `PRIORITY_DEFAULT` 或 `PRIORITY_OVERLAY` 回调，便会覆盖 Activity 的内部系统默认回调；若存在多个普通回调，则继续按优先级与同级后注册优先规则选出 top callback。只有当选出的 top callback 属于应用回调时，`BackNavigationController` 才会将本次导航归类为 `TYPE_CALLBACK`。

<!-- gracker-diagram: ch03-03-callback-priority-selection -->
![应用本地选 top callback，再把结果上报当前窗口](../../assets/diagrams/ch03/ch03-03-callback-priority-selection.png)

图：窗口分发器在应用进程维护普通回调，按优先级从高到低、同级后注册优先选出 top callback，再把 CallbackInfo 上报对应 WindowState。OVERLAY / DEFAULT 可以覆盖 Activity 的内部 SYSTEM 默认导航。SYSTEM_NAVIGATION_OBSERVER 不消费返回，API37 可有多个，观察者之间没有固定顺序。

#### 4.3 应用进程内的进度生成

为了减少逐帧跨进程调用的开销，系统还提供了一条进程内进度生成优化路径。只要同时满足以下条件，`BackNavigationInfo.isAppProgressGenerationAllowed()` 即可为 `true`：

- 当前回调实现了动画回调接口；
- 窗口允许应用在本进程生成进度；
- 手势可触摸区域与窗口区域匹配；
- 没有需要转交手势的嵌入窗口。

满足上述条件时，应用侧的 `ViewRootImpl` 会直接依据本地收到的 `MotionEvent` 更新 `BackTouchTracker` 与 `BackProgressAnimator`，Shell 则跳过相应的 Binder 进度分发；否则 Shell 仍会通过 `IOnBackInvokedCallback.onBackProgressed()` 跨进程发送进度。

因此，当在跟踪中看到应用回调逐帧运行时，未必意味着每一帧都经历了从 SystemUI 到 `system_server` 再到应用的完整 IPC 往返。

<!-- gracker-diagram: ch03-03-local-versus-binder-progress -->
![应用回调每帧运行，不代表每帧都跨进程发送进度](../../assets/diagrams/ch03/ch03-03-local-versus-binder-progress.png)

图：符合应用动画回调、窗口许可、触摸区域匹配且无需转交嵌入窗口等条件时，应用可根据本地 MotionEvent 生成进度，Shell 跳过对应 Binder 进度分发。其他条件下 Shell 经 IOnBackInvokedCallback 发送进度，应用 Handler 与 BackProgressAnimator 再驱动回调。

### 5. system_server 如何预测返回目标

在 `system_server` 中，`BackNavigationController.startBackNavigation()` 会在 WMS 全局锁下完成一轮快照式决策：

1. 找到目标显示屏的焦点窗口；必要时退到焦点任务的窗口；
2. 要求窗口已有有效绘制 Surface；
3. 检查当前是否处于不允许插入预测返回的窗口转场；
4. 读取窗口的 `OnBackInvokedCallbackInfo`；
5. 若应用回调获胜，直接返回 `TYPE_CALLBACK`；
6. 若框架系统回调获胜，再计算对话框、前一 Activity、前一 Task 或主屏；
7. 确认 Shell 声明支持该类型后，准备远程动画。

#### 5.1 放弃预览的回退条件

当存在以下任一条件时，系统会放弃对应的预览动画，回退到常规回调：

- 前一个 Activity 没有进程或窗口；
- Activity 尚未创建，作为跨 Activity 目标还不够安全；
- 参与者包含不适合该路径的透明 Activity；
- 锁屏（keyguard）、应用锁定、任务锁定或浮动任务条件不满足；
- 当前 Activity 使用场景转场（scene transition）；
- 多窗口模式下前后 Task 不在兼容的父层级。

这也说明了跨 Activity 与跨任务预测动画的一个重要前提：目标页面通常必须已经具备存活进程与窗口，系统不会为了生成预览而强行冷启动一个已死亡的目标进程。此时呈现出的普通回调或标准窗口转场属于安全回退机制，并非任务快照丢失。

#### 5.2 预览阶段的生命周期顺序

对于具备动画条件的目标，WMS 核心会创建 `TRANSIT_PREPARE_BACK_NAVIGATION`，收集打开与关闭两侧的 `WindowContainer`，并将前一 Activity 设为后置启动（launch-behind，即先在当前页面后方备妥目标窗口）或准备启动占位图层（starting surface）。若用户中途取消手势，这些临时状态会悉数恢复；只有手势确认提交后，才会由真实回调与正式窗口转场完成导航。

在生命周期时序上，应用代码需要留出兼容余地：`onPause()` 未必早于首个进度回调触发，输入焦点切换也未必恰好落在 `onPause()` 与目标 `onResume()` 之间，实际顺序会受到返回类型、目标可见性、窗口转场合并及窗口绘制进度的影响，应用仅能依赖公开的生命周期契约。

### 6. WM Shell 如何执行系统动画

#### 6.1 动画注册表与 `RemoteAnimationTarget`

`ShellBackAnimationRegistry` 按 `BackNavigationInfo` 类型索引并管理动画执行器。在 AOSP Android 17 的默认依赖注入（Dagger）模块中，系统会装配跨 Activity、跨任务与定制跨 Activity 动画执行器；返回主屏动画可由 Launcher 在运行时动态注册，关闭对话框的槽位默认仍为 `null`。

需要注意的是，`BackNavigationInfo` 返回了某种目标类型，仅表示 WMS 核心能够表达该目的地；产品侧实际是否具备对应的动画执行器，还必须经由 `BackAnimationAdapter.isAnimatable(type)` 确认。

WMS 核心准备就绪后，会将描述打开与关闭窗口图层的 `RemoteAnimationTarget` 及其 leash 交付给 Shell。手势滑动期间，Shell 每帧主要完成以下工作：

- 把触摸位移映射为手势进度；
- 计算打开和关闭图层的边界、缩放、位移、裁剪、圆角半径与透明度；
- 在同一个 `SurfaceControl.Transaction` 中写入目标 leash；
- 用当前 `Choreographer` 的 VSync ID 标记事务；
- 提交给 SurfaceFlinger 合成。

在此阶段，目标 Activity 无需每帧重新执行测量与布局；即便目标页面自身仍在绘制内容，其缓冲区更新与 Shell 对 leash 的图层变换也运行在两条各自独立的工作流上。

#### 6.2 提交后的顺序

手指松开后，导航流程会走向三种主要结局：

- 取消：当前动画执行器收到 `onBackCancelled()`，播放回弹并恢复目标；
- 回调路径：Shell 直接调用应用回调的取消或提交方法；
- 系统动画路径：Shell 启动提交后动画；跨 Activity、跨任务和返回主屏会在这一阶段开始时触发真实回调，让关闭转场与动画衔接，其他类型可在动画结束时再触发。

在 `invokeOrCancelBack()` 收尾阶段，如果持有 `IBackAnimationFinishedCallback`，Shell 会先通过 `onAnimationFinished()` 同步通知 WMS，再去调用尚未执行的真实回调。由于跨 Activity、跨任务和返回主屏路径已在 `startPostCommitAnimation()` 中提前触发真实回调（并用 `mRealCallbackInvoked` 防止重复调用），分析这些类型的提交时机时不能按收尾方法里的代码顺序推断。此外，系统通过看门狗（watchdog）防止动画执行器长期无响应：一旦动画完成或看门狗超时，Shell 就会释放动画目标、结束本次导航，并交由 `BackTransitionHandler` 衔接后续转场。

源码中 2 秒的 `MAX_ANIMATION_DURATION` 常量正是等待远程动画完成的看门狗阈值，用于兜底动画执行器未回调或严重滞后等异常情况，不应将其视为产品的动画时长或性能标准。

<!-- gracker-diagram: ch03-03-leash-content-and-postcommit -->
![系统预览改变 leash，应用内容与提交导航另行推进](../../assets/diagrams/ch03/ch03-03-leash-content-and-postcommit.png)

图：系统动画 runner 根据进度更新打开 / 关闭目标的 leash 几何，应用若继续生产内容则走独立 buffer 路径。松手取消要恢复预览；提交时 Shell 进入 post-commit、按类型触发真实回调并与 Transition 衔接。2 秒常量用于异常看门狗，不能当作动画时长。

### 7. 任务快照在预测返回中的角色

当同时满足以下组合条件时，系统可以为打开侧目标创建无窗口启动占位图层（windowless starting surface）：

- TaskOrganizer 支持无窗口启动占位图层；
- `config_predictShowStartingSurface` 开启；
- 当前策略没有直接采用 `launch-behind`；
- 存在与目标屏幕方向、夜间模式和组件兼容的 Task 或 Activity 快照。

任务快照用于在打开侧窗口尚未完成首帧绘制时填充临时画面。Android 17 并未实现“实时窗口图层掉帧后动态切换为快照”的通用降级策略，也不存在按帧挑选预览图层的 `TaskAnimationCoordinator`——采用真实窗口还是占位快照，在动画启动前就已经确定。

此外，任务快照的分辨率、像素格式、是否包含输入法 Surface、是否降采样以及缓存寿命均受具体实现与设备配置影响。仅用屏幕分辨率乘以四来估算全部快照内存开销，会忽略实际缓冲区复用、缓存淘汰策略及安全窗口限制；要评估快照内存占用，应在目标设备上读取实际的图形内存与 `TaskSnapshot` 运行时数据。

### 8. 应用回调路径的性能

当应用回调胜出时，`WindowOnBackInvokedDispatcher.OnBackInvokedCallbackWrapper` 会将来自 Binder 的回调投递至创建 `ViewRootImpl` 的 Handler（通常即应用主线程），再由 `BackProgressAnimator` 平滑插值后触发应用的 `onBackProgressed()`。

因此，应用侧在每一帧进度回调中应严格限定为轻量、可预测的属性更新：

- 预先保存起止位置；
- 更新位移、缩放、透明度或已创建动画的进度比例；
- 避免同步 I/O、Bitmap 解码、导航提交和大对象分配；
- 不在每帧反复修改复杂 `LayoutParams`；
- 取消后完整恢复界面状态。

下面这段代码可用于标记应用回调的墙钟耗时区间；若要核算实际占用的 CPU 时间，还需结合线程调度状态进一步拆分：

```kotlin
override fun onBackProgressed(backEvent: BackEvent) {
    Trace.beginSection("AppBackProgress")
    try {
        content.translationX = maxTranslation * backEvent.progress
    } finally {
        Trace.endSection()
    }
}
```

如果测量显示 `AppBackProgress` 自身很短但画面依然卡顿，还需继续核查应用 `RenderThread`、WM Shell、SurfaceFlinger 以及显示刷新率，因为主线程区段仅覆盖了整条渲染链路中的一环。

在实际开发中，AndroidX `OnBackPressedDispatcher`、Navigation、Fragment 与 Compose `PredictiveBackHandler` 会将平台事件桥接至各自框架的回调。具体的分发路径与对象分配行为随 AndroidX 版本而异，排查前应先核对 Activity、Navigation 与 Compose 的依赖版本，再界定问题出自兼容库层还是 `frameworks/base` 的 Android 17 实现。

### 9. Predictive Back 与 IME

输入法（IME）的返回路径横跨输入法进程与应用进程。下面的流程图展示了回调注册转发与 Insets 动画控制权之间的协作分工：

<!-- gracker-diagram: ch03-03-ime-back-callback-control -->
![IME 返回先转发注册，再由应用窗口控制 Insets 动画](../../assets/diagrams/ch03/ch03-03-ime-back-callback-control.png)

图：IME 通过 Sender / ResultReceiver 把回调注册传给当前应用 Proxy；默认系统回调在应用窗口映射到 DEFAULT，通常高于 Activity 的内部 SYSTEM 回调。可用时 ImeBackAnimationController 在预提交阶段做 peek，取消恢复，提交后完成隐藏并临时清除回调，让后续返回可以继续导航。

输入法进程通过 `ImeBackCallbackSender` 将回调注册转发至当前应用。应用侧的 `ImeBackCallbackProxy` 收到默认系统回调后，会将其映射为 `PRIORITY_DEFAULT`；只要 `ViewRoot` 已就绪 `ImeBackAnimationController`，分发器便会交由该控制器驱动预测性动画。

在默认情况下，输入法回调的优先级高于 Activity 的框架系统回调，因此首次返回手势会优先收起键盘，但仍存在以下明确例外：

- 输入法可通过返回处置策略（back disposition）选择跳过默认回调；
- 应用更高优先级的覆盖层回调可以先处理；
- 多窗口与输入法全屏模式会禁用预测性输入法动画；
- 使用 `adjustResize`、没有应用 Insets 动画回调且页面也未采用 edge-to-edge 时，会回退到普通隐藏动画；
- `onKeyPreIme()` 的兼容分支仍可能消费事件并取消 IME 动画。

`ImeBackAnimationController` 在预提交阶段仅将输入法向下移动一小段距离作为预探效果（peek），松手取消则恢复原状，确认提交后才完成完整隐藏。由于它直接操控 `WindowInsetsAnimationController`，IMMS 不会与页面的跨 Activity 动画并行冲突。

当输入法隐藏提交后，控制器会暂时清除输入法回调，使得紧接着的下一次返回能够顺延交由后续回调处理，哪怕此时键盘隐藏动画仍在收尾。这正是日常常见的“首次返回收起键盘、再次返回退出页面”的状态基础；但考虑到上述各类输入法策略、窗口模式与高优先级覆盖层等例外，不能将其当作毫无例外的固定规律。


### 10. 如何建立性能结论

#### 10.1 先判定卡在哪个阶段

| 现象 | 优先证据 | 可能范围 |
|---|---|---|
| 手势开始后预览迟迟不出现 | `ACTION_BACK_SYSTEM_ANIMATION`、Shell 就绪日志 | WMS 目标计算、远程动画目标、目标窗口 |
| 手指移动时持续掉帧 | FrameTimeline、Shell 与应用主线程、RenderThread、SurfaceFlinger | 进度回调或 Surface 事务 |
| 松手后停顿 | 提交后动画执行器、Transition、真实回调 | 应用导航、动画执行器、转场合并 |
| 取消后界面没恢复 | 应用取消轨迹或 Shell 动画执行器 | 回调状态机错误 |
| 偶发退回旧动画 | `BackNavigationInfo` 类型、目标进程与窗口 | 预测条件不足 |
| 键盘先闪再隐藏 | `ImeBackAnimationController`、Insets 控制对象 | 输入法控制对象是否就绪、回退模式 |

#### 10.2 分段毫秒预算的局限

虽然 60 Hz 刷新周期约为 16.7 ms、120 Hz 约为 8.3 ms，但 SystemUI、Shell、应用、RenderThread 与 SurfaceFlinger 是按流水线并发协作的，各阶段并不共享一张可以直接相加的“2 + 4 + 4 ms”静态预算表。评估帧预算时，需要将每一帧 FrameTimeline 的预期与实际耗时、CPU 可运行态等待时间以及 Surface 事务提交时序对齐比较。

此外，这条源码路径中并未实现“持续掉帧就自动缩短 AppTransition”或“实时窗口图层掉帧就改用任务快照”的通用自动降级策略。遇到跳帧、动态刷新率波动或 HWC/GPU 合成切换时，仍需回到 SurfaceFlinger 与调度器记录中核实具体诱因，无法仅凭卡顿表现倒推出固定降级逻辑。

### 11. Perfetto 与系统状态观测

#### 11.1 平台已有的指标

WM Shell 内建了两类观测指标：

- `LatencyTracker.ACTION_BACK_SYSTEM_ANIMATION`：从 Shell 发起 `startBackNavigation()` 到收到有效远程动画目标；
- InteractionJankMonitor 的关键用户旅程（CUJ）指标：覆盖返回主屏、跨任务和跨 Activity 预测性返回，对相应 leash 的动画帧统计卡顿。

同时，WMS 的协议缓冲转储（proto dump）与窗口跟踪中也记录了 `BackNavigationController` 的 `ANIMATION_IN_PROGRESS` 与 `LAST_BACK_TYPE`；WM Shell 转储则会输出 `BackAnimationController` 的当前手势状态、提交后动画、指针抢占情况以及当前和排队中的跟踪器状态。

#### 11.2 Perfetto 需要覆盖的线程

录制系统跟踪（System Trace）时，建议至少勾选以下进程与数据源：

- SystemUI 与 WM Shell 主线程；
- `system_server` 中 WindowManager 与 ActivityTaskManager 相关线程和 Binder；
- 应用主线程与 RenderThread；
- SurfaceFlinger、GPU、HWC 及 FrameTimeline；
- `input`、`sched`、`freq`、`view`、`wm`、`gfx` 等相关数据源。

分析时可按以下步骤推进：

1. 以边缘手势开始为时间原点；
2. 确认本次 `BackNavigationInfo` 类型；
3. 检查远程动画目标到达时间；
4. 区分进度在 Shell 还是应用生成；
5. 对齐每帧事务、应用缓冲区与 SurfaceFlinger 呈现时间；
6. 松手后继续观察，直至真实回调和窗口转场完成。

需要留意，FrameTimeline 中的帧异常类型仅标明最终呈现结果；具体开销究竟源自布局、进度回调、Binder、GPU 还是合成，仍需展开同一时间窗内的线程轨迹区段逐一确认。

#### 11.3 建议的覆盖组合

测试矩阵建议至少涵盖以下条件组合，并分别统计 P50、P90、P95 分位数：

- 应用回调、系统跨 Activity、跨任务和返回主屏；
- 目标 Activity 已有窗口、条件不足回退；
- 手势提交、中途取消、快速连续两次返回；
- 输入法已显示或隐藏，`adjustResize` 或内容延伸到系统栏边缘（edge-to-edge）；
- 60 Hz 与高刷新率；
- 分屏、自由窗口（freeform）和折叠状态变化；
- AndroidX 回调启用与禁用；
- 目标 SDK 35 与 36+ 的行为差异。

### 12. 源码索引

- [`EdgeBackGestureHandler.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/EdgeBackGestureHandler.java)
- [`DisplayBackGestureHandler.kt`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/DisplayBackGestureHandler.kt)
- [`BackAnimationController.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/back/BackAnimationController.java)
- [`ShellBackAnimationRegistry.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/back/ShellBackAnimationRegistry.java)
- [`BackAnimationRunner.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/back/BackAnimationRunner.java)
- [`ShellBackAnimationModule.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/dagger/back/ShellBackAnimationModule.java)
- [`CrossActivityBackAnimation.kt`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/back/CrossActivityBackAnimation.kt)
- [`CrossTaskBackAnimation.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/libs/WindowManager/Shell/src/com/android/wm/shell/back/CrossTaskBackAnimation.java)
- [`BackNavigationController.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/wm/BackNavigationController.java)
- [`BackNavigationInfo.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/window/BackNavigationInfo.java)
- [`OnBackInvokedDispatcher.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/window/OnBackInvokedDispatcher.java)
- [`WindowOnBackInvokedDispatcher.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/window/WindowOnBackInvokedDispatcher.java)
- [`Activity.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/app/Activity.java)
- [`ViewRootImpl.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/view/ViewRootImpl.java)
- [`ImeBackAnimationController.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/view/ImeBackAnimationController.java)
- [`ImeBackCallbackSender.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/window/ImeBackCallbackSender.java)
- [`ImeBackCallbackProxy.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/core/java/android/window/ImeBackCallbackProxy.java)
- [Add support for the predictive back gesture](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture)
- [Android 16 behavior changes for target SDK 36+](https://developer.android.com/about/versions/16/behavior-changes-16)


## 版本与实现边界

- Android 13、API 33 引入 `OnBackInvokedCallback` 和提前返回分发模型；
- Android 14、API 34 向应用开放 `OnBackAnimationCallback` 的进度能力；
- Android 15、API 35 移除预测性返回动画的开发者开关，已显式加入的应用会显示返回主屏、跨任务和跨 Activity 系统动画；
- Android 16、API 36 对目标 SDK 36+ 应用默认启用新模型，仍可通过 `android:enableOnBackInvokedCallback="false"` 临时退出；启用时不再走 `onBackPressed()` 和返回 `KEYCODE_BACK` 的常规分发；
- Android 17、API 37 延续该默认行为，并允许同一分发器注册多个 `PRIORITY_SYSTEM_NAVIGATION_OBSERVER`。

以上结论以 `android-17.0.0_r1` 为版本基线，Android 17 后续小版本或更新版 AndroidX 库的行为可能继续演进。此外，设备厂商对 SystemUI 手势、Launcher 动画执行器、动画资源以及窗口策略所作的定制，均需在对应设备构建上单独复核。


## 常见误区

### 所有返回手势都会注入 `KEYCODE_BACK` 吗

并非如此。`EdgeBackGestureHandler.triggerBack()` 仅在 `mBackAnimation == null` 时直接注入按键；在提前分发路径中，手势先通过 `setTriggerBack(true)` 标记提交状态，待 `ACTION_UP` 到来后直接执行返回回调或系统转场，Shell 只有在缺乏有效 `BackNavigationInfo` 等兜底条件下才会回退注入返回键。

### 设置手势排除矩形后，整块区域都会生效吗

未必全部生效。WMS 还会将应用上报的矩形与窗口可触摸区域求交，并按左右边缘各自的纵向总高度预算依次裁剪；因此分析排除区是否生效时不能只看应用的请求列表，还需要核实最终获批的区域。

### `systemGestures()` 能代表所有可排除区域吗

不能完全代表。`mandatorySystemGestures()` 标明了其中必须保留给系统的子集，这部分区域无法被 `setSystemGestureExclusionRects()` 覆盖；因此底部主屏、快速切换冲突需要与左右返回边缘的有限排除区分对待。

### Android 13 到 Android 17 的开关行为相同吗

各个版本存在明显演进差异：API 33 引入提交回调，API 34 增加进度回调，Android 15 移除了系统动画的开发者开关，Android 16 对目标版本为 36+ 的应用改为默认启用并改变了旧版返回事件分发，API 37 则进一步放开了观察者回调的数量限制。调试此类问题时，必须同步核对系统版本、目标 SDK 版本、清单属性与回调注册情况。

### 手势监视器收到事件后，应用还能收到完整指针事件流吗

在越过手势识别阈值之前，应用通常可以与监视器并行接收事件；一旦发生 `pilferPointers()` 指针抢占，原目标窗口就会收到 `ACTION_CANCEL`，后续事件流转由抢占方接管。旧式分发与提前分发分支都可能触发抢占，具体时机由各自的状态机决定。


## 参考资料

- AOSP 源码路径：
  - `frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/EdgeBackGestureHandler.java` — 资格判定、阈值、旧式提交与 Shell 入口
  - `frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/DisplayBackGestureHandler.kt` — Android 17 每块显示屏的监视器、接收器、排除区监听和面板
  - `frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/BackPanelController.kt` — 当前默认的边缘返回反馈插件
  - `frameworks/base/packages/SystemUI/src/com/android/systemui/navigationbar/gestural/BackPanel.kt` — 边缘面板的绘制与动画实现
  - `frameworks/base/packages/SystemUI/shared/src/com/android/systemui/shared/system/InputMonitorCompat.java` — `monitorGestureInput()` 的 SystemUI 包装层
  - `frameworks/base/packages/SystemUI/src/com/android/systemui/util/concurrency/SysUIConcurrencyModule.kt` — `BackPanelUiThread` 与主线程的选择
  - `frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/back/BackAnimationController.java` — 提前返回分发、目标解析、进度、指针抢占与提交动画
  - `frameworks/native/services/inputflinger/dispatcher/InputDispatcher.cpp` — `pilferPointersLocked()` 与 `CANCEL_POINTER_EVENTS` 合成
  - `frameworks/base/core/java/android/view/ViewRootImpl.java` — View 排除矩形收集与 WMS 上报
  - `frameworks/base/services/core/java/com/android/server/wm/DisplayContent.java` — 最终排除区域、每侧高度预算与粘性沉浸窗口的配额例外
  - [`WindowState.java`](https://android.googlesource.com/platform/frameworks/base/+/refs/tags/android-17.0.0_r1/services/core/java/com/android/server/wm/WindowState.java) — 旧目标 SDK 应用在粘性沉浸模式下的隐式排除兼容条件
  - `frameworks/base/core/java/android/window/OnBackInvokedCallback.java` — API 33 的提交回调
  - `frameworks/base/core/java/android/window/OnBackAnimationCallback.java` — API 34 的进度回调
  - `frameworks/base/core/java/android/window/OnBackInvokedDispatcher.java` — 观察者优先级与回调注册入口
  - `frameworks/base/core/java/android/window/WindowOnBackInvokedDispatcher.java` — 回调排序、观察者与应用进度分发
  - `frameworks/native/services/inputflinger/include/InputTracingPerfettoBackend.h` — 结构化输入 Perfetto 数据源
- 官方文档：
  - [Ensure compatibility with gesture navigation | Android Developers](https://developer.android.com/develop/ui/views/touch-and-input/gestures/gesturenav)
  - [Add support for the predictive back gesture | Android Developers](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture)
  - [Android 16 behavior changes for target 36+ | Android Developers](https://developer.android.com/about/versions/16/behavior-changes-16)
  - [OnBackInvokedCallback | Android Developers](https://developer.android.com/reference/android/window/OnBackInvokedCallback)
  - [OnBackAnimationCallback | Android Developers](https://developer.android.com/reference/android/window/OnBackAnimationCallback)
  - [OnBackInvokedDispatcher | Android Developers](https://developer.android.com/reference/android/window/OnBackInvokedDispatcher)
  - [WindowInsets | Android Developers](https://developer.android.com/reference/android/view/WindowInsets)
  - [OnBackPressedCallback | Android Developers](https://developer.android.com/reference/androidx/activity/OnBackPressedCallback)
  - [Recording system traces with Perfetto](https://perfetto.dev/docs/getting-started/system-tracing)
  - [FrameTimeline data source | Perfetto](https://perfetto.dev/docs/data-sources/frametimeline)
- 外部参考：
  - TechMerger《深入理解 Android 系统 Back Gesture 的实现》
  - 郭霖《Android 15 新特性：预测性返回手势》

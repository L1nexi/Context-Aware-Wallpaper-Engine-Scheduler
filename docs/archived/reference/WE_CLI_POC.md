# Wallpaper Engine CLI 验证计划 (POC)

基于 `WE_CLI.md` 文档，我们需要验证以下核心接口，以确保调度器的可行性。

## 一、 基础控制验证 (已完成)

- [x] **暂停/播放**: `wallpaper64.exe -control pause` / `play`
  - 结果: 无黑框，不抢焦点。
- [x] **获取当前壁纸**: `wallpaper64.exe -control getWallpaper`
  - 结果: 返回绝对路径，如 `E:/.../scene.pkg`。

## 二、 核心功能验证 (待执行)

### 1. Profile (配置文件) 切换测试

这是实现“场景切换”最直接的方式。

- **命令:** `wallpaper64.exe -control openProfile -profile "WorkMode"`
- **验证点:**
  - **延迟:** 从命令发出到壁纸变化的耗时是多少？
  - **卡顿:** 切换瞬间是否有明显的画面撕裂、黑屏或系统卡顿？
  - **焦点:** 切换 Profile 是否会导致全屏游戏弹窗或失去焦点？(关键)
  - **无效名:** 如果 Profile 不存在，WE 会直接忽略

### 2. 播放列表控制 (openPlaylist) - 核心路径

在 `config.json` 中发现了已存在的播放列表："WORK" 和 "GAME"。

- **机制确认:** `openPlaylist` 只是告诉 WE 加载哪个列表，**列表内部的播放逻辑（顺序、定时、过渡效果）完全由 WE 根据 `config.json` 中的 `settings` 接管**。
  - 用户偏好: "无过渡" -> 对应 `config.json` 中 `"transition": false`。
  - 用户偏好: "随机/有序" -> 对应 `config.json` 中 `"order": "random"` / `"sorted"`。
- **结论:** 调度器不需要操心列表内的微观逻辑（怎么切、切多快），只需要在宏观上决定“现在该用哪个列表”。

### 3. 属性动态注入 (applyProperties) - [已搁置]

用户设想中不涉及单张壁纸的属性微调，而是直接切换列表。此项测试优先级降低。

### 4. Profile (配置文件) 切换测试 - [已搁置]

用户主要使用单显示器，且 Playlist 方案已能满足需求。此项测试优先级降低。

## 三、 异常与边界测试

### 1. 进程交互

- **验证:** 当 WE 未启动时，执行 CLI 命令会启动 WE 并且在启动后正确处理命令。
- **验证:** 连续快速发送 10 次切换命令，WE 是否会崩溃或卡死？

### 2. 路径与格式

- **验证:** `getWallpaper` 返回的路径在不同壁纸类型（Web/Video/Scene）下是否一致？我们需要编写正则来解析它。

---

## 四、 实验记录

### 实验 1: 获取壁纸路径格式

无论是播放列表还是单张壁纸，都是类似如下的输出。

```text
E:/SteamLibrary/steamapps/workshop/content/431960/1353344455/index.html
E:/SteamLibrary/steamapps/workshop/content/431960/909478942/Miko fox (Ver.1.2).mp4
E:/SteamLibrary/steamapps/workshop/content/431960/2802161091/scene.pkg
```

**结论:** 可以通过文件扩展名 (.html, .mp4, .pkg) 判断壁纸类型。

### 实验 2: 播放列表切换测试

- 执行 `wallpaper64.exe -control openPlaylist -playlist "WORK"`
  - 结果: 正常切换。
- 执行 `wallpaper64.exe -control openPlaylist -playlist "GAME"`
  - 结果: 正常切换。

补充：

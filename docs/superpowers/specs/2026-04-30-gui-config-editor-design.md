# GUI Config Editor — 设计文档

## 动机

当前唯一配置方式是手写 `scheduler_config.json`。小白用户少一个逗号/引号就会导致启动失败。需要一个表单驱动的图形化配置界面，消除 JSON 语法接触。

## 架构概览

```
main.py                         dashboard.py (Bottle HTTP)
───────                         ──────────────────────────
                                GET  /api/config         → 返回完整 JSON
                                POST /api/config         → 校验 + 原子写入
                                GET  /api/tags/presets   → 预设标签列表
                                GET  /api/playlists/scan → WE 播放列表扫描

dashboard/src/
├── views/
│   ├── DashboardView.vue   (改: 新增 Config tab)
│   └── ConfigView.vue      (新: 配置编辑主视图)
├── components/
│   ├── PlaylistEditor.vue  (新: 播放列表增删改弹窗)
│   ├── TagPalette.vue      (新: 标签下拉 + 权重滑块)
│   └── SchedulingForm.vue  (新: scheduling 参数表单)
└── composables/
    └── useConfig.ts        (新: config API 封装)
```

**数据流**：Config Tab 打开 → GET /api/config → 填充表单 → 用户编辑 → el-form 前端校验 → POST /api/config → Pydantic 后端校验 → 原子写入 → 调度循环检测 mtime 变化 → 热重载生效。

**冲突策略**：最后写入者胜出。不做编辑期间的冲突检测（MVP 简化；用户通常不会同时手动改 JSON + 用编辑器）。

## 后端 API

### `GET /api/config`

返回完整配置 JSON（原样读文件，保留格式）。返回前先跑 `AppConfig.model_validate()` 确认合法，不合法则返回 500。

`weather.api_key` 原样返回（仅绑 127.0.0.1，无泄露风险）。

### `POST /api/config`

```python
@app.route('/api/config', method='POST')
def api_config_save():
    data = bottle.request.json
    try:
        AppConfig.model_validate(data)
    except ValidationError as e:
        bottle.response.status = 422
        return json.dumps({"error": "validation_failed", "details": _flatten_errors(e)})
    
    config_path = _resolve_config_path()
    tmp = config_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, config_path)  # Windows 上原子 rename
    return json.dumps({"ok": True})
```

`_flatten_errors()` 将 Pydantic `ValidationError.errors()` 递归展开为 `[{field, message}]`，路径用 `.` 连接。前端据此在对应字段旁显示红色错误。

### `GET /api/tags/presets`

返回 `core/policies.py` 中的 `KNOWN_TAGS` 列表——所有 Policy 可能输出的标签集合。驱动前端标签调色板的下拉候选。

### `GET /api/playlists/scan`

1. 从 scheduler_config 读 `wallpaper_engine_path` → 取父目录 → `config.json`
2. 若失败，通过 Steam 注册表查找：`HKLM/HKCU\Software\Valve\Steam\SteamPath` → `libraryfolders.vdf` → 遍历每个库文件夹 → `steamapps\common\wallpaper_engine\config.json`
3. 读取 WE config.json，用 `getpass.getuser()` 取当前 Windows 用户名作为 key，读 `{username}.general.playlists[]`，提取每个元素的 `name` 字段
4. 返回 `string[]` 供前端自动补全

WE 不支持跨用户切换播放列表，只扫描当前用户。

### DashboardHTTPServer 改造

构造器新增 `config_path` 参数，传递给 `_build_app`：

```python
class DashboardHTTPServer:
    def __init__(self, state_store, history_logger=None, config_path=""):
        ...
```

main.py 传入 `str(PathManager.get_config_path())`。

## 前端设计

### ConfigView.vue（主视图）

```
Config Tab 内部二级标签:
  [播放列表] [调度参数] [高级]

顶部（不随 tab 隐藏）:
  WE 路径: [文本输入框] ← 自动检测预填

播放列表 Tab:
  el-card 列表，每项显示 name / display / tag chips
  [+ 新增] 按钮，每个卡片有 [编辑] [删除]
  点击编辑/新增 → PlaylistEditor 弹窗

调度参数 Tab:
  SchedulingForm: 8 个字段用 el-slider / el-switch / el-input-number
  每个字段旁 tooltip 解释含义

高级 Tab (未来):
  Policy 配置、TagSpec fallback 编辑
  MVP 阶段显示 "此部分即将推出，当前请手动编辑 JSON"
```

底部固定栏：`[恢复默认] [保存配置]` 按钮。

### PlaylistEditor.vue（弹窗）

el-dialog 包裹 el-form，表单包含：

- **名称**：el-input + el-autocomplete（从 /api/playlists/scan 获取候选项），校验规则 `{ required: true, trigger: 'blur' }`
- **显示名**：el-input，可选
- **标签权重**：el-table 内联编辑，`#default="scope"` 自定义列模板
  - 标签列：el-select，候选来自 /api/tags/presets
  - 权重列：el-slider (0 ~ 2, step 0.1)
  - 操作列：el-button @click="removeTag(index)"
  - 表格底部：el-button @click="addTag" → push `{ key: Date.now(), tag: '', weight: 0 }`
  - 每一行用 `:key="row.key"` 确保 VNode 复用正确
- **校验**：自定义 validator 确保 `tags.length > 0`，通过 `formRef.value.validate()` 程序化触发
- 动态数组 prop 路径：`:prop="'tags.' + index + '.weight'"`

参考模式来自 Element Plus 文档的 [Dynamic Form Item](https://element-plus.org/en-US/component/form) 和 [Custom Column Templates](https://element-plus.org/en-US/component/table)。

### SchedulingForm.vue

| 字段 | 控件 | 默认值 |
|------|------|--------|
| idle_threshold | el-slider (0-300s) | 60 |
| switch_cooldown | el-slider (0-7200s) | 1800 |
| cycle_cooldown | el-slider (0-3600s) | 600 |
| force_after | el-slider (0-86400s) | 14400 |
| cpu_threshold | el-slider (50-100%) | 85 |
| cpu_sample_window | el-input-number (1-60) | 10 |
| pause_on_fullscreen | el-switch | true |
| startup_delay | el-slider (0-120s) | 15 |

每个字段带 el-tooltip 解释。

### useConfig.ts

```typescript
export function useConfig() {
  const config = ref<AppConfig | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchConfig(): Promise<void>
  async function saveConfig(data: AppConfig): Promise<{ok: boolean; errors?: FieldError[]}>
  async function scanPlaylists(): Promise<string[]>
  async function fetchTagPresets(): Promise<string[]>

  return { config, loading, error, fetchConfig, saveConfig, scanPlaylists, fetchTagPresets }
}
```

## 标签词汇中心化

`core/policies.py` 新增：

```python
KNOWN_TAGS: list[str] = sorted({
    "#focus", "#chill",                          # ActivityPolicy
    "#dawn", "#day", "#sunset", "#night",        # TimePolicy
    "#spring", "#summer", "#autumn", "#winter",  # SeasonPolicy
    "#clear", "#cloudy", "#rain", "#storm", "#snow", "#fog",  # WeatherPolicy
})
```

新增 Policy/标签时，只需在 `KNOWN_TAGS` 加一行。前端 `/api/tags/presets` 自动同步。

## WE 路径检测策略

```
1. 从 scheduler_config 读 wallpaper_engine_path → 存在则直接用
2. 读 Steam 注册表 (HKLM/HKCU\Software\Valve\Steam\SteamPath)
3. 解析 {SteamPath}\steamapps\libraryfolders.vdf → 所有库路径
4. 遍历 库\steamapps\common\wallpaper_engine\wallpaper64.exe → 存在则返回
5. 都失败 → config 编辑器默认路径为空，/api/playlists/scan 返回空列表
```

不依赖 WE 进程运行状态。封装在 `utils/we_path.py`。

## 原子写入

```
写临时文件 {config_path}.tmp → os.replace(tmp, config_path)
```

`os.replace` 在 Windows 上是原子操作，保证 config.json 不会处于半写状态。调度器的热重载检测 `mtime` 变化，自动加载新配置。

## 错误处理

| 层级 | 机制 |
|------|------|
| 前端表单 | Element Plus el-form rules（必填项、类型约束、范围约束） |
| 前端网络 | HTTP 错误 → 红色 toast 通知 |
| 后端校验 | Pydantic `model_validate` → 422 + 字段级错误详情 |
| 后端写入 | OSError → 500 + 错误信息 |
| 热重载 | 校验失败的配置不会被加载，调度器保留旧配置继续运行 |

## 实现阶段

### Phase 1: 基础设施 (后端 + 标签词汇)

1. `core/policies.py` 新增 `KNOWN_TAGS`
2. `ui/dashboard.py` 新增 4 个端点
3. `DashboardHTTPServer` 接受 `config_path` 参数
4. `main.py` 传入 config_path
5. `utils/we_path.py` — WE 路径检测

### Phase 2: 前端 Config Tab

1. `useConfig.ts` composable
2. `ConfigView.vue` — 主视图 + 二级标签
3. `PlaylistEditor.vue` — 播放列表弹窗
4. `TagPalette.vue` — 标签选择+权重滑块
5. `SchedulingForm.vue` — 调度参数表单
6. `DashboardView.vue` — 新增 Config tab

### Phase 3: 构建 & 验证

1. `cd dashboard && npm run type-check && npm run build`
2. 手动测试：从托盘打开 Dashboard → Config Tab → 编辑播放列表 → 保存 → 确认 hot-reload

## 参考

- Element Plus [Dynamic Form Item](https://element-plus.org/en-US/component/form) — 动态数组字段 prop 路径、增删行模式
- Element Plus [Custom Column Templates](https://element-plus.org/en-US/component/table) — el-table slot 自定义列、操作按钮
- Element Plus [Custom Validation](https://element-plus.org/en-US/component/form) — 自定义 validator 函数、程序化触发校验

## 验证

```bash
# 后端 API
python -c "
from ui.dashboard import _build_app, StateStore
import json
app = _build_app(StateStore())
# 验证 4 个端点注册
for r in app.routes:
    print(r.rule, r.method)
"

# 标签词汇
python -c "from core.policies import KNOWN_TAGS; assert len(KNOWN_TAGS) >= 15"

# 前端
cd dashboard && npm run type-check && npm run build
```

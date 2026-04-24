# 语义重构规范

> **状态**：草案 v0.1  
> **范围**：v0.4.x → v0.5.0（破坏性变更，semver-0.x）  
> **最后更新**：2026-04-24

## 1. 动机

当前的标签-值系统将多个语义维度混淆（conflate）到了一个浮点数中：

- **强度 (Intensity)**（现象的物理强度）：WeatherPolicy 直接将 T1-T4 的严重程度编码为标签值。
- **显著性 (Salience)**（信号归属于某个语义类别的清晰程度）：TimePolicy 的汉宁窗（Hann window）输出代表了“现在是白天的确定程度”，而不是任何物理强度。
- **方向权重 (Direction weight)**（播放列表与概念的相对亲和度）：播放列表的 `#rain: 0.3` 意味着“轻微的雨天主题”，这与策略输出 `#rain: 0.85` 表示“正在下大雨”本质上是完全不同的量。

这种混淆造成了几个问题：

1. **隐式归一化契约**：策略是否对其输出进行 L2 归一化会改变 `weight_scale` 的含义（固定影响力 vs 影响力上限），但这个决定被深埋在每个策略的具体实现中。
2. **新策略的认知负担**：开发者必须了解整个聚合流水线，才能决定是否需要进行归一化。
3. **用户的认知负担**：`weight_scale` 同时控制“这种信号类型有多重要”和“信号之间如何竞争”，需要反复试错来调优。
4. **信息丢失**：余弦相似度丢弃了聚合向量的范数（norm），而该范数携带着有意义的信号强度信息，控制器本可以利用这些信息来做出切换决策。

## 2. 语义模型

### 2.1 策略输出分解

每个策略输出都被分解为三个正交的维度：

| 维度                  | 类型               | 范围          | 不变量             | 描述                                                             |
| --------------------- | ------------------ | ------------- | ------------------ | ---------------------------------------------------------------- |
| **方向 (direction)**  | `Dict[str, float]` | L2 范数 = 1.0 | 始终保持单位归一化 | 信号的*种类*。标签空间中单位超球面上的一个点。                   |
| **显著性 (salience)** | `float`            | [0, 1]        | 默认 1.0           | 信号属于该类别的*清晰程度*。在峰值时较高，在过渡期或模糊时较低。 |
| **强度 (intensity)**  | `float`            | [0, 1]        | 默认 1.0           | 现象的*强烈程度*。物理或行为的幅度。                             |

策略对聚合环境向量的**贡献向量（contribution vector）**为：

```python
contribution = direction * salience * intensity * weight_scale
```

`salience` 和 `intensity` 是 PolicyOutput 上的可选字段，默认为 1.0。未能有意义地区分它们的策略（例如 ActivityPolicy）可以保持默认值，并通过其他方式控制幅度。

### 2.2 各策略语义映射

| 策略               | direction (方向)                                                    | salience (显著性)              | intensity (强度)          | 备注                               |
| ------------------ | ------------------------------------------------------------------- | ------------------------------ | ------------------------- | ---------------------------------- |
| **TimePolicy**     | 24小时内循环经过 `#dawn/#day/#sunset/#night`                        | 汉宁窗值（峰值为1.0，边界为0） | 1.0（始终）               | 时间始终存在；只有清晰度会变化。   |
| **SeasonPolicy**   | 365天内循环经过 `#spring/#summer/#autumn/#winter`                   | 汉宁窗值                       | 1.0（始终）               | 与 TimePolicy 模式相同。           |
| **WeatherPolicy**  | 天气类型（`#rain`, `#storm`, `#snow`, `#fog`, `#clear`, `#cloudy`） | 1.0（天气ID是明确的）          | T1-T4 严重程度 (0.25–1.0) | 强度即为物理现象的强度。           |
| **ActivityPolicy** | 匹配规则的标签，单位归一化                                          | 1.0（规则匹配是明确的）        | 1.0（始终）               | 参见第 3.3 节关于 EMA 的行为说明。 |

### 2.3 播放列表标签值

播放列表标签值代表**亲和度（affinity）**——“该播放列表的美学与此概念的契合程度”。打上 `{#rain: 0.3, #focus: 1.0}` 标签的播放列表意味着“主要是一个专注型播放列表，带有轻微的雨天天气兼容性”。

播放列表向量在匹配前会进行 L2 归一化。对于给定的播放列表，只有标签之间的相对比例是有意义的。

### 2.4 `weight_scale` 语义

`weight_scale` 是一个**策略级别的优先级乘数**。它回答了：“这种信号类型在整个系统中有多重要？”

它与显著性和强度都是正交的（相互独立的）：

- `intensity` = “这个信号的当前实例有多强”
- `weight_scale` = “这类信号有多重要”

策略的有效贡献范数为 `salience * intensity * weight_scale`。

> **未来展望**：如果引入基于组的抑制机制（第 7.2 节），`weight_scale` 在跨组优先级方面可能会变得冗余。但它在组内微调中仍会保持其用处。

## 3. PolicyOutput 结构

### 3.1 数据结构

```python
@dataclass
class PolicyOutput:
    direction: Dict[str, float]    # L2 归一化，非空
    salience: float = 1.0          #[0, 1]
    intensity: float = 1.0         # [0, 1]
```

策略可以返回 `None` 以表示没有贡献（等同于幅度 = 0）。

### 3.2 基类契约

`Policy` 基类强制执行方向归一化：

```python
class Policy(ABC):
    @abstractmethod
    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        """子类计算原始的 PolicyOutput（direction 无需归一化）。"""
        ...

    def get_output(self, context: Context) -> Optional[PolicyOutput]:
        """公共接口。对 direction 进行归一化，在下游应用 weight_scale。"""
        output = self._compute_output(context)
        if output is None:
            return None
        # 将 direction 归一化为单位向量
        norm = sqrt(sum(w*w for w in output.direction.values()))
        if norm < 1e-6:
            return None
        output.direction = {t: w/norm for t, w in output.direction.items()}
        return output
```

这消除了每个策略都要考虑“我应该归一化吗？”的问题。方向始终由基类进行归一化。幅度信息存在于 `salience` 和 `intensity` 中。

### 3.3 ActivityPolicy：EMA（指数移动平均）设计

ActivityPolicy 是独一无二的，因为“没有规则匹配”是一个有意义的状态（用户正在做一些未被识别的事情）。新模型下的 EMA 行为如下：

**两条独立的 EMA 轨道：**

1. **方向 EMA**：当规则匹配时，瞬时方向为匹配的标签（单位归一化）。方向通过对原始（未归一化的）向量进行 EMA 平滑处理，然后在每个 tick 重新归一化。这保留了平滑的方向过渡（例如，从 `#focus` 到 `#chill`）。

2. **幅度 EMA**：一个标量 EMA 轨道。当规则匹配时，瞬时幅度 = 1.0。当没有规则匹配时，瞬时幅度 = 0.0。平滑后的幅度向零衰减。

**边界条件（幅度接近零时）：** 无需特殊处理。当幅度可忽略不计（例如 0.001）时，方向仍参与聚合，但实际上毫无贡献。这在数学上等同于自然消失。

**输出构建：**

```python
def _compute_output(self, context):
    instant_direction = self._match_rules(context)  # Dict 或为空

    # 方向 EMA（原始向量空间，输出时重新归一化）
    self._dir_ema = ema_update(self._dir_ema, instant_direction, self.alpha)

    # 幅度 EMA（标量）
    instant_mag = 1.0 if instant_direction else 0.0
    self._mag_ema = self.alpha * instant_mag + (1 - self.alpha) * self._mag_ema

    if not self._dir_ema:  # 所有标签已衰减至零
        return None

    return PolicyOutput(
        direction=self._dir_ema,  # 基类将进行归一化
        salience=1.0,
        intensity=1.0,
        # 幅度通过原始方向向量的范数传递
        # 基类归一化后，EMA 幅度可从 _dir_ema 归一化前的范数中恢复
    )
```

**修订方案**：由于 ActivityPolicy 的 EMA 自然会衰减整个向量，最清晰的映射是：

- `direction` = 归一化后的 EMA 向量（由基类处理）
- `salience` 和 `intensity` 均不设置（皆为 1.0）
- EMA 幅度由方向向量归一化前的范数捕获，基类在归一化之前提取该范数

这需要基类在归一化之前提取原始范数：

```python
def get_output(self, context: Context) -> Optional[PolicyOutput]:
    output = self._compute_output(context)
    if output is None:
        return None
    norm = sqrt(sum(w*w for w in output.direction.values()))
    if norm < 1e-6:
        return None
    output.direction = {t: w/norm for t, w in output.direction.items()}
    # 策略可以通过将 salience/intensity 保持在 1.0，并依赖内置于归一化前方向中的幅度，
    # 来发出原始范数携带幅度信息的信号。我们提取并保留它：
    output._raw_magnitude = norm  # 内部使用，用于聚合
    return output
```

**替代方案（更简单）：** ActivityPolicy 显式地设置 `intensity = self._mag_ema` 和 `direction = normalized(self._dir_ema)`。基类只负责归一化方向。不需要 `_raw_magnitude` 的魔法。

**最终决定：采用显式方案。** ActivityPolicy 分别计算方向和幅度，设置 `intensity = magnitude_ema`，`direction = normalized(direction_ema)`。这是透明的，不需要特殊的基类行为。

## 4. TagSpec 扩展

### 4.1 当前结构（保留）

```json
{
  "tag_name": {
    "fallback": { "target_tag": 0.8 }
  }
}
```

Fallback（降级/回退）语义（已确认）：**强度沿着 fallback 边以基于权重的衰减方式传输。** 当 `#storm`（强度=1.0） fallback 到 `#rain`（权重=0.8）时，`#rain` 的贡献获得的强度为 0.8。这与暴风雨意味着大雨的物理直觉相一致。

## 5. Matcher / Controller 接口变更

### 5.1 Matcher（匹配器）

**输入**：`List[PolicyOutput]`（每个活跃策略一个，过滤掉 `None`）加上策略的 `weight_scale` 值。

**聚合**：

```python
env_vector = sum(output.direction * output.salience * output.intensity * weight_scale
                 for output, weight_scale in active_policies)
```

**Fallback 解析**：在匹配之前应用于 `env_vector`。在任何播放列表中都不存在的标签，将沿着 fallback 图（递归，强度受边缘权重衰减）被解析或消散。

**匹配**：余弦相似度（保留，未来讨论见第 7.1 节）。

**给控制器的附加输出**：

```python
@dataclass
class MatchResult:
    aggregated_tags: Dict[str, float]   # 原始聚合向量（用于日志记录）
    best_playlist: Optional[str]        # 余弦相似度胜出者
    similarity_gap: float               # (可选)sim(第一名) - sim(第二名)，衡量决断力
                                        # 也可以考虑保留完整的分数列表
    similarity: float                   # 第一名的相似度，衡量匹配质量
    max_policy_magnitude: float         # 所有策略中最大的 (salience * intensity * ws)
```

### 5.2 Controller（控制器）

控制器目前使用门控链（CPU、全屏、冷却时间）。来自 `MatchResult` 的两个新信号可供将来使用：

- **`similarity_gap`**：当差距很小时，匹配是不果断的。控制器可以增加冷却时间以避免在接近的候选者之间来回切换。
- **`max_policy_magnitude`**：当最强的策略信号微弱时，所有信号都属于环境背景音。控制器可以表现得更保守。当存在强烈的强前景信号时，控制器可以表现得更激进。

这些信号在接口中暴露，但它们在控制器逻辑中的具体使用是一个独立的设计决策，不属于本次重构的范畴。

## 6. 配置变更

### 6.1 配置中的 TagSpec

`scheduler_config.json` 中的新顶层部分： [DONE]

```json
  "tags": {
    "#dawn": { "fallback": { "#day": 0.7, "#chill": 0.3 } },
    "#sunset": { "fallback": { "#chill": 0.3, "#night": 0.7 } },
    "#spring": { "fallback": { "#day": 0.5, "#chill": 0.5 } },
    "#summer": { "fallback": { "#day": 0.7, "#clear": 0.3 } },
    "#autumn": { "fallback": { "#sunset": 0.6, "#chill": 0.4 } },
    "#winter": { "fallback": { "#night": 0.5, "#chill": 0.5 } },
    "#storm": { "fallback": { "#rain": 1 } },
    "#snow": { "fallback": { "#winter": 0.6, "#rain": 0.6 } },
    "#fog": { "fallback": { "#rain": 0.4, "#chill": 0.4 } },
    "#cloudy": { "fallback": { "#clear": 0.5, "#chill": 0.3 } }
  },
```

### 6.2 weight_scale

在 `_BasePolicyConfig` 中原样保留。此版本中不重命名。语义在文档中已明确说明：“策略级别的优先级乘数，与强度正交。”

## 7. 延期决策

### 7.1 余弦相似度 vs. 点积

**状态**：推迟到未来版本。

余弦相似度丢弃了聚合向量的范数，这意味着强度/显著性仅影响策略之间的方向竞争，而不影响最终的匹配质量。点积会让强信号产生更强的匹配，但会引入偏置问题：拥有更多标签的播放列表会系统性地获得更高的分数。

由于强度/显著性现在变得明确，范数携带了比以前更干净的语义信息，这可能会改变权衡。一旦重构的系统运行起来，并且可以通过经验进行行为对比（例如，通过热力图可视化），就应重新审视此决定。

### 7.2 动态组抑制

**状态**：推迟。已记录架构方向。

概念：策略被分组（例如 `ambient: [time, season]`，`foreground: [activity, weather]`）。当前景总幅度超过阈值时，抑制环境背景的贡献。

当前的缓解措施：静态 `weight_scale` 比例提供了固定的优先级排序。对于参数经过调优的 4 个策略来说已经足够了。

何时重新审视：如果策略数量增长超过 4-5 个，跨策略调优变得不切实际，或者如果用户反馈表明配置 `weight_scale` 比例存在困难。

风险：动态抑制放大了过渡斜率（前景上升 + 环境下降 = 双倍的方向变化率）。缓解此问题需要对抑制系数本身进行平滑处理，从而引入了另一个参数。

### 7.3 对范数敏感的匹配算法

与 7.1 相关。另一种替代方案是“混合方法”：余弦相似度选择播放列表（方向匹配），但范数影响控制器的行为（切换置信度）。第 5.2 节通过向控制器暴露 `similarity_gap` 和 `max_policy_magnitude` 部分实现了这一点，而无需更改匹配算法本身。

## 8. 决策记录

| #   | 决策 (Decision)                                           | 依据 (Rationale)                                                                                                           |
| --- | --------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| D1  | 播放列表值 = 亲和度（纯方向）                             | 播放列表向量是预先归一化的；只有相对标签比例才重要。避免了将播放列表配置与策略输出尺度耦合。                               |
| D2  | ActivityPolicy EMA = 整体向量衰减，而非分为显著性/强度    | 关闭 IDE 并不意味着“不太确定这是专注状态”或“专注程度变弱了”——它意味着该信号正在衰退。这种衰减在本体论上是统一的。          |
| D3  | Fallback 传输强度（受边缘权重衰减）                       | `#storm → #rain (0.8)`：暴风雨暗示大雨。强度衰减符合物理直觉。                                                             |
| D4  | 保留 `weight_scale` 作为策略优先级                        | 与强度正交。未来可能会被组抑制取代，但目前是唯一的跨策略调整旋钮。                                                         |
| D5  | 废除子向量，fallback 图是通用机制                         | 子向量是用于处理对立关系的一种工程妥协。Fallback 消散（未定义 fallback = 能量丢失）更加统一地处理了相同的情况。            |
| D6  | 领域分组作为一种约定，无运行时验证                        | 领域用于组织标签以供人类理解和未来的工具开发。运行时强制检查增加了每个 tick 的开销，但实用价值很低。                       |
| D7  | 扁平的标签命名（`#rain`）+ TagSpec 领域声明               | 层级化名称（`#weather.rain`）增加了冗长性，没有运行时收益。Domain 信息存在于 TagSpec 中，而不是标签字符串中。              |
| D8  | 方向始终由基类进行 L2 归一化                              | 消除了每个策略关于归一化的决定。每个策略都回答相同的三个问题：方向（是什么？）、显著性（确定吗？）、强度（有多强？）。     |
| D9  | ActivityPolicy：方向 EMA + 幅度 EMA，每个 tick 重新归一化 | 保留了方向过渡（例如 `#focus` → `#chill`）。单位向量的线性插值需要重新归一化；每个 tick 计算一次平方根的开销可以忽略不计。 |
| D10 | 幅度接近零时：自然衰减，无特殊处理                        | 极小的幅度实际上对聚合没有贡献。不需要阈值截断。                                                                           |
| D11 | 控制器接收 `similarity_gap` 和 `max_policy_magnitude`     | 为未来实现基于切换置信度的逻辑提供支持，而无需更改匹配算法。                                                               |
| D12 | 一步到位的破坏性变更 (v0.5.0)                             | Semver 0.x 允许破坏性变更。渐进式迁移会增加临时性的复杂性，对用户没有任何好处。                                            |
| D13 | 保留余弦相似度（暂时）                                    | 推迟到重构后的经验评估阶段再考虑。当前行为已得到验证。                                                                     |
| D14 | 跨领域的标签不重叠                                        | 设计约束。简化聚合过程（在聚合之前或之后进行 fallback 效果相同）。                                                         |

## 9. 迁移指南

### 9.1 受影响的文件

| 文件 (File)                     | 变更内容 (Changes)                                                                                                                                                                                                     |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `core/policies.py`              | 基类：`_compute_output() -> Optional[PolicyOutput]`，`get_output()` 中添加 L2 归一化。重写所有四个策略以返回 `PolicyOutput`。ActivityPolicy EMA 分拆为方向和幅度双轨道。WeatherPolicy `_ID_TAGS` 重组为单个字典。      |
| `core/matcher.py`               | 接收 `List[PolicyOutput]`。聚合使用 `direction * salience * intensity * weight_scale`。在聚合向量上进行 Fallback 解析。返回包含 `similarity_gap` 和 `max_policy_magnitude` 的 `MatchResult`。移除子向量投影/补偿逻辑。 |
| `core/controller.py`            | `SchedulingController` 接收 `MatchResult`（目前仅使用 `best_playlist`；`similarity_gap` 和 `max_policy_magnitude` 供将来使用）。                                                                                       |
| `utils/config_loader.py`        | 添加 `TagSpecConfig` 模型，`AppConfig` 增加 `tag_schema` 字段。                                                                                                                                                        |
| `scheduler_config.example.json` | 添加 `tag_schema` 节点。更新任何已变更的字段名称。                                                                                                                                                                     |
| `core/scheduler.py`             | 更新 Matcher/Controller 的调用签名。根据新的 ActivityPolicy EMA 结构更新状态的导出/导入。                                                                                                                              |

### 9.2 迁移步骤

1. 定义 `PolicyOutput` 和 `MatchResult` 数据类。
2. 在 config loader 中添加 `TagSpecConfig`；在示例配置中添加 `tag_schema`。
3. 重构 `Policy` 基类：`_compute_tags()` → `_compute_output()`，在 `get_output()` 中添加方向归一化。
4. 重写每个策略，使其返回 `PolicyOutput`。
5. 重构 `Matcher`：新的聚合逻辑、fallback 解析、`MatchResult` 输出。
6. 更新 `SchedulingController` 以接收 `MatchResult`。
7. 更新 `Scheduler` 的编排以及状态的导出/导入逻辑。
8. 使用 `misc/sim_match.py` 和热力图可视化进行验证。

### 9.3 配置迁移

没有自动化迁移工具。用户需手动更新 `scheduler_config.json`：

1. 添加 `tag_schema` 节点（可以开始为空；系统在没有它的情况下也可以工作，只是 fallback 不会生效）。
2. `playlists` 或 `policies` 节点无需更改（结构保持不变）。

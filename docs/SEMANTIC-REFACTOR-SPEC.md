****# Semantic Refactor Specification

> **Status**: Draft v0.1  
> **Scope**: v0.4.x → v0.5.0 (breaking change, semver-0.x)  
> **Last updated**: 2026-04-24

## 1. Motivation

The current tag-value system conflates multiple semantic dimensions into a single float:

- **Intensity** (physical strength of a phenomenon): WeatherPolicy encodes T1–T4 severity directly as tag values.
- **Salience** (how clearly a signal belongs to a semantic category): TimePolicy's Hann window output represents "how definitely it is daytime", not any physical intensity.
- **Direction weight** (relative affinity of a playlist to a concept): Playlist `#rain: 0.3` means "mildly rain-themed", a fundamentally different quantity from a policy's `#rain: 0.85` meaning "heavy rain is occurring".

This conflation creates several problems:

1. **Implicit normalization contract**: Whether a policy L2-normalizes its output changes the meaning of `weight_scale` (fixed influence vs. influence ceiling), but this decision is buried in each policy's implementation.
2. **Cognitive load for new policies**: A developer must understand the full aggregation pipeline to decide whether to normalize.
3. **Cognitive load for users**: `weight_scale` simultaneously controls "how important is this signal type" and "how do signals compete", requiring trial-and-error tuning.
4. **Lost information**: Cosine similarity discards the aggregated vector's norm, which carries meaningful signal-strength information that the controller could use for switching decisions.

## 2. Semantic Model

### 2.1 Policy Output Decomposition

Every policy output is decomposed into three orthogonal dimensions:

| Dimension | Type | Range | Invariant | Description |
|-----------|------|-------|-----------|-------------|
| **direction** | `Dict[str, float]` | L2 norm = 1.0 | Always unit-normalized | *What kind* of signal. A point on the unit hypersphere in tag space. |
| **salience** | `float` | [0, 1] | Default 1.0 | *How clearly* the signal belongs to this category. High at peaks, low during transitions or ambiguity. |
| **intensity** | `float` | [0, 1] | Default 1.0 | *How strong* the phenomenon is. Physical or behavioral magnitude. |

The **contribution vector** of a policy to the aggregated environment vector is:

```
contribution = direction * salience * intensity * weight_scale
```

`salience` and `intensity` are optional fields on PolicyOutput, defaulting to 1.0. Policies that don't meaningfully distinguish them (e.g., ActivityPolicy) may leave both at default and control magnitude through other means.

### 2.2 Per-Policy Semantic Mapping

| Policy | direction | salience | intensity | Notes |
|--------|-----------|----------|-----------|-------|
| **TimePolicy** | Rotates through `#dawn/#day/#sunset/#night` over 24h | Hann window value (1.0 at peak, 0 at boundary) | 1.0 (always) | Time is always present; only clarity varies. |
| **SeasonPolicy** | Rotates through `#spring/#summer/#autumn/#winter` over 365d | Hann window value | 1.0 (always) | Same pattern as TimePolicy. |
| **WeatherPolicy** | Weather type (`#rain`, `#storm`, `#snow`, `#fog`, `#clear`, `#cloudy`) | 1.0 (weather ID is unambiguous) | T1–T4 severity (0.25–1.0) | Intensity is the physical phenomenon strength. |
| **ActivityPolicy** | Matched rule's tag(s), unit-normalized | 1.0 (rule match is unambiguous) | 1.0 (always) | See Section 3.3 for EMA behavior. |

### 2.3 Playlist Tag Values

Playlist tag values represent **affinity** — "how much this playlist's aesthetic aligns with this concept". A playlist tagged `{#rain: 0.3, #focus: 1.0}` means "primarily a focus playlist, with mild rain-weather compatibility".

Playlist vectors are L2-normalized before matching. Only relative proportions between tags matter for a given playlist.

### 2.4 `weight_scale` Semantics

`weight_scale` is a **policy-level priority multiplier**. It answers: "How important is this signal type in the overall system?"

It is orthogonal to both salience and intensity:
- `intensity` = "how strong is this instance of the signal"
- `weight_scale` = "how important is this category of signal"

The effective contribution norm of a policy is `salience * intensity * weight_scale`.

> **Future note**: If group-based inhibition is introduced (Section 7.2), `weight_scale` may become redundant for cross-group priority. It would remain useful for intra-group tuning.

## 3. PolicyOutput Structure

### 3.1 Data Structure

```python
@dataclass
class PolicyOutput:
    direction: Dict[str, float]    # L2-normalized, non-empty
    salience: float = 1.0          # [0, 1]
    intensity: float = 1.0         # [0, 1]
```

A policy may return `None` to indicate no contribution (equivalent to magnitude = 0).

### 3.2 Base Class Contract

The `Policy` base class enforces direction normalization:

```python
class Policy(ABC):
    @abstractmethod
    def _compute_output(self, context: Context) -> Optional[PolicyOutput]:
        """Subclass computes raw PolicyOutput (direction need not be normalized)."""
        ...

    def get_output(self, context: Context) -> Optional[PolicyOutput]:
        """Public interface. Normalizes direction, applies weight_scale downstream."""
        output = self._compute_output(context)
        if output is None:
            return None
        # Normalize direction to unit vector
        norm = sqrt(sum(w*w for w in output.direction.values()))
        if norm < 1e-6:
            return None
        output.direction = {t: w/norm for t, w in output.direction.items()}
        return output
```

This eliminates the per-policy "should I normalize?" decision. Direction is always normalized by the base class. Magnitude information lives in `salience` and `intensity`.

### 3.3 ActivityPolicy: EMA Design

ActivityPolicy is unique because "no rule matched" is a meaningful state (the user is doing something unrecognized). Its EMA behavior under the new model:

**Two separate EMA tracks:**

1. **Direction EMA**: When a rule matches, the instant direction is the matched tag(s) (unit-normalized). Direction is smoothed via EMA on the raw (non-normalized) vector, then re-normalized each tick. This preserves smooth direction transitions (e.g., `#focus` to `#chill`).

2. **Magnitude EMA**: A scalar EMA track. When a rule matches, instant magnitude = 1.0. When no rule matches, instant magnitude = 0.0. The smoothed magnitude decays toward zero.

**Boundary condition (magnitude near zero):** No special handling. When magnitude is negligible (e.g., 0.001), direction still participates in aggregation but contributes effectively nothing. This is mathematically equivalent to natural disappearance.

**Output construction:**
```python
def _compute_output(self, context):
    instant_direction = self._match_rules(context)  # Dict or empty
    
    # Direction EMA (raw vector space, re-normalized on output)
    self._dir_ema = ema_update(self._dir_ema, instant_direction, self.alpha)
    
    # Magnitude EMA (scalar)
    instant_mag = 1.0 if instant_direction else 0.0
    self._mag_ema = self.alpha * instant_mag + (1 - self.alpha) * self._mag_ema
    
    if not self._dir_ema:  # all tags decayed to zero
        return None
    
    return PolicyOutput(
        direction=self._dir_ema,  # base class will normalize
        salience=1.0,
        intensity=1.0,
        # magnitude is carried via the raw direction vector's norm
        # after base class normalization, the EMA magnitude is recovered
        # from the pre-normalization norm of _dir_ema
    )
```

**Revised approach**: Since ActivityPolicy's EMA naturally decays the whole vector, the cleanest mapping is:
- `direction` = normalized EMA vector (base class handles)
- Neither `salience` nor `intensity` is set (both 1.0)
- The EMA magnitude is captured by the pre-normalization norm of the direction vector, which the base class extracts before normalizing

This requires the base class to extract the raw norm before normalizing:

```python
def get_output(self, context: Context) -> Optional[PolicyOutput]:
    output = self._compute_output(context)
    if output is None:
        return None
    norm = sqrt(sum(w*w for w in output.direction.values()))
    if norm < 1e-6:
        return None
    output.direction = {t: w/norm for t, w in output.direction.items()}
    # Policy can signal that raw norm carries magnitude info
    # by leaving salience/intensity at 1.0 and relying on
    # the magnitude being baked into the direction pre-normalization.
    # We extract and preserve it:
    output._raw_magnitude = norm  # internal, used by aggregation
    return output
```

**Alternative (simpler):** ActivityPolicy explicitly sets `intensity = self._mag_ema` and `direction = normalized(self._dir_ema)`. The base class just normalizes direction. No `_raw_magnitude` magic.

**Decision: Use the explicit approach.** ActivityPolicy computes direction and magnitude separately, sets `intensity = magnitude_ema`, `direction = normalized(direction_ema)`. This is transparent and requires no special base class behavior.

## 4. TagSpec Extension

### 4.1 Current Structure (Retained)

```json
{
  "tag_name": {
    "fallback": { "target_tag": 0.8 }
  }
}
```

Fallback semantics (confirmed): **Intensity is transmitted along fallback edges with weight-based attenuation.** When `#storm` (intensity=1.0) falls back to `#rain` (weight=0.8), the `#rain` contribution receives intensity 0.8. This is consistent with the physical intuition that a violent storm implies heavy rain.

### 4.2 New: Domain Grouping

```json
{
  "#rain":  { "domain": "weather", "fallback": { "#chill": 0.2 } },
  "#storm": { "domain": "weather", "fallback": { "#rain": 0.8 } },
  "#dawn":  { "domain": "time" },
  "#day":   { "domain": "time" },
  "#focus": { "domain": "activity" }
}
```

**Domain** is an organizational attribute, not a runtime constraint. It groups tags into semantic families:
- `weather`: `#rain`, `#snow`, `#storm`, `#fog`, `#clear`, `#cloudy`
- `time`: `#dawn`, `#day`, `#sunset`, `#night`
- `season`: `#spring`, `#summer`, `#autumn`, `#winter`
- `activity`: `#focus`, `#chill`, `#media`, etc. (user-defined)

**Design constraint**: Tags across different domains do not overlap. Each tag belongs to exactly one domain.

**Validation**: Pure convention, no runtime enforcement. Domain information serves documentation, future tooling, and potential future domain-aware aggregation.

### 4.3 Opposition

Not introduced in this version. Opposition between tags (e.g., `#clear` vs `#cloudy`) is handled implicitly: if no fallback is defined between two tags, energy dissipates when the source tag is absent from the playlist universe. This is sufficient for the current system.

## 5. Matcher / Controller Interface Changes

### 5.1 Matcher

**Input**: `List[PolicyOutput]` (one per active policy, `None`s filtered out) plus policy `weight_scale` values.

**Aggregation**:
```
env_vector = sum(output.direction * output.salience * output.intensity * weight_scale
                 for output, weight_scale in active_policies)
```

**Fallback resolution**: Applied to `env_vector` before matching. Tags not present in any playlist are resolved along the fallback graph (recursive, intensity attenuated by edge weight) or dissipated.

**Matching**: Cosine similarity (retained, see Section 7.1 for future discussion).

**Additional outputs for controller**:
```python
@dataclass
class MatchResult:
    aggregated_tags: Dict[str, float]   # raw aggregated vector (for logging)
    best_playlist: Optional[str]        # cosine winner
    similarity_gap: float               # sim(1st) - sim(2nd), measures decisiveness
    max_policy_magnitude: float         # max(salience * intensity * ws) across policies
```

### 5.2 Controller

The controller currently uses a gate chain (CPU, fullscreen, cooldown). Two new signals from `MatchResult` are available for future use:

- **`similarity_gap`**: When the gap is small, the match is indecisive. The controller can increase cooldown to avoid flip-flopping between close candidates.
- **`max_policy_magnitude`**: When the strongest policy signal is weak, all signals are ambient. The controller can be more conservative. When a strong foreground signal exists, the controller can be more aggressive.

These are exposed in the interface but their use in controller logic is a separate design decision, not part of this refactor.

## 6. Configuration Changes

### 6.1 TagSpec in Config

New top-level section in `scheduler_config.json`:

```json
{
  "tag_schema": {
    "#rain":    { "domain": "weather", "fallback": { "#chill": 0.2 } },
    "#storm":   { "domain": "weather", "fallback": { "#rain": 0.8 } },
    "#snow":    { "domain": "weather", "fallback": { "#chill": 0.3 } },
    "#fog":     { "domain": "weather" },
    "#clear":   { "domain": "weather" },
    "#cloudy":  { "domain": "weather" },
    "#dawn":    { "domain": "time" },
    "#day":     { "domain": "time" },
    "#sunset":  { "domain": "time" },
    "#night":   { "domain": "time" },
    "#spring":  { "domain": "season" },
    "#summer":  { "domain": "season" },
    "#autumn":  { "domain": "season" },
    "#winter":  { "domain": "season" },
    "#focus":   { "domain": "activity" },
    "#chill":   { "domain": "activity" },
    "#media":   { "domain": "activity" }
  }
}
```

### 6.2 Pydantic Models

```python
class TagSpecConfig(BaseModel):
    domain: str
    fallback: Dict[str, float] = Field(default_factory=dict)

# In AppConfig:
tag_schema: Dict[str, TagSpecConfig] = Field(default_factory=dict)
```

### 6.3 weight_scale

Retained as-is in `_BasePolicyConfig`. No rename in this version. Semantics clarified in documentation: "policy-level priority multiplier, orthogonal to intensity."

### 6.4 Sub-vector Config in WeatherPolicy

The `_ID_TAGS` lookup table is restructured. Instead of `Dict[int, List[Dict[str, float]]]` (sub-vectors), entries become `Dict[int, Dict[str, float]]` (single dict). Opposition handling for tags like `#clear`/`#cloudy` is managed by fallback graph dissipation, not sub-vector isolation.

## 7. Deferred Decisions

### 7.1 Cosine Similarity vs. Dot Product

**Status**: Deferred to a future version.

Cosine similarity discards the aggregated vector's norm, meaning intensity/salience only influence direction competition between policies, not the final match quality. Dot product would let strong signals produce stronger matches, but introduces the bias problem: playlists with more tags systematically score higher.

With intensity/salience now explicit, the norm carries cleaner semantic information than before, which may change the calculus. This decision should be revisited once the refactored system is running and the behavior can be compared empirically (e.g., via heatmap visualization).

### 7.2 Dynamic Group Inhibition

**Status**: Deferred. Architectural direction recorded.

Concept: Policies are grouped (e.g., `ambient: [time, season]`, `foreground: [activity, weather]`). When foreground total magnitude exceeds a threshold, ambient contributions are suppressed.

Current mitigation: Static `weight_scale` ratios provide fixed priority ordering. Adequate for 4 policies with tuned parameters.

When to revisit: If the policy count grows beyond 4–5 and cross-policy tuning becomes impractical, or if user feedback indicates difficulty configuring `weight_scale` ratios.

Risk: Dynamic inhibition amplifies transition slopes (foreground rising + ambient falling = double the direction change rate). Mitigation would require smoothing the inhibition coefficient itself, adding another parameter.

### 7.3 Matching Algorithm Sensitive to Norm

Related to 7.1. An alternative is the "mixed approach": cosine selects the playlist (direction match), but the norm influences controller behavior (switching confidence). Section 5.2 partially enables this by exposing `similarity_gap` and `max_policy_magnitude` to the controller, without changing the matching algorithm itself.

## 8. Decision Record

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Playlist values = affinity (pure direction) | Playlist vectors are pre-normalized; only relative tag proportions matter. Avoids coupling playlist config to policy output scales. |
| D2 | ActivityPolicy EMA = whole-vector decay, not salience/intensity split | Closing an IDE doesn't mean "less certain it was focus" or "focus was weaker" — it means the signal is fading. The decay is ontologically unified. |
| D3 | Fallback transmits intensity (attenuated by edge weight) | `#storm → #rain (0.8)`: a violent storm implies heavy rain. Intensity attenuation matches physical intuition. |
| D4 | `weight_scale` retained as policy priority | Orthogonal to intensity. May be superseded by group inhibition in the future but currently the only cross-policy tuning knob. |
| D5 | Sub-vectors abolished, fallback graph is the universal mechanism | Sub-vectors were an engineering workaround for opposition handling. Fallback dissipation (no fallback defined = energy lost) handles the same case more uniformly. |
| D6 | Domain grouping as convention, no runtime validation | Domains organize tags for human understanding and future tooling. Runtime enforcement adds per-tick overhead for low practical value. |
| D7 | Flat tag naming (`#rain`) + TagSpec domain declaration | Hierarchical names (`#weather.rain`) add verbosity without runtime benefit. Domain info lives in TagSpec, not in the tag string. |
| D8 | Direction always L2-normalized by base class | Eliminates per-policy normalization decisions. Every policy answers the same three questions: direction (what?), salience (how certain?), intensity (how strong?). |
| D9 | ActivityPolicy: direction EMA + magnitude EMA, re-normalize each tick | Preserves direction transitions (e.g., `#focus` → `#chill`). Linear interpolation of unit vectors requires re-normalization; per-tick sqrt is negligible. |
| D10 | Magnitude near zero: natural decay, no special handling | Negligible magnitude contributes effectively nothing to aggregation. No threshold cutoff needed. |
| D11 | Controller receives `similarity_gap` and `max_policy_magnitude` | Enables future switching-confidence logic without changing the matching algorithm. |
| D12 | One-shot breaking change (v0.5.0) | Semver 0.x allows breaking changes. Gradual migration adds temporary complexity with no user benefit. |
| D13 | Cosine similarity retained (for now) | Deferred to post-refactor empirical evaluation. Current behavior is validated. |
| D14 | Tags across domains do not overlap | Design constraint. Simplifies aggregation (fallback before vs. after aggregation is equivalent). |

## 9. Migration Guide

### 9.1 Affected Files

| File | Changes |
|------|---------|
| `core/policies.py` | Base class: `_compute_output() -> Optional[PolicyOutput]`, `get_output()` with L2 normalization. All four policies rewritten to return `PolicyOutput`. ActivityPolicy EMA split into direction + magnitude tracks. WeatherPolicy `_ID_TAGS` restructured to single dicts. |
| `core/matcher.py` | Accepts `List[PolicyOutput]`. Aggregation uses `direction * salience * intensity * weight_scale`. Fallback resolution on aggregated vector. Returns `MatchResult` with `similarity_gap` and `max_policy_magnitude`. Sub-vector projection/compensation logic removed. |
| `core/controller.py` | `SchedulingController` accepts `MatchResult` (currently uses `best_playlist` only; `similarity_gap` and `max_policy_magnitude` available for future use). |
| `utils/config_loader.py` | Add `TagSpecConfig` model, `tag_schema` field on `AppConfig`. |
| `scheduler_config.example.json` | Add `tag_schema` section. Update any changed field names. |
| `core/scheduler.py` | Updated call signatures for Matcher/Controller. State export/import updated for new ActivityPolicy EMA structure. |

### 9.2 Migration Steps

1. Define `PolicyOutput` and `MatchResult` data classes.
2. Add `TagSpecConfig` to config loader; add `tag_schema` to example config.
3. Refactor `Policy` base class: `_compute_tags()` → `_compute_output()`, add direction normalization in `get_output()`.
4. Rewrite each policy to return `PolicyOutput`.
5. Refactor `Matcher`: new aggregation logic, fallback resolution, `MatchResult` output.
6. Update `SchedulingController` to accept `MatchResult`.
7. Update `Scheduler` orchestration and state export/import.
8. Validate with `misc/sim_match.py` and heatmap visualization.

### 9.3 Config Migration

No automated migration tool. Users update `scheduler_config.json` manually:
1. Add `tag_schema` section (can start empty; system works without it, fallback just doesn't apply).
2. No changes required to `playlists` or `policies` sections (structure unchanged).

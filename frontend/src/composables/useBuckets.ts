import { computed, ref } from "vue";
import rawBuckets from "../../public/buckets.json";

export const RAW_BUCKET_SECONDS = 60;

export const playlists = [
  { key: "summer_glow", label: "夏日余温", color: "#e38200" },
  { key: "bright_flow", label: "明亮流动", color: "#3f6df6" },
  { key: "night_chill", label: "夜间低语", color: "#6d55e8" },
  { key: "night_focus", label: "深度专注", color: "#4a5a8a" },
  { key: "sunset_glow", label: "落日余晖", color: "#c04f8a" },
  { key: "spring_bloom", label: "春日花开", color: "#58a861" },
  { key: "casual_anime", label: "闲适日常", color: "#8da0b7" },
  { key: "winter_vibes", label: "冬日氛围", color: "#7b8794" },
  { key: "autumn_drift", label: "秋日漂流", color: "#9a6a3a" },
  { key: "rainy_mood", label: "雨落时分", color: "#168a96" },
] as const;

export type PlaylistKey = (typeof playlists)[number]["key"];

export interface RawBucket {
  index: number;
  tsStart: number;
  tsEnd: number;
  scores: Record<string, number>;
}

export interface AggBucket {
  index: number;
  tsStart: number;
  tsEnd: number;
  scores: Record<PlaylistKey, number>;
}

const data = rawBuckets as RawBucket[];

export function useBuckets() {
  const aggSize = ref(8);
  const viewportSize = ref(15);
  const powerExponent = ref([1]);
  const viewportStart = ref([0]);

  const aggregated = computed<AggBucket[]>(() => {
    const n = aggSize.value;
    const result: AggBucket[] = [];

    for (let i = 0; i < data.length; i += n) {
      const chunk = data.slice(i, i + n);
      const avgScores: Record<string, number> = {};

      for (const pl of playlists) {
        const key = pl.key.toUpperCase();
        let sum = 0;
        for (const b of chunk) {
          sum += b.scores[key] ?? 0;
        }
        avgScores[pl.key] = sum / chunk.length;
      }

      result.push({
        index: result.length,
        tsStart: chunk[0].tsStart,
        tsEnd: chunk[chunk.length - 1].tsEnd,
        scores: avgScores as Record<PlaylistKey, number>,
      });
    }

    return result;
  });

  const maxStart = computed(() =>
    Math.max(0, aggregated.value.length - viewportSize.value),
  );

  const viewport = computed(() => {
    const start = Math.min(viewportStart.value[0], maxStart.value);
    return aggregated.value.slice(start, start + viewportSize.value);
  });

  const aggSeconds = computed(() => aggSize.value * RAW_BUCKET_SECONDS);

  /** 幂变换：f(s) = s^p，不做归一化 */
  function applyPowerTransform(
    scores: Record<PlaylistKey, number>,
    p: number,
  ): Record<PlaylistKey, number> {
    const result: Record<string, number> = {};
    for (const pl of playlists) {
      result[pl.key] = Math.pow(scores[pl.key] ?? 0, p);
    }
    return result as Record<PlaylistKey, number>;
  }

  /** 归一化：让所有播单分数之和 = 1（用于堆叠面积图等相对比例场景） */
  function normalizeScores(
    scores: Record<PlaylistKey, number>,
  ): Record<PlaylistKey, number> {
    let sum = 0;
    for (const pl of playlists) {
      sum += scores[pl.key] ?? 0;
    }
    if (sum === 0) return scores;
    const result: Record<string, number> = {};
    for (const pl of playlists) {
      result[pl.key] = (scores[pl.key] ?? 0) / sum;
    }
    return result as Record<PlaylistKey, number>;
  }

  function formatElapsed(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h <= 0) return `${m}m`;
    return `${h}h${m.toString().padStart(2, "0")}m`;
  }

  function formatAxisTick(value: number | Date): string {
    if (value instanceof Date) return "";
    const start = viewportStart.value[0];
    return formatElapsed((start + value) * aggSeconds.value);
  }

  function formatTimestamp(ts: number): string {
    return new Date(ts * 1000).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  const viewportTimeRange = computed(() => {
    const v = viewport.value;
    if (v.length === 0) return "";
    return `${formatTimestamp(v[0].tsStart)} - ${formatTimestamp(v[v.length - 1].tsEnd)}`;
  });

  return {
    data,
    aggregated,
    viewport,
    viewportStart,
    viewportSize,
    maxStart,
    aggSize,
    aggSeconds,
    powerExponent,
    applyPowerTransform,
    normalizeScores,
    formatAxisTick,
    formatTimestamp,
    viewportTimeRange,
  };
}

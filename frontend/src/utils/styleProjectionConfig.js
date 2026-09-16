// 投影スタイル分析（StyleProfile）の指標定義。
// バックエンド style_projection/metrics.py の compute_style_profile が返すキーと対応する。
export const STYLE_METRICS = [
  {
    key: "avg_group_size",
    label: "平均グループサイズ",
    desc: "1グループあたりの平均冊数",
    format: (v) => v.toFixed(2),
  },
  {
    key: "stdev_group_size",
    label: "グループサイズのばらつき",
    desc: "グループサイズの標準偏差",
    format: (v) => v.toFixed(2),
  },
  {
    key: "isolated_ratio",
    label: "孤立本の割合",
    desc: "どのグループにも属さない本の割合",
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: "avg_multi_membership",
    label: "平均複数所属数",
    desc: "1冊あたりが属するグループ数の平均",
    format: (v) => v.toFixed(2),
  },
  {
    key: "max_depth",
    label: "グループ階層の深さ",
    desc: "サブグループの最大階層",
    format: (v) => `${v}`,
  },
  {
    key: "clustering_coefficient",
    label: "クラスタ係数",
    desc: "本棚での隣接ネットワークの密集度（GDS localClusteringCoefficient）",
    format: (v) => v.toFixed(3),
  },
  {
    key: "modularity",
    label: "モジュラリティ",
    desc: "グループ分けと配置の一致度",
    format: (v) => v.toFixed(3),
  },
  {
    key: "modularity_nmi",
    label: "モジュラリティ (NMI)",
    desc: "GDS Louvainのコミュニティ検出との一致度（GDS利用時のみ）",
    format: (v) => v.toFixed(3),
  },
];

export function formatMetricValue(metric, value) {
  if (value === null || value === undefined) return "—";
  return metric.format(value);
}

export function formatComputedAt(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

// 本棚の物理配置分析（PlacementProfile）の指標定義。
// バックエンド backend/placement_analysis/metrics.py の compute_placement_metrics が
// 返すキーと対応する。
export const PLACEMENT_METRICS = [
  {
    key: "height_order_score",
    label: "高さの並び順",
    desc: "段の中で、本の高さが左右どちらかへ順に大きく/小さくなっていく度合い",
    format: (v) => v.toFixed(2),
  },
  {
    key: "height_staircase_score",
    label: "高さの段々（階段状）",
    desc: "隣り合う本同士を1組ずつ比べたとき、高さの増減が同じ方向へどれだけ連続するか",
    format: (v) => v.toFixed(2),
  },
  {
    key: "row_height_trend_score",
    label: "段をまたいだ高さの傾向",
    desc: "段を追うごとに本の高さがどちらかへ変化していく度合い（プラスは下段ほど大きい、マイナスは上段ほど大きい）",
    format: (v) => v.toFixed(2),
  },
  {
    key: "height_group_order_score",
    label: "グループ単位の高さの並び順",
    desc: "間隔で大きく区切られた小グループごとに高さの順序を見て平均した度合い（山型・谷型など、段全体では打ち消し合って見えない部分的な高さ順を拾う）",
    format: (v) => v.toFixed(2),
  },
  {
    key: "height_grouping_score",
    label: "高さのまとまり",
    desc: "隣り合う本同士が近い高さになりやすいか（マイナスは逆に離れた高さを並べる傾向）",
    format: (v) => v.toFixed(2),
  },
  {
    key: "color_grouping_score",
    label: "背表紙の色のまとまり",
    desc: "隣り合う本同士が近い色味になりやすいか",
    format: (v) => v.toFixed(2),
  },
  {
    key: "color_gradient_score",
    label: "色のグラデーション",
    desc: "背表紙の色相が、隣り合う本の間で色相環を一定方向へなだらかに変化しているか（虹色配置の度合い）",
    format: (v) => v.toFixed(2),
  },
  {
    key: "color_uniformity_score",
    label: "色の統一感",
    desc: "段全体として使われている色数がどれだけ絞られているか（パレットの統一感）",
    format: (v) => v.toFixed(2),
  },
  {
    key: "author_grouping_score",
    label: "著者のまとまり",
    desc: "同じ著者の本を隣り合わせに置きやすいか",
    format: (v) => v.toFixed(2),
  },
  {
    key: "genre_placement_modularity",
    label: "ジャンル×配置の一致度",
    desc: "NDCジャンル分類と、実際の物理的な配置のまとまりがどれだけ一致しているか",
    format: (v) => v.toFixed(3),
  },
  {
    key: "genre_placement_nmi",
    label: "ジャンル×配置の一致度（NMI）",
    desc: "配置だけから自動検出したまとまりと、ジャンル分類がどれだけ一致しているか",
    format: (v) => v.toFixed(3),
  },
  {
    key: "theme_placement_modularity",
    label: "内容テーマ×配置の一致度",
    desc: "あらすじからAIが抽出した内容テーマと、実際の配置のまとまりがどれだけ一致しているか",
    format: (v) => v.toFixed(3),
  },
  {
    key: "theme_placement_nmi",
    label: "内容テーマ×配置の一致度（NMI）",
    desc: "配置だけから自動検出したまとまりと、内容テーマがどれだけ一致しているか",
    format: (v) => v.toFixed(3),
  },
  {
    key: "concept_placement_modularity",
    label: "意味づけ×配置の一致度",
    desc: "自分で本に付けた意味づけ（Concept）と、実際の配置のまとまりがどれだけ一致しているか",
    format: (v) => v.toFixed(3),
  },
  {
    key: "concept_placement_nmi",
    label: "意味づけ×配置の一致度（NMI）",
    desc: "配置だけから自動検出したまとまりと、自分で付けた意味づけがどれだけ一致しているか",
    format: (v) => v.toFixed(3),
  },
  {
    key: "symmetry_score",
    label: "左右対称性",
    desc: "段の中の高さの並びが、中央を軸に鏡映的に対称かどうか",
    format: (v) => v.toFixed(2),
  },
  {
    key: "rhythm_score",
    label: "色の周期性",
    desc: "背表紙の色相が、2冊おき・3冊おきなど一定の周期で繰り返されているか",
    format: (v) => v.toFixed(2),
  },
  {
    key: "spacing_regularity",
    label: "間隔の均一さ",
    desc: "本と本の隙間の広さが、段の中でどれだけ一定に保たれているか",
    format: (v) => v.toFixed(2),
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

// backend/placement_analysis/isolation.py の4種のフラグに対応するラベル。
export const ISOLATION_FLAG_LABELS = {
  topological_isolated: "知識グラフ全体で孤立",
  semantic_isolated: "意味づけを誰とも共有していない",
  physical_isolated: "棚の同じ段に他の本がない",
  floating: "隣はあるが、高さ・色・著者・ジャンルどれも共通点がない",
};

export const ISOLATION_FLAG_DESCRIPTIONS = {
  topological_isolated: "意味づけ・著者・出版社・ジャンル・本棚での隣接のいずれでも他の本とつながっていません。",
  semantic_isolated: "この本に付けた意味づけ（Concept）を、他のどの本とも共有していません。",
  physical_isolated: "この本が置かれている段には、他に本がありません。",
  floating: "本棚では他の本の隣にありますが、高さ・色・著者・ジャンルのどの観点でも共通点がありません。",
};

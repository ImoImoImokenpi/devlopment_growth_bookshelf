export const NODE_CFG = {
  Book:      { color: "#5b9bd5", r: 7,    ja: "本" },
  Author:    { color: "#c9a84c", r: 5,    ja: "著者" },
  Publisher: { color: "#6aab8c", r: 5,    ja: "出版社" },
  NDC:       { color: "#9d78c4", r: null, ja: "NDC" },
  Concept:   { color: "#e07070", r: 6,    ja: "コンセプト" },
  Meaning:   { color: "#e09040", r: 4,    ja: "意味" },
};

export const LINK_CFG = {
  WRITTEN_BY:    { color: "#c9a84c", ja: "著者" },
  PUBLISHED_BY:  { color: "#6aab8c", ja: "出版社" },
  CLASSIFIED_AS: { color: "#9d78c4", ja: "分類" },
  BROADER:       { color: "#c8a0e8", ja: "上位NDC" },
  SHELF_NEXT:    { color: "#5b9bd5", ja: "本棚で隣接" },
  CONCEPT:       { color: "#e07070", ja: "コンセプト" },
  HAS_MEANING:   { color: "#e09040", ja: "意味" },
};

export const NDC_L1 = {
  "0": "総記", "1": "哲学", "2": "歴史・地理", "3": "社会科学",
  "4": "自然科学", "5": "技術", "6": "産業", "7": "芸術", "8": "言語", "9": "文学",
};

export const ndcR = (level) => ([13, 9, 7, 5][level - 1] ?? 5);

export const nodeDisplayLabel = (n) =>
  n.title || n.name || n.code || n.text || "";

// タップした本の関連理由(type)を、対応するリレーション種別(LINK_CFG のキー)にマッピングする。
// BookDetailPanel の関連本リストの色分けに使う。
export const REASON_LINK_TYPE = {
  concept:   "CONCEPT",
  author:    "WRITTEN_BY",
  publisher: "PUBLISHED_BY",
  ndc:       "CLASSIFIED_AS",
  shelf:     "SHELF_NEXT",
};

// My本棚のドロップダウンから開く「スタイル分析」画面。
// 左に自分の本棚（読み取り専用のビジュアル表示）、右に本棚の物理配置分析
// （PlacementProfile: 高さ・色・著者・ジャンルの並べ方の癖、孤立している本、
// デザイン配置と判断した根拠）を並べ、クリックすると本棚側がそのまま
// 光って対応するので、本棚と分析内容を同時に見比べられる。
//
// 以前は投影スタイル分析システム（style_projection、実験用の抽象的な
// グループ指標）の数値をここに出していたが、一般参加者が自分の本棚を見て
// 「へえ」と思えるような内容ではなかったため、本棚配置分析システム
// （placement_analysis）の指標に差し替えた。投影バイアス実験向けの
// 履歴付き分析は引き続き「投影スタイル分析」ページ（StyleProjectionHistory）
// に残っている。
import { useEffect, useState } from "react";
import PageHeader from "../components/PageHeader";
import Breadcrumb from "../components/Breadcrumb";
import ReadOnlySpineShelf from "../components/explore/ReadOnlySpineShelf";
import { API_ORIGIN, getParticipantId } from "../utils/participant";
import {
  PLACEMENT_METRICS, formatMetricValue, formatComputedAt,
  ISOLATION_FLAG_LABELS, ISOLATION_FLAG_DESCRIPTIONS,
} from "../utils/placementAnalysisConfig";

const API = API_ORIGIN;
const ISOLATION_FLAGS = ["topological_isolated", "semantic_isolated", "physical_isolated", "floating"];

export default function MyStyleAnalysis() {
  const participantId = getParticipantId();

  const [profile, setProfile] = useState(null);
  const [isolation, setIsolation] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);
  const [narrative, setNarrative] = useState(null);
  const [isNarrating, setIsNarrating] = useState(false);
  const [narrativeError, setNarrativeError] = useState(null);
  const [themes, setThemes] = useState([]);
  const [isGeneratingThemes, setIsGeneratingThemes] = useState(false);
  const [themeError, setThemeError] = useState(null);
  const [contentAlignment, setContentAlignment] = useState(null);

  const [focusIsbn, setFocusIsbn] = useState(null);
  const [hoveredIsbns, setHoveredIsbns] = useState([]);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    setNarrative(null);
    setNarrativeError(null);
    setThemeError(null);
    try {
      const [profileRes, isolationRes, evidenceRes, themesRes, alignmentRes] = await Promise.all([
        fetch(`${API}/placement_analysis/${participantId}/profile/latest`),
        fetch(`${API}/placement_analysis/${participantId}/isolation`),
        fetch(`${API}/placement_analysis/${participantId}/design-evidence`),
        fetch(`${API}/placement_analysis/${participantId}/themes`),
        fetch(`${API}/placement_analysis/${participantId}/content-alignment`),
      ]);

      setProfile(profileRes.ok ? await profileRes.json() : null);
      setIsolation(isolationRes.ok ? await isolationRes.json() : null);
      setEvidence(evidenceRes.ok ? (await evidenceRes.json()).evidence || [] : []);
      setThemes(themesRes.ok ? (await themesRes.json()).themes || [] : []);
      setContentAlignment(alignmentRes.ok ? await alignmentRes.json() : null);
    } catch (err) {
      setError(err.message || "読み込みに失敗しました");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participantId]);

  const handleSaveSnapshot = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const res = await fetch(`${API}/placement_analysis/${participantId}/recompute`, { method: "POST" });
      if (!res.ok) throw new Error("記録に失敗しました");
      const saved = await res.json();
      setProfile(saved);
      const [isolationRes, evidenceRes] = await Promise.all([
        fetch(`${API}/placement_analysis/${participantId}/isolation`),
        fetch(`${API}/placement_analysis/${participantId}/design-evidence`),
      ]);
      setIsolation(isolationRes.ok ? await isolationRes.json() : null);
      setEvidence(evidenceRes.ok ? (await evidenceRes.json()).evidence || [] : []);
      setSaveMessage("この状態を記録し、分析を更新しました。");
      setNarrative(null); // 記録し直したので、古い言語化結果は破棄する
    } catch (err) {
      setSaveMessage(err.message || "記録に失敗しました");
    } finally {
      setIsSaving(false);
    }
  };

  const handleNarrate = async () => {
    setIsNarrating(true);
    setNarrativeError(null);
    try {
      const res = await fetch(`${API}/placement_analysis/${participantId}/narrative`);
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error(json?.detail || "言語化に失敗しました");
      setNarrative(json.narrative);
    } catch (err) {
      setNarrativeError(err.message || "言語化に失敗しました");
    } finally {
      setIsNarrating(false);
    }
  };

  const handleGenerateThemes = async () => {
    setIsGeneratingThemes(true);
    setThemeError(null);
    try {
      const res = await fetch(`${API}/placement_analysis/${participantId}/themes/generate`, { method: "POST" });
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error(json?.detail || "内容テーマの生成に失敗しました");
      if (json.skipped) {
        setThemeError(json.reason || "あらすじのある本が少なすぎます");
      } else {
        // テーマが変わったのでPlacementProfile側のtheme_placement_*とクロス分析も更新する
        const [profileRes, themesRes, alignmentRes] = await Promise.all([
          fetch(`${API}/placement_analysis/${participantId}/recompute`, { method: "POST" }),
          fetch(`${API}/placement_analysis/${participantId}/themes`),
          fetch(`${API}/placement_analysis/${participantId}/content-alignment`),
        ]);
        if (profileRes.ok) setProfile(await profileRes.json());
        if (themesRes.ok) setThemes((await themesRes.json()).themes || []);
        if (alignmentRes.ok) setContentAlignment(await alignmentRes.json());
        setNarrative(null);
      }
    } catch (err) {
      setThemeError(err.message || "内容テーマの生成に失敗しました");
    } finally {
      setIsGeneratingThemes(false);
    }
  };

  const isolationBooks = isolation?.books || [];
  const isolationSummary = isolation?.summary || null;

  const isolationGroups = ISOLATION_FLAGS
    .map(flag => ({
      flag,
      books: isolationBooks.filter(b => b[flag]),
    }))
    .filter(g => g.books.length > 0);

  return (
    <div style={s.page}>
      <div style={s.headerRow}>
        <PageHeader
          title={<Breadcrumb items={[{ label: "My本棚", to: "/" }, { label: "スタイル分析" }]} />}
          sub="本棚の高さ・色・著者・ジャンルの並べ方の癖と、孤立している本、デザイン重視と判断した配置の根拠を、実際の配置から分析しています。"
          right={
            <button style={s.saveBtn} onClick={handleSaveSnapshot} disabled={isSaving}>
              {isSaving ? "記録中…" : "この状態を記録する"}
            </button>
          }
        />
      </div>

      {error && <p style={s.statusError}>{error}</p>}
      {saveMessage && <p style={s.saveMessage}>{saveMessage}</p>}

      <div style={s.body}>
        <div style={s.shelfPane} onClick={() => setFocusIsbn(null)}>
          <ReadOnlySpineShelf
            participantId={participantId}
            focusIsbn={focusIsbn}
            onFocus={setFocusIsbn}
            highlightIsbns={hoveredIsbns}
          />
        </div>

        <aside style={s.analysisPane}>
          {isLoading && <p style={s.status}>分析中…</p>}

          {!isLoading && profile && profile.book_count > 0 && (
            <>
              <div style={s.metricGrid}>
                {PLACEMENT_METRICS.map(metric => (
                  <div key={metric.key} style={s.metricCard}>
                    <div style={s.metricLabel}>{metric.label}</div>
                    <div style={s.metricValue}>{formatMetricValue(metric, profile[metric.key])}</div>
                    <div style={s.metricDesc}>{metric.desc}</div>
                  </div>
                ))}
              </div>
              {profile.computed_at && (
                <div style={s.computedAt}>{formatComputedAt(profile.computed_at)} 時点</div>
              )}

              {profile.design_intent && (
                <div style={s.designBadge}>
                  機能的な理由（高さ・色・著者・ジャンル）では説明しづらく、見た目を意識した配置の可能性があります
                </div>
              )}

              <div style={s.section}>
                <div style={s.sectionTitle}>あらすじから内容テーマを分析</div>
                <div style={s.sectionHint}>
                  あらすじの内容が近い本同士をAIがまとめます。生成すると、上の指標の
                  「内容テーマ×配置の一致度」が更新されます。
                </div>
                <button style={s.narrateBtn} onClick={handleGenerateThemes} disabled={isGeneratingThemes}>
                  {isGeneratingThemes ? "分析中…" : themes.length > 0 ? "内容テーマを作り直す" : "内容テーマを生成する"}
                </button>
                {themeError && <div style={s.error}>{themeError}</div>}
                {themes.length > 0 && (
                  <div style={s.list}>
                    {themes.map(t => (
                      <button
                        key={t.name}
                        style={s.listRow}
                        title={t.titles?.join("、")}
                        onMouseEnter={() => setHoveredIsbns(t.isbns)}
                        onMouseLeave={() => setHoveredIsbns([])}
                        onClick={(ev) => { ev.stopPropagation(); setFocusIsbn(t.isbns[0] || null); }}
                      >
                        <span style={s.listRowName}>{t.name}</span>
                        <span style={s.listRowCount}>{t.count}冊</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {contentAlignment && (contentAlignment.themes?.length > 0 || contentAlignment.concepts?.length > 0) && (
                <div style={s.section}>
                  <div style={s.sectionTitle}>配置×内容のクロス分析</div>
                  <div style={s.sectionHint}>
                    テーマ・意味づけごとに、実際にどれだけ物理的にまとめて置いているか（1.0に近いほど固めて配置）。
                  </div>
                  {contentAlignment.themes?.length > 0 && (
                    <>
                      <div style={s.crossSubTitle}>内容テーマ別</div>
                      <div style={s.list}>
                        {contentAlignment.themes.map(g => (
                          <button
                            key={`theme-${g.name}`}
                            style={s.listRow}
                            title={g.titles?.join("、")}
                            onMouseEnter={() => setHoveredIsbns(g.isbns)}
                            onMouseLeave={() => setHoveredIsbns([])}
                            onClick={(ev) => { ev.stopPropagation(); setFocusIsbn(g.isbns[0] || null); }}
                          >
                            <span style={s.listRowName}>{g.name}（{g.book_count}冊・{g.shelves_used}段）</span>
                            <span style={s.listRowCount}>{g.clustering_rate.toFixed(2)}</span>
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                  {contentAlignment.concepts?.length > 0 && (
                    <>
                      <div style={{ ...s.crossSubTitle, marginTop: 10 }}>意味づけ別</div>
                      <div style={s.list}>
                        {contentAlignment.concepts.map(g => (
                          <button
                            key={`concept-${g.name}`}
                            style={s.listRow}
                            title={g.titles?.join("、")}
                            onMouseEnter={() => setHoveredIsbns(g.isbns)}
                            onMouseLeave={() => setHoveredIsbns([])}
                            onClick={(ev) => { ev.stopPropagation(); setFocusIsbn(g.isbns[0] || null); }}
                          >
                            <span style={s.listRowName}>{g.name}（{g.book_count}冊・{g.shelves_used}段）</span>
                            <span style={s.listRowCount}>{g.clustering_rate.toFixed(2)}</span>
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              <div style={s.section}>
                <div style={s.sectionTitle}>言葉で説明してもらう</div>
                {!narrative && (
                  <button style={s.narrateBtn} onClick={handleNarrate} disabled={isNarrating}>
                    {isNarrating ? "分析中…" : "この指標から並べ方の癖を説明してもらう"}
                  </button>
                )}
                {narrativeError && <div style={s.error}>{narrativeError}</div>}
                {narrative && (
                  <>
                    <div style={s.narrativeText}>{narrative}</div>
                    <button style={s.narrateRetryBtn} onClick={handleNarrate} disabled={isNarrating}>
                      {isNarrating ? "再分析中…" : "もう一度説明してもらう"}
                    </button>
                  </>
                )}
              </div>
            </>
          )}

          {!isLoading && (!profile || profile.book_count === 0) && (
            <p style={s.status}>本棚に本を並べるとここに分析結果が表示されます。</p>
          )}

          {!isLoading && evidence.length > 0 && (
            <div style={s.section}>
              <div style={s.sectionTitle}>デザイン重視と判断した根拠（{evidence.length}件）</div>
              <div style={s.list}>
                {evidence.map(e => (
                  <button
                    key={e.evidence_id}
                    style={s.listRow}
                    title={e.titles?.join("、")}
                    onMouseEnter={() => setHoveredIsbns(e.isbns)}
                    onMouseLeave={() => setHoveredIsbns([])}
                    onClick={(ev) => { ev.stopPropagation(); setFocusIsbn(e.isbns[0] || null); }}
                  >
                    <span style={s.listRowName}>
                      {e.label}（{e.shelf_index + 1}段目）
                    </span>
                    <span style={s.listRowCount}>score {Number(e.score).toFixed(2)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {!isLoading && isolationSummary && isolationGroups.length > 0 && (
            <div style={s.section}>
              <div style={s.sectionTitle}>
                孤立している本（{isolationSummary.book_count}冊中、いずれか該当する本があります）
              </div>
              {isolationGroups.map(group => (
                <div key={group.flag} style={s.isolationGroup}>
                  <div style={s.isolationGroupTitle} title={ISOLATION_FLAG_DESCRIPTIONS[group.flag]}>
                    {ISOLATION_FLAG_LABELS[group.flag]}（{group.books.length}冊）
                  </div>
                  <div style={s.list}>
                    {group.books.map(book => (
                      <button
                        key={book.isbn}
                        style={s.listRow}
                        onMouseEnter={() => setHoveredIsbns([book.isbn])}
                        onMouseLeave={() => setHoveredIsbns([])}
                        onClick={(ev) => { ev.stopPropagation(); setFocusIsbn(book.isbn); }}
                      >
                        <span style={s.listRowName}>{book.title}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

const NAVBAR_SPACE = 66;
const SHELF_WIDTH_PCT = 40; // My本棚（Home.js）の既定の本棚幅と揃える

const s = {
  page: {
    height: "100vh", paddingTop: NAVBAR_SPACE, boxSizing: "border-box",
    display: "flex", flexDirection: "column",
    background: "#f7f3ea", overflow: "hidden",
  },
  headerRow: { flexShrink: 0, padding: "20px 28px 12px" },
  statusError: { color: "#c9506a", fontSize: 13, padding: "0 28px" },
  saveMessage: { color: "#5a7a4a", fontSize: 13, padding: "0 28px" },
  status: { color: "#888", fontSize: 14 },

  body: {
    flex: 1, minHeight: 0, overflow: "hidden",
    display: "flex", gap: 20, padding: "0 28px 24px", boxSizing: "border-box",
  },
  shelfPane: {
    flex: "0 0 auto", flexBasis: `${SHELF_WIDTH_PCT}%`, minWidth: 0, height: "100%",
    overflow: "auto", display: "flex", alignItems: "flex-start", justifyContent: "center",
  },
  analysisPane: {
    flex: "1 1 auto", minWidth: 280, height: "100%", overflowY: "auto",
    borderLeft: "1px solid #ede8da", paddingLeft: 20,
  },

  saveBtn: {
    border: "1px solid #c9a84c", borderRadius: 999, padding: "7px 16px",
    fontSize: 13, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb",
    cursor: "pointer",
  },

  metricGrid: {
    display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 4,
  },
  metricCard: {
    border: "1px solid #e5ded0", borderRadius: 10, padding: "10px 12px", background: "#fff",
  },
  metricLabel: { fontSize: 11.5, fontWeight: 700, color: "#8a7a63" },
  metricValue: { fontSize: 18, fontWeight: 700, color: "#2a1f0e", margin: "4px 0 2px" },
  metricDesc: { fontSize: 10.5, color: "#a89a83", lineHeight: 1.4 },
  computedAt: { fontSize: 10.5, color: "#a89a83", marginBottom: 12 },

  designBadge: {
    fontSize: 12, color: "#6a4a1f", background: "#fff3dc", border: "1px solid #f0dcaa",
    borderRadius: 10, padding: "10px 12px", lineHeight: 1.6, marginBottom: 8,
  },

  narrateBtn: {
    border: "1px solid #c9a84c", borderRadius: 10, padding: "10px 14px",
    fontSize: 12.5, fontWeight: 700, color: "#8a5a1f", background: "#fdeecb",
    cursor: "pointer", width: "100%", textAlign: "center",
  },
  narrateRetryBtn: {
    marginTop: 8, border: "1px solid #e5ded0", borderRadius: 8, padding: "6px 12px",
    fontSize: 11.5, color: "#8a7a63", background: "#fff", cursor: "pointer",
  },
  narrativeText: {
    fontSize: 13, color: "#3a3024", lineHeight: 1.8, background: "#fff",
    border: "1px solid #ede8da", borderRadius: 10, padding: "12px 14px",
  },
  error: {
    fontSize: 11.5, color: "#c9506a", padding: "8px 12px", borderRadius: 10, background: "#fff0f2",
  },

  section: { marginTop: 20 },
  sectionTitle: { fontSize: 12.5, fontWeight: 700, color: "#5a4a33", marginBottom: 8 },
  sectionHint: { fontSize: 11, color: "#a89a83", lineHeight: 1.5, marginBottom: 8 },
  crossSubTitle: { fontSize: 11, fontWeight: 700, color: "#8a5a1f", marginBottom: 4 },
  isolationGroup: { marginBottom: 14 },
  isolationGroupTitle: { fontSize: 11.5, fontWeight: 700, color: "#8a5a1f", marginBottom: 6 },
  list: { display: "flex", flexDirection: "column", gap: 4 },
  listRow: {
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
    width: "100%", textAlign: "left",
    border: "1px solid #ede8da", borderRadius: 8, padding: "7px 10px",
    background: "#fff", cursor: "pointer", fontSize: 12.5, color: "#3a3024",
  },
  listRowName: {
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
  },
  listRowCount: { flexShrink: 0, color: "#8a7a63", fontSize: 11 },
};

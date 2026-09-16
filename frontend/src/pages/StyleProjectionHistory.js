// 投影スタイル分析（StyleProfile）の閲覧ページ。
// StyleProfileは上書きせず追記式で保存されているため、参加者ごとの
// 「昔のスタイル」と「今のスタイル」を並べて見比べられる。
import { useEffect, useMemo, useState } from "react";
import { API_ORIGIN } from "../utils/participant";
import { STYLE_METRICS, formatMetricValue, formatComputedAt } from "../utils/styleProjectionConfig";

const API = `${API_ORIGIN}/style_projection`;

export default function StyleProjectionHistory() {
  const [participants, setParticipants] = useState([]);
  const [participantId, setParticipantIdState] = useState(null);
  const [history, setHistory] = useState([]);
  const [fromId, setFromId] = useState(null);
  const [toId, setToId] = useState(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/participants`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("参加者一覧の取得に失敗しました"))))
      .then((json) => {
        if (cancelled) return;
        const list = json.participants || [];
        setParticipants(list);
        if (list.length > 0) setParticipantIdState(list[0].participant_id);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoadingList(false));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!participantId) return;
    let cancelled = false;
    setLoadingHistory(true);
    setError(null);
    fetch(`${API}/${participantId}/profile/history`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("履歴の取得に失敗しました"))))
      .then((json) => {
        if (cancelled) return;
        const profiles = json.profiles || [];
        setHistory(profiles);
        if (profiles.length > 0) {
          setFromId(profiles[0].profile_id);
          setToId(profiles[profiles.length - 1].profile_id);
        } else {
          setFromId(null);
          setToId(null);
        }
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoadingHistory(false));
    return () => { cancelled = true; };
  }, [participantId]);

  const fromProfile = useMemo(() => history.find((p) => p.profile_id === fromId) || null, [history, fromId]);
  const toProfile = useMemo(() => history.find((p) => p.profile_id === toId) || null, [history, toId]);

  return (
    <div style={s.scrollArea}>
      <div style={s.header}>
        <h1 style={s.title}>投影スタイル分析</h1>
        <p style={s.subtitle}>
          本の配置・グルーピングから計算した構造指標（StyleProfile）は上書きせず記録が残ります。
          「昔」と「今」を選んで見比べられます。
        </p>
      </div>

      {loadingList && <p style={s.status}>参加者一覧を読み込んでいます…</p>}
      {error && <p style={s.statusError}>{error}</p>}

      {!loadingList && !error && participants.length === 0 && (
        <p style={s.status}>
          まだStyleProfileが計算された参加者がいません。
          <code style={s.code}>POST /style_projection/ingest</code> で本棚配置を投入し、
          <code style={s.code}>POST /style_projection/&#123;participant_id&#125;/profile/recompute</code> で計算してください。
        </p>
      )}

      {!loadingList && participants.length > 0 && (
        <>
          <div style={s.controlsRow}>
            <label style={s.selectLabel}>
              参加者
              <select
                value={participantId || ""}
                onChange={(e) => setParticipantIdState(e.target.value)}
                style={s.select}
              >
                {participants.map((p) => (
                  <option key={p.participant_id} value={p.participant_id}>
                    {p.participant_id}（{p.role || "role不明"}・{p.profile_count}件）
                  </option>
                ))}
              </select>
            </label>
          </div>

          {loadingHistory && <p style={s.status}>履歴を読み込んでいます…</p>}

          {!loadingHistory && history.length === 0 && (
            <p style={s.status}>この参加者にはまだStyleProfileがありません。</p>
          )}

          {!loadingHistory && history.length > 0 && (
            <>
              <Timeline history={history} fromId={fromId} toId={toId} />

              <div style={s.controlsRow}>
                <label style={s.selectLabel}>
                  昔（比較元）
                  <select value={fromId || ""} onChange={(e) => setFromId(e.target.value)} style={s.select}>
                    {history.map((p) => (
                      <option key={p.profile_id} value={p.profile_id}>{formatComputedAt(p.computed_at)}</option>
                    ))}
                  </select>
                </label>
                <span style={s.arrow}>→</span>
                <label style={s.selectLabel}>
                  今（比較先）
                  <select value={toId || ""} onChange={(e) => setToId(e.target.value)} style={s.select}>
                    {history.map((p) => (
                      <option key={p.profile_id} value={p.profile_id}>{formatComputedAt(p.computed_at)}</option>
                    ))}
                  </select>
                </label>
              </div>

              {fromProfile && toProfile && (
                <MetricTable fromProfile={fromProfile} toProfile={toProfile} history={history} />
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── スナップショットのタイムライン ──────────────────────────
function Timeline({ history, fromId, toId }) {
  return (
    <div style={s.timeline}>
      {history.map((p, i) => {
        const isFrom = p.profile_id === fromId;
        const isTo = p.profile_id === toId;
        return (
          <div key={p.profile_id} style={s.timelineItem}>
            <div
              style={{
                ...s.timelineDot,
                background: isTo ? "#c9a84c" : isFrom ? "#8a7a63" : "#e5ded0",
              }}
            />
            <div style={s.timelineLabel}>{formatComputedAt(p.computed_at)}</div>
            {isFrom && <div style={s.timelineTag}>昔</div>}
            {isTo && <div style={{ ...s.timelineTag, color: "#8a5a1f", background: "#fdeecb" }}>今</div>}
            {i < history.length - 1 && <div style={s.timelineConnector} />}
          </div>
        );
      })}
    </div>
  );
}

// ── 指標比較テーブル（各指標に全履歴のスパークライン付き） ──────
function MetricTable({ fromProfile, toProfile, history }) {
  return (
    <div style={s.table}>
      <div style={{ ...s.tableRow, ...s.tableHeadRow }}>
        <div style={s.colMetric}>指標</div>
        <div style={s.colTrend}>推移</div>
        <div style={s.colValue}>昔</div>
        <div style={s.colValue}>今</div>
        <div style={s.colDiff}>差分</div>
      </div>
      {STYLE_METRICS.map((metric) => {
        const a = fromProfile[metric.key];
        const b = toProfile[metric.key];
        const diff = a !== null && a !== undefined && b !== null && b !== undefined ? b - a : null;
        const series = history.map((p) => p[metric.key]);
        return (
          <div key={metric.key} style={s.tableRow} title={metric.desc}>
            <div style={s.colMetric}>
              <div style={s.metricLabel}>{metric.label}</div>
              <div style={s.metricDesc}>{metric.desc}</div>
            </div>
            <div style={s.colTrend}>
              <Sparkline series={series} />
            </div>
            <div style={s.colValue}>{formatMetricValue(metric, a)}</div>
            <div style={s.colValue}>{formatMetricValue(metric, b)}</div>
            <div style={{ ...s.colDiff, color: diffColor(diff) }}>
              {diff === null ? "—" : `${diff > 0 ? "+" : ""}${metric.format(diff)}`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function diffColor(diff) {
  if (diff === null || diff === undefined || diff === 0) return "#8a7a63";
  return diff > 0 ? "#2f7a4f" : "#c9506a";
}

// ── 小さな折れ線（全履歴の推移を一目で見せる） ─────────────────
function Sparkline({ series, width = 96, height = 28 }) {
  const points = series
    .map((v, i) => ({ i, v }))
    .filter((p) => p.v !== null && p.v !== undefined);

  if (points.length < 2) {
    return <div style={s.sparklineEmpty}>データ不足</div>;
  }

  const values = points.map((p) => p.v);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / Math.max(1, series.length - 1);

  const path = points
    .map((p) => {
      const x = p.i * stepX;
      const y = height - ((p.v - min) / span) * (height - 6) - 3;
      return `${x},${y}`;
    })
    .join(" ");

  const last = points[points.length - 1];
  const lastX = last.i * stepX;
  const lastY = height - ((last.v - min) / span) * (height - 6) - 3;

  return (
    <svg width={width} height={height}>
      <polyline points={path} fill="none" stroke="#c9a84c" strokeWidth="1.6" />
      <circle cx={lastX} cy={lastY} r="2.4" fill="#c9a84c" />
    </svg>
  );
}

const s = {
  scrollArea: {
    height: "100%", overflowY: "auto", boxSizing: "border-box",
    maxWidth: 900, margin: "0 auto", padding: "0 28px 40px",
  },
  header: { marginBottom: 18 },
  title: { fontSize: 22, fontWeight: 700, color: "#2a1f0e", margin: "0 0 6px" },
  subtitle: { fontSize: 13, color: "#8a7a63", lineHeight: 1.6, margin: 0 },
  status: { color: "#888", fontSize: 14 },
  statusError: { color: "#c9506a", fontSize: 14 },
  code: {
    display: "inline-block", margin: "0 4px", padding: "1px 6px",
    background: "#f3ede0", borderRadius: 4, fontSize: 12, fontFamily: "monospace",
  },

  controlsRow: {
    display: "flex", alignItems: "flex-end", gap: 14, marginBottom: 18, flexWrap: "wrap",
  },
  selectLabel: { display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "#8a7a63" },
  select: {
    border: "1px solid #e5ded0", borderRadius: 8, padding: "6px 10px",
    fontSize: 13, background: "#fff", color: "#2a1f0e", minWidth: 220,
  },
  arrow: { fontSize: 16, color: "#c9a84c", paddingBottom: 8 },

  timeline: {
    display: "flex", alignItems: "flex-start", gap: 0, marginBottom: 24,
    overflowX: "auto", padding: "8px 4px 16px",
  },
  timelineItem: { position: "relative", display: "flex", flexDirection: "column", alignItems: "center", width: 110, flexShrink: 0 },
  timelineDot: { width: 12, height: 12, borderRadius: "50%", marginBottom: 6, border: "2px solid #fff", boxShadow: "0 0 0 1px #e5ded0" },
  timelineLabel: { fontSize: 10.5, color: "#8a7a63", textAlign: "center", whiteSpace: "nowrap" },
  timelineTag: {
    marginTop: 4, fontSize: 9.5, fontWeight: 700, color: "#5a4a33", background: "#efe6d0",
    borderRadius: 999, padding: "1px 8px",
  },
  timelineConnector: {
    position: "absolute", top: 5, left: "60%", width: "80%", height: 2, background: "#e5ded0", zIndex: -1,
  },

  table: {
    border: "1px solid #e5ded0", borderRadius: 12, overflow: "hidden", background: "#fff",
  },
  tableRow: {
    display: "grid",
    gridTemplateColumns: "1.6fr 1fr 0.8fr 0.8fr 0.9fr",
    alignItems: "center",
    gap: 10,
    padding: "12px 16px",
    borderBottom: "1px solid #f0ebdd",
  },
  tableHeadRow: {
    background: "#faf6ec", fontSize: 11, fontWeight: 700, color: "#8a7a63",
    textTransform: "uppercase", letterSpacing: "0.04em",
  },
  colMetric: { display: "flex", flexDirection: "column", gap: 2 },
  metricLabel: { fontSize: 13, fontWeight: 700, color: "#2a1f0e" },
  metricDesc: { fontSize: 11, color: "#a89a83" },
  colTrend: {},
  colValue: { fontSize: 13, color: "#4a3f2f", textAlign: "right", fontVariantNumeric: "tabular-nums" },
  colDiff: { fontSize: 13, fontWeight: 700, textAlign: "right", fontVariantNumeric: "tabular-nums" },
  sparklineEmpty: { fontSize: 10, color: "#c9c0ac" },
};

// 本棚（中央）と発見と対話（左）・本詳細（右）で共有する状態。
//
// ペイン間で同じものを見ている必要がある：
//   - どの本が選ばれているか      → 意味づけ入力の対象
//   - どの発見が未確定か          → 本棚上の光の線、質問カード、まとめて確認
//   - どの本を強調するか          → 対話で言及された本を本棚側で光らせる
//
// これらをどれか一つのコンポーネントに持たせると、他から触れなくなる。
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const API = "http://localhost:8000";

export const ShelfWorkspaceContext = createContext(null);

export function useShelfWorkspace() {
  const ctx = useContext(ShelfWorkspaceContext);
  if (!ctx) throw new Error("ShelfWorkspaceProvider の外で useShelfWorkspace が呼ばれました");
  return ctx;
}

export function ShelfWorkspaceProvider({ children }) {
  // ── 選択（設計書4章：1冊タップ / 範囲選択）──
  const [selectedIsbns, setSelectedIsbns] = useState([]);

  // 1冊タップで開く「この本について」の対象（設計書4章①）。
  // 以前は画面右に別のスライドパネルを重ねていたが、2ペイン構成では
  // 右ペインの中に出す。パネルが二重に出るのを避けるため。
  const [focusIsbn, setFocusIsbn] = useState(null);

  // タップした本の「周辺」＝関連本とつながりの理由、そして描画用の部分グラフ。
  // 右ペインのKGミニビューと関連本リスト、本棚側の強調が同じものを見るので、
  // それぞれで取りに行かずここで1回だけ取る。
  const [focusDetail, setFocusDetail] = useState(null);
  const [isFocusLoading, setIsFocusLoading] = useState(false);

  useEffect(() => {
    if (!focusIsbn) {
      setFocusDetail(null);
      return;
    }
    let cancelled = false;
    setIsFocusLoading(true);
    fetch(`${API}/knowledge_graph/book/${focusIsbn}`)
      .then(res => (res.ok ? res.json() : null))
      .then(json => { if (!cancelled) setFocusDetail(json); })
      .catch(err => console.error("本の周辺グラフを取得できませんでした", err))
      .finally(() => { if (!cancelled) setIsFocusLoading(false); });
    return () => { cancelled = true; };
  }, [focusIsbn]);


  // ── 発見（設計書3.3）──
  const [discoveries, setDiscoveries] = useState([]);
  const [isLoadingDiscoveries, setIsLoadingDiscoveries] = useState(false);

  // ── 強調（対話や提案が根拠にした本）──
  const [highlightIsbns, setHighlightIsbns] = useState([]);

  // 意味づけ単位の強調。右ペインの意味づけにカーソルを合わせている間だけ、
  // その意味づけ固有の色で本棚を光らせる。
  // 色を棚まで運ぶ必要があるので、ISBNの配列とは別の入れ物にしている。
  const [conceptHighlight, setConceptHighlight] = useState(null); // { color, isbns } | null

  // 発見バブルの「さらに話す」から左ペインの対話へ話題を引き継ぐための種
  // （設計書6.2の2段階構成：一次応答 → 自由記述への展開）
  const [chatSeed, setChatSeed] = useState(null); // { question, discoveryId } | null

  // 対話ストリームがAIの返信を待っている間かどうか。DialoguePanelが立てる。
  // 発見に関する会話（さらに話す）と自由な会話が同じ1本のストリームに
  // 同時に流れ込むと、返信が来る順番と表示順がずれて誰の発言への返信か
  // 分からなくなる。返信待ち中は発見一覧側の「さらに話す」を押せなくして、
  // 2つの会話が交錯しないようにする。
  const [isChatBusy, setIsChatBusy] = useState(false);

  // ── 育成インジケータ（設計書6.4）──
  const [growth, setGrowth] = useState({ level: 0 });

  // 発見への「はい」「一部ちがう」や、対話の要約確認で知識グラフに意味づけが
  // 書き戻されたとき、右ペイン（本詳細）の意味づけ一覧に取り直しを促すための
  // バージョン番号。書き戻す経路が複数あるので、関数として外に出す。
  const [conceptsVersion, setConceptsVersion] = useState(0);
  const bumpConceptsVersion = useCallback(() => setConceptsVersion(v => v + 1), []);

  // ── 本棚のサイズ感（設定パネルの「本棚サイズの調整」）──
  // 画面幅に対する本棚ペインの割合。段が増えても縮まないよう固定幅にしたが、
  // 画面いっぱいだと圧迫感が出るので、ユーザーが自分で調整できるようにする。
  const [shelfWidthPct, setShelfWidthPct] = useState(40); // 30〜50の範囲

  // ── 左ペイン「棚を見て気づいたこと」の開閉 ──
  // 本詳細（右）と違い特定の本に紐づかない常設の相棒機能だが、本棚の幅を
  // 圧迫するため初期状態はしまっておく。ユーザーがいつでも開ける。
  const [isDialogueOpen, setIsDialogueOpen] = useState(false);

  const refreshDiscoveries = useCallback(async () => {
    setIsLoadingDiscoveries(true);
    try {
      const res = await fetch(`${API}/knowledge_graph/discoveries`);
      if (!res.ok) return;
      const json = await res.json();
      setDiscoveries(json.discoveries || []);
    } catch (err) {
      console.error("発見の取得に失敗しました", err);
    } finally {
      setIsLoadingDiscoveries(false);
    }
  }, []);

  const refreshGrowth = useCallback(async () => {
    try {
      const res = await fetch(`${API}/knowledge_graph/growth`);
      if (!res.ok) return;
      setGrowth(await res.json());
    } catch (err) {
      console.error("育成度の取得に失敗しました", err);
    }
  }, []);

  // 発見の初回取得が終わるまでは自動分析を走らせない（既にある未回答の発見を
  // 見る前に二重で分析してしまうのを防ぐため）。
  const [hasLoadedDiscoveriesOnce, setHasLoadedDiscoveriesOnce] = useState(false);

  useEffect(() => {
    refreshDiscoveries().finally(() => setHasLoadedDiscoveriesOnce(true));
    refreshGrowth();
  }, [refreshDiscoveries, refreshGrowth]);

  // ── 棚を読み直して新しい発見を生む（設計書5章の発見エンジンを起動する）──
  // ボタン操作はなく、未回答の発見が尽きるたびに自動で棚を読み直す
  // （下のuseEffect参照）。ユーザー操作を待たず勝手に提案してくる、という
  // 挙動そのものが「発見と対話」の売りなので、手動トリガーは持たせない。
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState(null);

  const runAnalysis = useCallback(async ({ silent = false } = {}) => {
    setIsAnalyzing(true);
    if (!silent) setAnalysisError(null);
    try {
      const res = await fetch(`${API}/knowledge_graph/analyze`, { method: "POST" });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail || "棚を読み取れませんでした");
      await refreshDiscoveries();
      await refreshGrowth();
    } catch (err) {
      // 自動実行時（棚が空、LLM一時エラーなど）はユーザーに逐一見せず、次のクールダウン明けに
      // また静かに試す。
      if (!silent) setAnalysisError(err.message);
      console.error("棚の自動分析に失敗しました", err);
    } finally {
      setIsAnalyzing(false);
    }
  }, [refreshDiscoveries, refreshGrowth]);

  /**
   * 発見への一次応答（設計書6.2：Yes / No / 一部訂正）。
   * status: "confirmed" | "rejected" | "modified"
   */
  const answerDiscovery = useCallback(async (discoveryId, status, extra = {}) => {
    // 応答は即座に画面へ反映する（往復を待たせると本棚の手触りが鈍る）
    setDiscoveries(list =>
      list.map(d => (d.discovery_id === discoveryId ? { ...d, status, ...extra } : d))
    );
    try {
      const res = await fetch(`${API}/knowledge_graph/discovery/${discoveryId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          surprise_score: extra.surprise_score ?? null,
          agreement_score: extra.agreement_score ?? null,
          comment: extra.comment ?? null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      refreshGrowth();
      // 「はい」「一部ちがう」は知識グラフに意味づけとして書き戻されるため、
      // 右ペイン（本詳細）が同じ本を開いていれば意味づけ一覧を取り直させる。
      if (status === "confirmed" || status === "modified") {
        bumpConceptsVersion();
      }
    } catch (err) {
      console.error("フィードバックの記録に失敗しました", err);
      // 失敗したら元に戻す。研究データなので、記録できていないものを
      // 記録済みに見せてはいけない。
      setDiscoveries(list =>
        list.map(d => (d.discovery_id === discoveryId ? { ...d, status: "pending" } : d))
      );
    }
  }, [refreshGrowth, bumpConceptsVersion]);

  // 優先度順（＝関連する本の数が多いほど大きなパターンとみなして上に出す）。
  // 同数のときは新しい発見を先に見せる（discoveries は createdAt DESC で来る）。
  const pendingDiscoveries = useMemo(
    () => discoveries
      .filter(d => d.status === "pending")
      .slice()
      .sort((a, b) => (b.related_book_ids?.length || 0) - (a.related_book_ids?.length || 0)),
    [discoveries]
  );

  // 未回答の発見が0件になるたび、自動で棚を読み直して新しい発見を提案する。
  // 分析に失敗しても（棚が空、LLM一時エラーなど）pendingDiscoveries.length は
  // 0のまま変わらないため、isAnalyzing の変化だけでeffectが再実行されてしまい
  // 無限に叩き続けかねない。クールダウンで間隔をあける。
  const AUTO_ANALYSIS_COOLDOWN_MS = 30_000;
  const lastAutoAnalysisAtRef = useRef(0);

  useEffect(() => {
    if (!hasLoadedDiscoveriesOnce) return;
    if (isLoadingDiscoveries || isAnalyzing) return;
    if (pendingDiscoveries.length > 0) return;
    const now = Date.now();
    if (now - lastAutoAnalysisAtRef.current < AUTO_ANALYSIS_COOLDOWN_MS) return;
    lastAutoAnalysisAtRef.current = now;
    runAnalysis({ silent: true });
  }, [hasLoadedDiscoveriesOnce, pendingDiscoveries.length, isLoadingDiscoveries, isAnalyzing, runAnalysis]);

  const value = useMemo(() => ({
    selectedIsbns, setSelectedIsbns,
    focusIsbn, setFocusIsbn,
    focusDetail, isFocusLoading,
    discoveries, pendingDiscoveries,
    isLoadingDiscoveries, refreshDiscoveries,
    answerDiscovery,
    highlightIsbns, setHighlightIsbns,
    conceptHighlight, setConceptHighlight,
    growth, refreshGrowth,
    conceptsVersion, bumpConceptsVersion,
    chatSeed, setChatSeed,
    isChatBusy, setIsChatBusy,
    runAnalysis, isAnalyzing, analysisError,
    shelfWidthPct, setShelfWidthPct,
    isDialogueOpen, setIsDialogueOpen,
  }), [
    selectedIsbns, focusIsbn, focusDetail, isFocusLoading,
    discoveries, pendingDiscoveries,
    isLoadingDiscoveries, refreshDiscoveries,
    answerDiscovery, highlightIsbns, conceptHighlight,
    growth, refreshGrowth, conceptsVersion, bumpConceptsVersion,
    chatSeed, isChatBusy, runAnalysis, isAnalyzing, analysisError,
    shelfWidthPct, isDialogueOpen,
  ]);

  return (
    <ShelfWorkspaceContext.Provider value={value}>
      {children}
    </ShelfWorkspaceContext.Provider>
  );
}

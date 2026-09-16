// 本棚（中央）と本詳細（右）・グループ管理（左）で共有する状態。
//
// ペイン間で同じものを見ている必要がある：
//   - どの本が選ばれているか      → 意味づけ入力の対象／グループ作成の対象
//   - どの本を強調するか          → 関連本の強調で本棚側を光らせる
//   - 通常モードかグルーピングモードか → 各ペインの操作可否を切り替える
//
// これらをどれか一つのコンポーネントに持たせると、他から触れなくなる。
import { createContext, useContext, useCallback, useEffect, useMemo, useState } from "react";
import { CONCEPT_COLORS } from "../utils/graphConfig";

const API = "http://localhost:8000";

// グループのハイライト色は毎回ランダムに選ぶ（同じ色ばかりだと見飽きるため）。
// 直前の色は避けて、切り替えるたびにちゃんと変わったと分かるようにする。
function pickGroupHighlightColor(excludeColor) {
  const options = excludeColor ? CONCEPT_COLORS.filter(c => c !== excludeColor) : CONCEPT_COLORS;
  return options[Math.floor(Math.random() * options.length)];
}

export const ShelfWorkspaceContext = createContext(null);

export function useShelfWorkspace() {
  const ctx = useContext(ShelfWorkspaceContext);
  if (!ctx) throw new Error("ShelfWorkspaceProvider の外で useShelfWorkspace が呼ばれました");
  return ctx;
}

export function ShelfWorkspaceProvider({ children }) {
  // ── モード（通常／グルーピング）──
  // 通常モード: 棚の座標変更・詳細パネルの閲覧のみ。
  // グルーピングモード: 複数選択・グループ作成・左パネルでのグループ管理。
  const [mode, setModeRaw] = useState("normal"); // "normal" | "grouping"

  const setMode = useCallback((next) => {
    setModeRaw(prev => {
      if (prev === next) return prev;
      fetch(`${API}/knowledge_graph/mode-switch-event`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: next }),
      }).catch(err => console.error("モード切替のログ記録に失敗しました", err));
      return next;
    });
  }, []);

  // ── 選択（設計書4章：1冊タップ / 範囲選択）──
  // 通常モードでは使わない（グルーピングモードの複数選択専用）。
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

  // ── 強調（対話や提案が根拠にした本）──
  const [highlightIsbns, setHighlightIsbns] = useState([]);

  // 意味づけ／グループ単位の強調。キー "hover" は右ペインでのホバー強調
  // （1件だけ、他と共存しても問題ない）、キー "group" はグルーピングモードの
  // 左パネルで選んでいるグループの永続ハイライト（同時に1つだけ。別のグループを
  // 選ぶと切り替わる。違うグループを同時に選べると、どの本がどのグループに
  // 属すのか棚の上で読み取れなくなるため）。
  // { [key]: { color, isbns } }
  const [conceptHighlights, setConceptHighlights] = useState({});

  // 旧: 単一のホバー強調用インターフェース。BookFocusPanel はこのままの形で使う。
  const setConceptHighlight = useCallback((entry) => {
    setConceptHighlights(prev => {
      if (!entry) {
        if (!("hover" in prev)) return prev;
        const next = { ...prev };
        delete next.hover;
        return next;
      }
      return { ...prev, hover: entry };
    });
  }, []);

  // モードが切り替わったら、前のモードの選択・フォーカス・ハイライト状態を
  // 持ち越さない（通常モードに戻ったのに選択やグループのハイライトが残っている、
  // グルーピングモードに入ったのに詳細パネルのフォーカスが残っている、といった
  // 食い違いを防ぐ）。グルーピングモードで左パネルからオンにした永続ハイライトは、
  // 通常モードに戻った時点で全て消す。
  // "boundary"（フェーズ2(b): 区切り確認モード）も同様に、詳細パネルが
  // 開いたまま棚のタップが区切り確認用に奪われる、といった食い違いを避ける。
  useEffect(() => {
    setSelectedIsbns([]);
    if (mode === "grouping" || mode === "boundary") {
      setFocusIsbn(null);
    } else {
      setConceptHighlights({});
    }
  }, [mode]);

  const _logGroupHighlightEvent = (groupId, action) => {
    fetch(`${API}/knowledge_graph/groups/${groupId}/highlight-event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }).catch(err => console.error("ハイライトログの記録に失敗しました", err));
  };

  // グルーピングモードの左パネル用：グループのハイライトをオン/オフする。
  // 同時に光らせるのは1グループだけ（別のグループを選ぶとそちらに切り替わる）。
  // hover とは別キー（"group"）で管理する。
  const toggleGroupHighlight = useCallback((groupId, isbns) => {
    setConceptHighlights(prev => {
      const current = prev.group;
      const next = { ...prev };
      if (current) {
        delete next.group;
        _logGroupHighlightEvent(current.groupId, "off");
        if (current.groupId === groupId) {
          // 同じグループをもう一度選んだ＝オフにする
          return next;
        }
      }
      next.group = { groupId, color: pickGroupHighlightColor(current?.color), isbns };
      _logGroupHighlightEvent(groupId, "on");
      return next;
    });
  }, []);

  // グループそのものが無くなった（削除・統合で消えた）ときに、ハイライトが
  // 付けっぱなしのまま残らないよう明示的に消す。今ハイライト中のグループが
  // これでなければ何もしない（常に「消す」だけの操作で、トグルはしない）。
  const clearGroupHighlight = useCallback((groupId) => {
    setConceptHighlights(prev => {
      if (prev.group?.groupId !== groupId) return prev;
      const next = { ...prev };
      delete next.group;
      return next;
    });
  }, []);

  // 棚のタップから、今ハイライト中のグループへの追加／除外をした直後に呼ぶ。
  // サーバー側の反映を待たずに、光っている本の集合をその場で書き換える
  // （そうしないと、次にグループ一覧が取り直されるまでリングが古いままになる）。
  const setGroupHighlightMembers = useCallback((groupId, isbns) => {
    setConceptHighlights(prev => {
      if (prev.group?.groupId !== groupId) return prev;
      return { ...prev, group: { ...prev.group, isbns } };
    });
  }, []);

  // ── 育成インジケータ（設計書6.4）──
  const [growth, setGrowth] = useState({ level: 0 });

  // 発見への回答や意味づけの編集で知識グラフに書き戻されたとき、右ペイン
  // （本詳細）の意味づけ一覧に取り直しを促すためのバージョン番号。
  // 書き戻す経路が複数あるので、関数として外に出す。
  const [conceptsVersion, setConceptsVersion] = useState(0);
  const bumpConceptsVersion = useCallback(() => setConceptsVersion(v => v + 1), []);

  // グループ（=Concept）一覧の再取得を促すバージョン番号。左パネルはこれが
  // 変わるたびにグループ一覧を取り直す。
  const [groupsVersion, setGroupsVersion] = useState(0);
  const bumpGroupsVersion = useCallback(() => setGroupsVersion(v => v + 1), []);

  // ── Undoトースト（グループ削除・統合など元に戻しにくい操作の直後に表示）──
  // { message, actionLabel, onAction } | null
  const [toast, setToast] = useState(null);
  const showToast = useCallback((next) => setToast(next), []);
  const dismissToast = useCallback(() => setToast(null), []);

  // ── 本棚のサイズ感（設定パネルの「本棚サイズの調整」）──
  // 画面幅に対する本棚ペインの割合。段が増えても縮まないよう固定幅にしたが、
  // 画面いっぱいだと圧迫感が出るので、ユーザーが自分で調整できるようにする。
  const [shelfWidthPct, setShelfWidthPct] = useState(40); // 30〜50の範囲

  const refreshGrowth = useCallback(async () => {
    try {
      const res = await fetch(`${API}/knowledge_graph/growth`);
      if (!res.ok) return;
      setGrowth(await res.json());
    } catch (err) {
      console.error("育成度の取得に失敗しました", err);
    }
  }, []);

  useEffect(() => {
    refreshGrowth();
  }, [refreshGrowth]);

  const value = useMemo(() => ({
    mode, setMode,
    selectedIsbns, setSelectedIsbns,
    focusIsbn, setFocusIsbn,
    focusDetail, isFocusLoading,
    highlightIsbns, setHighlightIsbns,
    conceptHighlights, setConceptHighlight, toggleGroupHighlight, clearGroupHighlight, setGroupHighlightMembers,
    growth, refreshGrowth,
    conceptsVersion, bumpConceptsVersion,
    groupsVersion, bumpGroupsVersion,
    toast, showToast, dismissToast,
    shelfWidthPct, setShelfWidthPct,
  }), [
    mode, setMode,
    selectedIsbns, focusIsbn, focusDetail, isFocusLoading,
    highlightIsbns, conceptHighlights, setConceptHighlight, toggleGroupHighlight, clearGroupHighlight, setGroupHighlightMembers,
    growth, refreshGrowth, conceptsVersion, bumpConceptsVersion,
    groupsVersion, bumpGroupsVersion,
    toast, showToast, dismissToast,
    shelfWidthPct,
  ]);

  return (
    <ShelfWorkspaceContext.Provider value={value}>
      {children}
    </ShelfWorkspaceContext.Provider>
  );
}

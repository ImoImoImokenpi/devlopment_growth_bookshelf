// 育つ本棚（Home）の本棚・右パネル（本の詳細／対話）で共有する状態。
//
//   - どの本を選んでいるか（focusIsbn）     → 右パネルの本の詳細
//   - どの本を強調するか                     → 対話で話題にした本・意味づけの候補を本棚で光らせる
//   - 冊数などの育ち具合（growth）           → 見出しの冊数
//   - 本棚の大きさ（shelfWidthPct）          → 棚の設定
//   - 並べ替えの即時保存・進行中の対話のID  → 対話の開始時と、対話中の移動の記録
//
// これらをどれか一つのコンポーネントに持たせると、他から触れなくなる。
import { createContext, useContext, useCallback, useEffect, useMemo, useRef, useState } from "react";

const API = "http://localhost:8000";

export const ShelfWorkspaceContext = createContext(null);

export function useShelfWorkspace() {
  const ctx = useContext(ShelfWorkspaceContext);
  if (!ctx) throw new Error("ShelfWorkspaceProvider の外で useShelfWorkspace が呼ばれました");
  return ctx;
}

export function ShelfWorkspaceProvider({ children }) {
  // 1冊タップで右パネルに詳細を出す本
  const [focusIsbn, setFocusIsbn] = useState(null);

  // 対話で話題にした本（オレンジの破線で光らせる）
  const [highlightIsbns, setHighlightIsbns] = useState([]);

  // 意味づけ単位の強調（対話の「本棚に反映しますか？」で項目にマウスを乗せたとき）。
  // { [key]: { color, isbns } }。今はキー "hover" だけを使う。
  const [conceptHighlights, setConceptHighlights] = useState({});
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

  // 冊数など（/knowledge_graph/growth）
  const [growth, setGrowth] = useState({ level: 0 });
  const refreshGrowth = useCallback(async () => {
    try {
      const res = await fetch(`${API}/knowledge_graph/growth`);
      if (!res.ok) return;
      setGrowth(await res.json());
    } catch (err) {
      console.error("育成度の取得に失敗しました", err);
    }
  }, []);
  useEffect(() => { refreshGrowth(); }, [refreshGrowth]);

  // 画面幅に対する本棚の割合（棚の設定の「本棚サイズの調整」、30〜50）
  const [shelfWidthPct, setShelfWidthPct] = useState(40);

  // ── 並べ替えの即時保存 ──
  // 本棚は並べ替えを10秒待ってからまとめて保存する。対話を始めるときは
  // その待ちを飛ばして今すぐ保存し、知識グラフに最新の並びを反映させてから
  // LLMに読ませる必要がある。SpineShelfView が保存関数をここに登録する。
  const flushLayoutSyncRef = useRef(null);
  const flushLayoutSync = useCallback(async () => {
    if (flushLayoutSyncRef.current) await flushLayoutSyncRef.current();
  }, []);

  // 対話パネルで進行中の対話のID（なければ null）。並べ替えの保存に添えて送り、
  // 対話中の移動だけを移動履歴として残す（対話の外の移動は履歴に残さない）。
  // 保存処理は描画と無関係に読むので、state ではなく ref で持つ。
  const dialogueSessionIdRef = useRef(null);

  const value = useMemo(() => ({
    focusIsbn, setFocusIsbn,
    highlightIsbns, setHighlightIsbns,
    conceptHighlights, setConceptHighlight,
    growth, refreshGrowth,
    shelfWidthPct, setShelfWidthPct,
    flushLayoutSyncRef, flushLayoutSync, dialogueSessionIdRef,
  }), [
    focusIsbn, highlightIsbns, conceptHighlights, setConceptHighlight,
    growth, refreshGrowth, shelfWidthPct, flushLayoutSync,
  ]);

  return (
    <ShelfWorkspaceContext.Provider value={value}>
      {children}
    </ShelfWorkspaceContext.Provider>
  );
}

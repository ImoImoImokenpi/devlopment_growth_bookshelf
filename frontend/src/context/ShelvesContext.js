// 持ち主の本棚の一覧（本棚は複数つくれる）と、今開いている本棚。
//
// 本棚ごとに配置・知識グラフ・対話・おすすめが分かれている（バックエンドの routers/shelves.py）。
// 今開いている本棚は utils/participant.js が覚えていて、すべての通信に X-Shelf-Id を付ける。
// 切り替えると画面を読み込み直す（手元・本棚・対話の状態をまとめて取り直すため）。
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getActiveShelfId, getParticipantId, switchShelf } from "../utils/participant";

const API = "http://localhost:8000";

export const ShelvesContext = createContext(null);

export function useShelves() {
  const ctx = useContext(ShelvesContext);
  if (!ctx) throw new Error("ShelvesProvider の外で useShelves が呼ばれました");
  return ctx;
}

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "うまくいきませんでした");
  return data;
}

export function ShelvesProvider({ children }) {
  const [shelves, setShelves] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const activeScopeId = getActiveShelfId();

  const refreshShelves = useCallback(async () => {
    try {
      const data = await request("/shelves/");
      setShelves(data.shelves || []);
      // 開いていた本棚が消えていたら、最初の本棚に戻す
      if (!(data.shelves || []).some(s => s.scope_id === activeScopeId)) {
        switchShelf(getParticipantId());
      }
    } catch (err) {
      console.error("本棚の一覧を取得できませんでした", err);
    } finally {
      setLoaded(true);
    }
  }, [activeScopeId]);
  useEffect(() => { refreshShelves(); }, [refreshShelves]);

  const createShelf = useCallback(async (name) => {
    const shelf = await request("/shelves/", { method: "POST", body: JSON.stringify({ name }) });
    await refreshShelves();
    return shelf;
  }, [refreshShelves]);

  const renameShelf = useCallback(async (id, name) => {
    await request(`/shelves/${id}`, { method: "PATCH", body: JSON.stringify({ name }) });
    await refreshShelves();
  }, [refreshShelves]);

  const deleteShelf = useCallback(async (id) => {
    await request(`/shelves/${id}`, { method: "DELETE" });
    await refreshShelves();
  }, [refreshShelves]);

  // 今開いている本棚から、別の本棚へ1冊移す
  const moveBookToShelf = useCallback(async (isbn, toShelfId) => {
    await request("/shelves/move-book", { method: "POST", body: JSON.stringify({ isbn, to_shelf_id: toShelfId }) });
    await refreshShelves();
  }, [refreshShelves]);

  const activeShelf = useMemo(
    () => shelves.find(s => s.scope_id === activeScopeId) || null,
    [shelves, activeScopeId]
  );

  const value = useMemo(() => ({
    shelves, loaded, activeShelf, activeScopeId,
    refreshShelves, createShelf, renameShelf, deleteShelf, moveBookToShelf,
    openShelf: switchShelf,
  }), [shelves, loaded, activeShelf, activeScopeId, refreshShelves, createShelf, renameShelf, deleteShelf, moveBookToShelf]);

  return <ShelvesContext.Provider value={value}>{children}</ShelvesContext.Provider>;
}

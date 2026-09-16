// 新UI vs 旧UI比較実験のID管理。
//
// 既存の participant.js（「投影のズレ」研究）とは別の研究・別の参加者プールなので、
// ストレージキーもヘッダ名も完全に分ける。役割(参加者/観察者)ごとに別ヘッダを使う。
export const API_ORIGIN = "http://localhost:8000";

const STORAGE_ID_KEY = "growth_bookshelf.uiab_id";
const STORAGE_ROLE_KEY = "growth_bookshelf.uiab_role"; // "participant" | "observer"

const PARTICIPANT_HEADER = "X-Uiab-Participant-Id";
const OBSERVER_HEADER = "X-Uiab-Observer-Id";

export function getUiabId() {
  try { return localStorage.getItem(STORAGE_ID_KEY) || ""; } catch { return ""; }
}

export function getUiabRole() {
  try { return localStorage.getItem(STORAGE_ROLE_KEY) || ""; } catch { return ""; }
}

export function setUiabIdentity(id, role) {
  try {
    localStorage.setItem(STORAGE_ID_KEY, id);
    localStorage.setItem(STORAGE_ROLE_KEY, role);
  } catch { /* noop */ }
}

export function clearUiabIdentity() {
  try {
    localStorage.removeItem(STORAGE_ID_KEY);
    localStorage.removeItem(STORAGE_ROLE_KEY);
  } catch { /* noop */ }
}

// fetchのラッパー。/uiab/ 宛のリクエストにだけ、役割に応じたヘッダを自動で付ける。
export async function uiabFetch(path, init = {}) {
  const role = getUiabRole();
  const id = getUiabId();
  const headers = new Headers(init.headers || undefined);
  if (id) {
    headers.set(role === "observer" ? OBSERVER_HEADER : PARTICIPANT_HEADER, id);
  }
  const res = await fetch(`${API_ORIGIN}${path}`, { ...init, headers });
  return res;
}

export async function uiabGet(path) {
  const res = await uiabFetch(path);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

export async function uiabPost(path, body) {
  const res = await uiabFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `POST ${path} failed: ${res.status}`);
  }
  return res.json();
}

export async function uiabDelete(path) {
  const res = await uiabFetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} failed: ${res.status}`);
  return res.json();
}

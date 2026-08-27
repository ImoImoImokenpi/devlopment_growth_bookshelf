// 被験者(participant)の識別。
//
// 研究では20人ほどの被験者がそれぞれ自分の本棚・知識グラフを持つ。
// バックエンドは X-Participant-Id ヘッダで持ち主を判別するため、
// バックエンド宛のリクエストすべてにこのヘッダを付ける必要がある。
//
// 通信の呼び出しがあちこちのコンポーネントに散らばっているので、
// 呼び出し側を1つずつ書き換えるのではなく1箇所で包む。
// こうすれば新しく追加したときにヘッダを付け忘れることがない。
//
// このアプリは fetch と axios の両方を使っている。axios は
// XMLHttpRequest を使うので fetch のラッパーを通らない。両方に入れること。

import axios from "axios";

export const API_ORIGIN = "http://localhost:8000";

const PARTICIPANT_HEADER = "X-Participant-Id";
const STORAGE_KEY = "growth_bookshelf.participant_id";

export const DEFAULT_PARTICIPANT_ID = "P00";

// 「他の参加者の本棚を観察する」画面ではP00をプロトタイプ参加者として扱う。
export const PROTOTYPE_PARTICIPANT_ID = "P00";

// 被験者IDの候補。P00 は開発用・既存データ用（かつプロトタイプ参加者）。
export const PARTICIPANT_IDS = [
  DEFAULT_PARTICIPANT_ID,
  ...Array.from({ length: 20 }, (_, i) => `P${String(i + 1).padStart(2, "0")}`),
];

export function getParticipantId() {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_PARTICIPANT_ID;
  } catch {
    // プライベートモードなどで localStorage が使えない場合
    return DEFAULT_PARTICIPANT_ID;
  }
}

export function setParticipantId(id) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* 保存できなくても、このセッション中の切り替えは行う */
  }
  // 本棚・手元・知識グラフなど複数のコンテキストが別々に状態を持っているため、
  // 部分的に前の被験者のデータが残らないよう、読み込み直す。
  window.location.reload();
}

function isBackendUrl(url) {
  return typeof url === "string" && url.startsWith(API_ORIGIN);
}

export function installParticipantHeader() {
  if (window.__participantHeaderInstalled) return;
  window.__participantHeaderInstalled = true;

  // --- axios ---
  axios.interceptors.request.use((config) => {
    const url = config.url || "";
    const full = url.startsWith("http") ? url : (config.baseURL || "") + url;
    if (isBackendUrl(full)) {
      // axios v1 の headers は AxiosHeaders。set があればそちらを使う。
      // 呼び出し側が既に明示的にヘッダを付けている場合（他の参加者の棚を
      // 読み取る withParticipant() 経由の呼び出しなど）はそちらを優先し、
      // 自分のIDで上書きしない。
      if (config.headers && typeof config.headers.set === "function") {
        if (!config.headers.has(PARTICIPANT_HEADER)) {
          config.headers.set(PARTICIPANT_HEADER, getParticipantId());
        }
      } else if (!config.headers || !(PARTICIPANT_HEADER in config.headers)) {
        config.headers = {
          ...(config.headers || {}),
          [PARTICIPANT_HEADER]: getParticipantId(),
        };
      }
    }
    return config;
  });

  // --- fetch ---
  const originalFetch = window.fetch.bind(window);

  window.fetch = (input, init) => {
    const url =
      typeof input === "string"
        ? input
        : input && typeof input.url === "string"
        ? input.url
        : "";

    // 外部API（書影の取得など）にまでヘッダを付けるとCORSに引っかかるので、
    // 自分のバックエンド宛だけに限定する。
    if (!isBackendUrl(url)) {
      return originalFetch(input, init);
    }

    const headers = new Headers(
      (init && init.headers) ||
        (typeof Request !== "undefined" && input instanceof Request
          ? input.headers
          : undefined)
    );
    // 呼び出し側が既に明示的にヘッダを付けている場合は上書きしない
    // （他の参加者の棚を読み取る withParticipant() 経由の呼び出しなど）。
    if (!headers.has(PARTICIPANT_HEADER)) {
      headers.set(PARTICIPANT_HEADER, getParticipantId());
    }

    return originalFetch(input, { ...(init || {}), headers });
  };
}

// 「他の参加者の本棚を観察する」画面専用。自分のIDを変えずに、
// 指定した参加者のデータだけを読み取るための fetch オプションを作る。
// 例: fetch(`${API_ORIGIN}/bookshelf/`, withParticipant(otherId))
export function withParticipant(participantId, init = {}) {
  const headers = new Headers(init.headers || undefined);
  headers.set(PARTICIPANT_HEADER, participantId);
  return { ...init, headers };
}

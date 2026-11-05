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

const API_ORIGIN = "http://localhost:8000";

const PARTICIPANT_HEADER = "X-Participant-Id";
const STORAGE_KEY = "growth_bookshelf.participant_id";

const DEFAULT_PARTICIPANT_ID = "P00";

// 今開いている本棚（持ち主は本棚を複数持てる）。バックエンドは X-Shelf-Id で
// 本棚ごとに配置・知識グラフ・対話を分ける。持ち主ごとに覚えておく。
const SHELF_HEADER = "X-Shelf-Id";
const shelfStorageKey = (pid) => `growth_bookshelf.shelf_id.${pid}`;

export function getActiveShelfId() {
  const pid = getParticipantId();
  try {
    return localStorage.getItem(shelfStorageKey(pid)) || pid;
  } catch {
    return pid;
  }
}

// 本棚を切り替える。手元・本棚・対話などの状態を全部取り直すため、画面を読み込み直す。
export function switchShelf(scopeId) {
  try {
    localStorage.setItem(shelfStorageKey(getParticipantId()), scopeId);
  } catch {
    // 覚えておけなくても、この読み込みの間は切り替えられないだけ
  }
  window.location.reload();
}

export function getParticipantId() {
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_PARTICIPANT_ID;
  } catch {
    // プライベートモードなどで localStorage が使えない場合
    return DEFAULT_PARTICIPANT_ID;
  }
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
      // 呼び出し側が既に明示的にヘッダを付けている場合はそちらを優先する。
      if (config.headers && typeof config.headers.set === "function") {
        if (!config.headers.has(PARTICIPANT_HEADER)) {
          config.headers.set(PARTICIPANT_HEADER, getParticipantId());
        }
        if (!config.headers.has(SHELF_HEADER)) {
          config.headers.set(SHELF_HEADER, getActiveShelfId());
        }
      } else if (!config.headers || !(PARTICIPANT_HEADER in config.headers)) {
        config.headers = {
          [SHELF_HEADER]: getActiveShelfId(),
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
    // 呼び出し側が既に明示的にヘッダを付けている場合は上書きしない。
    if (!headers.has(PARTICIPANT_HEADER)) {
      headers.set(PARTICIPANT_HEADER, getParticipantId());
    }
    if (!headers.has(SHELF_HEADER)) {
      headers.set(SHELF_HEADER, getActiveShelfId());
    }

    return originalFetch(input, { ...(init || {}), headers });
  };
}

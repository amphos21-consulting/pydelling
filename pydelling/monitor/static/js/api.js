// HTTP + SSE client. The session token arrives once in the URL hash (#token=…) and is
// kept per viewer in localStorage so new tabs of the same server session work.

const TOKEN_KEY = 'pydelling-monitor-token';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function storage(action, value) {
  try {
    if (action === 'get') return window.localStorage.getItem(TOKEN_KEY);
    if (action === 'set') window.localStorage.setItem(TOKEN_KEY, value);
  } catch {
    return null;
  }
  return null;
}

let memoryToken = null;

export function captureToken() {
  const match = window.location.hash.match(/token=([A-Za-z0-9_-]+)/);
  if (match) {
    memoryToken = match[1];
    storage('set', memoryToken);
    window.history.replaceState(null, '', `${window.location.pathname}#/runs`);
  }
  return token();
}

export function token() {
  return memoryToken || storage('get') || '';
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { Authorization: `Bearer ${token()}` };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new ApiError(response.status, (data && data.error) || `HTTP ${response.status}`);
  }
  return data;
}

// Server-Sent Events with our own reconnect (so the cursor is always current).
export function openStream(getCursor, { onChanges, onState }) {
  let source = null;
  let closed = false;
  let retry = 1000;

  const connect = () => {
    if (closed) return;
    const { rev, event_id: eventId } = getCursor();
    const url = `/api/stream?token=${encodeURIComponent(token())}&rev=${rev}&event_id=${eventId}`;
    source = new EventSource(url);
    source.addEventListener('ready', () => {
      retry = 1000;
      onState('live');
    });
    source.addEventListener('changes', (event) => onChanges(JSON.parse(event.data)));
    source.onerror = () => {
      source.close();
      onState('offline');
      setTimeout(connect, retry);
      retry = Math.min(15000, retry * 2);
    };
  };
  connect();
  return () => {
    closed = true;
    if (source) source.close();
  };
}

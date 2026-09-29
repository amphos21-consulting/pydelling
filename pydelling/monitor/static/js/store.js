// Reactive client state fed by one overview fetch and the SSE change stream.
import { reactive } from '../vendor/vue.esm-browser.prod.js';
import { api, ApiError, captureToken, openStream } from './api.js';

export const state = reactive({
  phase: 'loading', // loading | ready | auth | error
  error: null,
  connection: 'connecting',
  project: null,
  hosts: {},
  runs: {},
  kpis: {},
  cursor: { rev: 0, event_id: 0 },
  details: {},
  studies: {},
  toast: null,
  now: Date.now() / 1000,
});

const EVENTS_KEPT = 400;
const timers = new Map();
const deletedRuns = new Set();

export function removeRuns(ids) {
  for (const id of ids) {
    deletedRuns.add(id);
    if (window.location.hash === `#/runs/${id}`) window.location.hash = '#/runs';
    delete state.runs[id];
    delete state.details[id];
    for (const key of Object.keys(state.studies)) {
      if (key.startsWith(`${id}/`)) delete state.studies[key];
    }
  }
  refreshKpis();
}


function debounce(key, delay, fn) {
  if (timers.has(key)) return;
  timers.set(key, setTimeout(() => {
    timers.delete(key);
    fn();
  }, delay));
}

export function toast(message, tone = 'neutral') {
  state.toast = { message, tone, id: Date.now() };
  const id = state.toast.id;
  setTimeout(() => {
    if (state.toast && state.toast.id === id) state.toast = null;
  }, 4200);
}

function mergeHost(row) {
  const current = state.hosts[row.id] || {};
  state.hosts[row.id] = { ...current, ...row };
}

function mergeRun(row) {
  if (deletedRuns.has(row.id)) return;
  state.runs[row.id] = { ...(state.runs[row.id] || {}), ...row };
  const detail = state.details[row.id];
  if (detail) detail.run = { ...detail.run, ...row };
}

export async function loadOverview() {
  const data = await api('/overview?limit=500');
  state.project = data.project;
  data.hosts.forEach(mergeHost);
  data.runs.forEach(mergeRun);
  state.kpis = data.kpis;
  return data;
}

const COLLECT_PROGRESS_KEYS = ['files', 'total_files', 'bytes', 'total_bytes', 'elapsed'];

// Download counters arrive up to twice a second: patch the collect stage in place instead of
// reloading the whole run detail (the debounced reload still reconciles it afterwards).
function patchCollect(detail, event) {
  const stage = detail.stages.find((s) => s.id === 'collect');
  if (!stage) return;
  const kind = event.event_type;
  if (kind === 'collect.queued') {
    stage.status = 'queued';
  } else if (kind === 'collect.started') {
    Object.assign(stage, { status: 'running', started: event.ts, progress: null, detail: null, seconds: null });
  } else if (kind === 'collect.progress') {
    const payload = event.payload_json || {};
    stage.status = 'running';
    stage.progress = Object.fromEntries(COLLECT_PROGRESS_KEYS.map((k) => [k, payload[k] ?? null]));
  } else if (kind === 'collect.done') {
    Object.assign(stage, { status: 'done', finished: event.ts, seconds: stage.started != null ? event.ts - stage.started : null });
  } else if (kind === 'collect.failed') {
    Object.assign(stage, { status: 'failed', finished: event.ts, detail: event.message });
  }
}

function applyChanges(data) {
  if (data.deleted_runs && data.deleted_runs.length) removeRuns(data.deleted_runs);
  data.hosts.forEach(mergeHost);
  data.runs.forEach(mergeRun);
  const touched = new Set();
  for (const study of data.studies) {
    const detail = state.details[study.run_id];
    if (detail) {
      detail.studies[study.name] = { ...(detail.studies[study.name] || {}), ...study };
      const key = `${study.run_id}/${study.name}`;
      if (state.studies[key]) debounce(`study:${key}`, 900, () => loadStudy(study.run_id, study.name).catch(() => {}));
    }
  }
  for (const event of data.events) {
    const detail = state.details[event.run_id];
    if (detail && event.event_type.startsWith('collect.')) patchCollect(detail, event);
    if (event.event_type === 'collect.progress') continue; // live counters only: no timeline, no reload
    if (detail && !detail.eventIds.has(event.id)) {
      detail.eventIds.add(event.id);
      detail.events.push(event);
      if (detail.events.length > EVENTS_KEPT) detail.events.splice(0, detail.events.length - EVENTS_KEPT);
      touched.add(event.run_id);
    }
  }
  for (const run of data.runs) {
    if (state.details[run.id]) touched.add(run.id);
  }
  touched.forEach((id) => debounce(`detail:${id}`, 1500, () => loadRun(id).catch(() => {})));
  if (data.runs.length || data.studies.length) debounce('kpis', 2000, refreshKpis);
  state.cursor = { rev: data.rev, event_id: data.event_id };
}

async function refreshKpis() {
  try {
    const data = await api('/overview?limit=1');
    state.kpis = data.kpis;
  } catch {
    // transient; next change retries
  }
}

export async function loadRun(id) {
  const data = await api(`/runs/${id}`);
  if (deletedRuns.has(id)) return null;
  const studies = {};
  for (const study of data.studies) studies[study.name] = study;
  const existing = state.details[id];
  state.details[id] = {
    run: data.run,
    studies,
    events: data.events,
    eventIds: new Set(data.events.map((e) => e.id)),
    stages: data.stages,
    actions: data.actions,
    loadedAt: Date.now(),
    selected: existing ? existing.selected : null,
  };
  mergeRun(data.run);
  return state.details[id];
}

export async function loadStudy(runId, name) {
  const study = await api(`/runs/${runId}/studies/${encodeURIComponent(name)}`);
  if (!deletedRuns.has(runId)) state.studies[`${runId}/${name}`] = study;
  return study;
}

let stopStream = null;
let clock = null;

export async function bootstrap() {
  if (stopStream) {
    stopStream();
    stopStream = null;
  }
  if (!captureToken()) {
    state.phase = 'auth';
    return;
  }
  state.phase = 'loading';
  try {
    const data = await loadOverview();
    state.cursor = { rev: data.rev, event_id: data.event_id };
    state.phase = 'ready';
  } catch (error) {
    state.phase = error instanceof ApiError && error.status === 401 ? 'auth' : 'error';
    state.error = error.message;
    return;
  }
  stopStream = openStream(() => state.cursor, {
    onChanges: applyChanges,
    onState: async (value) => {
      state.connection = value;
      if (value === 'offline') {
        try {
          await api('/overview?limit=1');
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            state.phase = 'auth';
            if (stopStream) stopStream();
          }
        }
      }
    },
  });
  if (!clock) {
    clock = setInterval(() => {
      state.now = Date.now() / 1000;
    }, 1000);
  }
}

export async function action(path, body = {}, success) {
  try {
    const result = await api(path, { method: 'POST', body });
    if (success) toast(success, 'good');
    return result;
  } catch (error) {
    toast(error.message, 'critical');
    throw error;
  }
}

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

function applyChanges(data) {
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
  state.studies[`${runId}/${name}`] = study;
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

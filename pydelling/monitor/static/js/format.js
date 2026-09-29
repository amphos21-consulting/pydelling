// Formatting helpers and the status vocabulary (label + tone + icon, never color alone).

export const RUN_STATUS = {
  queued: { label: 'En cola', tone: 'neutral', icon: 'clock' },
  preflight: { label: 'Comprobando acceso', tone: 'active', icon: 'shield', anim: 'scan' },
  deploying: { label: 'Desplegando', tone: 'active', icon: 'upload', anim: 'upload' },
  starting: { label: 'Arrancando', tone: 'active', icon: 'rocket', anim: 'launch' },
  running: { label: 'En ejecución', tone: 'running', icon: 'loader', anim: 'spin' },
  cancelling: { label: 'Cancelando', tone: 'warning', icon: 'loader', anim: 'spin' },
  completed: { label: 'Completado', tone: 'good', icon: 'check' },
  failed: { label: 'Fallido', tone: 'critical', icon: 'x' },
  cancelled: { label: 'Cancelado', tone: 'serious', icon: 'stop' },
  interrupted: { label: 'Interrumpido', tone: 'serious', icon: 'pause' },
  lost: { label: 'Worker perdido', tone: 'critical', icon: 'alert' },
  missing: { label: 'Carpeta no disponible', tone: 'warning', icon: 'folder' },
  unknown: { label: 'Estado desconocido', tone: 'neutral', icon: 'help' },
  prepared: { label: 'Preparado', tone: 'neutral', icon: 'layers' },
};

export const STUDY_STATE = {
  pending: { label: 'Pendiente', tone: 'neutral', icon: 'clock' },
  running: { label: 'En ejecución', tone: 'running', icon: 'loader' },
  completed: { label: 'Completado', tone: 'good', icon: 'check' },
  failed: { label: 'Fallido', tone: 'critical', icon: 'x' },
  interrupted: { label: 'Interrumpido', tone: 'serious', icon: 'pause' },
};
export const STUDY_ORDER = ['completed', 'running', 'failed', 'interrupted', 'pending'];

export const HOST_STATE = {
  connected: { label: 'Conectado', tone: 'good', icon: 'check' },
  connecting: { label: 'Conectando…', tone: 'active', icon: 'loader' },
  auth_required: { label: 'Requiere autenticación', tone: 'warning', icon: 'key' },
  unreachable: { label: 'Inalcanzable', tone: 'critical', icon: 'wifi-off' },
  host_key: { label: 'Clave de host no válida', tone: 'critical', icon: 'shield' },
  missing_ssh: { label: 'OpenSSH no encontrado', tone: 'critical', icon: 'alert' },
  error: { label: 'Error', tone: 'critical', icon: 'alert' },
  offline: { label: 'Sin conexión', tone: 'neutral', icon: 'wifi-off' },
};

export const STAGE_STATE = {
  pending: { tone: 'neutral', icon: 'circle', label: 'Pendiente' },
  skipped: { tone: 'neutral', icon: 'minus', label: 'No aplica' },
  queued: { tone: 'active', icon: 'clock', label: 'En cola' },
  running: { tone: 'running', icon: 'loader', label: 'En curso' },
  done: { tone: 'good', icon: 'check', label: 'Hecho' },
  failed: { tone: 'critical', icon: 'x', label: 'Error' },
};

export const ACTIVE = ['queued', 'preflight', 'deploying', 'starting', 'running', 'cancelling'];

export const ORIGIN = { ui: 'Dashboard', cli: 'Terminal', discovered: 'Descubierto' };

export function runStatus(status) {
  return RUN_STATUS[status] || RUN_STATUS.unknown;
}

export function studyState(state) {
  return STUDY_STATE[state] || STUDY_STATE.pending;
}

const numberFormat = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
const intFormat = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 0 });

export function fmtInt(value) {
  return value == null ? '—' : intFormat.format(value);
}

export function fmtNumber(value, digits = 1) {
  if (value == null || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(value);
}

export function fmtPct(fraction) {
  if (fraction == null || !Number.isFinite(fraction)) return '—';
  return `${numberFormat.format(Math.min(1, Math.max(0, fraction)) * 100)} %`;
}

export function fmtDuration(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const s = Math.max(0, seconds);
  if (s < 1) return `${fmtNumber(s * 1000, 0)} ms`;
  if (s < 60) return `${fmtNumber(s, s < 10 ? 1 : 0)} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${Math.round(s % 60)} s`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${String(m % 60).padStart(2, '0')} min`;
  return `${Math.floor(h / 24)} d ${h % 24} h`;
}

export function fmtAgo(ts, now = Date.now() / 1000) {
  if (!ts) return '—';
  const delta = now - ts;
  if (delta < 5) return 'ahora';
  if (delta < 60) return `hace ${Math.round(delta)} s`;
  if (delta < 3600) return `hace ${Math.round(delta / 60)} min`;
  if (delta < 86400) return `hace ${Math.round(delta / 3600)} h`;
  return fmtDate(ts);
}

export function fmtDate(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

export function fmtTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleTimeString('es-ES', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const SIM_UNITS = [
  ['a', 31557600], ['d', 86400], ['h', 3600], ['min', 60], ['s', 1],
];

export function fmtSimTime(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  for (const [unit, size] of SIM_UNITS) {
    if (Math.abs(seconds) >= size || unit === 's') {
      const value = seconds / size;
      return `${new Intl.NumberFormat('es-ES', { maximumSignificantDigits: 3 }).format(value)} ${unit}`;
    }
  }
  return `${seconds} s`;
}

export function fmtBytes(bytes) {
  if (bytes == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let index = 0;
  while (value >= 1000 && index < units.length - 1) {
    value /= 1000;
    index += 1;
  }
  return `${fmtNumber(value, value < 10 ? 1 : 0)} ${units[index]}`;
}

export function runDuration(run, now = Date.now() / 1000) {
  if (!run.started_at) return null; // prepared or not yet synchronised: nothing ran yet
  return (run.finished_at || now) - run.started_at;
}

export function totalStudies(counts) {
  return Object.values(counts || {}).reduce((a, b) => a + b, 0);
}

// Minimal shell-like splitting for script arguments ("a b" 'c d' e).
export function splitArgs(text) {
  const out = [];
  const pattern = /"((?:\\.|[^"])*)"|'([^']*)'|(\S+)/g;
  let match;
  while ((match = pattern.exec(text || ''))) {
    out.push(match[1] !== undefined ? match[1].replace(/\\(.)/g, '$1') : match[2] ?? match[3]);
  }
  return out;
}

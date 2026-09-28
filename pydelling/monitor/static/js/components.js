// Reusable components as plain objects ({props, setup, template}) — portable 1:1 to .vue SFCs.
import {
  computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch,
} from '../vendor/vue.esm-browser.prod.js';
import {
  HOST_STATE, STAGE_STATE, STUDY_ORDER, fmtDuration, fmtInt, fmtNumber, fmtPct, fmtSimTime,
  fmtTime, runStatus, studyState,
} from './format.js';
import { ICONS } from './icons.js';

// Shared hover tooltip ---------------------------------------------------------------
export const tip = reactive({ visible: false, x: 0, y: 0, html: '' });
export function showTip(event, html) {
  tip.visible = true;
  tip.html = html;
  moveTip(event);
}
export function moveTip(event) {
  const x = event.clientX ?? (event.target.getBoundingClientRect().right);
  const y = event.clientY ?? (event.target.getBoundingClientRect().bottom);
  tip.x = Math.min(x, window.innerWidth - 340);
  tip.y = Math.min(y, window.innerHeight - 90);
}
export function hideTip() {
  tip.visible = false;
}
const escapeHtml = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));

export const Tooltip = {
  setup: () => ({ tip }),
  template: `<div v-if="tip.visible" class="tooltip" role="tooltip" :style="{left: tip.x + 'px', top: tip.y + 'px'}" v-html="tip.html"></div>`,
};

export const Icon = {
  props: { name: String, size: { type: String, default: '' }, spin: Boolean },
  setup: (props) => ({ path: computed(() => ICONS[props.name] || ICONS.circle) }),
  template: `<svg class="icon" :class="[size, {spin}]" viewBox="0 0 24 24" aria-hidden="true" v-html="path"></svg>`,
};

export const StatusPill = {
  components: { Icon },
  props: { status: String, kind: { type: String, default: 'run' } },
  setup(props) {
    const info = computed(() => {
      if (props.kind === 'study') return studyState(props.status);
      if (props.kind === 'host') return HOST_STATE[props.status] || HOST_STATE.offline;
      return runStatus(props.status);
    });
    return { info };
  },
  template: `<span class="pill" :class="'tone-' + info.tone"><Icon :name="info.icon" size="sm" :spin="info.spin || info.icon === 'loader'"/>{{ info.label }}</span>`,
};

export const Kpi = {
  components: { Icon },
  props: { label: String, value: [String, Number], unit: String, foot: String, icon: String },
  template: `<div class="card kpi"><div class="kpi-label"><Icon v-if="icon" :name="icon" size="sm"/>{{ label }}</div>
    <div class="kpi-value tabular">{{ value }}<small v-if="unit">{{ unit }}</small></div>
    <div v-if="foot" class="kpi-foot">{{ foot }}</div></div>`,
};

export const StateBar = {
  props: { counts: Object, legend: Boolean },
  setup(props) {
    const segments = computed(() => STUDY_ORDER
      .map((state) => ({ state, count: (props.counts || {})[state] || 0, ...studyState(state) }))
      .filter((s) => s.count > 0));
    const total = computed(() => segments.value.reduce((a, s) => a + s.count, 0));
    const hover = (event, segment) => showTip(
      event,
      `<b>${escapeHtml(segment.label)}</b>: ${fmtInt(segment.count)} de ${fmtInt(total.value)} estudios`,
    );
    return { segments, total, hover, moveTip, hideTip, fmtInt };
  },
  template: `<div>
    <div class="statebar" role="img" :aria-label="segments.map(s => s.label + ' ' + s.count).join(', ') || 'Sin estudios'">
      <span v-for="s in segments" :key="s.state" :class="'tone-' + s.tone" :style="{flexGrow: s.count}"
        @mouseenter="hover($event, s)" @mousemove="moveTip" @mouseleave="hideTip"></span>
      <span v-if="!segments.length" class="tone-neutral" style="flex-grow:1;opacity:.35"></span>
    </div>
    <div v-if="legend" class="statebar-legend">
      <span v-for="s in segments" :key="s.state"><b class="tabular">{{ fmtInt(s.count) }}</b> {{ s.label.toLowerCase() }}</span>
    </div></div>`,
};

export const ProgressBar = {
  props: { value: Number, tone: { type: String, default: 'running' }, label: String },
  template: `<div class="progress" :class="'tone-' + tone" role="progressbar" :aria-label="label"
    aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round((value || 0) * 100)">
    <span :style="{width: Math.min(100, Math.max(0, (value || 0) * 100)) + '%', background: 'var(--tone)'}"></span></div>`,
};

export const Stages = {
  components: { Icon },
  props: { stages: Array },
  setup() {
    const info = (stage) => STAGE_STATE[stage.status] || STAGE_STATE.pending;
    const detail = (stage) => {
      if (stage.status === 'failed' && stage.detail) return stage.detail;
      if (stage.counts) {
        return Object.entries(stage.counts).map(([k, v]) => `${v} ${studyState(k).label.toLowerCase()}`).join(' · ');
      }
      if (stage.total && stage.status === 'running') return `${fmtInt(stage.total)} estudios`;
      if (stage.seconds != null) return fmtDuration(stage.seconds);
      return info(stage).label;
    };
    return { info, detail };
  },
  template: `<div class="pipeline" role="list" aria-label="Fases del run">
    <div v-for="stage in stages" :key="stage.id" role="listitem" class="stage"
      :class="['tone-' + info(stage).tone, 'status-' + stage.status]" :title="stage.detail || ''">
      <div class="stage-top"><Icon :name="info(stage).icon" size="sm" :spin="stage.status === 'running'"/>
        <span class="ellipsis">{{ stage.label }}</span></div>
      <div class="stage-detail ellipsis">{{ detail(stage) }}</div>
    </div></div>`,
};

export const StudyGrid = {
  props: { studies: Array, selected: String },
  emits: ['select'],
  setup(props, { emit }) {
    const dense = computed(() => props.studies.length > 300);
    const fill = (study) => (study.state === 'running' ? `${Math.round((study.progress || 0) * 100)}%` : '100%');
    const hover = (event, study) => {
      const info = studyState(study.state);
      const lines = [`<b>${escapeHtml(study.name)}</b>`, escapeHtml(info.label)];
      if (study.state === 'running' && study.final_time_s) {
        lines.push(`t = ${fmtSimTime(study.sim_time_s)} de ${fmtSimTime(study.final_time_s)} (${fmtPct(study.progress)})`);
      }
      if (study.runtime_s != null && study.state !== 'running') lines.push(`Duración ${fmtDuration(study.runtime_s)}`);
      if (study.error) lines.push(escapeHtml(study.error));
      showTip(event, lines.join('<br>'));
    };
    return { dense, fill, hover, moveTip, hideTip, studyState, emit };
  },
  template: `<div class="grid-tiles" role="list" aria-label="Estudios por estado">
    <button v-for="s in studies" :key="s.name" type="button" role="listitem" class="tile"
      :class="['tone-' + studyState(s.state).tone, 'state-' + (s.state || 'pending'), {selected: s.name === selected, dense}]"
      :style="{'--fill': fill(s)}" :aria-label="s.name + ': ' + studyState(s.state).label"
      @click="emit('select', s.name)" @mouseenter="hover($event, s)" @mousemove="moveTip" @mouseleave="hideTip"
      @focus="hover($event, s)" @blur="hideTip"><i></i></button>
  </div>`,
};

export const StudyTable = {
  components: { StatusPill },
  props: { studies: Array, selected: String },
  emits: ['select'],
  setup(props, { emit }) {
    const sort = reactive({ key: 'name', dir: 1 });
    const columns = [
      { key: 'name', label: 'Estudio' },
      { key: 'state', label: 'Estado' },
      { key: 'attempt', label: 'Intento', num: true },
      { key: 'progress', label: 'Progreso', num: true },
      { key: 'sim_time_s', label: 't simulado', num: true },
      { key: 'dt_s', label: 'Δt', num: true },
      { key: 'step', label: 'Pasos', num: true },
      { key: 'cuts', label: 'Recortes', num: true },
      { key: 'runtime_s', label: 'Duración', num: true },
    ];
    const rows = computed(() => [...props.studies].sort((a, b) => {
      const x = a[sort.key] ?? -Infinity;
      const y = b[sort.key] ?? -Infinity;
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    }));
    const by = (key) => {
      sort.dir = sort.key === key ? -sort.dir : 1;
      sort.key = key;
    };
    return { sort, columns, rows, by, emit, fmtPct, fmtSimTime, fmtDuration, fmtInt };
  },
  template: `<div class="table-wrap"><table class="data">
    <thead><tr><th v-for="c in columns" :key="c.key" :class="{num: c.num}" @click="by(c.key)"
      :aria-sort="sort.key === c.key ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none'">
      {{ c.label }}<span v-if="sort.key === c.key">{{ sort.dir > 0 ? ' ↑' : ' ↓' }}</span></th></tr></thead>
    <tbody><tr v-for="s in rows" :key="s.name" :class="{selected: s.name === selected}" @click="emit('select', s.name)">
      <td class="mono">{{ s.name }}</td><td><StatusPill :status="s.state" kind="study"/></td>
      <td class="num">{{ s.attempt ?? '—' }}</td><td class="num">{{ fmtPct(s.progress) }}</td>
      <td class="num">{{ fmtSimTime(s.sim_time_s) }}</td><td class="num">{{ fmtSimTime(s.dt_s) }}</td>
      <td class="num">{{ fmtInt(s.step) }}</td><td class="num">{{ fmtInt(s.cuts) }}</td>
      <td class="num">{{ fmtDuration(s.runtime_s) }}</td></tr></tbody></table></div>`,
};

// Δt vs simulated time (log-log), single series + cut markers; crosshair tooltip.
export const DtChart = {
  props: { series: Array, finalTime: Number, height: { type: Number, default: 180 } },
  setup(props) {
    const root = ref(null);
    const width = ref(520);
    const hoverIndex = ref(null);
    let observer = null;
    onMounted(() => {
      observer = new ResizeObserver(([entry]) => { width.value = Math.max(240, entry.contentRect.width); });
      observer.observe(root.value);
    });
    onBeforeUnmount(() => observer && observer.disconnect());
    const margin = { left: 54, right: 14, top: 10, bottom: 26 };
    const points = computed(() => (props.series || []).filter((p) => p[0] > 0 && p[1] > 0));
    const log = Math.log10;
    const domain = computed(() => {
      const pts = points.value;
      if (pts.length < 2) return null;
      const ts = pts.map((p) => p[0]);
      const ds = pts.map((p) => p[1]);
      let x0 = log(Math.min(...ts));
      let x1 = log(Math.max(Math.max(...ts), props.finalTime || 0));
      let y0 = log(Math.min(...ds)) - 0.15;
      let y1 = log(Math.max(...ds)) + 0.15;
      if (x1 - x0 < 1e-9) { x0 -= 0.5; x1 += 0.5; }
      if (y1 - y0 < 0.5) { const mid = (y0 + y1) / 2; y0 = mid - 0.5; y1 = mid + 0.5; }
      return { x0, x1, y0, y1 };
    });
    const sx = (t) => margin.left + ((log(t) - domain.value.x0) / (domain.value.x1 - domain.value.x0)) * (width.value - margin.left - margin.right);
    const sy = (d) => margin.top + (1 - (log(d) - domain.value.y0) / (domain.value.y1 - domain.value.y0)) * (props.height - margin.top - margin.bottom);
    const ticks = (a, b) => {
      const lo = Math.ceil(a);
      const hi = Math.floor(b);
      const step = Math.max(1, Math.ceil((hi - lo + 1) / 6));
      const out = [];
      for (let k = lo; k <= hi; k += step) out.push(10 ** k);
      return out;
    };
    const geometry = computed(() => {
      if (!domain.value) return null;
      const pts = points.value;
      const line = pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join('');
      const base = props.height - margin.bottom;
      const area = `${line}L${sx(pts[pts.length - 1][0]).toFixed(1)},${base}L${sx(pts[0][0]).toFixed(1)},${base}Z`;
      const cuts = pts.filter((p, i) => i > 0 && (p[2] || 0) > (pts[i - 1][2] || 0));
      return {
        line, area, cuts,
        xticks: ticks(domain.value.x0, domain.value.x1),
        yticks: ticks(domain.value.y0, domain.value.y1),
        final: props.finalTime ? sx(props.finalTime) : null,
      };
    });
    const onMove = (event) => {
      const rect = root.value.getBoundingClientRect();
      const x = event.clientX - rect.left;
      let best = null;
      let bestDistance = Infinity;
      points.value.forEach((p, i) => {
        const distance = Math.abs(sx(p[0]) - x);
        if (distance < bestDistance) { best = i; bestDistance = distance; }
      });
      hoverIndex.value = best;
      if (best != null) {
        const p = points.value[best];
        showTip(event, `<b>t = ${fmtSimTime(p[0])}</b><br>Δt = ${fmtSimTime(p[1])}<br>Recortes acumulados: ${fmtInt(p[2] || 0)}`);
      }
    };
    const onLeave = () => { hoverIndex.value = null; hideTip(); };
    const label = computed(() => `Paso de tiempo frente a tiempo simulado: ${points.value.length} puntos, ${geometry.value ? geometry.value.cuts.length : 0} recortes`);
    return { root, width, margin, geometry, points, sx, sy, hoverIndex, onMove, onLeave, label, fmtSimTime };
  },
  template: `<div class="chart" ref="root">
    <p v-if="!geometry" class="muted" style="margin:18px 0">Sin datos de convergencia todavía.</p>
    <svg v-else :viewBox="'0 0 ' + width + ' ' + height" :height="height" role="img" :aria-label="label"
      @mousemove="onMove" @mouseleave="onLeave">
      <g class="grid"><line v-for="t in geometry.yticks" :key="'gy' + t" :x1="margin.left" :x2="width - margin.right" :y1="sy(t)" :y2="sy(t)"/></g>
      <g class="axis">
        <text v-for="t in geometry.yticks" :key="'ly' + t" :x="margin.left - 8" :y="sy(t) + 4" text-anchor="end">{{ fmtSimTime(t) }}</text>
        <text v-for="t in geometry.xticks" :key="'lx' + t" :x="sx(t)" :y="height - 6" text-anchor="middle">{{ fmtSimTime(t) }}</text>
      </g>
      <line v-if="geometry.final" class="final" :x1="geometry.final" :x2="geometry.final" :y1="margin.top" :y2="height - margin.bottom"/>
      <path class="area" :d="geometry.area"/>
      <path class="line" :d="geometry.line"/>
      <circle v-for="(c, i) in geometry.cuts" :key="'c' + i" class="cut" :cx="sx(c[0])" :cy="sy(c[1])" r="4.5"/>
      <g v-if="hoverIndex != null">
        <line class="cross" :x1="sx(points[hoverIndex][0])" :x2="sx(points[hoverIndex][0])" :y1="margin.top" :y2="height - margin.bottom"/>
        <circle class="focus" :cx="sx(points[hoverIndex][0])" :cy="sy(points[hoverIndex][1])" r="5"/>
      </g>
      <rect :x="margin.left" :y="margin.top" :width="Math.max(0, width - margin.left - margin.right)" :height="height - margin.top - margin.bottom" fill="transparent"/>
    </svg></div>`,
};

export const LogView = {
  props: { text: String, empty: { type: String, default: 'Sin salida todavía.' }, height: { type: Number, default: 320 } },
  setup(props) {
    const pre = ref(null);
    const follow = ref(true);
    const onScroll = () => {
      const el = pre.value;
      follow.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    };
    const stick = () => nextTick(() => { if (pre.value && follow.value) pre.value.scrollTop = pre.value.scrollHeight; });
    watch(() => props.text, stick);
    onMounted(stick);
    return { pre, onScroll };
  },
  template: `<pre class="log" ref="pre" :style="{maxHeight: height + 'px'}" @scroll="onScroll" tabindex="0">{{ text || empty }}</pre>`,
};

const EVENT_LABELS = {
  'launch.queued': 'Lanzamiento en cola',
  'launch.requested': 'Lanzamiento solicitado',
  'launch.failed': 'El lanzamiento falló',
  'launch.lost': 'El lanzador terminó inesperadamente',
  'launch.cancelled': 'Lanzamiento cancelado',
  'preflight.started': 'Comprobando acceso',
  'preflight.done': 'Acceso verificado',
  'preflight.failed': 'Comprobación de acceso fallida',
  'deploy.started': 'Desplegando código',
  'deploy.hashed': 'Ficheros inventariados (SHA-256)',
  'deploy.uploaded': 'Código subido al host',
  'deploy.verified': 'Integridad verificada en el host',
  'deploy.synced': 'Entorno uv sincronizado',
  'deploy.done': 'Despliegue completado',
  'deploy.failed': 'Despliegue fallido',
  'start.started': 'Arrancando worker',
  'start.done': 'Worker en marcha',
  'start.failed': 'No se pudo arrancar el worker',
  'worker.started': 'Worker iniciado',
  'batch.started': 'Lote iniciado',
  'batch.finished': 'Lote terminado',
  'cancel.requested': 'Cancelación solicitada',
  'cancel.sent': 'Cancelación enviada',
  'collect.queued': 'Descarga en cola',
  'collect.started': 'Descargando resultados',
  'collect.done': 'Resultados descargados',
  'collect.failed': 'Descarga fallida',
  'run.status': 'Cambio de estado',
  'verification.gate': 'Control de verificación',
  'watcher.warning': 'Aviso del watcher',
  'campaign.state': 'Estado de la campaña',
};

export const Timeline = {
  components: { Icon },
  props: { events: Array },
  setup(props) {
    const showStudies = ref(false);
    // By default only non-routine study/check events (failures, warnings) are listed.
    const routine = (e) => ['study.state', 'preflight.check'].includes(e.event_type) && e.level === 'info';
    const items = computed(() => [...(props.events || [])]
      .filter((e) => showStudies.value || !routine(e))
      .reverse()
      .slice(0, 250));
    const tone = (e) => ({ error: 'critical', warning: 'warning' }[e.level] || (e.source === 'worker' ? 'running' : 'active'));
    const icon = (e) => ({ error: 'x', warning: 'alert' }[e.level] || (e.event_type.endsWith('.done') ? 'check' : 'activity'));
    const text = (e) => e.message || EVENT_LABELS[e.event_type] || e.event_type;
    const title = (e) => (e.message ? EVENT_LABELS[e.event_type] || e.event_type : '');
    return { showStudies, items, tone, icon, text, title, fmtTime };
  },
  template: `<div>
    <label class="muted" style="display:flex;gap:6px;align-items:center;font-size:12.5px;margin-bottom:6px">
      <input type="checkbox" v-model="showStudies"> Mostrar todos los eventos de estudios</label>
    <ul class="timeline" aria-live="polite">
      <li v-for="e in items" :key="e.id" :class="'tone-' + tone(e)">
        <span class="tl-icon"><Icon :name="icon(e)" size="sm"/></span>
        <span><span>{{ text(e) }}</span><span v-if="title(e)" class="faint"> · {{ title(e) }}</span></span>
        <span class="when tabular">{{ fmtTime(e.ts) }}</span>
      </li>
      <li v-if="!items.length"><span></span><span class="muted">Sin actividad registrada.</span><span></span></li>
    </ul></div>`,
};

export const CheckList = {
  components: { Icon },
  props: { checks: Array },
  setup() {
    const map = {
      ok: { icon: 'check', tone: 'good' },
      warn: { icon: 'alert', tone: 'warning' },
      fail: { icon: 'x', tone: 'critical' },
      skip: { icon: 'minus', tone: 'neutral' },
    };
    return { map, fmtNumber };
  },
  template: `<ul class="checks">
    <li v-for="(c, i) in checks" :key="c.id" :style="{animationDelay: (i * 70) + 'ms'}" :class="'tone-' + map[c.status].tone">
      <span style="color: var(--tone-text)"><Icon :name="map[c.status].icon"/></span>
      <span><div class="label">{{ c.label }}</div><div class="detail">{{ c.detail }}</div></span>
      <span class="faint tabular" style="font-size:12px">{{ c.ms ? fmtNumber(c.ms, 0) + ' ms' : '' }}</span>
    </li></ul>`,
};

export const Command = {
  components: { Icon },
  props: { command: String },
  setup(props) {
    const copied = ref(false);
    const copy = async () => {
      try {
        await navigator.clipboard.writeText(props.command);
        copied.value = true;
        setTimeout(() => { copied.value = false; }, 1500);
      } catch {
        copied.value = false;
      }
    };
    return { copied, copy };
  },
  template: `<div class="cmd"><code>{{ command }}</code>
    <button type="button" class="btn sm" @click="copy" :aria-label="'Copiar ' + command"><Icon :name="copied ? 'check' : 'copy'" size="sm"/>{{ copied ? 'Copiado' : 'Copiar' }}</button></div>`,
};

export const HostMeter = {
  props: { heartbeat: Object },
  setup(props) {
    const disk = computed(() => {
      const hb = props.heartbeat || {};
      if (!hb.disk_total) return null;
      return { used: 1 - hb.disk_free / hb.disk_total, free: hb.disk_free };
    });
    return { disk };
  },
  template: `<div v-if="disk" class="meter" :class="disk.used > 0.9 ? 'tone-critical' : disk.used > 0.75 ? 'tone-warning' : 'tone-running'"
    role="img" :aria-label="'Disco usado ' + Math.round(disk.used * 100) + ' %'"><span :style="{width: (disk.used * 100) + '%'}"></span></div>`,
};

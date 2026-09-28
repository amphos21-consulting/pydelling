// Pages: runs overview/history, run detail, launch wizard, hosts, missing token.
import { computed, onMounted, reactive, ref, watch } from '../vendor/vue.esm-browser.prod.js';
import { api } from './api.js';
import {
  CheckList, Command, DtChart, HostMeter, Icon, Kpi, LogView, ProgressBar, StateBar,
  Stages, StatusPill, StudyGrid, StudyTable, Timeline,
} from './components.js';
import {
  ACTIVE, HOST_STATE, ORIGIN, fmtAgo, fmtBytes, fmtDate, fmtDuration, fmtInt, fmtNumber, fmtPct,
  fmtSimTime, runDuration, runStatus, splitArgs, studyState, totalStudies,
} from './format.js';
import { action, loadRun, loadStudy, state, toast } from './store.js';

const hostLabel = (id) => (state.hosts[id] && (state.hosts[id].label || id)) || id;

// Runs --------------------------------------------------------------------------------
export const RunsView = {
  components: { Icon, Kpi, StateBar, StatusPill },
  setup() {
    const filters = reactive({ q: '', status: 'all', host: 'all' });
    const groups = {
      all: null,
      active: ACTIVE,
      completed: ['completed'],
      failed: ['failed', 'lost'],
      cancelled: ['cancelled', 'interrupted'],
    };
    const runs = computed(() => Object.values(state.runs)
      .filter((r) => !groups[filters.status] || groups[filters.status].includes(r.status))
      .filter((r) => filters.host === 'all' || r.host_id === filters.host)
      .filter((r) => !filters.q || `${r.name} ${r.entry_path || ''} ${r.remote_folder}`.toLowerCase().includes(filters.q.toLowerCase()))
      .sort((a, b) => (b.started_at || b.created_at || 0) - (a.started_at || a.created_at || 0)));
    const hosts = computed(() => Object.values(state.hosts));
    const hostTone = (h) => (HOST_STATE[h.stream_state] || HOST_STATE.offline).tone;
    const hostText = (h) => (HOST_STATE[h.stream_state] || HOST_STATE.offline).label;
    const load = (h) => {
      const hb = h.heartbeat || {};
      if (!hb.load) return hb.cpus ? `${hb.cpus} CPUs` : '';
      return `carga ${fmtNumber(hb.load[0], 1)} / ${hb.cpus} CPUs`;
    };
    const progress = (r) => (r.progress == null ? null : r.progress);
    return {
      state, filters, runs, hosts, hostTone, hostText, load, progress, fmtInt, fmtPct, fmtAgo,
      fmtDuration, runDuration, ORIGIN, hostLabel, runStatus, totalStudies, fmtBytes,
    };
  },
  template: `<div class="page">
    <div class="page-head">
      <div><h1 class="page-title">Runs</h1>
        <p class="page-sub">Campañas y scripts lanzados, en curso e históricos{{ state.project ? ' · ' + state.project.name : '' }}</p></div>
      <div class="page-actions"><a class="btn primary" href="#/launch"><Icon name="rocket" size="sm"/>Nuevo lanzamiento</a></div>
    </div>
    <div class="kpis">
      <Kpi label="Runs activos" icon="activity" :value="fmtInt(state.kpis.active)"/>
      <Kpi label="Estudios en ejecución" icon="layers" :value="fmtInt(state.kpis.running_studies)"/>
      <Kpi label="Completados (7 días)" icon="check" :value="fmtInt(state.kpis.completed_7d)"/>
      <Kpi label="Fallidos (7 días)" icon="alert" :value="fmtInt(state.kpis.failed_7d)" :foot="fmtInt(state.kpis.total) + ' runs en el historial'"/>
    </div>
    <div class="hosts-row">
      <a v-for="h in hosts" :key="h.id" class="host-chip" href="#/hosts" :class="'tone-' + hostTone(h)" style="color:inherit;text-decoration:none">
        <span class="dot" :class="{pulse: h.stream_state === 'connecting'}"></span>
        <span class="ellipsis"><div class="name">{{ h.label || h.id }}</div>
          <div class="meta">{{ hostText(h) }}<template v-if="load(h)"> · {{ load(h) }}</template></div></span>
      </a>
    </div>
    <div class="toolbar">
      <div class="search"><Icon name="search" size="sm"/><input class="input" v-model="filters.q" placeholder="rc1-smoke, cases/rc1/study.yaml…" aria-label="Buscar runs"></div>
      <div class="segmented" role="group" aria-label="Filtrar por estado">
        <button v-for="[k, label] in [['all','Todos'],['active','Activos'],['completed','Completados'],['failed','Fallidos'],['cancelled','Cancelados']]"
          :key="k" :class="{on: filters.status === k}" @click="filters.status = k" :aria-pressed="filters.status === k">{{ label }}</button>
      </div>
      <select class="select" v-model="filters.host" aria-label="Filtrar por host">
        <option value="all">Todos los hosts</option>
        <option v-for="h in hosts" :key="h.id" :value="h.id">{{ h.label || h.id }}</option>
      </select>
    </div>
    <div class="card runs">
      <div class="run-row head"><span>Estado</span><span>Run</span><span class="col-host">Host</span><span class="col-bar">Estudios</span>
        <span class="col-progress">Progreso</span><span class="col-when">Inicio</span><span class="col-go"></span></div>
      <a v-for="r in runs" :key="r.id" class="run-row" :href="'#/runs/' + r.id">
        <span><StatusPill :status="r.status"/></span>
        <span class="ellipsis"><div class="run-name ellipsis">{{ r.name }}</div>
          <div class="run-entry ellipsis">{{ r.entry_path || r.remote_folder }} · <span class="faint">{{ ORIGIN[r.origin] || r.origin }}</span></div></span>
        <span class="col-host ellipsis muted">{{ hostLabel(r.host_id) }}</span>
        <span class="col-bar"><StateBar :counts="r.counts_json"/>
          <div class="faint" style="font-size:11.5px;margin-top:4px">{{ totalStudies(r.counts_json) ? fmtInt(totalStudies(r.counts_json)) + ' estudios' : r.kind === 'script' ? 'Script' : 'Sin estudios' }}</div></span>
        <span class="col-progress tabular">{{ fmtPct(r.progress) }}<div class="faint" style="font-size:11.5px">{{ fmtDuration(runDuration(r, state.now)) }}</div></span>
        <span class="col-when muted" style="font-size:12.5px">{{ r.started_at ? fmtAgo(r.started_at, state.now) : '—' }}</span>
        <span class="col-go faint"><Icon name="chevron" size="sm"/></span>
      </a>
      <div v-if="!runs.length" class="empty">
        <div class="empty-icon"><Icon name="rocket" size="lg"/></div>
        <h3>{{ Object.keys(state.runs).length ? 'Ningún run coincide con los filtros' : 'Todavía no hay runs' }}</h3>
        <p>Lanza una campaña o un script desde aquí o con <code>just run</code>. Las campañas existentes en los hosts aparecen solas al conectar.</p>
        <a class="btn primary" href="#/launch"><Icon name="rocket" size="sm"/>Lanzar un run</a>
      </div>
    </div>
  </div>`,
};

// Run detail ---------------------------------------------------------------------------
const StudyPanel = {
  components: { DtChart, Icon, LogView, ProgressBar, StatusPill },
  props: { runId: String, study: Object },
  setup(props) {
    const log = ref(null);
    const loadingLog = ref(false);
    const full = computed(() => props.study && state.studies[`${props.runId}/${props.study.name}`]);
    const fetchFull = () => props.study && loadStudy(props.runId, props.study.name).catch(() => {});
    watch(() => props.study && props.study.name, () => { log.value = null; fetchFull(); }, { immediate: true });
    const showLog = async (stream) => {
      loadingLog.value = true;
      try {
        log.value = (await api(`/runs/${props.runId}/studies/${encodeURIComponent(props.study.name)}/log?stream=${stream}`)).text;
      } catch (error) {
        toast(error.message, 'critical');
      } finally {
        loadingLog.value = false;
      }
    };
    return { full, log, loadingLog, showLog, fmtSimTime, fmtDuration, fmtInt, fmtPct, studyState };
  },
  template: `<div class="card" v-if="study">
    <div class="card-head"><h2 class="card-title mono">{{ study.name }}</h2><StatusPill :status="study.state" kind="study"/>
      <span v-if="study.attempt" class="badge">intento {{ study.attempt }}</span></div>
    <div class="card-body" style="display:grid;gap:14px">
      <div>
        <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:6px">
          <span class="muted">t = {{ fmtSimTime(study.sim_time_s) }} de {{ fmtSimTime(study.final_time_s) }}</span>
          <span class="tabular">{{ fmtPct(study.progress) }}</span></div>
        <ProgressBar :value="study.progress" :tone="studyState(study.state).tone" :label="'Progreso de ' + study.name"/>
      </div>
      <div class="stats">
        <div><div class="stat-label">Pasos</div><div class="stat-value">{{ fmtInt(study.step) }}</div></div>
        <div><div class="stat-label">Δt actual</div><div class="stat-value">{{ fmtSimTime(study.dt_s) }}</div></div>
        <div><div class="stat-label">Recortes de Δt</div><div class="stat-value" :style="study.cuts ? 'color: var(--st-serious-text)' : ''">{{ fmtInt(study.cuts) }}</div></div>
        <div><div class="stat-label">{{ study.state === 'running' ? 'Iteraciones Newton' : 'Duración' }}</div>
          <div class="stat-value">{{ study.state === 'running' ? fmtInt(study.newton) : fmtDuration(study.runtime_s) }}</div></div>
      </div>
      <div><div class="stat-label" style="margin-bottom:4px">Δt frente al tiempo simulado (log-log) · <span style="color:var(--st-serious-text)">●</span> recorte de paso · línea discontinua = tiempo final</div>
        <DtChart :series="full ? full.series_json : []" :final-time="study.final_time_s"/></div>
      <div v-if="study.error" class="error-banner"><Icon name="alert"/><div>{{ study.error }}</div></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn sm" @click="showLog('stdout')" :disabled="!study.workdir || loadingLog"><Icon name="terminal" size="sm"/>Salida de PFLOTRAN</button>
        <button class="btn sm" @click="showLog('stderr')" :disabled="!study.workdir || loadingLog"><Icon name="alert" size="sm"/>stderr</button>
        <span v-if="study.workdir" class="faint mono ellipsis" style="align-self:center">{{ study.workdir }}</span>
      </div>
      <LogView v-if="log !== null" :text="log" :height="260"/>
    </div></div>
    <div class="card" v-else><div class="card-body muted">Selecciona un estudio para ver su progreso y convergencia.</div></div>`,
};

export const RunView = {
  components: { Icon, Kpi, LogView, Stages, StateBar, StatusPill, StudyGrid, StudyPanel, StudyTable, Timeline },
  props: { id: String },
  setup(props) {
    const view = ref('grid');
    const error = ref(null);
    const busy = ref('');
    const detail = computed(() => state.details[props.id]);
    const run = computed(() => (detail.value ? { ...detail.value.run, ...(state.runs[props.id] || {}) } : state.runs[props.id]));
    const studies = computed(() => (detail.value ? Object.values(detail.value.studies) : []).sort((a, b) => a.name.localeCompare(b.name)));
    const selected = computed(() => {
      if (!detail.value) return null;
      const chosen = detail.value.selected && detail.value.studies[detail.value.selected];
      return chosen || studies.value.find((s) => s.state === 'running') || studies.value[0] || null;
    });
    const select = (name) => { detail.value.selected = name; };
    const load = () => loadRun(props.id).then(() => { error.value = null; }).catch((e) => { error.value = e.message; });
    onMounted(load);
    watch(() => props.id, load);
    const counts = computed(() => (run.value && run.value.counts_json) || {});
    const total = computed(() => totalStudies(counts.value));
    const host = computed(() => run.value && state.hosts[run.value.host_id]);
    const stale = computed(() => host.value && host.value.stream_state !== 'connected' && host.value.transport === 'ssh');
    const doAction = async (name, body = {}, message = '') => {
      if (name === 'cancel' && !window.confirm('¿Cancelar este run? Los estudios en curso se detendrán y quedarán como interrumpidos.')) return;
      busy.value = name;
      try {
        const result = await action(`/runs/${props.id}/${name}`, body, message);
        if (result && result.run_id && result.run_id !== props.id) window.location.hash = `#/runs/${result.run_id}`;
        await load();
      } catch {
        // toast already shown
      } finally {
        busy.value = '';
      }
    };
    const refreshLog = async () => {
      try {
        const data = await api(`/runs/${props.id}/log?live=1`);
        detail.value.run.log_tail = data.text;
      } catch (e) {
        toast(e.message, 'critical');
      }
    };
    const lostHelp = computed(() => run.value && run.value.status === 'lost');
    return {
      state, view, error, busy, detail, run, studies, selected, select, counts, total, host, stale,
      doAction, refreshLog, lostHelp, fmtInt, fmtAgo, fmtDate, fmtDuration, runDuration, hostLabel, ORIGIN,
      HOST_STATE,
    };
  },
  template: `<div class="page">
    <div class="crumbs"><a href="#/runs"><Icon name="back" size="sm"/> Runs</a><span>/</span><span class="ellipsis">{{ run ? run.name : id }}</span></div>
    <div v-if="error && !detail" class="error-banner"><Icon name="alert"/><div>{{ error }}</div></div>
    <template v-if="run && detail">
      <div class="page-head">
        <div style="min-width:0">
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h1 class="page-title ellipsis">{{ run.name }}</h1><StatusPill :status="run.status"/></div>
          <div class="run-meta" style="margin-top:6px">
            <span><Icon :name="run.host_id === 'local' ? 'laptop' : 'server'" size="sm"/>{{ hostLabel(run.host_id) }}</span>
            <span v-if="run.entry_path" class="mono">{{ run.entry_path }}</span>
            <span v-if="run.release_id" class="mono" title="Release desplegado">release {{ run.release_id.slice(0, 10) }}</span>
            <span><Icon name="clock" size="sm"/>{{ fmtDate(run.started_at || run.created_at) }} · {{ fmtDuration(runDuration(run, state.now)) }}</span>
            <span class="badge">{{ ORIGIN[run.origin] || run.origin }}</span>
          </div>
        </div>
        <div class="page-actions">
          <button v-if="detail.actions.resume" class="btn" :disabled="!!busy" @click="doAction('resume', {}, 'Reanudación lanzada')"><Icon name="refresh" size="sm" :spin="busy === 'resume'"/>Reanudar</button>
          <button v-if="detail.actions.collect" class="btn" :disabled="!!busy" @click="doAction('collect', {}, 'Descarga en marcha')"><Icon name="download" size="sm"/>Descargar</button>
          <button v-if="detail.actions.collect" class="btn" :disabled="!!busy" @click="doAction('collect', {raw: true}, 'Descarga con HDF5 en marcha')" title="Incluye los ficheros HDF5 originales"><Icon name="disk" size="sm"/>Con HDF5</button>
          <button v-if="detail.actions.open" class="btn" @click="doAction('open')"><Icon name="folder" size="sm"/>Abrir carpeta</button>
          <button v-if="detail.actions.cancel" class="btn danger" :disabled="!!busy" @click="doAction('cancel', {}, 'Cancelación enviada')"><Icon name="stop" size="sm"/>Cancelar</button>
        </div>
      </div>
      <div v-if="run.error" class="error-banner"><Icon name="alert"/><div><b>{{ run.status === 'failed' ? 'El run falló' : 'Aviso' }}</b><pre>{{ run.error }}</pre></div></div>
      <div v-if="lostHelp" class="error-banner"><Icon name="alert"/><div>El worker terminó sin cerrar la campaña (reinicio del host o proceso matado). Revisa el log y usa <b>Reanudar</b>: los estudios completados se conservan.</div></div>
      <div v-if="stale" class="error-banner tone-warning"><Icon name="wifi-off"/><div>Sin conexión en vivo con {{ hostLabel(run.host_id) }} ({{ (HOST_STATE[host.stream_state] || {}).label }}). Se muestran los últimos datos sincronizados. <a href="#/hosts">Ver hosts</a></div></div>
      <Stages :stages="detail.stages"/>
      <div class="kpis" v-if="run.kind === 'script'">
        <Kpi label="Worker" icon="cpu" :value="run.worker_alive ? 'En marcha' : 'Terminado'" :foot="run.worker_json && run.worker_json.pid ? 'pid ' + run.worker_json.pid : ''"/>
        <Kpi label="Código de salida" icon="flag" :value="run.exit_code == null ? '—' : String(run.exit_code)" :foot="run.exit_code === 0 ? 'Correcto' : run.exit_code == null ? '' : 'Error'"/>
        <Kpi label="Duración" icon="clock" :value="fmtDuration(runDuration(run, state.now))" :foot="run.finished_at ? 'Terminó ' + fmtAgo(run.finished_at, state.now) : ''"/>
        <Kpi label="Host" :icon="run.host_id === 'local' ? 'laptop' : 'server'" :value="hostLabel(run.host_id)"/>
      </div>
      <div class="kpis" v-else>
        <div class="card kpi"><div class="kpi-label"><Icon name="check" size="sm"/>Completados</div>
          <div class="kpi-value tabular">{{ fmtInt(counts.completed || 0) }}<small>/ {{ fmtInt(total) }}</small></div>
          <StateBar :counts="counts" style="margin-top:8px"/></div>
        <Kpi label="En ejecución" icon="loader" :value="fmtInt(counts.running || 0)"/>
        <Kpi label="Fallidos o interrumpidos" icon="alert" :value="fmtInt((counts.failed || 0) + (counts.interrupted || 0))"/>
        <Kpi label="Duración" icon="clock" :value="fmtDuration(runDuration(run, state.now))" :foot="run.finished_at ? 'Terminó ' + fmtAgo(run.finished_at, state.now) : (run.worker_alive ? 'Worker vivo' : '')"/>
      </div>
      <div class="detail-grid">
        <div class="stack">
          <div class="card" v-if="run.kind !== 'script'">
            <div class="card-head"><h2 class="card-title">Estudios</h2>
              <div class="segmented" style="margin-left:auto" role="group" aria-label="Vista de estudios">
                <button :class="{on: view === 'grid'}" @click="view = 'grid'" :aria-pressed="view === 'grid'"><Icon name="grid" size="sm"/> Rejilla</button>
                <button :class="{on: view === 'table'}" @click="view = 'table'" :aria-pressed="view === 'table'"><Icon name="list" size="sm"/> Tabla</button>
              </div></div>
            <div class="card-body" v-if="studies.length">
              <template v-if="view === 'grid'">
                <StudyGrid :studies="studies" :selected="selected && selected.name" @select="select"/>
                <div class="legend" style="margin-top:12px">
                  <span class="tone-good"><i></i>Completado</span><span class="tone-running"><i></i>En ejecución (relleno = progreso)</span>
                  <span class="tone-critical"><i></i>Fallido</span><span class="tone-serious"><i></i>Interrumpido</span>
                  <span class="tone-neutral"><i style="background:transparent;box-shadow:inset 0 0 0 1px var(--border-strong)"></i>Pendiente</span>
                </div>
              </template>
            </div>
            <StudyTable v-if="studies.length && view === 'table'" :studies="studies" :selected="selected && selected.name" @select="select"/>
            <div v-if="!studies.length" class="card-body muted">Todavía no hay estudios registrados.</div>
          </div>
          <div class="card">
            <div class="card-head"><h2 class="card-title">Log del worker</h2>
              <button class="btn sm ghost" style="margin-left:auto" @click="refreshLog"><Icon name="refresh" size="sm"/>Leer del host</button></div>
            <div class="card-body"><LogView :text="detail.run.log_tail" empty="El worker todavía no ha escrito nada."/></div>
          </div>
        </div>
        <div class="stack">
          <StudyPanel v-if="run.kind !== 'script'" :run-id="id" :study="selected"/>
          <div class="card"><div class="card-head"><h2 class="card-title">Actividad</h2></div>
            <div class="card-body"><Timeline :events="detail.events"/></div></div>
        </div>
      </div>
    </template>
    <div v-else-if="!error" class="card"><div class="card-body muted"><Icon name="loader" spin size="sm"/> Cargando run…</div></div>
  </div>`,
};

// Launch -------------------------------------------------------------------------------
export const LaunchView = {
  components: { CheckList, Command, Icon, StatusPill },
  setup() {
    const entries = ref([]);
    const form = reactive({ entry: null, path: null, host: null, args: '' });
    const preview = ref(null);
    const previewError = ref(null);
    const checks = ref(null);
    const checking = ref(false);
    const launching = ref(false);
    onMounted(async () => {
      entries.value = await api('/entries');
      if (entries.value.length) form.entry = entries.value[0].id;
    });
    const entry = computed(() => entries.value.find((e) => e.id === form.entry));
    const hosts = computed(() => Object.values(state.hosts));
    const fixedHost = computed(() => (entry.value && entry.value.kind === 'campaign' && preview.value ? preview.value.host_id : null));
    const refreshPreview = async () => {
      preview.value = null;
      previewError.value = null;
      if (!form.entry || !form.path) return;
      try {
        const query = new URLSearchParams({ entry: form.entry, path: form.path });
        if (form.host && entry.value.kind === 'script') query.set('host', form.host);
        preview.value = await api(`/preview?${query}`);
        if (fixedHost.value) form.host = fixedHost.value;
      } catch (error) {
        previewError.value = error.message;
      }
    };
    watch(() => form.entry, () => { form.path = null; preview.value = null; checks.value = null; });
    watch(() => [form.path, form.entry], refreshPreview);
    const runCheck = async () => {
      if (!form.host) return;
      checking.value = true;
      checks.value = null;
      try {
        checks.value = await action(`/hosts/${form.host}/preflight`);
      } catch {
        checks.value = null;
      } finally {
        checking.value = false;
      }
    };
    watch(() => form.host, () => { checks.value = null; if (form.host) runCheck(); if (entry.value && entry.value.kind === 'script') refreshPreview(); });
    const args = computed(() => splitArgs(form.args));
    const cli = computed(() => {
      if (!entry.value || !form.path) return '';
      if (entry.value.kind === 'campaign') return `just run ${form.path}`;
      const plain = (a) => /^[\w@%+=:,./-]+$/.test(a);
      const host = form.host || 'local';
      if (args.value.every(plain)) {
        return `just launch ${form.path} ${host}${args.value.map((a) => ` ${a}`).join('')}`;
      }
      // just re-joins variadic arguments with spaces; call the CLI directly to keep quoting.
      const quoted = args.value.map((a) => (plain(a) ? a : `'${a.replace(/'/g, "''")}'`)).join(' ');
      return `uv run --locked python -m pydelling.monitor launch ${form.entry} ${form.path} --host ${host} -- ${quoted}`;
    });
    const canLaunch = computed(() => form.entry && form.path && form.host && checks.value && checks.value.ok && !launching.value);
    const launch = async () => {
      launching.value = true;
      try {
        const result = await action('/launch', { entry: form.entry, path: form.path, host: form.host, args: args.value }, 'Lanzamiento en marcha');
        window.location.hash = `#/runs/${result.run_id}`;
      } catch {
        // toast shown
      } finally {
        launching.value = false;
      }
    };
    const hostState = (h) => HOST_STATE[h.stream_state] || HOST_STATE.offline;
    return {
      entries, form, entry, hosts, preview, previewError, fixedHost, checks, checking, runCheck, cli,
      canLaunch, launch, launching, hostState, fmtInt, args,
    };
  },
  template: `<div class="page">
    <div class="page-head"><div><h1 class="page-title">Nuevo lanzamiento</h1>
      <p class="page-sub">Elige qué ejecutar y dónde. Se comprueba el acceso antes de desplegar nada.</p></div></div>
    <div class="steps">
      <div class="card"><div class="card-head"><span class="step-num">1</span><h2 class="card-title">Qué quieres lanzar</h2>
        <div class="segmented" style="margin-left:auto" v-if="entries.length > 1">
          <button v-for="e in entries" :key="e.id" :class="{on: form.entry === e.id}" @click="form.entry = e.id">{{ e.label }}</button></div></div>
        <div class="card-body">
          <p v-if="!entries.length" class="muted">Este proyecto no declara entradas en <code>[tool.pydelling.monitor.entries]</code>.</p>
          <div class="choice-grid" v-if="entry">
            <button v-for="p in entry.paths" :key="p" type="button" class="choice" :class="{on: form.path === p}" @click="form.path = p" :aria-pressed="form.path === p">
              <Icon :name="entry.kind === 'campaign' ? 'layers' : 'terminal'"/><span class="mono ellipsis">{{ p }}</span></button>
          </div>
          <p v-if="entry && !entry.paths.length" class="muted">No hay ficheros que coincidan con esta entrada.</p>
          <div v-if="entry && entry.kind === 'script'" style="margin-top:12px;display:grid;gap:6px;max-width:560px">
            <label for="args" class="muted" style="font-size:12.5px">Argumentos del script</label>
            <input id="args" class="input mono" v-model="form.args" placeholder="--casos 10 --semilla 42">
          </div>
          <div v-if="previewError" class="error-banner" style="margin-top:12px"><Icon name="alert"/><div>{{ previewError }}</div></div>
          <dl v-if="preview" class="preview-box" style="margin:14px 0 0">
            <dt>Nombre</dt><dd class="mono">{{ preview.name }}</dd>
            <dt>Host</dt><dd>{{ preview.host_id }}<span v-if="fixedHost" class="faint"> (definido en el YAML)</span></dd>
            <dt>Carpeta en el host</dt><dd class="mono">{{ preview.remote_folder }}</dd>
            <dt>Carpeta local</dt><dd class="mono">{{ preview.local_folder }}</dd>
            <template v-if="preview.study_count"><dt>Estudios</dt><dd>{{ fmtInt(preview.study_count) }}<span v-if="preview.training_count != null" class="faint"> ({{ fmtInt(preview.training_count) }} de entrenamiento)</span></dd></template>
            <template v-if="preview.assumptions && preview.assumptions.length"><dt>Hipótesis</dt><dd>{{ preview.assumptions.join(', ') }}</dd></template>
          </dl>
        </div></div>
      <div class="card"><div class="card-head"><span class="step-num">2</span><h2 class="card-title">Dónde</h2></div>
        <div class="card-body"><div class="choice-grid">
          <button v-for="h in hosts" :key="h.id" type="button" class="choice" :class="{on: form.host === h.id}"
            :disabled="!!fixedHost && fixedHost !== h.id" @click="form.host = h.id" :aria-pressed="form.host === h.id">
            <Icon :name="h.transport === 'local' ? 'laptop' : 'server'"/>
            <span style="min-width:0"><div style="font-weight:600" class="ellipsis">{{ h.label || h.id }}</div>
              <div class="faint mono ellipsis" style="font-size:12px">{{ h.ssh || h.root }}</div>
              <div style="margin-top:6px"><StatusPill :status="h.stream_state" kind="host"/></div></span>
          </button></div></div></div>
      <div class="card"><div class="card-head"><span class="step-num">3</span><h2 class="card-title">Comprobación de acceso</h2>
        <button class="btn sm" style="margin-left:auto" :disabled="!form.host || checking" @click="runCheck"><Icon name="refresh" size="sm" :spin="checking"/>Repetir</button></div>
        <div class="card-body">
          <p v-if="!form.host" class="muted">Elige un host para comprobar SSH, Python, uv, disco, PFLOTRAN y la base de datos.</p>
          <p v-else-if="checking" class="muted"><Icon name="loader" spin size="sm"/> Comprobando {{ form.host }}…</p>
          <template v-if="checks">
            <CheckList :checks="checks.checks"/>
            <div v-for="c in checks.checks.filter(x => x.hint)" :key="c.id + 'hint'" class="hint">{{ c.hint.split('\`')[0] }}
              <Command :command="'just ssh-key-install ' + form.host"/><Command :command="'just connect ' + form.host"/></div>
          </template>
        </div></div>
      <div class="card"><div class="card-body" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap">
        <button class="btn primary" :disabled="!canLaunch" @click="launch"><Icon :name="launching ? 'loader' : 'rocket'" :spin="launching" size="sm"/>Lanzar</button>
        <span class="muted" v-if="!canLaunch && form.path && form.host && checks && !checks.ok">Resuelve los fallos de acceso antes de lanzar.</span>
        <div v-if="cli" style="flex:1;min-width:260px"><div class="faint" style="font-size:12px">Equivalente en terminal</div><Command :command="cli"/></div>
      </div></div>
    </div></div>`,
};

// Hosts --------------------------------------------------------------------------------
export const HostsView = {
  components: { CheckList, Command, HostMeter, Icon, StatusPill },
  setup() {
    const hosts = computed(() => Object.values(state.hosts));
    const checks = reactive({});
    const checking = reactive({});
    const check = async (id) => {
      checking[id] = true;
      try {
        checks[id] = await action(`/hosts/${id}/preflight`);
      } catch {
        delete checks[id];
      } finally {
        checking[id] = false;
      }
    };
    const reconnect = (id) => action(`/hosts/${id}/reconnect`, {}, 'Reconectando…').catch(() => {});
    const needsAuth = (h) => h.stream_state === 'auth_required';
    return { hosts, checks, checking, check, reconnect, needsAuth, fmtBytes, fmtNumber, fmtAgo, state };
  },
  template: `<div class="page">
    <div class="page-head"><div><h1 class="page-title">Hosts</h1>
      <p class="page-sub">Equipos donde se ejecutan los runs. La conexión en vivo usa SSH sin contraseña (BatchMode).</p></div></div>
    <div class="choice-grid" style="grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap:16px">
      <div v-for="h in hosts" :key="h.id" class="card">
        <div class="card-head"><Icon :name="h.transport === 'local' ? 'laptop' : 'server'" size="lg"/>
          <div style="min-width:0"><h2 class="card-title ellipsis">{{ h.label || h.id }}</h2><div class="faint mono ellipsis" style="font-size:12px">{{ h.ssh || 'local' }}</div></div>
          <span style="margin-left:auto"><StatusPill :status="h.stream_state" kind="host"/></span></div>
        <div class="card-body" style="display:grid;gap:12px">
          <div v-if="h.stream_error && h.stream_state !== 'connected'" class="error-banner" :class="needsAuth(h) ? 'tone-warning' : ''"><Icon name="alert"/><div class="mono" style="font-size:12px">{{ h.stream_error }}</div></div>
          <div v-if="needsAuth(h)" class="hint">El monitor no pide contraseñas. Instala tu clave pública una vez (te pedirá la contraseña en tu terminal):
            <Command :command="'just ssh-key-install ' + h.id"/>
            <div style="margin-top:8px">En macOS/Linux también puedes abrir una sesión compartida que el monitor reutiliza:</div>
            <Command :command="'just connect ' + h.id"/></div>
          <div v-if="h.heartbeat" class="stats">
            <div><div class="stat-label">CPUs</div><div class="stat-value">{{ h.heartbeat.cpus }}</div></div>
            <div><div class="stat-label">Carga (1 min)</div><div class="stat-value">{{ h.heartbeat.load ? fmtNumber(h.heartbeat.load[0], 2) : '—' }}</div></div>
            <div><div class="stat-label">Disco libre</div><div class="stat-value">{{ fmtBytes(h.heartbeat.disk_free) }}</div></div>
            <div><div class="stat-label">Latido</div><div class="stat-value">{{ fmtAgo(h.heartbeat.ts, state.now) }}</div></div>
          </div>
          <HostMeter :heartbeat="h.heartbeat"/>
          <dl class="preview-box">
            <dt>Carpeta de campañas</dt><dd class="mono">{{ h.campaigns_root }}</dd>
            <dt>uv</dt><dd class="mono">{{ h.uv }}</dd>
            <template v-if="h.executable"><dt>PFLOTRAN</dt><dd class="mono">{{ h.executable }}</dd></template>
            <template v-if="h.database"><dt>Base de datos</dt><dd class="mono">{{ h.database }}</dd></template>
            <template v-if="h.hello"><dt>Sistema</dt><dd>{{ h.hello.hostname }} · Python {{ h.hello.python }} · {{ h.hello.platform }}</dd></template>
          </dl>
          <div style="display:flex;gap:8px">
            <button class="btn" :disabled="checking[h.id]" @click="check(h.id)"><Icon name="shield" size="sm" :spin="checking[h.id]"/>Comprobar acceso</button>
            <button class="btn ghost" @click="reconnect(h.id)"><Icon name="refresh" size="sm"/>Reconectar</button>
          </div>
          <CheckList v-if="checks[h.id]" :checks="checks[h.id].checks"/>
        </div></div>
    </div></div>`,
};

export const AuthView = {
  components: { Command, Icon },
  template: `<div class="page" style="max-width:640px;margin-top:10vh">
    <div class="card"><div class="empty">
      <div class="empty-icon"><Icon name="key" size="lg"/></div>
      <h3>Abre el enlace del monitor</h3>
      <p>Por seguridad, el dashboard solo acepta el enlace con token que imprime el servidor al arrancar. Si lo reiniciaste, vuelve a abrir el enlace nuevo.</p>
      <Command command="just ui"/>
    </div></div></div>`,
};

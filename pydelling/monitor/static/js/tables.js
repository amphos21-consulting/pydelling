// Downloaded tables (CSV, parquet) of a run, shown page by page (the server never sends a whole file).
import { computed, reactive, ref, watch } from '../vendor/vue.esm-browser.prod.js';
import { api } from './api.js';
import { Icon } from './components.js';
import { fmtBytes, fmtInt } from './format.js';

const PAGE = 100;
const NUMBER = /^-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/;

export const TablePanel = {
  components: { Icon },
  props: { runId: String, refresh: { type: [String, Number], default: '' } },
  setup(props) {
    const files = ref([]);
    const page = reactive({ path: null, query: '', offset: 0, data: null, loading: false, error: '' });
    let timer = null;

    const loadFiles = async () => {
      try {
        files.value = (await api(`/runs/${props.runId}/tables`)).tables;
      } catch {
        files.value = [];
      }
      if (!files.value.some((f) => f.path === page.path)) {
        page.path = files.value.length ? files.value[0].path : null;
        page.offset = 0;
      }
    };
    const loadPage = async () => {
      if (!page.path) { page.data = null; return; }
      page.loading = true;
      page.error = '';
      try {
        const query = new URLSearchParams({ path: page.path, offset: page.offset, limit: PAGE });
        if (page.query) query.set('q', page.query);
        page.data = await api(`/runs/${props.runId}/table?${query}`);
      } catch (error) {
        page.error = error.message;
        page.data = null;
      } finally {
        page.loading = false;
      }
    };
    watch(() => [props.runId, props.refresh], async () => { await loadFiles(); loadPage(); }, { immediate: true });
    watch(() => page.path, () => { page.offset = 0; page.query = ''; loadPage(); });
    watch(() => page.query, () => {
      clearTimeout(timer);
      timer = setTimeout(() => { page.offset = 0; loadPage(); }, 300);
    });
    const move = (rows) => {
      const total = page.data ? page.data.total : 0;
      page.offset = Math.max(0, Math.min(page.offset + rows, Math.max(0, total - 1)));
      loadPage();
    };
    // A column is numeric if every non-empty cell of the page is (right-aligned, tabular).
    const numeric = computed(() => {
      const data = page.data;
      if (!data) return [];
      return data.columns.map((_, i) => {
        const cells = data.rows.map((r) => r[i]).filter((v) => v !== undefined && v !== '');
        return cells.length > 0 && cells.every((v) => NUMBER.test(v));
      });
    });
    const range = computed(() => {
      const d = page.data;
      if (!d || !d.total) return '0 filas';
      return `${fmtInt(d.offset + 1)}–${fmtInt(d.offset + d.rows.length)} de ${fmtInt(d.total)}`;
    });
    return { files, page, move, numeric, range, fmtBytes, PAGE };
  },
  template: `<div class="card" v-if="files.length">
    <div class="card-head"><h2 class="card-title">Tablas</h2>
      <span class="muted" style="margin-left:8px;font-size:12.5px">Tablas descargadas de este run (CSV y parquet)</span></div>
    <div class="card-body" style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
      <select class="select mono" v-model="page.path" aria-label="Tabla" style="max-width:100%">
        <option v-for="f in files" :key="f.path" :value="f.path">{{ f.path }} · {{ fmtBytes(f.size) }}</option>
      </select>
      <div class="search" style="flex:1;min-width:180px;position:relative">
        <Icon name="search" size="sm"/>
        <input class="input" v-model="page.query" placeholder="Filtrar filas (texto en cualquier celda)" aria-label="Filtrar filas">
      </div>
    </div>
    <div v-if="page.error" class="error-banner" style="margin:0 16px 12px"><Icon name="alert"/><div>{{ page.error }}</div></div>
    <div class="table-wrap" v-if="page.data" :style="{opacity: page.loading ? 0.6 : 1}">
      <table class="data plain">
        <thead><tr><th class="num" style="cursor:default">#</th>
          <th v-for="(c, i) in page.data.columns" :key="c + i" :class="{num: numeric[i]}" style="cursor:default">{{ c }}</th></tr></thead>
        <tbody>
          <tr v-for="(row, r) in page.data.rows" :key="page.data.offset + r">
            <td class="num faint">{{ page.data.offset + r + 1 }}</td>
            <td v-for="(c, i) in page.data.columns" :key="i" :class="{num: numeric[i], mono: numeric[i]}">{{ row[i] }}</td>
          </tr>
          <tr v-if="!page.data.rows.length"><td :colspan="page.data.columns.length + 1" class="muted">{{ page.query ? 'Ninguna fila coincide.' : 'La tabla no tiene filas.' }}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="card-body" style="display:flex;gap:8px;align-items:center" v-if="page.data">
      <span class="muted tabular" style="font-size:12.5px">{{ range }}<template v-if="page.query"> (filtradas)</template></span>
      <span style="margin-left:auto;display:flex;gap:6px">
        <button class="btn sm" :disabled="page.loading || page.offset === 0" @click="move(-PAGE)"><Icon name="back" size="sm"/>Anterior</button>
        <button class="btn sm" :disabled="page.loading || page.offset + PAGE >= page.data.total" @click="move(PAGE)">Siguiente<Icon name="chevron" size="sm"/></button>
      </span>
    </div>
  </div>`,
};

// pydelling monitor — app shell, hash router and theme.
import { computed, createApp, onBeforeUnmount, onMounted, ref } from './vendor/vue.esm-browser.prod.js';
import { Icon, Tooltip } from './js/components.js';
import { CleanupDialog } from './js/cleanup.js';
import { ACTIVE } from './js/format.js';
import { bootstrap, state } from './js/store.js';
import { AuthView, HostsView, LaunchView, RunView, RunsView } from './js/views.js';

const THEME_KEY = 'pydelling-monitor-theme';

function readTheme() {
  try {
    return window.localStorage.getItem(THEME_KEY) || 'auto';
  } catch {
    return 'auto';
  }
}

function applyTheme(theme) {
  if (theme === 'auto') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // per-viewer convenience only
  }
}

function parseRoute() {
  const hash = window.location.hash.replace(/^#/, '') || '/runs';
  const run = hash.match(/^\/runs\/([0-9a-f]+)/);
  if (run) return { name: 'run', id: run[1] };
  if (hash.startsWith('/launch')) return { name: 'launch' };
  if (hash.startsWith('/hosts')) return { name: 'hosts' };
  return { name: 'runs' };
}

const App = {
  components: { CleanupDialog, AuthView, HostsView, Icon, LaunchView, RunView, RunsView, Tooltip },
  setup() {
    const route = ref(parseRoute());
    const theme = ref(readTheme());
    const onHash = () => {
      if (/token=/.test(window.location.hash)) {
        bootstrap(); // a fresh link pasted into an open tab
        return;
      }
      route.value = parseRoute();
      window.scrollTo({ top: 0 });
    };
    onMounted(() => {
      window.addEventListener('hashchange', onHash);
      applyTheme(theme.value);
      bootstrap();
    });
    onBeforeUnmount(() => window.removeEventListener('hashchange', onHash));
    const cycleTheme = () => {
      theme.value = { auto: 'light', light: 'dark', dark: 'auto' }[theme.value];
      applyTheme(theme.value);
    };
    const themeLabel = computed(() => ({ auto: 'Tema: sistema', light: 'Tema: claro', dark: 'Tema: oscuro' }[theme.value]));
    const activeCount = computed(() => Object.values(state.runs).filter((r) => ACTIVE.includes(r.status)).length);
    const connection = computed(() => ({
      live: { label: 'En vivo', cls: 'on' },
      offline: { label: 'Reconectando…', cls: 'off' },
      connecting: { label: 'Conectando…', cls: '' },
    }[state.connection]));
    return { route, state, theme, themeLabel, cycleTheme, activeCount, connection };
  },
  template: `
  <div v-if="state.phase === 'auth'"><AuthView/></div>
  <div v-else class="shell">
    <nav class="sidebar" aria-label="Navegación principal">
      <div class="brand"><div class="brand-mark"><Icon name="activity"/></div>
        <div class="brand-text"><div class="brand-name">pydelling</div><div class="brand-sub">Monitor de runs</div></div></div>
      <a class="nav-link" :class="{active: route.name === 'runs' || route.name === 'run'}" href="#/runs"><Icon name="layers"/><span>Runs</span>
        <span v-if="activeCount" class="count">{{ activeCount }}</span></a>
      <a class="nav-link" :class="{active: route.name === 'launch'}" href="#/launch"><Icon name="rocket"/><span>Lanzar</span></a>
      <a class="nav-link" :class="{active: route.name === 'hosts'}" href="#/hosts"><Icon name="server"/><span>Hosts</span></a>
      <div class="sidebar-foot">
        <span class="live" role="status" aria-live="polite"><span class="live-dot" :class="connection.cls"></span><span class="live-label">{{ connection.label }}</span></span>
        <button class="btn ghost sm" @click="cycleTheme" :aria-label="themeLabel" :title="themeLabel">
          <Icon :name="theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'circle'" size="sm"/><span class="live-label">{{ themeLabel }}</span></button>
      </div>
    </nav>
    <main class="main">
      <div v-if="state.phase === 'loading'" class="page"><p class="muted"><Icon name="loader" spin size="sm"/> Cargando…</p></div>
      <div v-else-if="state.phase === 'error'" class="page"><div class="error-banner"><Icon name="alert"/><div>{{ state.error }}</div></div></div>
      <template v-else>
        <RunsView v-if="route.name === 'runs'"/>
        <RunView v-else-if="route.name === 'run'" :id="route.id" :key="route.id"/>
        <LaunchView v-else-if="route.name === 'launch'"/>
        <HostsView v-else-if="route.name === 'hosts'"/>
      </template>
    </main>
  </div>
  <Tooltip/>
  <CleanupDialog/>
  <div v-if="state.toast" class="toast" role="status" :class="'tone-' + state.toast.tone">
    <Icon :name="state.toast.tone === 'critical' ? 'alert' : 'check'"/><span>{{ state.toast.message }}</span></div>`,
};

createApp(App).mount('#app');

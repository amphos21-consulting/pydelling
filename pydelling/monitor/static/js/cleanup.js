import { computed, ref, watch } from '../vendor/vue.esm-browser.prod.js';
import { action, removeRuns, toast } from './store.js';

const request = ref(null);

export const DeleteHistory = {
  props: { runId: String, disabled: Boolean },
  setup(props) {
    return { open: () => { request.value = { runId: props.runId }; } };
  },
  template: `<button class="btn danger" :disabled="disabled" @click="open">{{ runId ? 'Eliminar run' : 'Limpiar historial' }}</button>`,
};

// Lives in the app shell so SSE updates and route changes cannot dismiss the result.
export const CleanupDialog = {
  setup() {
    const runId = computed(() => request.value?.runId);
    const dialog = ref(null);
    const files = ref(false);
    const busy = ref(false);
    const error = ref('');
    const completed = ref(null);
    const close = () => {
      dialog.value.close();
      if (completed.value && runId.value) window.location.hash = '#/runs';
    };
    watch(request, () => { files.value = false; error.value = ''; completed.value = null; dialog.value.showModal(); });
    const submit = async () => {
      busy.value = true;
      error.value = '';
      try {
        const path = runId.value ? `/runs/${runId.value}/delete` : '/history/clear';
        const result = await action(path, { files: files.value });
        completed.value = result;
        removeRuns(result.deleted_runs);
        toast(`${result.deleted_runs.length} runs eliminados. Los runs activos se conservan.`, 'good');
        if (!result.skipped_folders?.length) close();
      } catch (e) {
        error.value = e.message;
      } finally {
        busy.value = false;
      }
    };
    return { dialog, files, busy, error, completed, close, runId, submit };
  },
  template: `<dialog ref="dialog" class="card cleanup-dialog" aria-label="Eliminar historial" @cancel="$event.preventDefault(); !busy && close()">
      <div class="card-head"><h2 class="card-title">{{ runId ? 'Eliminar este run' : 'Limpiar todo el historial' }}</h2></div>
      <div class="card-body" style="display:grid;gap:16px">
        <template v-if="!completed">
        <p>Se borrarán {{ runId ? 'este run y sus' : 'los runs inactivos de todos los hosts y sus' }} estudios, eventos y logs guardados en la base de datos. Esta acción no se puede deshacer.</p>
        <label style="display:flex;gap:10px;align-items:start"><input type="checkbox" v-model="files" :disabled="busy">
          <span>Eliminar también las carpetas de resultados locales y remotas</span></label>
        <p class="muted">{{ files ? 'Se borrarán permanentemente los archivos de esos runs. Todos los hosts afectados deben estar accesibles. Si ocurre un fallo, se conserva el historial para reintentar; algunas carpetas podrían haberse borrado.' : 'Los archivos de simulación se conservarán. Los runs eliminados no volverán a importarse automáticamente.' }}</p>
        <p class="muted">Los runs activos se conservan junto con sus archivos.<template v-if="!runId"> La limpieza abarca el historial inactivo de todos los hosts, sin aplicar los filtros de la lista.</template></p>
        <p class="muted" v-if="files">Las carpetas fuera de las ubicaciones permitidas, reservadas o enlazadas se conservarán y se indicarán al terminar.</p>
        </template>
        <div v-if="completed" role="status">
          <p>{{ completed.deleted_runs.length }} runs eliminados. Los runs activos se conservan.</p>
          <p>Se han conservado estas carpetas:</p>
          <ul><li v-for="item in completed.skipped_folders" :key="item.host_id + ':' + item.folder" style="overflow-wrap:anywhere">
            <strong>{{ item.host_id }}</strong>: {{ item.folder }} — {{ item.reason }}
          </li></ul>
        </div>
        <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
        <div class="page-actions"><button class="btn" autofocus :disabled="busy" @click="close">{{ completed ? 'Cerrar' : 'Volver' }}</button>
          <button v-if="!completed" class="btn danger" :disabled="busy" @click="submit">{{ busy ? 'Eliminando…' : files ? 'Eliminar historial y archivos' : 'Eliminar solo historial' }}</button></div>
      </div>
    </dialog>`,
};

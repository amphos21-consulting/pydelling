import { ref } from '../vendor/vue.esm-browser.prod.js';
import { action, removeRuns, toast } from './store.js';

export const DeleteHistory = {
  props: { runId: String, disabled: Boolean },
  setup(props) {
    const dialog = ref(null);
    const files = ref(false);
    const busy = ref(false);
    const error = ref('');
    const open = () => { files.value = false; error.value = ''; dialog.value.showModal(); };
    const submit = async () => {
      busy.value = true;
      error.value = '';
      try {
        const path = props.runId ? `/runs/${props.runId}/delete` : '/history/clear';
        const result = await action(path, { files: files.value });
        removeRuns(result.deleted_runs);
        toast(`${result.deleted_runs.length} runs eliminados. Los runs activos se conservan.`, 'good');
        if (dialog.value) dialog.value.close();
        if (props.runId) window.location.hash = '#/runs';
      } catch (e) {
        error.value = e.message;
      } finally {
        busy.value = false;
      }
    };
    return { dialog, files, busy, error, open, submit };
  },
  template: `<button class="btn danger" :disabled="disabled" @click="open">{{ runId ? 'Eliminar run' : 'Limpiar historial' }}</button>
    <dialog ref="dialog" class="card cleanup-dialog" aria-label="Eliminar historial" @cancel="busy && $event.preventDefault()">
      <div class="card-head"><h2 class="card-title">{{ runId ? 'Eliminar este run' : 'Limpiar todo el historial' }}</h2></div>
      <div class="card-body" style="display:grid;gap:16px">
        <p>Se borrarán {{ runId ? 'este run y sus' : 'los runs inactivos de todos los hosts y sus' }} estudios, eventos y logs guardados en la base de datos. Esta acción no se puede deshacer.</p>
        <label style="display:flex;gap:10px;align-items:start"><input type="checkbox" v-model="files" :disabled="busy">
          <span>Eliminar también las carpetas de resultados locales y remotas</span></label>
        <p class="muted">{{ files ? 'Se borrarán permanentemente los archivos de esos runs. Todos los hosts afectados deben estar accesibles. Si ocurre un fallo, se conserva el historial para reintentar; algunas carpetas podrían haberse borrado.' : 'Los archivos de simulación se conservarán. Los runs eliminados no volverán a importarse automáticamente.' }}</p>
        <p class="muted">Los runs activos se conservan junto con sus archivos.<template v-if="!runId"> La limpieza abarca el historial inactivo de todos los hosts, sin aplicar los filtros de la lista.</template></p>
        <p v-if="error" class="error-banner" role="alert">{{ error }}</p>
        <div class="page-actions"><button class="btn" autofocus :disabled="busy" @click="dialog.close()">Volver</button>
          <button class="btn danger" :disabled="busy" @click="submit">{{ busy ? 'Eliminando…' : files ? 'Eliminar historial y archivos' : 'Eliminar solo historial' }}</button></div>
      </div>
    </dialog>`,
};

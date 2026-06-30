import logging
from typing import TYPE_CHECKING
import threading
from pathlib import Path
import time, re
from tqdm import tqdm
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..comsol_manager import ComsolManager
    from .comsol_component import ComsolComponent

class ComsolStudy:
    """Wrapper around a COMSOL study API object.

    Category: COMSOL management.
    Tags: comsol, study, run, parametric-sweep, progress.
    Use when: an MCP agent needs to run COMSOL studies, watch progress logs, or
        perform parameter sweeps through pydelling.
    """

    def __init__(self,
                 comsol: 'ComsolManager.ComsolModel',
                 tag: str):
        """Load a COMSOL study by tag.

        Category: COMSOL management.
        Tags: comsol, study, initialization.
        Use when: attaching pydelling helpers to an existing COMSOL study.
        Parameters:
            comsol (ComsolModel): The ComsolModel object from ComsolManager
            tag (str): The tag of the study
        Side effects:
            Registers the study wrapper under the model when needed.
        """
        self.comsol = comsol
        self.manager = self.comsol.manager
        self.model = self.comsol.model
        self.tag = tag
        self._api = self.model.study(self.tag)
        self.childs = []
    
        if self.tag not in [study.tag for study in self.comsol.studies]:
            self.comsol.studies.append(self)
            self.comsol.childs.append(self)
        logger.info(f"Study {self.tag} loaded.")
        
    def apply(self):
        """Placeholder for applying study changes.

        Category: COMSOL management.
        Tags: comsol, study, apply, extension-point.
        Use when: extending study wrappers with explicit apply behavior.
        """
        pass
        
    def run(self, save = True, convergence_plot: bool = True):
        """Run the COMSOL study and monitor progress.

        Category: COMSOL management.
        Tags: comsol, study, run, progress, convergence.
        Use when: executing a COMSOL study from pydelling while optionally
            saving the model and plotting convergence.
        Parameters:
            save (bool): If True, saves the COMSOL model after running the study. Default is True.
            convergence_plot (bool): If True, shows a convergence plot during the run. Default is True.
        Side effects:
            Starts the COMSOL run in a thread, reads a temporary progress log,
            may show a convergence plot, may save the model, and cleans logs.
        """
            
        logfile = Path(f"./logs/temp_{Path(self.comsol.file_path).name}_{int(time.time())}.log")
        if logfile.exists():
            logfile.unlink()
        
        from com.comsol.model.util import ModelUtil
        ModelUtil.showProgress(str(logfile))

        def _run(study):
            study._api.run()
        
        # Read COMSOL log file to show progress bar
        self.thread = threading.Thread(target=_run, args=([self]))
        
        self.thread.start()

        pat = re.compile(r"Current Progress:\s+(\d+)\s*%")
        # Capture: integer index, scientific/decimal float, decimal/float
        float_re = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        delta_pat = re.compile(rf"^\s*(\d+)\s+({float_re})\s+({float_re})")

        label = self.tag

        # Prepare interactive plotting (best-effort; disabled if backend unavailable)
        if convergence_plot:
            do_plot = True
            try:
                plt.ion()
                fig, ax = plt.subplots()
                line_plot, = ax.plot([], [], '-')
                ax.set_xlabel('Time step')
                ax.set_ylabel('Reciprocal of step size')
                ax.set_title(f'Convergence - {label}')
                ax.set_yscale('log')
            except Exception:
                do_plot = False
        else:
            do_plot = False
            
        with tqdm(total=100, desc=f"     Running {Path(self.comsol.file_path).name}/{label}", unit="%") as pbar:
            last = 0
            step = []
            convergence = []

            while self.thread.is_alive() or logfile.exists() or last < 100:
                if logfile.exists():
                    with logfile.open(encoding="utf-8") as f:
                        for line in f:
                            m = pat.search(line)
                            delta_m = delta_pat.search(line)
                            if delta_m:
                                if step[-1] < int(delta_m.group(1)) if len(step) > 1 else True:
                                    step.append(int(delta_m.group(1)))
                                    convergence.append(1/float(delta_m.group(3)))
                                    if do_plot and len(step) > 1:
                                        try:
                                            line_plot.set_data(step, convergence)
                                            ax.relim()
                                            ax.autoscale_view()
                                            fig.canvas.draw()
                                            plt.pause(0.01)
                                        except Exception:
                                            # disable plotting if any runtime error occurs
                                            do_plot = False
                                
                            if m:
                                pct = int(m.group(1))
                                if pct > last:
                                    pbar.update(pct - last)
                                    last = pct              
                                if pct == last:
                                    pbar.refresh()
                if not self.thread.is_alive(): break
                if not self.thread.is_alive() and last >= 100:
                    break
                time.sleep(0.1)
        
        if save: self.comsol.save()

        self.manager._clean_logs()
        
    def run_parametric_sweep(self,
                             param_type: str,
                             name: str,
                             values_list: list,
                             var_tag: str | None = None,
                             ):
        """Run the study repeatedly while sweeping one parameter or variable.

        Category: COMSOL management.
        Tags: comsol, study, parametric-sweep, parameters, variables.
        Use when: an MCP workflow needs a separate COMSOL output file for each
            value in a sweep.
        Parameters:
            param_type (str): Valid values are "parameter" or "variable".
            name (str): Name of the parameter/variable.
            values_list (list): A list with the values to change.
            var_tag (str): The tag of the variable collection if its a variable. Defaults to None.
        Raises:
            ValueError: If ``param_type`` is invalid or a variable sweep omits
            ``var_tag``.
        Side effects:
            Updates a parameter or variable, changes ``save_name`` for each run,
            runs the study, and restores the previous save name.
        """
        if param_type == "variable":
            if var_tag is None:
                raise ValueError('If param_type is "variable", var_tag must be provided.')
        elif param_type != "parameter": raise ValueError('param_type must be "parameter" or "variable"')

        old_save_name = self.comsol.save_name

        if param_type == "parameter":
            param = self.comsol.parameters()
            for i in tqdm(range(len(values_list)), "Running parametric sweep"):
                param.set_parameter(name, values_list[i])
                self.comsol.save_name = f"{Path(self.comsol.file_path).parent}/{Path(self.comsol.file_path).stem}_{name}_{values_list[i]}.mph"
                self.run()
        
        elif param_type == "variable":
            var = self.comsol.variables(var_tag)
            for i in tqdm(range(len(values_list)), "Running parametric sweep"):
                var.set_variable(name, values_list[i])
                self.comsol.save_name = f"{Path(self.comsol.file_path).parent}/{Path(self.comsol.file_path).stem}_{name}_{values_list[i]}.mph"
                self.run()
        
        self.comsol.save_name = old_save_name

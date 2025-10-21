import glob
import os
from typing import Dict, List, Tuple, Optional, Sequence
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import logging
from pathlib import Path
import re

logger = logging.getLogger(__name__)


class MassBalanceCheckPflotran:
    """
    Instantiate with a path or list of glob patterns pointing to PFLOTRAN mass-balance files.
    Use methods to process single files, summarize all files, plot heatmaps and save CSVs/figures.

    Example:
        checker = MassBalanceCheckPflotran("results/**/*.mass_balance", outdir="out")
        checker.summarize_all_files()    # prints & saves combined summary + heatmap
        checker.process_file("results/run1.mass_balance", save_csv=True)
    """

    def __init__(
        self,
        input_patterns: Sequence[str],
        outdir: Optional[str] = None,
        base_folder: Optional[str] = None,
    ) -> None:
        if isinstance(input_patterns, str):
            input_patterns = [input_patterns]
        self.input_patterns: List[str] = list(input_patterns)
        self.outdir = outdir or os.getcwd()
        os.makedirs(self.outdir, exist_ok=True)

        # Determine base_folder: use provided value or infer from input_patterns (strip glob chars)
        if base_folder:
            self.base_folder = os.path.abspath(base_folder)
        else:
            prefixes: List[str] = []
            for pat in self.input_patterns:
                if not pat:
                    continue
                m = re.search(r"[*?\[]", pat)
                cut = m.start() if m else len(pat)
                prefix = pat[:cut]
                if prefix:
                    prefixes.append(os.path.abspath(prefix))
            if prefixes:
                try:
                    self.base_folder = os.path.commonpath(prefixes)
                except Exception:
                    self.base_folder = prefixes[0]
            else:
                self.base_folder = os.getcwd()

    # ---- low level / utilities ----
    @staticmethod
    def read_pflotran_balance(path: str) -> pd.DataFrame:
        """
        Reads a file with CSV header (in quotes) and numeric data separated by spaces.
        """
        with open(path, "r", encoding="utf-8") as f:
            header_line = f.readline().strip()
        raw_cols = [c.strip().strip('"') for c in header_line.split(",")]
        df = pd.read_csv(path, skiprows=1, delim_whitespace=True, header=None, names=raw_cols, engine="python")
        # Normalize spaces in column names
        df.rename(columns={c: " ".join(c.split()) for c in df.columns}, inplace=True)
        return df

    @staticmethod
    def get_time_column(df: pd.DataFrame) -> str:
        """
        Returns the name of the time column, e.g. 'Time [h]', 'Time [y]', or 'Time [d]'.
        """
        for col in df.columns:
            if col.lower().startswith("time"):
                return col
        raise ValueError("No time column found (expected 'Time [h]', 'Time [y]', or 'Time [d]').")

    @staticmethod
    def find_species_columns(df: pd.DataFrame) -> Dict[str, Tuple[str, List[str]]]:
        """
        For each species X, find the 'Global X [mol]' column and all columns 'X [mol]' (not containing 'Region').
        Returns a dict: species -> (global_col, list of [mol] columns)
        """
        species_map: Dict[str, Tuple[str, List[str]]] = {}
        # Find all global columns
        for gcol in [c for c in df.columns if c.startswith("Global ") and c.endswith("[mol]")]:
            sp = gcol[len("Global "):].rsplit(" [mol]", 1)[0]
            # Find all [mol] columns for this species (excluding 'Region' and 'Global')
            flux_cols = [
                c for c in df.columns
                if sp in c and c.endswith("[mol]") and "Region" not in c and "Global" not in c
            ]
            species_map[sp] = (gcol, flux_cols)
        if not species_map:
            raise ValueError("No 'Global X [mol]' columns found.")
        return species_map

    @staticmethod
    def compute_mass_balance(df: pd.DataFrame, species_map: Dict[str, Tuple[str, List[str]]]) -> Dict[str, pd.DataFrame]:
        """
        For each species, compares the change in global amount to the sum of cumulative flux columns ([mol]).
        Returns a dict species -> timeseries DataFrame with residuals.
        """
        time_col = MassBalanceCheckPflotran.get_time_column(df)

        df = df.sort_values(time_col).reset_index(drop=True)
        t = df[time_col].to_numpy()
        dt_time = np.empty_like(t)
        dt_time[:] = np.nan
        if len(t) > 1:
            dt_time[1:] = np.diff(t)
            if np.any(dt_time[1:] <= 0):
                raise ValueError("Non-positive Δt detected in time column. Check the file.")

        eps = 1e-30
        results: Dict[str, pd.DataFrame] = {}

        for sp, (gcol, flux_cols) in species_map.items():
            M = df[gcol].to_numpy()
            # Sum all cumulative flux columns for this species
            flux_total = np.zeros_like(M)
            for fcol in flux_cols:
                flux_total += df[fcol].to_numpy()

            # Change in global amount (backward difference)
            dM = np.empty_like(M)
            dM[:] = np.nan
            if len(M) > 1:
                dM[1:] = M[1:] - M[:-1]

            # Change in cumulative flux (backward difference)
            dFlux = np.empty_like(flux_total)
            dFlux[:] = np.nan
            if len(flux_total) > 1:
                dFlux[1:] = flux_total[1:] - flux_total[:-1]

            # Residual: difference between change in global amount and net flux
            residual = dM - dFlux
            denom = np.maximum(np.maximum(np.abs(dM), np.abs(dFlux)), eps)
            residual_rel = residual / denom

            out = pd.DataFrame({
                time_col: t,
                f"dt_{time_col}": dt_time,
                f"{sp} Global [mol]": M,
                f"{sp} Total Flux [mol]": flux_total,
                f"{sp} ΔGlobal [mol]": dM,
                f"{sp} ΔFlux [mol]": dFlux,
                f"{sp} Residual [mol]": residual,
                f"{sp} Residual rel [-]": residual_rel,
            })
            results[sp] = out

        return results

    # ---- high level operations ----
    def expand_input_patterns(self) -> List[str]:
        files: List[str] = []
        for pattern in self.input_patterns:
            matched = sorted(glob.glob(pattern, recursive=True))
            if matched:
                files.extend(matched)
            elif os.path.isfile(pattern):
                files.append(pattern)
        return files

    def process_file(self, path: str) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
        """
        Process a single file: compute per-species timeseries and a summary DataFrame.
        Optionally saves CSVs and returns (per_species, summary).
        """
        print(f"\n==> File: {path}")
        df = self.read_pflotran_balance(path)
        species_map = self.find_species_columns(df)
        per_species = self.compute_mass_balance(df, species_map)
        summary = self.summarize_residuals(per_species)

        pd.set_option("display.float_format", lambda x: f"{x: .3e}")
        time_col = self.get_time_column(df)
        print(f"\nSummary by species (Δt = diff({time_col})):")
        print(summary.to_string(index=False))

        return per_species, summary

    def summarize_residuals(self, per_species: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Summarizes for each species:
        - ΔGlobal: change in global amount between last and first timestep
        - Final Flux: total flux at last timestep
        - Residual: ΔGlobal - Final Flux
        - Percent error: residual divided by throughput amount (initial global amount + |flux|)
        """
        rows = []
        eps = 1e-30
        for sp, dfsp in per_species.items():
            global_first = dfsp[f"{sp} Global [mol]"].iloc[0]
            global_last = dfsp[f"{sp} Global [mol]"].iloc[-1]
            delta_global = global_last - global_first
            final_flux = dfsp[f"{sp} Total Flux [mol]"].iloc[-1]
            residual = abs(delta_global - final_flux)
            denom = (abs(global_first) + abs(final_flux)) if (abs(global_first) + abs(final_flux)) > eps else eps
            percent_error = residual / denom * 100
            rows.append({
                "Species": sp,
                "ΔGlobal [mol]": delta_global,
                "Final Flux [mol]": final_flux,
                "Residual [mol]": residual,
                "Percent error [%]": percent_error,
            })
        return pd.DataFrame(rows).sort_values("Species").reset_index(drop=True)

    def summarize_all_files(self) -> pd.DataFrame:
        """
        Process all files matching input patterns. Saves combined CSV and produces a heatmap.
        Returns combined summary DataFrame.
        """
        files = self.expand_input_patterns()
        if not files:
            raise SystemExit("No files found. Adjust input_patterns in the MassBalanceCheckPflotran instance.")
        all_summaries = []
        for path in files:
            try:
                _, summary = self.process_file(path)
                # Add file identifier relative to base_folder (robust on Windows different drives)
                summary = summary.copy()
                try:
                    rel = os.path.relpath(path, self.base_folder)
                except ValueError:
                    # Happens on Windows when paths are on different drives (C: vs D:)
                    # Fallback to absolute path without the drive letter to keep the "File" column informative
                    abs_path = os.path.abspath(path)
                    drive, tail = os.path.splitdrive(abs_path)
                    rel = tail.lstrip(os.sep)
                summary["File"] = os.path.dirname(rel) or os.path.basename(path)
                all_summaries.append(summary)
            except Exception as e:
                logger.exception("Failed processing file %s: %s", path, e)

        combined = pd.concat(all_summaries, ignore_index=True) if all_summaries else pd.DataFrame()
        if not combined.empty:
            summary_path = os.path.join(self.outdir, "mass_balance_summary_all_files.csv")
            combined.to_csv(summary_path, index=False)
            print(f"Combined summary saved at: {summary_path}")
            print(combined.to_string(index=False))
            # produce matrix/heatmap
            self.summarize_errors_matrix(all_summaries)
        else:
            print("No summaries produced.")
        return combined

    def summarize_errors_matrix(self, all_summaries: List[pd.DataFrame]) -> None:
        """
        Creates a matrix summary: rows = files, columns = species, values = percent error,
        then plots and saves heatmap.
        """
        if not all_summaries:
            print("No summaries to create error matrix.")
            return
        combined = pd.concat(all_summaries, ignore_index=True)
        matrix = combined.pivot(index="File", columns="Species", values="Percent error [%]")

        # Build list of concrete path prefixes derived from input_patterns (strip glob chars)
        prefixes: List[str] = []
        for pat in self.input_patterns:
            if not pat:
                continue
            m = re.search(r"[*?\[]", pat)
            cut = m.start() if m else len(pat)
            prefix = pat[:cut]
            if prefix:
                prefixes.append(os.path.abspath(prefix).replace("\\", "/"))

        # Shorten y-axis labels by removing the configured base_folder and any input pattern prefixes
        try:
            base = Path(self.base_folder).resolve() if self.base_folder else None

            def _strip_label(label: str) -> str:
                if not label:
                    return label
                lab = str(label).replace("\\", "/")

                # Remove base folder if present
                if base:
                    base_norm = str(base).replace("\\", "/")
                    if os.name == "nt":
                        if lab.lower().startswith(base_norm.lower()):
                            lab = lab[len(base_norm):].lstrip("/\\")
                    else:
                        if lab.startswith(base_norm):
                            lab = lab[len(base_norm):].lstrip("/\\")

                # Remove any configured input pattern prefixes
                for pre in prefixes:
                    if not pre:
                        continue
                    if os.name == "nt":
                        if lab.lower().startswith(pre.lower()):
                            lab = lab[len(pre):].lstrip("/\\")
                            break
                    else:
                        if lab.startswith(pre):
                            lab = lab[len(pre):].lstrip("/\\")
                            break

                return lab.lstrip("/\\") or "."

            matrix.index = [_strip_label(i) for i in matrix.index]
        except Exception:
            # if anything goes wrong, fall back to the original labels
            pass

        self.plot_percent_error_matrix(matrix)

    def plot_percent_error_matrix(self, matrix: pd.DataFrame) -> None:
        """
        Plots a heatmap of the percent error matrix and saves the figure in outdir.
        """
        if matrix.empty:
            print("Empty matrix, nothing to plot.")
            return

        # Prepare matrix for log scale: replace non-positive values with NaN
        matrix_plot = matrix.copy()
        matrix_plot = matrix_plot.where(matrix_plot > 0, np.nan)

        # Enforce minimum vmin = 0.01 for the log scale
        vmin = 0.01
        vmax = np.nanmax(matrix_plot.values)
        if np.isnan(vmax) or vmax <= vmin:
            vmax = vmin * 10  # ensure vmax > vmin for LogNorm

        plt.figure(figsize=(max(8, 0.7 * len(matrix_plot.columns)), max(6, 0.25 * len(matrix_plot))))
        sns.heatmap(
            matrix_plot,
            annot=True,
            fmt=".2f",
            cmap="coolwarm",
            cbar_kws={'label': 'Percent error [%]'},
            norm=LogNorm(vmin=vmin, vmax=vmax),
            annot_kws={'size': 8}
        )
        plt.title("Mass Balance Percent Error Matrix")
        plt.ylabel("File")
        plt.xlabel("Species")
        plt.tight_layout()
        fig_path = os.path.join(self.outdir, "mass_balance_percent_error_matrix.png")
        plt.savefig(fig_path, dpi=200)
        #plt.show()
        plt.close()
        print(f"Percent error matrix figure saved at: {fig_path}")
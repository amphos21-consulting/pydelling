"""
Tools for checking PFLOTRAN mass-balance files.

This module provides utilities to read PFLOTRAN mass-balance outputs, identify
species-specific global and cumulative flux columns, compute residuals, and
summarize balance errors.

It also includes methods to process multiple files, save summary tables, and
generate heatmaps of percent error across files and species.


"""

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
    """Analyse PFLOTRAN mass-balance files and evaluate residuals.

    Category: postprocessing
    Tags: pflotran, mass-balance, residuals, species, heatmap
    Use when: scripts need to QA PFLOTRAN mass-balance files across one or more simulations.
    """

    def __init__(
        self,
        input_patterns: Sequence[str],
        outdir: Optional[str] = None,
        base_folder: Optional[str] = None,
    ) -> None:
        """Initialize mass-balance inputs and output location.

        Category: postprocessing
        Tags: pflotran, mass-balance, files, setup
        Use when: scripts need to configure file patterns and output folders for balance summaries.

        Returns:
            None: stores input patterns, output directory, and base-folder label root.
        """
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
        """Read a PFLOTRAN mass-balance file into a DataFrame.

        Category: reader
        Tags: pflotran, mass-balance, dataframe, parser
        Use when: scripts need quoted CSV headers with whitespace-delimited numeric rows parsed.

        Returns:
            pandas.DataFrame: parsed mass-balance table with normalized column spacing.
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
        """Return the time column name in a mass-balance DataFrame.

        Category: postprocessing
        Tags: pflotran, mass-balance, time, dataframe
        Use when: balance calculations need the timestep column regardless of unit.

        Returns:
            str: column name beginning with Time.
        """
        for col in df.columns:
            if col.lower().startswith("time"):
                return col
        raise ValueError("No time column found (expected 'Time [h]', 'Time [y]', or 'Time [d]').")

    @staticmethod
    def find_species_columns(df: pd.DataFrame) -> Dict[str, Tuple[str, List[str]]]:
        """Map species to global amount and cumulative flux columns.

        Category: postprocessing
        Tags: pflotran, mass-balance, species, columns
        Use when: residual calculations need to pair Global species amounts with flux columns.

        Returns:
            dict: species mapped to global column and flux column list.
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
        """Compute per-species mass-balance residual time series.

        Category: postprocessing
        Tags: pflotran, mass-balance, residuals, species
        Use when: scripts need ΔGlobal, ΔFlux, absolute residual, and relative residual by timestep.

        Returns:
            dict: species mapped to residual DataFrames.
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
        """Expand configured file paths and glob patterns.

        Category: postprocessing
        Tags: files, glob, pflotran, mass-balance
        Use when: batch processing needs the concrete mass-balance files to read.

        Returns:
            list: matched file paths.
        """
        files: List[str] = []
        for pattern in self.input_patterns:
            matched = sorted(glob.glob(pattern, recursive=True))
            if matched:
                files.extend(matched)
            elif os.path.isfile(pattern):
                files.append(pattern)
        return files

    def process_file(self, path: str) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
        """Process one PFLOTRAN mass-balance file.

        Category: postprocessing
        Tags: pflotran, mass-balance, summary, residuals
        Use when: scripts need both detailed per-species residuals and a summary table for one file.

        Returns:
            tuple: per-species residual DataFrames and summary DataFrame.
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
        """Summarize final mass-balance residuals by species.

        Category: postprocessing
        Tags: pflotran, mass-balance, summary, percent-error
        Use when: scripts need final residual and percent error per species.

        Returns:
            pandas.DataFrame: summary rows sorted by species.
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
        """Process all configured files and export combined summaries.

        Category: postprocessing
        Tags: pflotran, mass-balance, batch, heatmap, csv
        Use when: scripts need a cross-file mass-balance summary and percent-error heatmap.

        Returns:
            pandas.DataFrame: combined summary across all processed files.
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
        """Create a file-by-species percent-error matrix.

        Category: postprocessing
        Tags: pflotran, mass-balance, matrix, percent-error
        Use when: heatmap plotting needs a pivoted percent-error table.

        Returns:
            None: builds the matrix and delegates plotting.
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
        """Plot and save a mass-balance percent-error heatmap.

        Category: writer
        Tags: pflotran, mass-balance, heatmap, percent-error, plot
        Use when: scripts need a visual QA artifact for mass-balance errors by file and species.

        Returns:
            None: writes the heatmap PNG.
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

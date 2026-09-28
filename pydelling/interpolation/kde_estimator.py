"""
This class performs a KDE estimation on a given dataset and provides useful methods
to plot and manipulate the estimated distributions.


"""

import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.neighbors import KernelDensity

from pydelling.utils.decorators import set_run

logger = logging.getLogger(__name__)

class KdeEstimator:
    """Fit and sample kernel density estimates from tabular data.

    Category: interpolation
    Tags: kde, density-estimation, sampling, plotting, scikit-learn
    Usage: scripts need a fitted KDE model, sampled synthetic values, or distribution comparison plots.
    """
    is_run: bool
    kde_estimator: KernelDensity
    def __init__(self, data:pd.DataFrame=None, kernel='gaussian', bandwidth=1000, package='scikit'):
        """
        __init__ method.
        
        Args:
            data (pd.DataFrame): Description.
            kernel (Any): Description.
            bandwidth (Any): Description.
            package (Any): Description.
        """
        self.data = self._normalize_data(data) if data is not None else None
        self.kernel = kernel
        self.bandwidth = bandwidth
        self.package = package
        self.kde_estimator = None
        self.is_run = False

    @set_run
    def run(self, data: pd.DataFrame=None):
        """Fit the KDE model to the current or provided data.

        Category: interpolation
        Tags: kde, fit, density-estimation, scikit-learn
        Usage: scripts need a trained KernelDensity object before sampling or plotting.

        Returns:
            sklearn.neighbors.KernelDensity: fitted KDE estimator.
        """
        self.is_run = False
        self.kde_estimator = None
        if data is not None:
            self.data = self._normalize_data(data)
        if self.data is None or self.data.empty:
            raise ValueError("non-empty data must be provided before fitting the KDE")
        logger.info(f'Fitting KDE generator for {self.data.columns.to_list()} variables')
        self.kde_estimator: KernelDensity = KernelDensity(kernel=self.kernel, bandwidth=self.bandwidth).fit(self._training_data)
        return self.kde_estimator

    @staticmethod
    def _normalize_data(data):
        if isinstance(data, pd.Series):
            return data.to_frame()
        if isinstance(data, pd.DataFrame):
            return data
        array = np.asarray(data)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        if array.ndim != 2:
            raise ValueError("KDE data must be one- or two-dimensional")
        return pd.DataFrame(array)

    def _require_fitted(self):
        if not self.is_run or self.kde_estimator is None:
            raise RuntimeError("the KDE estimator has not been fitted")

    def plot_1d_comparison_histograms(self,
                                      variable=None,
                                      n=10000,
                                      savefig=None,
                                      bins=30,
                                      colors=None,
                                      xlabel=None,
                                      ylabel=None
                                      ):
        """Plot original and KDE-sampled histograms for one variable.

        Category: interpolation
        Tags: kde, histogram, sampling, plot
        Usage: scripts need to visually compare observed values against KDE-generated samples.

        Returns:
            matplotlib.axes.Axes: histogram axes.
        """
        plt.clf()
        fig, ax = plt.subplots()
        fig: plt.Figure
        ax: plt.Axes
        self._require_fitted()
        if variable is None:
            variable = self.data.columns[0]

        sampled_values = pd.DataFrame(self.kde_estimator.sample(n), columns=self.data.columns)

        ax.hist(self.data[variable].values, bins=bins,
                density=True,
                alpha=0.5,
                label=variable,
                color=colors[0] if colors else 'C0'
                )

        ax.hist(sampled_values[variable].values, bins=bins,
                density=True,
                alpha=0.5,
                label=f"{variable}-kde",
                color=colors[1] if colors else 'C1'
                )
        ax.set_axisbelow(True)
        if xlabel:
            ax.set_xlabel(xlabel)
        if ylabel:
            ax.set_ylabel(ylabel)
        plt.legend()
        plt.grid()
        if savefig:
            plt.savefig(savefig)
        else:
            plt.show()
        return ax

    def plot_1d_comparison_histograms_multi(self, variables, n=10000, savefig=None, bins=30, palette=None, dpi=150):
        """Plot original and KDE-sampled histograms for multiple variables.

        Category: interpolation
        Tags: kde, histogram, sampling, multi-variable, plot
        Usage: scripts need a visual comparison across several KDE variables.

        Returns:
            matplotlib.axes.Axes: histogram axes.
        """
        plt.clf()
        fig, ax = plt.subplots()
        fig: plt.Figure
        ax: plt.Axes

        self._require_fitted()
        sampled_values = pd.DataFrame(self.kde_estimator.sample(n), columns=self.data.columns)
        for idx, variable in enumerate(variables):
            if palette:
                color = palette[idx]
            histogram_options = {"color": color} if palette else {}
            sns.histplot(self.data[variable].values, bins=bins,
                    alpha=0.75,
                    label=variable,
                    **histogram_options,
                    )
            sns.histplot(sampled_values[variable].values, bins=bins,
                    alpha=0.25,
                    label=f"{variable}-kde",
                    **histogram_options,
                         )
        ax.set_axisbelow(True)
        plt.legend()
        plt.grid()
        if savefig:
            plt.savefig(savefig, dpi=dpi)
        else:
            plt.show()
        return ax

    def plot_1d(self, variable=None, n=100, savefig=None):
        """Plot the trained KDE density over original data bounds.

        Category: interpolation
        Tags: kde, density, plot, diagnostics
        Usage: scripts need to inspect the fitted density curve against observed values.

        Returns:
            matplotlib.axes.Axes: density plot axes.
        """
        plt.clf()
        self._require_fitted()
        if variable is None:
            variable = self.data.columns[0]
        logger.info(f'Generating 1D comparison plot for {variable} variable')

        temp = [np.linspace(self.data[column].min(), self.data[column].max(), n) for column in self.data]
        sampling_grid = np.meshgrid(*temp)
        sampling_data = np.stack(
            [grid.ravel() for grid in sampling_grid], axis=-1
        )

        predicted_distribution = self.kde_estimator.score_samples(sampling_data)
        predicted_distribution = np.exp(predicted_distribution)

        # Plot result
        fig, ax = plt.subplots()
        fig: plt.Figure
        ax: plt.Axes
        ax.hist(self.data[variable].values, bins=30,
                density=True,
                alpha=0.5,
                label=variable,
                )
        ax.plot(sampling_data,
                predicted_distribution,
                alpha=0.80,
                label=f'{variable}-predicted KDE'
                )
        plt.legend()
        plt.grid()
        ax.set_ylabel('Density [-]')
        ax.set_xlabel('Integration time [y]')
        if savefig:
            plt.savefig(savefig)
        else:
            plt.show()
        return ax

    @property
    def _training_data(self):
        if self.data is None or self.data.empty:
            raise ValueError("non-empty data must be provided before fitting the KDE")
        return self.data.values.reshape(-1, self.data.shape[1])

    def sample(self, *args, **kwargs):
        """Sample values from the fitted KDE model.

        Category: interpolation
        Tags: kde, sampling, synthetic-data
        Usage: scripts need synthetic values drawn from the fitted density.

        Returns:
            numpy.ndarray: samples returned by KernelDensity.sample.
        """
        self._require_fitted()
        return self.kde_estimator.sample(*args, **kwargs)

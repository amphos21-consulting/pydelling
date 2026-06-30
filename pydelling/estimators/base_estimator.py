"""Base estimator interfaces and shared utility behavior.
    """

import pandas as pd
from abc import ABC, abstractmethod
from pathlib import Path
from scipy.ndimage import gaussian_filter1d
import matplotlib.pyplot as plt
import dill
import logging

logger = logging.getLogger(__name__)


class BaseEstimator(ABC):
    """Base interface for estimator implementations.

    Category: estimator
    Tags: estimator, data, prediction, smoothing, serialization
    Use when: implementing estimators that load data, preprocess it, plot it, predict from it, and persist state.
    """

    def __init__(self, file_path: str | Path, *args, **kwargs):
        """
        Initialize the estimator and run the common preprocessing pipeline.
        
        Args:
            file_path (str | Path): Description.
            *args (Any): Description.
            **kwargs (Any): Description.
        """
        self.file_path = Path(file_path) if file_path is not None else None
        self.data: pd.DataFrame = self.read_data(self.file_path, *args, **kwargs)
        self.original_data: pd.DataFrame = self.data.copy()
        self.process_data()
        self.prediction: pd.DataFrame = None
        logger.info(f"{self.__class__.__name__} initialized.")

    @abstractmethod
    def read_data(self, filename: Path) -> pd.DataFrame:
        """Read estimator input data.

        Category: estimator
        Tags: estimator, input-data, dataframe, abstract
        Use when: subclasses need to define how source data is loaded.

        Returns:
            pandas.DataFrame: loaded estimator data.
        """
        pass

    @abstractmethod
    def process_data(self):
        """Preprocess loaded estimator data.

        Category: estimator
        Tags: estimator, preprocessing, abstract
        Use when: subclasses need to normalize or derive fields before prediction.

        Returns:
            None: subclasses mutate estimator data.
        """
        pass

    @abstractmethod
    def smooth_data(self, window_size=3, sigma=1):
        """Smooth estimator data.

        Category: estimator
        Tags: estimator, smoothing, abstract
        Use when: subclasses expose a public smoothing operation for noisy input data.

        Returns:
            None: subclasses mutate estimator data.
        """
        pass

    def _smooth_data(self, column_name, method="rolling", window_size=3, sigma=1):
        """Smooth one data column with rolling, exponential, or gaussian methods.

        Category: estimator
        Tags: estimator, smoothing, dataframe, preprocessing
        Use when: subclasses need a shared column-level smoothing helper.

        Returns:
            None: mutates the selected data column.
        """
        assert self.data is not None, "Data is None"
        if method == "rolling":
            logger.info(f"Smoothing {column_name} with rolling window of size {window_size}")
            self.data[column_name] = self.data[column_name].rolling(window=window_size).mean()
        elif method == "exponential":
            logger.info(f"Smoothing {column_name} with exponential window of size {window_size}")
            self.data[column_name] = self.data[column_name].ewm(span=window_size).mean()
        elif method == "gaussian":
            logger.info(f"Smoothing {column_name} with gaussian filter of sigma {sigma}")
            self.data[column_name] = gaussian_filter1d(self.data[column_name], sigma=sigma)
        else:
            raise ValueError(f"Invalid smoothing method: {method}")

    @abstractmethod
    def plot_data(self, filename=None, *args, **kwargs):
        """Plot estimator data.

        Category: estimator
        Tags: estimator, plot, abstract, diagnostics
        Use when: subclasses need to expose basic diagnostic plots.

        Returns:
            None: subclasses show or save plots.
        """
        pass

    def _plot_data(self,
                   column_name,
                   title,
                   filename=None,
                   prediction_data=None,
                   ):
        """Plot one data column and optional prediction data.

        Category: estimator
        Tags: estimator, plot, prediction, diagnostics
        Use when: subclasses need a shared matplotlib plot helper.

        Returns:
            None: shows or saves the plot.
        """
        assert self.data is not None, "Data is None"
        fig, ax = plt.subplots()
        ax.plot(self.data[column_name])
        ax.set_title(title)
        ax.set_xlabel("Time")
        ax.set_ylabel(column_name)
        if prediction_data is not None:
            ax.plot(prediction_data, label="Prediction")
            ax.legend()
        if filename is not None:
            fig.savefig(filename, dpi=300)
        else:
            plt.show()

    @abstractmethod
    def predict(self, method=None, days=365, return_whole_data=False):
        """Run estimator prediction.

        Category: estimator
        Tags: estimator, prediction, abstract
        Use when: subclasses define forecasting or classification behavior.

        Returns:
            Any: subclass-specific prediction output.
        """
        pass

    def save(self, file_name: str):
        """Serialize this estimator instance with dill.

        Category: writer
        Tags: estimator, serialize, dill, save
        Use when: scripts need to persist a fitted or configured estimator.

        Returns:
            None: writes the serialized estimator file.
        """
        with open(file_name, 'wb') as f:
            dill.dump(self, f)
            logger.info(f"Saved estimator instance to {file_name}")

    @classmethod
    def load(cls, file_name: str):
        """Load a serialized estimator instance with dill.

        Category: reader
        Tags: estimator, serialize, dill, load
        Use when: scripts need to restore a saved estimator object.

        Returns:
            BaseEstimator: deserialized estimator instance.
        """
        with open(file_name, 'rb') as f:
            logger.info(f"Loaded estimator instance from {file_name}")
            return dill.load(f)

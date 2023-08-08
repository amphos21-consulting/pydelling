import pandas as pd
from abc import ABC, abstractmethod
from pathlib import Path
from scipy.ndimage import gaussian_filter1d
import matplotlib.pyplot as plt
import dill
import logging

logger = logging.getLogger(__name__)


class BaseEstimator(ABC):
    def __init__(self, file_path: str or Path, *args, **kwargs):
        self.file_path = Path(file_path) if file_path is not None else None
        self.data: pd.DataFrame = self.read_data(self.file_path, *args, **kwargs)
        self.original_data: pd.DataFrame = self.data.copy()
        self.process_data()
        self.prediction: pd.DataFrame = None
        logger.info(f"{self.__class__.__name__} initialized.")

    @abstractmethod
    def read_data(self, filename: Path) -> pd.DataFrame:
        """
        Reads data from an excel file.
        """
        pass

    @abstractmethod
    def process_data(self):
        """
        Preprocesses the data and generate
        """
        pass

    @abstractmethod
    def smooth_data(self, window_size=3, sigma=1):
        """
        Smooths the self.data variable.
        """
        pass

    def _smooth_data(self, column_name, method="rolling", window_size=3, sigma=1):
        """
        Smooths the self.data variable.
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
        """
        Makes some basic plots of the data.
        """
        pass

    def _plot_data(self,
                   column_name,
                   title,
                   filename=None,
                   prediction_data=None,
                   ):
        """
        Plots the data.
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
        """
        Makes a prediction.
        """
        pass

    def save(self, file_name: str):
        """
        Save the current object instance to a file.
        """
        with open(file_name, 'wb') as f:
            dill.dump(self, f)
            logger.info(f"Saved estimator instance to {file_name}")

    @classmethod
    def load(cls, file_name: str):
        """
        Load an object instance from a file.
        """
        with open(file_name, 'rb') as f:
            logger.info(f"Loaded estimator instance from {file_name}")
            return dill.load(f)

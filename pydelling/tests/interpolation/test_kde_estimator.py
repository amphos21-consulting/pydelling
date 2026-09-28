import unittest
from pydelling.interpolation import KdeEstimator
import numpy as np
import pandas as pd
import pytest


class KdeEstimatorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.test_data = pd.DataFrame(np.random.normal(size=1000))

    def test_set_up(self):
        self.kde_estimator = KdeEstimator()

    def test_train_gaussian(self):
        self.kde_estimator = KdeEstimator(data=self.test_data, bandwidth=0.0001)
        self.kde_estimator.run()
        test_samples = self.kde_estimator.sample(100)
        self.assertLess(abs(test_samples.mean()), 0.5)


def test_run_accepts_replacement_dataframe():
    estimator = KdeEstimator(data=pd.DataFrame({"old": [0.0, 1.0]}), bandwidth=0.5)
    replacement = pd.DataFrame({"new": [10.0, 11.0, 12.0]})

    estimator.run(data=replacement)

    assert estimator.data is replacement
    assert estimator.is_run


def test_run_normalizes_series_and_rejects_missing_data():
    estimator = KdeEstimator(bandwidth=0.5)

    with pytest.raises(ValueError, match="data"):
        estimator.run()

    estimator.run(data=pd.Series([1.0, 2.0, 3.0], name="value"))
    assert list(estimator.data.columns) == ["value"]


def test_sample_requires_fitted_estimator():
    with pytest.raises(RuntimeError, match="not been fitted"):
        KdeEstimator(data=pd.DataFrame({"value": [1.0, 2.0]})).sample(1)


def test_failed_refit_does_not_leave_previous_estimator_marked_current():
    estimator = KdeEstimator(data=pd.DataFrame({"value": [1.0, 2.0]}), bandwidth=0.5)
    estimator.run()

    with pytest.raises(ValueError, match="data"):
        estimator.run(data=pd.DataFrame())

    assert not estimator.is_run
    with pytest.raises(RuntimeError, match="not been fitted"):
        estimator.sample(1)

if __name__ == '__main__':
    unittest.main()

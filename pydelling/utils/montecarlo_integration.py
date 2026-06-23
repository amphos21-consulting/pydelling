import numpy as np
from typing import Optional, Union


def montecarlo_integration(
	x: Union[list, np.ndarray],
	y: Union[list, np.ndarray],
	n_samples: int = 100_000,
	random_state: Optional[int] = None,
) -> float:
	"""Estimate the curve integral with Monte Carlo sampling.

	The function estimates the integral of a curve using Monte Carlo integration:

		integral_a^b f(x) dx ≈ (b - a) * mean(f(x_i))

	by sampling x uniformly in [a, b], interpolating y = f(x), and computing
	the average value.

	Args:
		x (list or np.ndarray): X-axis values.
		y (list or np.ndarray): Y-axis values corresponding to x.
		n_samples (int, optional): Number of Monte Carlo samples. Defaults to 100_000.
		random_state (int, optional): Seed for reproducible sampling. Defaults to None.

	Returns:
		float: Estimated integral of the curve over the x-range.

	Raises:
		ValueError: If n_samples is not positive, if x and y have different lengths,
			if they are empty, if all values are NaN, or if fewer than 2 unique
			x points are available after cleaning.
	"""
	if n_samples <= 0:
		raise ValueError("n_samples must be a positive integer")

	x_arr = np.asarray(x, dtype=float)
	y_arr = np.asarray(y, dtype=float)

	if x_arr.shape != y_arr.shape:
		raise ValueError("x and y must have the same length")

	if len(x_arr) == 0:
		raise ValueError("x and y must not be empty")

	# Remove NaN values
	mask = ~(np.isnan(x_arr) | np.isnan(y_arr))
	x_clean = x_arr[mask]
	y_clean = y_arr[mask]

	if len(x_clean) == 0:
		raise ValueError("No valid data points after removing NaN values")

	# Ensure increasing x for interpolation and drop duplicated x values.
	sorted_indices = np.argsort(x_clean)
	x_clean = x_clean[sorted_indices]
	y_clean = y_clean[sorted_indices]

	# Remove duplicate x values, keeping the last one
	_, unique_indices = np.unique(x_clean, return_index=True)
	unique_indices = np.sort(unique_indices)
	x_clean = x_clean[unique_indices]
	y_clean = y_clean[unique_indices]

	if len(x_clean) < 2:
		raise ValueError("At least two unique x points are required")

	a = float(x_clean[0])
	b = float(x_clean[-1])
	if a == b:
		return 0.0

	rng = np.random.default_rng(seed=random_state)
	x_samples = rng.uniform(a, b, size=n_samples)
	y_samples = np.interp(x_samples, x_clean, y_clean)

	return float((b - a) * np.mean(y_samples))
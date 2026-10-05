import inspect
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Union

import numpy as np


@dataclass
class RootResult:
	"""Result of a root search.

	Attributes:
		x (np.ndarray): Root found, with shape (n_args,).
		value (float): Function value at x.
		x0 (np.ndarray): Starting point generated from the seed.
		n_iter (int): Number of Newton iterations performed.
		converged (bool): Whether |f(x)| < tol was reached.
	"""
	x: np.ndarray
	value: float
	x0: np.ndarray
	n_iter: int
	converged: bool


def _infer_n_args(func: Callable[..., float]) -> int:
	"""Count the positional parameters of func that have no default value."""
	try:
		signature = inspect.signature(func)
	except (TypeError, ValueError) as e:
		raise ValueError("Could not infer the number of arguments of func; pass n_args explicitly") from e

	positional_kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
	return sum(
		1 for p in signature.parameters.values()
		if p.kind in positional_kinds and p.default is inspect.Parameter.empty
	)


def _initial_point(
	n_args: int,
	seed: Optional[int],
	bounds: Optional[Sequence[tuple[float, float]]],
) -> np.ndarray:
	"""Generate the starting point: uniform inside bounds, standard normal otherwise."""
	rng = np.random.default_rng(seed=seed)
	if bounds is None:
		return rng.standard_normal(n_args)

	lower = np.array([b[0] for b in bounds], dtype=float)
	upper = np.array([b[1] for b in bounds], dtype=float)
	return rng.uniform(lower, upper)


def _gradient(
	func: Callable[..., float],
	x: np.ndarray,
	fprime: Optional[Callable[..., Union[float, Sequence[float]]]],
	fd_step: float,
) -> np.ndarray:
	"""Gradient of func at x, analytical if fprime is given, central differences otherwise."""
	if fprime is not None:
		grad = np.atleast_1d(np.asarray(fprime(*x), dtype=float))
		if grad.shape != x.shape:
			raise ValueError(f"fprime must return {x.size} value(s), got {grad.size}")
		return grad

	grad = np.empty_like(x)
	for i in range(x.size):
		h = fd_step * max(1.0, abs(x[i]))
		x_forward = x.copy()
		x_backward = x.copy()
		x_forward[i] += h
		x_backward[i] -= h
		grad[i] = (func(*x_forward) - func(*x_backward)) / (2 * h)
	return grad


def find_root(
	func: Callable[..., float],
	seed: Optional[int] = None,
	bounds: Optional[Sequence[tuple[float, float]]] = None,
	fprime: Optional[Callable[..., Union[float, Sequence[float]]]] = None,
	n_args: Optional[int] = None,
	tol: float = 1e-10,
	xtol: float = 1e-12,
	max_iter: int = 100,
	fd_step: float = 1e-6,
	max_backtracks: int = 30,
) -> RootResult:
	"""Find a root of a scalar function of one, two or three arguments.

	The starting point is generated from the seed: uniformly inside bounds if they
	are given, from a standard normal distribution otherwise. From there, a
	minimum-norm Newton iteration is applied:

		x_{k+1} = x_k - alpha * f(x_k) * grad f(x_k) / ||grad f(x_k)||^2

	which reduces to the classical Newton method in 1D. For two or three arguments
	the roots form a curve or a surface, and the iteration converges to one point
	of it. The step length alpha is halved until |f| decreases (backtracking).

	The bounds only define where the starting point is sampled; the iteration
	itself is not constrained and the root may lie outside them.

	Args:
		func (Callable): Scalar function called as func(x), func(x, y) or func(x, y, z).
		seed (int, optional): Seed used to generate the starting point. Defaults to None.
		bounds (Sequence[tuple[float, float]], optional): (lower, upper) per argument
			used to sample the starting point. Defaults to None.
		fprime (Callable, optional): Analytical derivative (1D) or gradient (nD), called
			with the same arguments as func. Defaults to central finite differences.
		n_args (int, optional): Number of arguments of func. Inferred from its
			signature if not given.
		tol (float, optional): Convergence tolerance on |f(x)|. Defaults to 1e-10.
		xtol (float, optional): Minimum step norm before stopping. Defaults to 1e-12.
		max_iter (int, optional): Maximum number of Newton iterations. Defaults to 100.
		fd_step (float, optional): Relative step for finite differences. Defaults to 1e-6.
		max_backtracks (int, optional): Maximum step halvings per iteration. Defaults to 30.

	Returns:
		RootResult: Root, function value, starting point, iterations and convergence flag.

	Raises:
		ValueError: If func does not take 1 to 3 arguments, if bounds do not match the
			number of arguments or have lower >= upper, or if the tolerances,
			max_iter or fd_step are not positive.
	"""
	if n_args is None:
		n_args = _infer_n_args(func)
	if not 1 <= n_args <= 3:
		raise ValueError(f"func must take 1, 2 or 3 arguments, got {n_args}")

	if bounds is not None:
		if len(bounds) != n_args:
			raise ValueError(f"bounds must have {n_args} (lower, upper) pairs, got {len(bounds)}")
		for lower, upper in bounds:
			if not lower < upper:
				raise ValueError(f"Each bound must satisfy lower < upper, got ({lower}, {upper})")

	if tol <= 0 or xtol <= 0 or fd_step <= 0:
		raise ValueError("tol, xtol and fd_step must be positive")
	if max_iter <= 0:
		raise ValueError("max_iter must be a positive integer")

	x0 = _initial_point(n_args, seed, bounds)
	x = x0.copy()
	f_x = float(func(*x))

	n_iter = 0
	while n_iter < max_iter and np.isfinite(f_x) and abs(f_x) >= tol:
		grad = _gradient(func, x, fprime, fd_step)
		grad_norm2 = float(np.dot(grad, grad))
		if not np.isfinite(grad_norm2) or grad_norm2 == 0.0:
			break

		dx = -f_x * grad / grad_norm2
		n_iter += 1

		# Backtracking: halve the step until |f| decreases.
		alpha = 1.0
		for _ in range(max_backtracks):
			x_new = x + alpha * dx
			f_new = float(func(*x_new))
			if np.isfinite(f_new) and abs(f_new) < abs(f_x):
				break
			alpha /= 2
		else:
			break

		step_norm = float(np.linalg.norm(x_new - x))
		x, f_x = x_new, f_new
		if step_norm < xtol:
			break

	converged = bool(np.isfinite(f_x) and abs(f_x) < tol)
	return RootResult(x=x, value=f_x, x0=x0, n_iter=n_iter, converged=converged)

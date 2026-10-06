import unittest
from pydelling.utils.root_finding_solver import find_root
import numpy as np


class RootFindingSolverCase(unittest.TestCase):
    def test_1d(self):
        result = find_root(lambda x: x**2 - 2, seed=42)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(abs(result.x[0]), np.sqrt(2), places=8)

    def test_1d_analytical_derivative(self):
        result = find_root(lambda x: x**2 - 2, seed=42, fprime=lambda x: 2 * x)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(abs(result.x[0]), np.sqrt(2), places=8)

    def test_2d(self):
        result = find_root(lambda x, y: x**2 + y**2 - 1, seed=0)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(np.linalg.norm(result.x), 1.0, places=8)

    def test_3d(self):
        result = find_root(lambda x, y, z: x + y + z - 3, seed=1)
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.x.sum(), 3.0, places=8)

    def test_reproducible(self):
        f = lambda x, y: np.sin(x) * y - 0.5
        first = find_root(f, seed=7)
        second = find_root(f, seed=7)
        np.testing.assert_array_equal(first.x0, second.x0)
        np.testing.assert_array_equal(first.x, second.x)

    def test_initial_point_inside_bounds(self):
        bounds = [(2, 3), (-5, -4)]
        result = find_root(lambda x, y: x - y, seed=3, bounds=bounds)
        for value, (lower, upper) in zip(result.x0, bounds):
            self.assertTrue(lower <= value <= upper)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            find_root(lambda: 1.0)
        with self.assertRaises(ValueError):
            find_root(lambda x, y, z, w: x)
        with self.assertRaises(ValueError):
            find_root(lambda x, y: x + y, bounds=[(0, 1)])
        with self.assertRaises(ValueError):
            find_root(lambda x: x, bounds=[(1, 1)])

    def test_no_root(self):
        result = find_root(lambda x: x**2 + 1, seed=42)
        self.assertFalse(result.converged)


if __name__ == '__main__':
    unittest.main()

import unittest
from pydelling.utils.montecarlo_integration import montecarlo_integration
import numpy as np

class MonteCarloIntegrationCase(unittest.TestCase):
    def test_integration(self):
        x = np.linspace(0, 2*np.pi, 100)
        y = np.sin(x) + 1
        
        self.assertEqual(montecarlo_integration(x, y, 1000, random_state=42), 6.2731076868795554)


if __name__ == '__main__':
    unittest.main()

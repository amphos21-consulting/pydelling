"""
Tests the correct execution of pydelling even if there are files with
the name config in the working directory. This used to crash pydelling.
"""
import pathlib
import os
import unittest

class TestWrongConfigFile(unittest.TestCase):
    def setUp(self):
        cwd = pathlib.Path.cwd()
        wrong_config_path = os.path.join(cwd, "not_a_valid_config.dat")
        with open(wrong_config_path, "w") as wrong_config_file:
            print ("Not a valid config file", file=wrong_config_file)

    def test_wrong_config(self):
        try:
            # pydelling is imported here, after setUp has been run, so that the wrong
            # config file is found
            import pydelling
            test_passed = True
        except:
            test_passed = False

        self.assertTrue(test_passed)

    def tearDown(self):
        cwd = pathlib.Path.cwd()
        wrong_config_path = os.path.join(cwd, "not_a_valid_config.dat")
        os.remove(wrong_config_path)


if __name__ == '__main__':
    unittest.main()

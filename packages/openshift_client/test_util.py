from __future__ import absolute_import

import unittest

from .util import extract_numerical_value
from .model import Missing


def isclose(a, b, rel_tol=1e-09, abs_tol=0.0):
    return abs(a-b) <= max(rel_tol * max(abs(a), abs(b)), abs_tol)


class TestSelector(unittest.TestCase):

    def test_extract_numerical_value(self):
        test_dict = {
            None: 0.0,
            '': 0.0,
            'i': 0,
            'M': 0.0,
            'Mi': 0.0,
            '0': 0.0,
            '0i': 0.0,
            '0n': 0.0,
            '0ni': 0.0,
            '1e2': 100.0,
            '1e2Mi': 104857600.0,
            '1e2i': 100.0,
            '1e2M': 100000000.0,
            '.314ni': 2.9243528842926026e-10,
            '3.14n': 3.1400000000000003e-09,
            '3.14u': 3.14e-06,
            '3.14m': 0.00314,
            '3.14': 3.14,
            '3.14i': 3.14,
            '3.14K': 3140.0,
            '3.14k': 3140.0,
            '3.14M': 3140000.0,
            '3.14G': 3140000000.0,
            '3.14T': 3140000000000.0,
            '3.14P': 3140000000000000.0,
            '3.14E': 3.14e+18,
            '314.Ei': 3.6201735244654995e+20
        }

        for i in test_dict.keys():
            self.assertTrue(isclose(test_dict[i], extract_numerical_value(i)))
        # test oc.Missing
        self.assertTrue(isclose(extract_numerical_value(Missing), 0.0))


if __name__ == '__main__':
    unittest.main()

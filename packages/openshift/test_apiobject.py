import unittest

from .apiobject import APIObject


class TestModel(unittest.TestCase):

    def test_empty(self):
        obj = APIObject()
        self.assertIs(len(obj.model), 0)
        self.assertEqual(obj.as_dict(), {})
        self.assertEqual(obj.as_json(), '{}')
        self.assertIsNone(obj.context.project_name)


if __name__ == '__main__':
    unittest.main()

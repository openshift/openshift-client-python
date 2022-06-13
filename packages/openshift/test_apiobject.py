import unittest

from openshift import Context
from .apiobject import APIObject


class TestModel(unittest.TestCase):

    def test_empty(self):
        obj = APIObject()
        self.assertIs(len(obj.model), 0)
        self.assertEqual(obj.as_dict(), {})
        self.assertEqual(obj.as_json(), '{}')
        self.assertIsNone(obj.context.project_name)

    def test_context(self):
        context = Context()
        context.project_name = "my-project"
        obj = APIObject(context=context)
        self.assertEqual(obj.context.project_name, context.project_name)


if __name__ == '__main__':
    unittest.main()

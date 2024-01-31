from __future__ import absolute_import

import unittest

from .model import *


class TestModel(unittest.TestCase):

    def test_empty(self):
        empty = Model()
        self.assertIs(empty.metadata, Missing)
        self.assertIs(empty["metadata"], Missing)
        self.assertIs(empty.metadata.a, Missing)
        self.assertIs(empty.metadata["a"], Missing)

    def test_falsey(self):
        miss = Model().something.missing
        self.assertTrue(miss is Missing)
        if miss:
            self.fail("Expected falsey value")

        if len(miss) != 0:
            self.fail("Expected zero length")

    def test_primitive(self):
        d = {
            "a": 1,
            "b": 2,
            "map1": {
                "c": 3,
                "d": 4
            },
            "list1": [
                5,
                6,
                7,
            ],
            "list2": [
                {
                    "e": 5,
                    "f": 6
                },
                {
                    "g": 5,
                    "h": 6
                },
            ],
        }
        m = Model(dict_to_model=d)
        d2 = m._primitive()
        if d2 != d:
            self.fail('Primitive did not restore to expected state')

        self.assertTrue(isinstance(m, Model))
        self.assertFalse(isinstance(d2['map1'], Model))
        self.assertFalse(isinstance(d2['list2'], ListModel))
        self.assertFalse(isinstance(d2['list2'][0], Model))

    def test_access(self):
        m = Model()
        m.metadata = {
            "a": 1,
            "b": 2,
            "map1": {
                "c": 3,
                "d": 4
            },
            "list1": [
                5,
                6,
                7,
            ],
            "list2": [
                {
                    "e": 5,
                    "f": 6
                },
                {
                    "g": 5,
                    "h": 6
                },
            ],
            "anull": None,
            "astring": "thevalue"
        }

        self.assertIsNot(m.metadata, Missing)
        self.assertIsNot(m.metadata.a, Missing)
        self.assertIs(m.metadata.A, Missing)
        self.assertIs(m.metadata.B, Missing)
        self.assertEqual(m.metadata.b, 2)

        self.assertIsNot(m.metadata.map1, Missing)
        self.assertIsNot(m.metadata["map1"], Missing)

        self.assertIs(m.metadata["map_notthere"], Missing)
        self.assertIs(m.metadata.map_notthere, Missing)

        self.assertEqual(m.metadata.map1.c, 3)
        self.assertEqual(m.metadata.map1.d, 4)
        self.assertIs(m.metadata.map1.e, Missing)

        self.assertEqual(len(m.metadata.list1), 3)
        self.assertEqual(len(m.metadata["list1"]), 3)
        self.assertEqual(m.metadata.list1[0], 5)
        self.assertEqual(m.metadata.list1, [5,6,7])
        self.assertEqual(m.metadata["list1"], [5,6,7])

        try:
            m.metadata.list1[3]
            self.fail("Did not receive expected IndexError")
        except IndexError:
            pass

        self.assertIsNot(m.metadata.list2, Missing)
        self.assertIsNot(m.metadata.list2[0], Missing)
        self.assertIsNot(m.metadata.list2[1], Missing)
        self.assertIsNot(m.metadata.list2[1].g, Missing)
        self.assertIsNot(m.metadata.list2[1].h, Missing)
        self.assertIs(m.metadata.list2[1].notthere, Missing)
        self.assertIsNone(m.metadata.anull)

        self.assertEqual(m.metadata.astring, "thevalue")
        self.assertEqual(m.metadata["astring"], "thevalue")

        m.list3 = ['a', 'b']
        self.assertIsNot(m.list3, Missing)
        self.assertIsNot(m["list3"], Missing)
        self.assertEqual(m["list3"][0], "a")

        m.a = 5
        m.b = "hello"
        m.c = True
        m.d = False
        m.e = None

        self.assertEqual(m.a, 5)
        self.assertEqual(m.b, "hello")
        self.assertEqual(m.c, True)
        self.assertEqual(m.d, False)
        self.assertEqual(m.e, None)

    def test_access_case_insensitive(self):
        m = Model(case_insensitive=True)
        m.metadata = {
            "A": 1,
            "b": 2,
            "mAp1": {
                "c": 3,
                "D": 4
            },
            "lIst1": [
                5,
                6,
                7,
            ],
            "lisT2": [
                {
                    "e": 5,
                    "F": 6
                },
                {
                    "g": 5,
                    "h": 6
                },
            ],
            "aNull": None,
            "aString": "thevalue"
        }

        self.assertIsNot(m.metadata, Missing)
        self.assertIsNot(m.metadata.a, Missing)
        self.assertEqual(m.metadata.b, 2)
        self.assertIsNot(m.metadata.A, Missing)
        self.assertEqual(m.metadata.B, 2)

        self.assertIsNot(m.metadata.map1, Missing)
        self.assertIsNot(m.metadata["map1"], Missing)
        self.assertIsNot(m.metadata.MAP1, Missing)

        self.assertIs(m.metadata["map_notthere"], Missing)
        self.assertIs(m.metadata.map_notthere, Missing)

        self.assertEqual(m.metadata.map1.c, 3)
        self.assertEqual(m.metadata.map1.d, 4)
        self.assertIs(m.metadata.map1.e, Missing)

        self.assertEqual(m.metadata.MAP1.C, 3)
        self.assertEqual(m.metadata.MAP1.D, 4)
        self.assertIs(m.metadata.MAP1.E, Missing)

        self.assertEqual(len(m.metadata.list1), 3)
        self.assertEqual(len(m.metadata["list1"]), 3)
        self.assertEqual(m.metadata.list1[0], 5)
        self.assertEqual(m.metadata.list1, [5,6,7])
        self.assertEqual(m.metadata["list1"], [5,6,7])

        self.assertEqual(len(m.METADATA.LIST1), 3)
        self.assertEqual(len(m.METADATA["LIST1"]), 3)
        self.assertEqual(m.METADATA.LIST1[0], 5)
        self.assertEqual(m.METADATA.LIST1, [5,6,7])
        self.assertEqual(m.METADATA["LIST1"], [5,6,7])

        try:
            m.metadata.list1[3]
            self.fail("Did not receive expected IndexError")
        except IndexError:
            pass

        self.assertIsNot(m.metadata.list2, Missing)
        self.assertIsNot(m.metadata.list2[0], Missing)
        self.assertIsNot(m.metadata.list2[1], Missing)
        self.assertIsNot(m.metadata.list2[1].g, Missing)
        self.assertIsNot(m.metadata.list2[1].h, Missing)
        self.assertIs(m.metadata.list2[1].notthere, Missing)
        self.assertIsNone(m.metadata.anull)

        self.assertIsNot(m.METADATA.LIST2, Missing)
        self.assertIsNot(m.METADATA.LIST2[0], Missing)
        self.assertIsNot(m.METADATA.LIST2[1], Missing)
        self.assertIsNot(m.METADATA.LIST2[1].G, Missing)
        self.assertIsNot(m.METADATA.LIST2[1].H, Missing)
        self.assertIs(m.METADATA.LIST2[1].notthere, Missing)
        self.assertIsNone(m.METADATA.anull)


        self.assertEqual(m.metadata.astring, "thevalue")
        self.assertEqual(m.metadata["astring"], "thevalue")

        m.list3 = ['a', 'b']
        self.assertIsNot(m.list3, Missing)
        self.assertIsNot(m["list3"], Missing)
        self.assertEqual(m["list3"][0], "a")

        m.a = 5
        m.b = "hello"
        m.c = True
        m.d = False
        m.e = None

        self.assertEqual(m.a, 5)
        self.assertEqual(m.b, "hello")
        self.assertEqual(m.c, True)
        self.assertEqual(m.d, False)
        self.assertEqual(m.e, None)

    def test_dict_match(self):

        d = Model({
            'a': 1,
            'b': 2,
            'c': {
                'x': 1,
                'y': 2,
                'z': ['z1', 'z2', 'z3']
            }
        })

        self.assertTrue(d.can_match({'a': 1}))
        self.assertFalse(d.can_match({'a': 3}))

        self.assertTrue(d.can_match({'a': 1, 'b': 2}))
        self.assertFalse(d.can_match({'a': 1, 'b': 4}))
        self.assertFalse(d.can_match({'a': 1, 'r': 4}))

        self.assertTrue(d.can_match({'a': 1, 'b': 2, 'c': {}}))
        self.assertTrue(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1}}))
        self.assertFalse(d.can_match({'a': 1, 'b': 2, 'c': {'x': 2}}))
        self.assertTrue(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1, 'y': 2}}))
        self.assertFalse(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1, 'y': 3}}))

        self.assertTrue(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1, 'y': 2, 'z': []}}))
        self.assertTrue(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1, 'y': 2, 'z': ['z1']}}))
        self.assertTrue(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1, 'y': 2, 'z': ['z1', 'z2']}}))
        self.assertFalse(d.can_match({'a': 1, 'b': 2, 'c': {'x': 1, 'y': 2, 'z': ['z1', 'z5']}}))

    def test_list_match(self):

        l1 = ListModel(["a", "b", "c"])
        self.assertTrue(l1.can_match(l1))
        self.assertTrue(l1.can_match([]))
        self.assertTrue(l1.can_match(["b", "c"]))
        self.assertTrue(l1.can_match(["a", "c"]))
        self.assertTrue(l1.can_match("c"))
        self.assertTrue(l1.can_match("a"))

        nomatch_lm = ListModel(["1"])
        self.assertFalse(l1.can_match(nomatch_lm))
        self.assertFalse(l1.can_match("1"))
        self.assertFalse(l1.can_match(["1"]))
        self.assertFalse(l1.can_match(["1", "2"]))
        self.assertFalse(l1.can_match(True))

        self.assertFalse(l1.can_match({"a": 2}))

        l2 = ListModel([True])
        self.assertTrue(l2.can_match(True))
        self.assertFalse(l2.can_match(False))

        l3 = ListModel([
            {
                "a": 1,
                "b": 2,
                "c": 3
            },
            {
                "d": 1,
                "e": 2,
                "f": 3
            },
            {
                "d": True,
                "e": [2, 3, True],
                "f": 3
            }
        ])

        self.assertTrue(l3.can_match(
            {
                "c": 3
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "c": 3,
                "a": 1
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "c": 3,
                "a": 1,
                "b": 2
            }
        ))
        self.assertFalse(l3.can_match(
            {
                "a": 1,
                "b": 3,
            }
        ))
        self.assertFalse(l3.can_match(
            {
                "b": 3,
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "d": True,
                "f": 3,
            }
        ))
        self.assertFalse(l3.can_match(
            {
                "e": 3,
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "e": [3],
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "e": [2, 3],
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "e": [2, 3, True],
            }
        ))
        self.assertFalse(l3.can_match(
            {
                "d": True,
                "e": [2, 3, False],
            }
        ))
        self.assertTrue(l3.can_match(
            {
                "d": True,
                "e": [2, 3, True],
            }
        ))

        l4 = ListModel([
            {
                "a": 1,
                "b": {
                    "a1": 5,
                    "b1": {
                        "a2": 6,
                        "b2": {
                            "a3": 7,
                            "b3": 8
                        }
                    }
                },
                "c": 3
            },
        ])

        self.assertTrue(l4.can_match(
            {
                "a": 1,
            }
        ))
        self.assertTrue(l4.can_match(
            {
                "a": 1,
                "b": {
                    "a1": 5
                }
            }
        ))
        self.assertTrue(l4.can_match(
            {
                "a": 1,
                "b": {
                    "a1": 5,
                    "b1": {
                        "a2": 6
                    }
                }
            }
        ))
        self.assertTrue(l4.can_match(
            {
                "a": 1,
                "b": {
                    "a1": 5,
                    "b1": {
                        "b2": {
                            "b3": 8
                        }
                    }
                }
            }
        ))


if __name__ == '__main__':
    unittest.main()

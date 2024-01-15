from __future__ import absolute_import

import unittest

from .selector import selector
from .naming import qname_matches


class TestSelector(unittest.TestCase):

    def test_qname_matches(self):
        self.assertTrue(qname_matches('template/x', 'template/x'))
        self.assertTrue(qname_matches('template/x', ['template/x']))
        self.assertTrue(qname_matches('template/x', ['template/y', 'template/x']))
        self.assertFalse(qname_matches('template/x', ['template/y', 'template/x2']))

        # See whether fuzzy matching of kinds is working

        self.assertTrue(qname_matches('template/django', ['template.template.openshift.io/django']))
        self.assertFalse(qname_matches('template/django', ['template.template.openshift.io/django.2']))
        self.assertTrue(qname_matches('template/django', ['template.template/django']))
        self.assertFalse(qname_matches('template/django', ['template.template/django.2']))

        self.assertFalse(qname_matches('template2/django', ['template.template.openshift.io/django']))
        self.assertFalse(qname_matches('template/django2', ['template.template.openshift.io/django']))

    def test_set_operations(self):
        s1 = selector([])
        s2 = selector(['pod/abc', 'pod/xyz'])
        self.assertEqual(s1.subtract(s2).qnames(), [])
        self.assertEqual(s1.union(s2).qnames(), ['pod/abc', 'pod/xyz'])

        s3 = selector(['pod/abc2', 'pod/xyz'])
        self.assertEqual(s2.subtract(s3).qnames(), ['pod/abc'])
        self.assertEqual(s2.intersect(s3).qnames(), ['pod/xyz'])

        # See whether fuzzy matching of kinds is working

        t1 = selector(['template/django'])
        t2 = selector(['template.template.openshift.io/django', 'template.template.openshift.io/django2'])
        self.assertEqual(len(t1.union(t2).qnames()), 2)
        self.assertEqual(len(t1.intersect(t2).qnames()), 1)
        self.assertEqual(len(t1.subtract(t2).qnames()), 0)

        t1 = selector(['template/django'])
        t2 = selector(['template.template.openshift.io/django'])
        self.assertEqual(len(t1.union(t2).qnames()), 1)
        self.assertEqual(len(t1.intersect(t2).qnames()), 1)
        self.assertEqual(len(t1.subtract(t2).qnames()), 0)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python

from __future__ import print_function
from __future__ import absolute_import

from openshift import Result
import openshift as oc

'''
This example illustrates how you can utilize the "oc_action" method to perform any "oc" operations that are not
explicitly supported by the openshift-client-python library.
'''
if __name__ == '__main__':
    with oc.tracking() as tracker:
        try:
            r = Result("run-test")
            r.add_action(oc.oc_action(oc.cur_context(), "run", cmd_args=["nginx", "--image=nginx", "--dry-run=client", None]))
            r.fail_if("Unable to run nginx (dry-run)")
            print("Output: {}".format(r.out().strip()))
        except Exception as e:
            print(e)

        print("Tracker: {}".format(tracker.get_result()))

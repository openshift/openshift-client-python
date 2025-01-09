#!/usr/bin/env python

from __future__ import absolute_import
from __future__ import print_function

import openshift as oc
from openshift import OpenShiftPythonException

if __name__ == '__main__':
    with oc.tracking() as tracker:
        try:
            print('Current server: {}'.format(oc.api_url()))
            print('Current project: {}'.format(oc.get_project_name()))
            print('Current user: {}'.format(oc.whoami()))
        except OpenShiftPythonException as e:
            print('Error acquiring details about project/user: {}'.format(e))

        # Print out details about the invocations made within this context.
        print(tracker.get_result())

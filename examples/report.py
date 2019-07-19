#!/usr/bin/env python

import openshift as oc

if __name__ == '__main__':
    with oc.client_host():
        with oc.project('openshift-monitoring'):
            oc.selector(['dc', 'build', 'configmap']).print_report()


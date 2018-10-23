#!/usr/bin/env python

import openshift as oc

if __name__ == '__main__':
    with oc.client_host():
        oc.dumpinfo_core('dumps/')

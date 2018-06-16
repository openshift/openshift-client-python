#!/usr/bin/env python

import openshift

with openshift.tracker() as t:
    with openshift.client_host(hostname="54.147.205.250", username="root", auto_add_host=True):

        with openshift.project("jmp-test-3"):

            for pod in openshift.selector("pods", all_namespaces=True):
                print pod.name()

            secrets = openshift.selector("secrets")
            print("Found {} secrets".format(secrets.count_existing()))
            for secret in secrets:
                print('Secret: {} : {}'.format(secret.qname(), secret.exists()))

    print("Result:\n{}".format(t.get_result()))



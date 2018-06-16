#!/usr/bin/env python

import openshift

# NEWEST
# 1. Have core openshift.create, openshift.delete, openshift.name(s), etc.
# 2. Selectors call these methods to do their work
# These methods can take a list of models, yaml string, json string, python dicts, and even just a list of names in some cases.
# When user wants to perform som standard action, openshift.create( .... )
# But they can also   openshift.delete( openshift.selector( ... ).objects() )  or just   openshift.selector( ... ).delete()
# Model.asJSON|asYAML     ModelList.asJSON, ModelList.asYAML
# selector.object():Model     selector.objects():ModelList    (ModelList is a List<Model>)
# Make objects just Models

with openshift.tracker() as t:
    with openshift.client_host(hostname="54.147.205.250", username="root", auto_add_host=True):
        with openshift.project("jmp-test-3"):
            secrets = openshift.selector("secrets").objects()
            print("Found {} secrets".format(len(secrets)))
            for secret in secrets:
                print('Secret: {}'.format(secret.name()))

    print("Result:\n{}".format(t.get_result()))



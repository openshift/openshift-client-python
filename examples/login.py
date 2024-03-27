#!/usr/bin/python

import argparse
import traceback

import openshift_client as oc
from openshift_client import OpenShiftPythonException, Context

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OpenShift Client Login Example')
    parser.add_argument('-k', '--kubeconfig', help='The kubeconfig to create', required=True)
    parser.add_argument('-s', '--server', help='The API Server to communicate with', required=True)
    parser.add_argument('-t', '--token', help='The login token', required=True)
    args = vars(parser.parse_args())

    my_context = Context()
    my_context.token = args["token"]
    my_context.api_server = args["server"]
    my_context.kubeconfig_path = args["kubeconfig"]

    with oc.timeout(60 * 30), oc.tracking() as t, my_context:
        if oc.get_config_context() is None:
            print(f'Current context not set! Logging into API server: {my_context.api_server}\n')
            try:
                oc.invoke('login')
            except OpenShiftPythonException:
                print('error occurred logging into API Server')
                traceback.print_exc()
                print(f'Tracking:\n{t.get_result().as_json(redact_streams=False)}\n\n')
                exit(1)

        print(f'Current context: {oc.get_config_context()}')

        try:
            pods = oc.selector('pods').objects()
            print(f'Found: {len(pods)} pods')
        except OpenShiftPythonException:
            print('Error occurred getting pods')
            traceback.print_exc()
            print(f'Tracking:\n{t.get_result().as_json(redact_streams=False)}\n\n')

#!/usr/bin/env python

import openshift
import logging
import paramiko
import traceback

logging.getLogger("paramiko").setLevel(logging.DEBUG)
paramiko.util.log_to_file("paramiko.log")

with openshift.tracker() as t:
    with openshift.client_host(hostname="54.147.205.250", username="root", auto_add_host=True):

        with openshift.project("jmp-test-3"):

            try:
                openshift.selector('pod/busybox').delete(ignore_not_found=True)

                openshift.create({
                    'apiVersion': 'v1',
                    'kind': 'Pod',
                    'metadata': {
                        'name': 'busybox'
                    },
                    'spec': {
                        'containers': [
                            {
                                'name': 'busybox',
                                'image': 'busybox',
                                'command': ['sleep', '60']
                            }
                        ],
                        'restartPolicy': 'Never',
                        'terminationGracePeriodSeconds': '0'
                    },
                })

            except Exception:
                traceback.print_exc()

            #for pod in openshift.selector("pods", all_namespaces=True):
            #    print pod.name()

            #or node in openshift.selector("nodes"):
            #   with openshift.node_ssh_client(node, address_type_pref="Hostname") as node_client:
            #       _, stdout, stderr = node_client.exec_command("hostname")
            #       rc = stdout.channel.recv_exit_status()
            #       lines = stdout.read()
            #       print("Hostname ({}): {}".format(rc, lines.strip()))

    print("Result:\n{}".format(t.get_result()))



#!/usr/bin/env python

# Current thinking
# - Use model extensively. The use of dicts is just too painful syntax-wise.
# - Do not implement watch. Not targeting writing a controller and user can easy poll for changes they are
# interested in. It's technically possible if you polled channel recv_ready & read lines, but why bother with this
# complexity?
#


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

                openshift.selector('all').delete(ignore_not_found=True)

                bb = openshift.selector('secrets/test-secret')
                bb.delete(ignore_not_found=True)

                na_sel = openshift.new_app("https://github.com/openshift/ruby-hello-world")
                print("Created objects with new-app: {}".format(na_sel.qnames()))
                print('Found buildconfig: {}'.format(na_sel.narrow('bc').qnames()))

                openshift.create({
                    'apiVersion': 'v1',
                    'kind': 'Secret',
                    'type': 'Opaque',
                    'metadata': {
                        'name': 'test-secret'
                    },
                    'data': {
                        'somefile.yaml': 'abcd'
                    }
                })

                def apply_update(apiobj):

                    def make_model_change(apiobj):
                        apiobj.model.data['somefile.yaml'] = 'wyxz'
                        return True

                    apiobj.modify_and_apply(make_model_change, retries=5)
                    return True

                bb.for_each(apply_update)

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

    # print("Result:\n{}".format(t.get_result()))



#!/usr/bin/python

from __future__ import print_function
from __future__ import unicode_literals
from builtins import str
import argparse
import time
import logging
import traceback

import openshift as oc
from contextlib import contextmanager


def report_progress(msg):
    logging.info('PROGRESS: {}'.format(msg))


def report_verified(msg):
    logging.info('VERIFIED: {}'.format(msg))


@contextmanager
def temp_project(name, adm=False, cleanup=True):
    """
    Useful context manager for testing purposes. Creates a temporary project,
    runs the context within oc.project, and then deletes the project on exit.
    Exceptions thrown by content are thrown by contextmanager as well.
    :param name: The name of the project to create.
    :param adm: If True, the project will be created with 'oc adm ...'
    :param cleanup: If True, project will be deleted on return. Only set to False if you
    are trying to leave behind some sort of debug breadcrumb.
    :return:
    """
    oc.delete_project(name, ignore_not_found=True, grace_period=1)
    try:
        with oc.new_project(name, adm=adm):
            yield
    finally:
        if cleanup:
            report_progress('Cleaning up test project: {}'.format(name))
            oc.delete_project(name, ignore_not_found=True, grace_period=1)


def simple_http_server_resources(name, port=8080, create_service=False, create_route=False):
    """
    Returns a list<dict> representing resources which, if instantiated, will run
    a simple pod, running a python-based http server on a specified port. If
    requested, a kube Service and Route can be created.
    :param name: The name of the pod to create
    :param port: The port the pod should expose
    :param create_service: If True, a Service will be created for the server pod
    :param create_route: If True, a Service & Route will be created for the server port
    :return:
    """

    objs = [
        oc.build_pod_simple(
            name,
            'python:3',
            port=port,
            command=['python', '-m', 'http.server', str(port)],
            labels={'simple-server-run': name}
        ),
    ]

    if create_service or create_route:
        objs.append(oc.build_service_simple(name,
                                            {'simple-server-run': name},
                                            port,
                                            ),
                    )

    if create_route:
        objs.append({
            'apiVersion': 'v1',
            'kind': 'Route',
            'metadata': {
                'name': name,
            },
            'spec': {
                'host': '',
                'port': {
                    'targetPort': port,
                },
                'to': {
                    'kind': 'Service',
                    'name': name,
                    'weight': None,
                }
            }
        })

    return objs


def check_online_project_constraints():
    test_project_name = 'imperative-verify-test-project-constraints'

    with temp_project(test_project_name):
        time.sleep(2)

        oc.selector('limitrange').object()
        report_verified('New projects contain limit ranges')

        oc.selector('networkpolicy').objects()
        report_verified('New projects contain network policies')

        oc.selector('resourcequota').objects()
        report_verified('New projects contain resource quotas')

    report_verified("Template based project constraints are being created!")


def check_prevents_cron_jobs():
    """
    In our cluster configuration, cronjobs can only be created
    in privileged projects. Validate this.
    """

    cronjob = {
        'apiVersion': 'batch/v1beta1',
        'kind': 'CronJob',
        'metadata': {
            'name': 'prohibited-cron',
        },
        'spec': {
            'schedule': '@weekly',
            'jobTemplate': {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [
                                {
                                    'name': 'container0',
                                    'image': 'busybox',
                                }
                            ],
                            'restartPolicy': 'Never',
                        }
                    }
                }
            }
        }
    }

    user_project_name = 'imperative-verify-test-project-scheduled-jobs'
    with temp_project(user_project_name):
        try:
            report_progress('Creating cron job in normal project')
            oc.create(cronjob)
            assert False, 'Cronjob created but should have been prohibited'
        except:
            report_verified('Could not create cronjob in user project')
            pass

    priv_project_name = 'openshift-imperative-verify-test-project-scheduled-jobs'
    with temp_project(priv_project_name, adm=True):
        # In openshift-*, we should be able to create the cronjob.
        report_progress('Creating cron job in privileged project')
        oc.create(cronjob)
        report_verified('Able to create cronjob in privileged project')


def check_online_network_multitenant():
    def create_test_project(suffix, port):
        project_name = 'imperative-verify-test-project-network-{}'.format(suffix)

        # Delete any existing resources
        oc.delete_project(project_name, ignore_not_found=True, grace_period=1)

        server_name = 'server-{}'.format(suffix)
        client_name = 'client-{}'.format(suffix)

        with oc.new_project(project_name):
            # Create a simple http server running in project-A
            # It will be exposed by a service and route of the same name
            report_progress("Creating server in: " + project_name)
            server_sel = oc.create(
                simple_http_server_resources(server_name, port, create_service=True, create_route=True)
            )
            report_progress("Created: {}".format(server_sel.qnames()))
            report_progress("Waiting for resources readiness...")
            server_sel.narrow('pod').until_all(1, success_func=oc.status.is_pod_running)
            server_sel.narrow('route').until_all(1, success_func=oc.status.is_route_admitted)

            # Create a passive pod that blocks forever so we exec commands within it
            client_sel = oc.create(
                oc.build_pod_simple(client_name, image='python:3', command=['tail', '-f', '/dev/null']))
            client_sel.until_all(1, success_func=oc.status.is_pod_running)

            server_pod = server_sel.narrow('pod').object()
            service = server_sel.narrow('service').object()
            route = server_sel.narrow('route').object()
            client_pod = client_sel.narrow('pod').object()

            report_progress('Ensure client pod can communicate to server pod IP in same namespace')
            client_pod.execute(cmd_to_exec=['curl', 'http://{}:{}'.format(server_pod.model.status.podIP, port)],
                               auto_raise=True)

            report_progress('Ensure client pod can communicate to server service IP in same namespace')
            client_pod.execute(cmd_to_exec=['curl', 'http://{}:{}'.format(service.model.spec.clusterIP, port)],
                               auto_raise=True)

            report_progress('Ensure client pod can communicate to server service DNS in same namespace')
            client_pod.execute(cmd_to_exec=['curl', 'http://{}:{}'.format(server_name, port)],
                               auto_raise=True)

            report_progress('Ensure client pod can communicate to server route in same namespace')
            client_pod.execute(cmd_to_exec=['curl', 'http://{}'.format(route.model.spec.host)],
                               auto_raise=True)

            # Return a selector for server resources and client resources
            return project_name, server_pod, service, route, client_pod

    port_a = 4444
    port_b = 4555

    # Create two projects, A and B. Both will self test to make sure they can communicate within
    # pods in the same namespace.
    proj_a_name, server_pod_a, service_a, route_a, client_pod_a = create_test_project('a', port_a)
    proj_b_name, server_pod_b, service_b, route_b, client_pod_b = create_test_project('b', port_b)

    report_progress('Ensure client pod A cannot communicate to server service in another namespace')
    assert client_pod_a.execute(cmd_to_exec=['nc', '-z', service_b.model.spec.clusterIP, port_b],
                                auto_raise=False).status() != 0, 'Expected error 1'

    report_progress('Ensure client pod B cannot communicate to server service in another namespace')
    assert client_pod_b.execute(cmd_to_exec=['nc', '-z', service_a.model.spec.clusterIP, port_a],
                                auto_raise=False).status() != 0, 'Expected error 2'

    report_progress('Ensure client pod A cannot communicate to server pod IP in another namespace')
    assert client_pod_a.execute(cmd_to_exec=['nc', '-z', server_pod_b.model.status.podIP, port_b],
                                auto_raise=False).status() != 0, 'Expected error 1'

    report_progress('Ensure client pod B cannot communicate to server pod IP in another namespace')
    assert client_pod_b.execute(cmd_to_exec=['nc', '-z', server_pod_a.model.status.podIP, port_a],
                                auto_raise=False).status() != 0, 'Expected error 1'

    report_progress('Ensure client pod A can communicate to server route in another namespace')
    client_pod_a.execute(cmd_to_exec=['curl', 'http://{}'.format(route_b.model.spec.host)])

    report_progress('Ensure client pod B can communicate to server route in another namespace')
    client_pod_b.execute(cmd_to_exec=['curl', 'http://{}'.format(route_a.model.spec.host)])

    report_progress("Deleting project: " + proj_a_name)
    oc.delete_project(proj_a_name, grace_period=1)

    report_progress("Deleting project: " + proj_b_name)
    oc.delete_project(proj_b_name, grace_period=1)

    report_verified("Network policy for multitenant seems solid!")


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(description='Run a series of tests against a cluster')
    parser.add_argument('-b', '--bastion', default=None,
                        help='user@host, hostname, or IP on which to execute oc (oc is executed locally if not specified)',
                        required=False)
    parser.add_argument('--insecure-skip-tls-verify', action='store_true',
                        help='Skip TLS verify during oc interations (recommended when replacing api certs)')
    parser.set_defaults(insecure_skip_tls_verify=False)

    args = vars(parser.parse_args())

    skip_tls_verify = args['insecure_skip_tls_verify']

    if skip_tls_verify:
        oc.set_default_skip_tls_verify(True)

    bastion_hostname = args['bastion']
    if not bastion_hostname:
        print('Running in local mode. Expecting "oc" in PATH')

    with oc.client_host(hostname=bastion_hostname, username="root",
                        auto_add_host=True, load_system_host_keys=False):
        # Ensure tests complete within 30 minutes and track all oc invocations
        with oc.timeout(60*30), oc.tracking() as t:
            try:
                check_online_network_multitenant()
                check_prevents_cron_jobs()
                check_online_project_constraints
            except:
                logging.fatal('Error occurred during tests')
                traceback.print_exc()
                # print out all oc interactions and do not redact secret information
                print("Tracking:\n{}\n\n".format(t.get_result().as_json(redact_streams=False)))


#!/usr/bin/python

from __future__ import print_function

import argparse
import logging
import traceback
import openshift_client as oc
from openshift_client import OpenShiftPythonException
from openshift_client.decorators import ephemeral_project

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('EphemeralProject')
logger.setLevel(logging.INFO)


@ephemeral_project
def run_pods(pod_count=5, *, project_name=None):
    logger.info('Running in namespace: {}'.format(project_name))

    for i in range(pod_count):
        pod_name = 'pod-{}'.format(i)
        logger.info('Creating: {}'.format(pod_name))

        pod_selector = oc.create(oc.build_pod_simple(pod_name, image='python:3', command=['tail', '-f', '/dev/null']))
        pod_selector.until_all(1, success_func=oc.status.is_pod_running)

    pods = oc.selector('pods').objects()
    logger.info('Found {} pods'.format(len(pods)))
    assert len(pods) == pod_count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Demonstrate the ephemeral_project decorator')
    parser.add_argument('-b', '--bastion', default=None,
                        help='user@host, hostname, or IP on which to execute oc (oc is executed locally if not specified)',
                        required=False)
    parser.add_argument('--insecure-skip-tls-verify', action='store_true',
                        help='Skip TLS verify during oc interactions (recommended when replacing api certs)')
    parser.set_defaults(insecure_skip_tls_verify=False)

    params = vars(parser.parse_args())

    skip_tls_verify = params['insecure_skip_tls_verify']

    if skip_tls_verify:
        oc.set_default_skip_tls_verify(True)

    bastion_hostname = params['bastion']
    if not bastion_hostname:
        logging.info('Running in local mode. Expecting "oc" in PATH')

    with oc.client_host(hostname=bastion_hostname, username="root", auto_add_host=True, load_system_host_keys=False):
        # Ensure tests complete within 5 minutes and track all oc invocations
        with oc.timeout(60 * 5), oc.tracking() as t:
            try:
                run_pods()
            except (ValueError, OpenShiftPythonException, Exception):
                # Print out exception stack trace via the traceback module
                logger.info('Traceback output:\n{}\n'.format(traceback.format_exc()))

                # Print out all oc interactions and do not redact secret information
                logger.info("OC tracking output:\n{}\n".format(t.get_result().as_json(redact_streams=False)))

#!/usr/bin/python

from __future__ import print_function

import argparse
import logging
import traceback
import openshift as oc
from openshift import OpenShiftPythonException

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('ExceptionTracking')
logger.setLevel(logging.INFO)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Demonstrate oc tracking')
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
        logging.info('Running in local mode. Expecting "oc" in PATH')

    with oc.client_host(hostname=bastion_hostname, username="root", auto_add_host=True, load_system_host_keys=False):
        # Ensure tests complete within 30 minutes and track all oc invocations
        with oc.timeout(60 * 30), oc.tracking() as t:
            try:
                with oc.project('default'):
                    bc = oc.selector('bc/does-not-exist')
                    bc.start_build()
            except (ValueError, OpenShiftPythonException, Exception):
                # Print out exception stack trace via the traceback module
                logger.info('Traceback output:\n{}\n'.format(traceback.format_exc()))

                # Print out all oc interactions and do not redact secret information
                logger.info("OC tracking output:\n{}\n".format(t.get_result().as_json(redact_streams=False)))

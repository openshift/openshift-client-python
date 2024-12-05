#!/usr/bin/python

import argparse
import json
import logging
import sys
import traceback

import openshift_client as oc
from openshift_client import OpenShiftPythonException
from openshift_client.decorators import ephemeral_project

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(message)s')
logger = logging.getLogger('ModifyAndApply')


def validate_server_connection(ctx):
    with oc.options(ctx), oc.tracking(), oc.timeout(60):
        try:
            username = oc.whoami()
            version = oc.get_server_version()
            logger.debug(f'Connected to APIServer running version: {version}, as: {username}')
        except (ValueError, OpenShiftPythonException, Exception) as e:
            logger.error(f"Unable to verify cluster connection using context: \"{ctx['context']}\"")
            raise e


def test_update_dynamic_keyword_args(obj):
    def update_dynamic_keyword_args(apiobj, **kwargs):
        logger.info(f'Updating object: {apiobj.name()} with: {json.dumps(kwargs, indent=4, default=str)}')
        return False

    r, success = obj.modify_and_apply(update_dynamic_keyword_args, retries=0)
    assert len(r.actions()) == 0
    assert success == False

    r, success = obj.modify_and_apply(update_dynamic_keyword_args, retries=0, param1='foo')
    assert len(r.actions()) == 0
    assert success == False

    r, success = obj.modify_and_apply(update_dynamic_keyword_args, retries=0, param1='foo', param2='bar')
    assert len(r.actions()) == 0
    assert success == False

    r, success = obj.modify_and_apply(update_dynamic_keyword_args, retries=0, random1='foo', modnar1='bar')
    assert len(r.actions()) == 0
    assert success == False


def test_update_named_keyword_args(obj):
    def update_named_keyword_args(apiobj, param1=None, param2=None):
        logger.info(f'Updating object: {apiobj.name()} with "param1={param1}" and "param2={param2}"')
        return False

    r, success = obj.modify_and_apply(update_named_keyword_args, retries=0)
    assert len(r.actions()) == 0
    assert success == False

    r, success = obj.modify_and_apply(update_named_keyword_args, retries=0, param1='foo')
    assert len(r.actions()) == 0
    assert success == False

    r, success = obj.modify_and_apply(update_named_keyword_args, retries=0, param1='foo', param2='bar')
    assert len(r.actions()) == 0
    assert success == False

    try:
        obj.modify_and_apply(update_named_keyword_args, retries=0, param3='bip')
    except TypeError as e:
        if 'got an unexpected keyword argument' in e.__str__():
            logger.info(f'Unknown parameter specified: {e}')
        else:
            raise e


@ephemeral_project
def run(*, project_name=None):
    logger.info('Running in namespace: {}'.format(project_name))
    obj = oc.selector('serviceaccount/default').object()
    test_update_named_keyword_args(obj)
    test_update_dynamic_keyword_args(obj)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backup namespace resources')

    config_group = parser.add_argument_group('Configuration Options')
    config_group.add_argument('-v', '--verbose', help='Enable verbose output', action='store_true')

    ocp_group = parser.add_argument_group('Openshift Cluster Configuration Options')
    ocp_group.add_argument('-c', '--context', help='The OC context to use', default=None)
    ocp_group.add_argument('-k', '--kubeconfig', help='The kubeconfig to use (default is "~/.kube/config")', default=None)
    ocp_group.add_argument('-n', '--namespace', help='The namespace to process', default=None)

    args = vars(parser.parse_args())

    if args['verbose']:
        logger.setLevel(logging.DEBUG)

    # Validate the connection to the respective cluster
    context = {}
    if args['context'] is not None:
        context.update({'context': args['context']})

    if args['kubeconfig'] is not None:
        context.update({'kubeconfig': args['kubeconfig']})

    validate_server_connection(context)

    with oc.client_host():
        with oc.timeout(60 * 10), oc.tracking() as t:
            with oc.options(context):
                try:
                    run()
                except (ValueError, OpenShiftPythonException, Exception):
                    # Print out exception stack trace via the traceback module
                    logger.info('Traceback output:\n{}\n'.format(traceback.format_exc()))

                    # Print out all oc interactions and do not redact secret information
                    logger.info("OC tracking output:\n{}\n".format(t.get_result().as_json(redact_streams=False)))

#!/usr/bin/python

from __future__ import print_function

from ansible.module_utils.basic import AnsibleModule

import os
import StringIO
import tempfile
import shutil
import tarfile
import base64
import sys
import pprint


# Allows modules to trigger errors
def error(msg, **kwargs):
    import openshift as oc
    raise oc.OpenShiftPythonException(msg, **kwargs)


def main():
    import openshift as oc
    script = module.params["script"]
    time = module.params["timeout"]
    oc.ansible.reset()
    oc.ansible.vars = module.params["vars"]

    if time is not None:
        time = int(time)  # Allow time to come in as a string

    if module.params["project"] is not None:
        oc.context.default_project = module.params["project"]

    with oc.timeout(time):
        with oc.tracking() as ct:
            try:
                with oc.util.OutputCapture() as capture:
                    exec(script)

                module.debug("openshift_client_python module invocation result:\n" + str(ct.get_result()))
                module.exit_json(rc=ct.get_result().status(),
                                 changed=module.params['changes'],
                                 ansible_facts=oc.ansible.new_facts,
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 result=ct.get_result().as_dict()
                                 )
            except oc.OpenShiftPythonException as ose:
                module.debug("openshift_client_python module invocation exception: " + str(ose))
                module.debug("openshift_client_python module invocation result:\n" + str(ct.get_result()))
                module.fail_json(msg=ose.msg,
                                 rc=ose.result.status(),
                                 exception_attributes=ose.attributes(),
                                 changed=module.params['changes'] or oc.ansible.changed,
                                 ansible_facts=oc.ansible.new_facts,
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 result=ct.get_result().as_dict()
                                 )
            except KeyboardInterrupt:
                print('Received KeyboardInterrupt during module', file=sys.stderr)
                pprint.pprint(ct.get_result().as_dict(), stream=sys.stderr)
                raise


if __name__ == '__main__':
    # When openshift-client-python/ansible/rebuild_module.sh is executed, it will read in this template
    # and replace the following variable with a b64 encoded tarball of the openshift-client-library
    # package. The client_python_extract_dir path will contain the 'openshift' package directory.
    REPLACED_BY_REBUILD_MODULE = '{}'
    OPENSHIFT_CLIENT_PYTHON_TGZ = StringIO.StringIO(base64.b64decode(REPLACED_BY_REBUILD_MODULE))

    module = AnsibleModule(
        argument_spec=dict(
            script=dict(required=True),
            vars=dict(required=False, default={}, type='dict'),
            project=dict(required=False, default=None),
            timeout=dict(required=False, default=None, type='int'),
            changes=dict(required=False, default=False, type='bool')
        )
    )

    client_python_extract_dir = tempfile.mkdtemp()
    module.debug('Extracting openshift-client-python module to: {}'.format(client_python_extract_dir))

    try:
        tf = tarfile.open(fileobj=OPENSHIFT_CLIENT_PYTHON_TGZ, mode='r:gz')
        tf.extractall(client_python_extract_dir)
        # Add the newly extacted directory to the python path to resolve the openshift package
        sys.path.append(client_python_extract_dir)
        # Import openshift as oc so that we can delete the extract directory. module.exit_ type methods
        # call sys.exit, so this is our only chance to leave no trace.
        import openshift as oc
        shutil.rmtree(client_python_extract_dir)
        main()
    finally:
        if os.path.exists(client_python_extract_dir):
            shutil.rmtree(client_python_extract_dir)


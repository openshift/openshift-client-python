#!/usr/bin/python

from openshift.util import OutputCapture
from ansible.module_utils.basic import AnsibleModule

import openshift as oc


# Allows modules to trigger errors
def error(msg,**kwargs):
    raise oc.OpenShiftPythonException(msg, **kwargs)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            script=dict(required=True),
            vars=dict(required=False, default={}, type='dict'),
            project=dict(required=False, default=None),
            timeout=dict(required=False, default=None),
            changes=dict(required=False, default=True, type='bool')
        )
    )

    script = module.params["script"]
    time = module.params["timeout"]
    vars = module.params["vars"]

    if time is not None:
        time = int(time)  # Allow time to come in as a string

    if module.params["project"] is not None:
        oc.context.default_project = module.params["project"]

    new_facts = oc.Model()

    with oc.timeout(time):
        with oc.tracking() as ct:
            try:
                with OutputCapture() as capture:
                    exec script

                module.debug("openshift module invocation result:\n" + str(ct.get_result()))
                module.exit_json(rc=ct.get_result().status(),
                                 changed=module.params['changes'],
                                 ansible_facts=new_facts,
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 result=ct.get_result().as_dict()
                                 )
            except oc.OpenShiftPythonException as ose:
                module.debug("openshift module invocation exception: " + str(ose))
                module.debug("openshift module invocation result:\n" + str(ct.get_result()))
                module.fail_json(msg=ose.msg,
                                 rc=ose.result.status(),
                                 exception_attributes=ose.attributes(),
                                 changed=module.params['changes'],
                                 ansible_facts=new_facts,
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 result=ct.get_result().as_dict()
                                 )

if __name__ == '__main__':
    main()


#!/usr/bin/python

from openshift.util import OutputCapture
from ansible.module_utils.basic import AnsibleModule

from openshift import *


# Allows modules to trigger errors
def error(msg,**kwargs):
    raise OpenShiftException(msg, **kwargs)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            script=dict(required=True),
            project=dict(required=False, default=None),
            timeout=dict(required=False, default=None)
        )
    )

    script = module.params["script"]
    time = module.params["timeout"]

    if time is not None:
        time = int(time)  # Allow time to come in as a string

    if module.params["project"] is not None:
        set_default_project(module.params["project"])

    new_facts = Model()

    with timeout(time):
        with tracker() as ct:
            try:
                with OutputCapture() as capture:
                    exec script

                module.debug("openshift module invocation result:\n" + str(ct.get_result()))
                module.exit_json(rc=ct.get_result().status(),
                                 changed=len(ct.get_changes()) > 0,
                                 ansible_facts=new_facts,
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 actions=ct.get_result().actions()
                                 )
            except OpenShiftException as ose:
                module.debug("openshift module invocation exception: " + str(ose))
                module.debug("openshift module invocation result:\n" + str(ct.get_result()))
                module.fail_json(msg=ose.msg,
                                 rc=ose.result.status(),
                                 exception_attributes=ose.attributes(),
                                 changed=len(ct.get_changes()) > 0,
                                 ansible_facts=new_facts,
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 actions=ct.get_result().actions()
                                 )

if __name__ == '__main__':
    main()


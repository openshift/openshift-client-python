#!/usr/bin/python

from ansible.module_utils.basic import AnsibleModule

# The following lines force ansiballz to carry each of the files in
# module_utils in the payload. Without mentioning each, ansible only
# currently carries __init__.py without the files which support it.
# NOTE: If new files are added to the library, they must be mentioned here!
import ansible.module_utils.openshift.action as ___action
import ansible.module_utils.openshift.apiobject as ___apiobject
import ansible.module_utils.openshift.base_verbs as ___base_verbs
import ansible.module_utils.openshift.context as ___context
import ansible.module_utils.openshift.model as ___model
import ansible.module_utils.openshift.naming as ___naming
import ansible.module_utils.openshift.result as ___result
import ansible.module_utils.openshift.selector as ___selector
import ansible.module_utils.openshift.util as ___util
import ansible.module_utils.openshift.config as ___config
import ansible.module_utils.openshift.status as ___status

# Now actually import the package we need
import ansible.module_utils.openshift as oc


# Allows modules to trigger errors
def error(msg,**kwargs):
    raise oc.OpenShiftPythonException(msg, **kwargs)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            script=dict(required=True),
            vars=dict(required=False, default={}, type='dict'),
            project=dict(required=False, default=None),
            timeout=dict(required=False, default=None, type='int'),
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
                with oc.util.OutputCapture() as capture:
                    exec script

                module.debug("openshift_client_python module invocation result:\n" + str(ct.get_result()))
                module.exit_json(rc=ct.get_result().status(),
                                 changed=module.params['changes'],
                                 ansible_facts=new_facts._primitive(),
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
                                 changed=module.params['changes'],
                                 ansible_facts=new_facts._primitive(),
                                 stdout=capture.out.getvalue().decode('UTF-8'),
                                 stderr=capture.err.getvalue().decode('UTF-8'),
                                 result=ct.get_result().as_dict()
                                 )


if __name__ == '__main__':
    main()


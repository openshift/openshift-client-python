Role Name
=========

This role exposes the openshift_client_python module which allows you to use python leveraging
the openshift-client-python library directly within ansible playbooks.

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```snakeyaml
- hosts: servers
  gather_facts: False

  roles:
  - openshift_client_python

  tasks:

  - name: Set a fact to be used in script
    set_fact:
      op_types: "pods"

  - name: Await ingress

    openshift_client_python:
      # Default project scope unless overridden with oc.project.
      project: 'openshift-monitoring'

      # Timeout (seconds) applies to overall script / all oc interactions must complete.
      timeout: 15

      # If you know the script will make changes to the cluster, you can indicate it as a parameter.
      # Otherwise, set oc.ansible.changed inside of the script.
      changes: True

      # These values will be populated into oc.ansible.vars, which can be accessed within the script.
      vars:
        some_var_name: 'abc'
        another: 5

      script: |
        print('You can use an arg: {} and {}'.format(oc.ansible.vars['some_var_name'], oc.ansible.vars['another']))

        # "oc.ansible.new_facts" is a dict into which you can store new facts.
        # These facts will be set by ansible when the script exits.
        oc.ansible.new_facts['pods'] = oc.selector("{{op_types}}").qnames()

        oc.selector('route/prometheus-k8s').until_all(1, oc.status.is_route_admitted)

        # An alternate way of reporting a change occurred to the openshift_client_python ansible module.
        oc.ansible.changed = True

    # An oc.tracker object will be stored in the register variable. It will detail all
    # oc interactions performed by the script.
    register: result

  - name: Show tracking result (all oc interactions)
    debug:
      msg: "{{result}}"

  - name: Use those facts
    openshift_client_python:
      timeout: 60
      script: |
        with oc.project('openshift-monitoring'):

          def print_phase(pod_apiobj):
            print('Phase for {} = {}'.format(pod_apiobj.qname(), pod_apiobj.model.status.phase))

          oc.selector({{pods}}).for_each(print_phase)
```
     

License
-------

Apache License 2.0

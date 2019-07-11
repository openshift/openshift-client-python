Role Name
=========

This role exposes the openshift_client_python module which allows you to use python leveraging
the openshift-client-python library directly within ansible playbooks.

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```snakeyaml
- hosts: servers
  roles:
  - openshift_client_python
  
  tasks:
  - name: Run helloworld
    openshift_client_python:
      project: 'default'

      vars:
        some_var_name: 'abc'
        another: 5

      script: |
        print('You can use an arg: {} and {}'.format(vars['some_var_name'], vars['another']))

        # This example shows use of existing ansible facts (op_types) and storing a new one (pods).
        new_facts.pods = oc.selector("{{op_types}}").qnames()

    register: result
      
  - name: Show new_facts
    debug:
      msg: "{{pods}}"
```
     

License
-------

Apache License 2.0

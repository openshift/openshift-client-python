Role Name
=========

This role exposes the openshift-client-python module allows you to use python leveraging 
the openshift-client-python library directly within ansible playbooks.

Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------

A description of the settable variables for this role should go here, including any variables that are in defaults/main.yml, vars/main.yml, and any variables that can/should be set via parameters to the role. Any variables that are read from other roles and/or the global scope (ie. hostvars, group vars, etc.) should be mentioned here as well.

Dependencies
------------

A list of other roles hosted on Galaxy should go here, plus any details in regards to parameters that may need to be set for other roles, or variables that are used from other roles.

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```snakeyaml
- hosts: servers
  roles:
  - openshift
  
  tasks:
  - name: Run helloworld
    openshift-pthon:
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

BSD

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).

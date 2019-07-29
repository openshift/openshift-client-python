#!/usr/bin/python

from __future__ import absolute_import
from threading import local

# Used by openshift-client-python module to store new facts, variables, etc
# during the execution of a playbook task.
ansible = local()


def ansible_context_reset():

    # Facts set in this dict will be set as new facts when the task exits
    ansible.new_facts = {}

    # Will be populated with variables passed into the task
    ansible.vars = {}

    # Allows an ansible module script to indicate changes were made to the cluster
    ansible.changed = False


ansible.reset = ansible_context_reset
ansible.reset()

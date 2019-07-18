#!/bin/bash

if [[ -z "$1" ]]; then
    echo "Specify the hostname of a bastion with oc/kubeconfig ready for use."
    echo "Example: $0 my.bastion.hostname"
    exit 1
fi

ansible-playbook -vvvv sample_playbook.yml -i $1,

#!/bin/bash

if [[ -z "$1" ]]; then
    echo "Hostname is required for this operation"
    echo "Example: $0 int-2"
    exit 1
fi

echo "The following sample assumes that 'oc' is on the localhost and can communicate with an OpenShift cluster specified"
echo "Running..."
# export PYTHONPATH="$(pwd)/../packages"
ansible-playbook -vvvv sample_playbook.yml -i $1,

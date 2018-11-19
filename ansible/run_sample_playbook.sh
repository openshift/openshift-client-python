#!/bin/bash

echo "The following sample assumes that 'oc' is on the localhost and can communicate with an OpenShift cluster"
echo "Running..."
# export PYTHONPATH="$(pwd)/../packages"
ansible-playbook -vvvv sample_playbook.yml -i free-int-master,

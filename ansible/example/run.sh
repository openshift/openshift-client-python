#!/bin/bash

export PYTHONPATH="$(pwd)/../../packages"
ansible-playbook -vvv simple.yml

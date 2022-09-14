#!/bin/bash

SCRIPT_ROOT=$(dirname "${BASH_SOURCE[0]:-$0}")

export PYTHONPATH="${SCRIPT_ROOT}/packages"
cd ${SCRIPT_ROOT}/packages
python2 -m unittest discover
python3 -m unittest discover

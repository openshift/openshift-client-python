#!/bin/bash

SCRIPT_ROOT=$(dirname "${BASH_SOURCE[0]:-$0}")

export PYTHONPATH="${SCRIPT_ROOT}/packages"
cd ${SCRIPT_ROOT}/packages

if command -v python2 > /dev/null
then
  echo "python2: running unit tests"
  python2 -m unittest discover
else
  echo "python2 not detected. Skipping"
fi

echo "python3: running unit tests"
python3 -m unittest discover

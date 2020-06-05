#!/bin/bash

export PYTHONPATH="$(pwd)/packages"
cd $(pwd)/packages
python2 -m unittest discover
python3 -m unittest discover

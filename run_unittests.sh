#!/bin/bash

export PYTHONPATH="$(pwd)/packages"
cd $(pwd)/packages
python -m unittest discover

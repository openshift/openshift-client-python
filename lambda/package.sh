#!/bin/sh

set -e

F=$(pwd)/lambda-layer-model.zip
rm -f $F

pushd model
zip -r $F python/*


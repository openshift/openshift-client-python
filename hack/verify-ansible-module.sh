#!/usr/bin/bash

set -o errexit
set -o nounset
set -o pipefail

TEMP_DIR="$( mktemp -d )"
OUTPUT_DIR="${ARTIFACT_DIR:=${TEMP_DIR}}"
echo -e "Artifacts will be written to: ${OUTPUT_DIR}"

BASE_DIR="$( readlink -e $( dirname "${BASH_SOURCE[0]}" )/..)"

echo -e "\nVerifying ansible module"
cd ${BASE_DIR}/ansible
./rebuild_module.sh
git diff --exit-code rebuild_module.digest || (echo 'You need to run ansible/rebuild_module.sh and include changes in this PR' && exit 1)

exit 0

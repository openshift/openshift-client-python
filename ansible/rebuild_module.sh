#!/usr/bin/env bash

# Directory in which this script resides
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

TEMPLATE_FILE="$DIR/roles/openshift_client_python/library/openshift_client_python.template.py"
OUTPUT_FILE="$DIR/roles/openshift_client_python/library/openshift_client_python.py"

if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Unable to find template file: $TEMPLATE_FILE"
    exit 1
fi

PACKAGES_DIR="$DIR/../packages"
if [[ ! -d "$PACKAGES_DIR" ]]; then
    echo "Unable to find packages directory: $PACKAGES_DIR"
    exit 1
fi

pushd "$PACKAGES_DIR"
# Update module digest so that pr.groovy can ensure it is run after each module change
cat $(find openshift/ -name '*.py' | sort -d) | md5sum > $DIR/rebuild_module.digest
ENCODED_TGZ=$(tar c --owner=0 --numeric-owner --group=0 --mtime='UTC 2019-01-01' $(find openshift/ -name '*.py' | sort -d) | gzip -c -n | base64 --wrap=0)
popd

echo "#!/usr/bin/env python" > $OUTPUT_FILE
echo "# THIS IS A GENERATED FILE. DO NOT MODIFY IT" >> $OUTPUT_FILE
echo "# Modify: openshift_client_python.template.py and then run rebuild_module.sh to affect this file" >> $OUTPUT_FILE

replaced=0

while IFS= read -r line
do
    if [[ "$line" == "#!"* ]]; then  # Skip the shebang, we write it manually above
        continue
    fi
    if [[ "$line" == "    REPLACED_BY_REBUILD_MODULE = '{}'" ]]; then
        echo "    REPLACED_BY_REBUILD_MODULE = '${ENCODED_TGZ}'" >> "${OUTPUT_FILE}"
        replaced=1
    else
        echo "$line" >> "${OUTPUT_FILE}"
    fi
done < "$TEMPLATE_FILE"

if [[ "$replaced" != "1" ]]; then
    echo "Unable to find replacement pattern in template"
    exit 1
fi

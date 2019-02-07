#!/usr/bin/python

import argparse
import os
import yaml
import json
import hashlib

import openshift as oc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Apply the specified directory of yaml files against a cluster')
    parser.add_argument('-m', '--master', default=None,
                        help='The hostname or IP on which to run oc (oc is run locally if not specified)',
                        required=False)
    parser.add_argument('-d', '--dir', help='The directory of resources to process', required=True)
    args = vars(parser.parse_args())

    master_hostname = args['master']
    if not master_hostname:
        print('Running in local mode. Expecting "oc" in PATH')

    with oc.client_host(hostname=master_hostname, username="root", auto_add_host=True):

        yaml_dir = args['dir']
        for filename in os.listdir(yaml_dir):
            if filename.endswith(".yaml") or filename.endswith(".yml"):
                filepath = os.path.join(yaml_dir, filename)
                with open(filepath, 'r') as stream:
                    print("Processing file: " + filename)
                    d = yaml.load(stream)
                    sha = hashlib.sha1()
                    json_str = json.dumps(d, sort_keys=True, encoding="utf-8", separators=(',', ':'))
                    sha.update(json_str)
                    hashval = sha.hexdigest()

                    metadata = d.get('metadata', None)
                    if metadata is None:
                        raise "Expected metadata field in resource file: " + filename

                    labels = metadata.get('labels', dict())
                    metadata['labels'] = labels

                    annotations = metadata.get('annotations', dict())
                    metadata['annotations'] = annotations

                    labels['openshift-python-applier'] = hashval
                    annotations['openshift-python-applier/applied'] = json_str

                    oc.apply(d)
                continue
            else:
                continue

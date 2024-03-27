#!/usr/bin/python

import openshift_client as oc

if __name__ == '__main__':
    options = {
        'as': 'system:admin',
    }

    with oc.client_host():
        with oc.timeout(60 * 5):
            with oc.options(options):
                with oc.project("openshift-etcd"):
                    pods = oc.selector("pods", labels={'app': 'etcd'}).objects()
                    print(f'Found: {len(pods)} pods')
                    result = pods[0].execute(cmd_to_exec=['etcdctl', 'endpoint', 'status', '--cluster', '-w', 'table'])
                    print(f'Result:\n{result.out()}')

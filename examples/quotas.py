#!/usr/bin/python

import openshift_client as oc

if __name__ == '__main__':
    with oc.client_host():
        with oc.timeout(60 * 5):
            with oc.project('openshift-client-python'):
                resource_quotas = oc.selector('resourcequotas').objects()
                print(f'Found: {len(resource_quotas)} ResourceQuotas')

                for resource_quota in resource_quotas:
                    print(f'Processing ResourceQuota: {resource_quota.name()}')
                    for key in resource_quota.model.spec.hard:
                        print(f'  - {key}: {resource_quota.model.spec.hard[key]}')

                limit_ranges = oc.selector('limitranges').objects()
                print(f'\nFound: {len(limit_ranges)} LimitRanges')

                for limit_range in limit_ranges:
                    print(f'Processing LimitRange: {limit_range.name()}')
                    for limit in limit_range.model.spec.limits:
                        print(f'  Type: {limit.type}')
                        print(f'    Default CPU Limit: {limit.default.cpu}')
                        print(f'    Default Memory Limit: {limit.default.memory}')
                        print(f'    Default CPU Request: {limit.defaultRequest.cpu}')
                        print(f'    Default Memory Request: {limit.defaultRequest.memory}')

                pods = oc.selector('pods').objects()
                print(f'\nFound: {len(pods)} Pods')

                for pod in pods:
                    print(f'Processing Pod: {pod.name()}')
                    for container in pod.model.spec.containers:
                        print(f'  Processing Container: {container.name}')
                        print(f'    CPU Limit: {container.resources.limits.cpu}')
                        print(f'    CPU Request: {container.resources.requests.cpu}')
                        print(f'    Memory Limit: {container.resources.limits.memory}')
                        print(f'    Memory Request: {container.resources.requests.memory}')

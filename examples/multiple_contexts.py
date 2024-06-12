import openshift_client as oc

if __name__ == '__main__':
    context1 = {
        'context': 'cluster1',
    }
    context2 = {
        'context': 'cluster2',
    }
    with oc.client_host():
        with oc.timeout(60 * 5):
            for context in [context1, context2]:
                with oc.options(context):
                    with oc.project('my-project'):
                        jobs_list = oc.selector('pods').objects()
                        print(f'Found: {len(jobs_list)} pods in: {context["context"]}')

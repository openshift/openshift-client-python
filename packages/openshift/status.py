#!/usr/bin/python


def is_route_admitted(apiobj):
    return apiobj.model.status.can_match({
        'ingress': [
            {
                'conditions': [
                    {
                        'type': 'Admitted',
                        'status': 'True',
                    }
                ]
            }
        ]
    })


def is_pod_running(apiobj):
    return apiobj.model.status.phase == 'Running'


def is_node_ready(apiobj):
    return apiobj.model.status.conditions.can_match({
        'type': 'Ready',
        'status': 'True',
    })
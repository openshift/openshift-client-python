from __future__ import absolute_import

from .model import Missing


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


def is_pod_succeeded(apiobj):
    return apiobj.model.status.phase == 'Succeeded'


def is_node_ready(apiobj):
    return apiobj.model.status.conditions.can_match({
        'type': 'Ready',
        'status': 'True',
    })


def is_operator_ready(operator_apiobj):

    # Operator not reporting conditions yet?
    if not operator_apiobj.model.status.conditions:
        return False

    happy = True
    for condition in operator_apiobj.model.status.conditions:

        if condition.type == "Progressing" and condition.status == "True":
            happy = False

        if condition.type == "Failing" and condition.status == "True":
            happy = False

        # Degraded replaced 'Failing' in 4.1
        if condition.type == "Degraded" and condition.status == "True":
            happy = False

        if condition.type == "Available" and condition.status == "False":
            happy = False

    return happy


def is_credentialsrequest_provisioned(apiobj):
    if apiobj.model.status.provisioned is not Missing:
        return apiobj.model.status.provisioned  # This is a boolean
    return False


def is_pvc_bound(apiobj):
    return apiobj.model.status.phase == 'Bound'


def is_imagestream_imported(apiobj):
    """
    Returns False if an imagestream reports an issue
    importing images. Recommended that you run import-image --all
    against the imagestream.
    """
    return not apiobj.model.status.tags.can_match(
            {
                'conditions': [
                    {
                        'type': 'ImportSuccess',
                        'status': 'False'
                    }
                ]
            }
    )

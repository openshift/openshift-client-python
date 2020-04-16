from __future__ import absolute_import

import openshift as oc
import base64
import json


def get_kubeconfig():
    """
    :return: Returns the current kubeconfig as a python dict
    """
    return json.loads(oc.invoke('config',
                                cmd_args=['view',
                                          '-o=json',
                                          '--raw',
                                          ],
                                no_namespace=True).out().strip())


def _get_kubeconfig_model(_kc_model=None):
    if _kc_model:
        return _kc_model
    else:
        return oc.Model(dict_to_model=get_kubeconfig())


def get_kubeconfig_cluster_names(_kc_model=None):
    """
    :param _kc_model: Internally used to cache kubeconfig info.
    :return: Returns a list of all the cluster names in the kubeconfig.
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    names = []
    for cluster_entry in kc.clusters:
        names.append(cluster_entry.name)
    return names


def get_kubeconfig_current_context_name(_kc_model=None):
    """
    :param _kc_model: Internally used to cache kubeconfig info.
    :return: Returns the name of the current context in your kubeconfig
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    return kc['current-context']


def get_kubeconfig_context(context_name=None, _kc_model=None):
    """
    :param _kc_model: Internally used to cache kubeconfig info.
    :param context_name: The context to retrieve or None to retrieve the current context.
    :return: Returns a dict of the specified context or current context. e.g. {cluster:..., namespace:...., user:....}
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    if context_name is None:
        context_name = get_kubeconfig_current_context_name(_kc_model=kc)

    for context_entry in kc.contexts:
        if context_entry.name == context_name:
            return context_entry.context._primitive()

    return None


def get_kubeconfig_current_cluster_name(_kc_model=None):
    """
    :param _kc_model: Internally used to cache kubeconfig info.
    :return: Returns the cluster associated with the current context.
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    current_context_name = get_kubeconfig_current_context_name(_kc_model=kc)
    return get_kubeconfig_context(context_name=current_context_name, _kc_model=kc)['cluster']


def get_kubeconfig_cluster(cluster_name=None, _kc_model=None):
    """
    :param cluster_name: The context to retrieve or None for current context dict
    :param _kc_model: Internally used to cache kubeconfig info.
    :return: Returns a raw bytes from kubeconfig in a dict of the specified cluster or current cluster.
        e.g. {server:.. certificate-authority-data:.}. Note that since the bytes are raw, an entry like
        certificate-data-authority would need to be decoded to get PEM content.
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    if cluster_name is None:
        cluster_name = get_kubeconfig_current_cluster_name(_kc_model=kc)

    for cluster_entry in kc.clusters:
        if cluster_entry.name == cluster_name:
            return cluster_entry.cluster._primitive()

    return None


def set_kubeconfig_insecure_skip_tls_verify(active, cluster_name=None, _kc_model=None):
    """
    Sets or removes insecure-skip-tls-verify for the specified cluster (or the current cluster if
    not specified).
    :param active: If True, enable insecure-skip-tls-verify for the the cluster
    :param cluster_name: The cluster name to modify. If not specified, the current context's cluster will be modified.
    :param _kc_model: Internally used to cache kubeconfig info.
    """
    if not cluster_name:
        cluster_name = get_kubeconfig_current_cluster_name(_kc_model=_kc_model)

    oc.invoke('config',
              cmd_args=['set-cluster',
                        cluster_name,
                        '--insecure-skip-tls-verify={}'.format(str(active).lower()),
                        ],
              no_namespace=True)


def remove_kubeconfig_certifcate_authority(cluster_name=None, _kc_model=None):
    """
    When you installer a valid certificate for your api endpoint, you may want to
    use your host's local certificate authorities. To do that, references to certificate
    authorities must be removed from your kubeconfig.
    :param cluster_name: The cluster name to modify. If not specified, the current context's cluster will be modified.
    :param _kc_model: Internally used to cache kubeconfig info.
    """
    if not cluster_name:
        cluster_name = get_kubeconfig_current_cluster_name(_kc_model=_kc_model)

    # Setting insecure will remove any other certificate-authority data from the cluster's entry
    set_kubeconfig_insecure_skip_tls_verify(True, cluster_name=cluster_name, _kc_model=_kc_model)

    # Now set it back to false, removing the insecure-skip-tls-verify entry from kubeconfig
    set_kubeconfig_insecure_skip_tls_verify(False, cluster_name=cluster_name, _kc_model=_kc_model)


def get_kubeconfig_certificate_authority_data(cluster_name=None, _kc_model=None):
    """
    Returns the certificate authority data (if any) for the specified cluster.
    :param cluster_name: The cluster name to inspect. If not specified, the ca data will be
    returned for the current context's cluster.
    :param _kc_model: Internally used to cache kubeconfig info.
    :return: The PEM encoded x509 data or None if the cluster did not posses a certificate-authority-data
    field.
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    if not cluster_name:
        cluster_name = get_kubeconfig_current_cluster_name(_kc_model=kc)

    cluster_dict = get_kubeconfig_cluster(cluster_name, _kc_model=kc)
    data = cluster_dict.get('certificate-authority-data', None)

    if data:
        # the data is base64 encoded PEM, so decode it.
        return base64.b64decode(data)

    return None


def set_kubeconfig_certificate_authority_data(ca_data, cluster_name=None, _kc_model=None):
    """
    Sets the certificate authority data for one or more clusters in the kubeconfig.
    :param ca_data: The certificate authority data (PEM format). The chain will be encoded into
    base64 before being set in the kubeconfig.
    :param cluster_name: The cluster name to affect. If not specified, the ca data will be
    set for the current context.
    :param _kc_model: Internally used to cache kubeconfig info.
    :return: n/a
    """
    kc = _get_kubeconfig_model(_kc_model=_kc_model)
    if not cluster_name:
        cluster_name = get_kubeconfig_current_cluster_name(_kc_model=kc)

    # The kubeconfig cluster entry may have an existing certificate-authority file or have
    # insecure-skip-tls-verify set to true. Have ca-data set alongside either of these is
    # an invalid state for the kubeconfig, so we use a trick: setting insecure-skip-tls-verify
    # will clear existing certificate authority entries. When we set it back to true, we can
    # safely poke in the ca-data

    remove_kubeconfig_certifcate_authority(cluster_name=cluster_name, _kc_model=kc)

    b64_data = base64.b64encode(ca_data)

    # Now we can poke in the value that we need
    oc.invoke('config',
              # https://github.com/kubernetes/kubectl/issues/501#issuecomment-406890261
              cmd_args=['set',
                        'clusters.{}.certificate-authority-data'.format(cluster_name),
                        b64_data
                        ],
              no_namespace=True)

from __future__ import absolute_import

import six

# A dict of name -> APIResource.
# keys include shortnames, full names, uppercamel Kind, and lowercase kind
# this map is managed by register_api_resource
# todo: make thread & context safe?
_api_resource_lookup = {}

# A list of APIResources which have been register; todo: make thread & context safe?
_api_resources = list()


class APIResource:

    def __init__(self, name, group, kind, namespaced, shortnames=None):
        self.name = name
        self.kind = kind
        self.group = group
        self.namespaced = namespaced

        if shortnames is None:
            shortnames = []

        self.shortnames = shortnames

        if group:
            self.full_name = '{}.{}'.format(name, group)
        else:
            self.full_name = name


def register_api_resource(api_resource):
    _api_resources.append(api_resource)
    _api_resource_lookup[api_resource.full_name] = api_resource
    _api_resource_lookup[api_resource.kind] = api_resource
    _api_resource_lookup[api_resource.kind.lower()] = api_resource
    for shortname in api_resource.shortnames:
        _api_resource_lookup[shortname] = api_resource


def get_api_resources_kinds():
    """
    Returns a list of 'gettable' (i.e. oc get kind will work) kinds known to openshift-client-python. Run
    update_api_resources first if this needs to be exact for a cluster.
    :return: list<string> where each entry is a kind (qualified by group if available)
    """

    kinds = set()
    for api_resource in _api_resources:
        kinds.add(api_resource.full_name)

    # until https://bugzilla.redhat.com/show_bug.cgi?id=1684311 fixed
    ungettable = set()
    ungettable.update("""
rangeallocations.security.openshift.io
useridentitymappings.user.openshift.io
""".strip().split())

    return kinds.difference(ungettable)


def normalize_kind(kind):
    """
    Normalizes the kind string argument. If a shortname or plural, the lowercase kind
    is returned. For example 'po' -> 'pod'. 'Endpoints' -> 'endpoints'.
    :param kind: The kind string to normalize
    :return: Returns the normalized kind string.
    """

    kind = kind.strip().lower()

    # if a fully qualified kind is supplied, don't assume we know better
    if '.' in kind:
        return kind

    # if the kind is in the dict, we are done
    if kind in _api_resource_lookup:
        # Lookup the entry and return the real kind name
        return _api_resource_lookup[kind].kind.lower()

    if kind.endswith("s"):
        singular_kind = kind[:-1]
        if singular_kind in _api_resource_lookup:
            return _api_resource_lookup[singular_kind].kind.lower()

    # if we kind find it, just assume the user knows what they are doing
    return kind


def normalize_kinds(kinds):
    """
    Uses normalize_kind to normalize a single kind name or a list of kind names.
    :param kinds: A single string or a list of strings to be normalized.
    :return: Returns a list of normalized kind strings.
    """
    # if we receive a simple string, massage into a list before processing
    if isinstance(kinds, six.string_types):
        kinds = [kinds]

    normalized = []
    for k in kinds:
        normalized.append(normalize_kind(k))

    return normalized


def kind_matches(k1, k2_or_list):
    k1 = normalize_kind(k1)

    # If a single string is provided, turn it into a list
    if isinstance(k2_or_list, six.string_types):
        k2_or_list = [k2_or_list]

    for k2e in k2_or_list:
        k2e = normalize_kind(k2e)
        if k1 == k2e or k1.startswith(k2e + '.') or k2e.startswith(k1 + '.'):
            return True

    return False


def qname_matches(qn1, qn2_or_list):
    qn1 = normalize_kind(qn1)

    # If a single string is provided, turn it into a list
    if isinstance(qn2_or_list, six.string_types):
        qn2_or_list = [qn2_or_list]

    _, kind1, name1 = split_fqn(qn1)

    for qn2e in qn2_or_list:
        _, kind2, name2 = split_fqn(qn2e)

        if name1 == name2 and kind_matches(kind1, kind2):
            return True

    return False


def qualify_name(name_or_qname, to_kind):
    """
    Formats a name or qualified name (kind/name) into a qualified
    name of the specified target kind.
    :param name_or_qname: The name to transform
    :param to_kind: The kind to apply
    :return: A qualified name like: kind/name
    """

    if '/' in name_or_qname:
        name_or_qname = name_or_qname.split('/')[-1]
    return '{}/{}'.format(to_kind, name_or_qname)


def split_fqn(fqn, default_name=None, default_kind=None, default_namespace=None):
    """
    Splits a fully qualified name ('namespace:kind/name') into its components.
    :return: ns, kind, name . If a component is missing, the associated default argument value will be returned instead.
    """
    remainder = fqn
    ns = default_namespace
    if ':' in remainder:
        ns_test, remainder = remainder.split(':', 1)
        if ns_test:
            ns = ns_test

    kind = default_kind
    if '/' in remainder:
        kind_test, remainder = remainder.split('/', 1)
        if kind_test:
            kind = kind_test

    name = default_name
    if remainder:
        name = remainder

    return ns, kind, name


def process_api_resources_output(output):

    """
    Invoke this method with the output of `oc api-resources` and it will update openshift-client-python's
    internal understanding of api resource names / kinds. openshift-client-python comes with a built in
    set of shortnames and common kind information, so this is often not necessary.
    :param output: The output of `oc api-resources`
    :return: N/A.
    """

    # Reset the global maps so that we can repopulate them
    global _api_resource_lookup
    _api_resource_lookup = {}
    global _api_resources
    _api_resources = list()

    lines = output.strip().splitlines()
    it = iter(lines)
    header = next(it).lower()
    column_pos = {}  # maps column name to
    column_names = ['name', 'shortnames', 'apigroup', 'namespaced', 'kind']
    for column_name in column_names:
        pos = header.find(column_name)
        if pos == -1:
            raise IOError('Unable to find column: {} in api-resource output'.format(column_name.upper()))
        column_pos[column_name] = pos

    def get_column_value(line, column_name):
        # jump to where this column starts and copy up to the end of the line
        start = line[column_pos[column_name]:]
        # if there is a space at this column position, the column has no value
        if start.startswith(' '):
            return ''
        # otherwise, split on whitespace and use the first value we find
        val = start.split()[0].strip()
        return val

    # Read all lines after the header
    while True:
        try:
            line = next(it).strip()
            if not line:
                continue
            res = APIResource(
                name=get_column_value(line, 'name'),
                group=get_column_value(line, 'apigroup'),
                kind=get_column_value(line, 'kind'),
                namespaced='t' in get_column_value(line, 'namespaced').lower(),
                shortnames=get_column_value(line, 'shortnames').split(','),
            )
            register_api_resource(res)
        except StopIteration:
            break


# just paste the output of `oc api-resources --verbs=get` in this variable (including header!).
# It will be processed on startup. this could eventually be replaced with
# calls to --raw 'api/v1', 'apis/..../v1'.. etc, but let oc do the work for us.
_default_api_resources = """
NAME                               SHORTNAMES       APIGROUP                              NAMESPACED   KIND
componentstatuses                  cs                                                     false        ComponentStatus
configmaps                         cm                                                     true         ConfigMap
endpoints                          ep                                                     true         Endpoints
events                             ev                                                     true         Event
limitranges                        limits                                                 true         LimitRange
namespaces                         ns                                                     false        Namespace
nodes                              no                                                     false        Node
persistentvolumeclaims             pvc                                                    true         PersistentVolumeClaim
persistentvolumes                  pv                                                     false        PersistentVolume
pods                               po                                                     true         Pod
podtemplates                                                                              true         PodTemplate
replicationcontrollers             rc                                                     true         ReplicationController
resourcequotas                     quota                                                  true         ResourceQuota
secrets                                                                                   true         Secret
serviceaccounts                    sa                                                     true         ServiceAccount
services                           svc                                                    true         Service
mutatingwebhookconfigurations                       admissionregistration.k8s.io          false        MutatingWebhookConfiguration
validatingwebhookconfigurations                     admissionregistration.k8s.io          false        ValidatingWebhookConfiguration
customresourcedefinitions          crd,crds         apiextensions.k8s.io                  false        CustomResourceDefinition
apiservices                                         apiregistration.k8s.io                false        APIService
controllerrevisions                                 apps                                  true         ControllerRevision
daemonsets                         ds               apps                                  true         DaemonSet
deployments                        deploy           apps                                  true         Deployment
replicasets                        rs               apps                                  true         ReplicaSet
statefulsets                       sts              apps                                  true         StatefulSet
deploymentconfigs                  dc               apps.openshift.io                     true         DeploymentConfig
clusterrolebindings                                 authorization.openshift.io            false        ClusterRoleBinding
clusterroles                                        authorization.openshift.io            false        ClusterRole
rolebindingrestrictions                             authorization.openshift.io            true         RoleBindingRestriction
rolebindings                                        authorization.openshift.io            true         RoleBinding
roles                                               authorization.openshift.io            true         Role
horizontalpodautoscalers           hpa              autoscaling                           true         HorizontalPodAutoscaler
clusterautoscalers                                  autoscaling.openshift.io              false        ClusterAutoscaler
machineautoscalers                                  autoscaling.openshift.io              true         MachineAutoscaler
cronjobs                           cj               batch                                 true         CronJob
jobs                                                batch                                 true         Job
buildconfigs                       bc               build.openshift.io                    true         BuildConfig
builds                                              build.openshift.io                    true         Build
certificatesigningrequests         csr              certificates.k8s.io                   false        CertificateSigningRequest
credentialsrequests                                 cloudcredential.openshift.io          true         CredentialsRequest
apiservers                                          config.openshift.io                   false        APIServer
authentications                                     config.openshift.io                   false        Authentication
builds                                              config.openshift.io                   false        Build
clusteroperators                   co               config.openshift.io                   false        ClusterOperator
clusterversions                                     config.openshift.io                   false        ClusterVersion
consoles                                            config.openshift.io                   false        Console
dnses                                               config.openshift.io                   false        DNS
featuregates                                        config.openshift.io                   false        FeatureGate
images                                              config.openshift.io                   false        Image
infrastructures                                     config.openshift.io                   false        Infrastructure
ingresses                                           config.openshift.io                   false        Ingress
networks                                            config.openshift.io                   false        Network
oauths                                              config.openshift.io                   false        OAuth
projects                                            config.openshift.io                   false        Project
schedulers                                          config.openshift.io                   false        Scheduler
leases                                              coordination.k8s.io                   true         Lease
events                             ev               events.k8s.io                         true         Event
daemonsets                         ds               extensions                            true         DaemonSet
deployments                        deploy           extensions                            true         Deployment
ingresses                          ing              extensions                            true         Ingress
networkpolicies                    netpol           extensions                            true         NetworkPolicy
podsecuritypolicies                psp              extensions                            false        PodSecurityPolicy
replicasets                        rs               extensions                            true         ReplicaSet
machinehealthchecks                                 healthchecking.openshift.io           true         MachineHealthCheck
images                                              image.openshift.io                    false        Image
imagestreamimages                  isimage          image.openshift.io                    true         ImageStreamImage
imagestreams                       is               image.openshift.io                    true         ImageStream
imagestreamtags                    istag            image.openshift.io                    true         ImageStreamTag
configs                                             imageregistry.operator.openshift.io   false        Config
network-attachment-definitions     net-attach-def   k8s.cni.cncf.io                       true         NetworkAttachmentDefinition
machines                                            machine.openshift.io                  true         Machine
machinesets                                         machine.openshift.io                  true         MachineSet
containerruntimeconfigs            ctrcfg           machineconfiguration.openshift.io     false        ContainerRuntimeConfig
controllerconfigs                                   machineconfiguration.openshift.io     false        ControllerConfig
kubeletconfigs                                      machineconfiguration.openshift.io     false        KubeletConfig
machineconfigpools                                  machineconfiguration.openshift.io     false        MachineConfigPool
machineconfigs                                      machineconfiguration.openshift.io     false        MachineConfig
mcoconfigs                                          machineconfiguration.openshift.io     true         MCOConfig
nodes                                               metrics.k8s.io                        false        NodeMetrics
pods                                                metrics.k8s.io                        true         PodMetrics
alertmanagers                                       monitoring.coreos.com                 true         Alertmanager
prometheuses                                        monitoring.coreos.com                 true         Prometheus
prometheusrules                                     monitoring.coreos.com                 true         PrometheusRule
servicemonitors                                     monitoring.coreos.com                 true         ServiceMonitor
clusternetworks                                     network.openshift.io                  false        ClusterNetwork
egressnetworkpolicies                               network.openshift.io                  true         EgressNetworkPolicy
hostsubnets                                         network.openshift.io                  false        HostSubnet
netnamespaces                                       network.openshift.io                  false        NetNamespace
networkpolicies                    netpol           networking.k8s.io                     true         NetworkPolicy
oauthaccesstokens                                   oauth.openshift.io                    false        OAuthAccessToken
oauthauthorizetokens                                oauth.openshift.io                    false        OAuthAuthorizeToken
oauthclientauthorizations                           oauth.openshift.io                    false        OAuthClientAuthorization
oauthclients                                        oauth.openshift.io                    false        OAuthClient
authentications                                     operator.openshift.io                 false        Authentication
consoles                                            operator.openshift.io                 false        Console
dnses                                               operator.openshift.io                 false        DNS
ingresscontrollers                                  operator.openshift.io                 true         IngressController
kubeapiservers                                      operator.openshift.io                 false        KubeAPIServer
kubecontrollermanagers                              operator.openshift.io                 false        KubeControllerManager
kubeschedulers                                      operator.openshift.io                 false        KubeScheduler
networks                                            operator.openshift.io                 false        Network
openshiftapiservers                                 operator.openshift.io                 false        OpenShiftAPIServer
openshiftcontrollermanagers                         operator.openshift.io                 false        OpenShiftControllerManager
servicecas                                          operator.openshift.io                 false        ServiceCA
servicecatalogapiservers                            operator.openshift.io                 false        ServiceCatalogAPIServer
servicecatalogcontrollermanagers                    operator.openshift.io                 false        ServiceCatalogControllerManager
catalogsourceconfigs               csc              operators.coreos.com                  true         CatalogSourceConfig
catalogsources                     catsrc           operators.coreos.com                  true         CatalogSource
clusterserviceversions             csv,csvs         operators.coreos.com                  true         ClusterServiceVersion
installplans                       ip               operators.coreos.com                  true         InstallPlan
operatorgroups                     og               operators.coreos.com                  true         OperatorGroup
operatorsources                    opsrc            operators.coreos.com                  true         OperatorSource
subscriptions                      sub,subs         operators.coreos.com                  true         Subscription
packagemanifests                                    packages.operators.coreos.com         true         PackageManifest
poddisruptionbudgets               pdb              policy                                true         PodDisruptionBudget
podsecuritypolicies                psp              policy                                false        PodSecurityPolicy
projects                                            project.openshift.io                  false        Project
appliedclusterresourcequotas                        quota.openshift.io                    true         AppliedClusterResourceQuota
clusterresourcequotas              clusterquota     quota.openshift.io                    false        ClusterResourceQuota
clusterrolebindings                                 rbac.authorization.k8s.io             false        ClusterRoleBinding
clusterroles                                        rbac.authorization.k8s.io             false        ClusterRole
rolebindings                                        rbac.authorization.k8s.io             true         RoleBinding
roles                                               rbac.authorization.k8s.io             true         Role
routes                                              route.openshift.io                    true         Route
configs                                             samples.operator.openshift.io         false        Config
priorityclasses                    pc               scheduling.k8s.io                     false        PriorityClass
rangeallocations                                    security.openshift.io                 false        RangeAllocation
securitycontextconstraints         scc              security.openshift.io                 false        SecurityContextConstraints
storageclasses                     sc               storage.k8s.io                        false        StorageClass
volumeattachments                                   storage.k8s.io                        false        VolumeAttachment
brokertemplateinstances                             template.openshift.io                 false        BrokerTemplateInstance
templateinstances                                   template.openshift.io                 true         TemplateInstance
templates                                           template.openshift.io                 true         Template
tuneds                                              tuned.openshift.io                    true         Tuned
groups                                              user.openshift.io                     false        Group
identities                                          user.openshift.io                     false        Identity
useridentitymappings                                user.openshift.io                     false        UserIdentityMapping
users                                               user.openshift.io                     false        User
"""

process_api_resources_output(_default_api_resources)


# A dict of name -> APIResource.
# keys include shortnames, full names, uppercamel Kind, and lowercase kind
# this map is managed by register_api_resource
_api_resource_lookup = {
}


class APIResource:

    def __init__(self, name, group, kind, namespaced, shortnames=[]):
        self.name = name
        self.kind = kind
        self.group = group
        self.namespaced = namespaced
        self.shortnames = shortnames


def register_api_resource(api_resource):
    if api_resource.group:
        fullname = '{}.{}'.format(api_resource.group, api_resource.name)
    else:
        fullname = api_resource.name

    _api_resource_lookup[fullname] = api_resource
    _api_resource_lookup[api_resource.kind] = api_resource
    _api_resource_lookup[api_resource.kind.lower()] = api_resource
    for shortname in api_resource.shortnames:
        _api_resource_lookup[shortname] = api_resource


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
    if isinstance(kinds, basestring):
        kinds = [kinds]

    normalized = []
    for k in kinds:
        normalized.append(normalize_kind(k))

    return normalized


def kind_matches(k1, k2_or_list):
    k1 = normalize_kind(k1)

    # If a single string is provided, turn it into a list
    if isinstance(k2_or_list, basestring):
        k2_or_list = [k2_or_list]

    for k2e in k2_or_list:
        k2e = normalize_kind(k2e)
        if k1 == k2e or k1.startswith(k2e + '.') or k2e.startswith(k1 + '.'):
            return True

    return False


def qname_matches(qn1, qn2_or_list):
    qn1 = normalize_kind(qn1)

    # If a single string is provided, turn it into a list
    if isinstance(qn2_or_list, basestring):
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
    Invoke this method with the output of `oc api-resources` and it will update openshift-python's
    internal understanding of api resource names / kinds. openshift-python comes with a built in
    set of shortnames and common kind information, so this is often not necessary.
    :param output: The output of `oc api-resources`
    :return: N/A.
    """

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

# just paste the output of `oc api-resources` in this variable (including header!). It will be processed on startup.
# this could eventually be replaced with calls to --raw 'api/v1', 'apis/..../v1'.. etc, but let oc
# do the work for us.
_default_api_resources = """
NAME                                  SHORTNAMES     APIGROUP                       NAMESPACED   KIND
bindings                                                                            true         Binding
componentstatuses                     cs                                            false        ComponentStatus
configmaps                            cm                                            true         ConfigMap
endpoints                             ep                                            true         Endpoints
events                                ev                                            true         Event
limitranges                           limits                                        true         LimitRange
namespaces                            ns                                            false        Namespace
nodes                                 no                                            false        Node
persistentvolumeclaims                pvc                                           true         PersistentVolumeClaim
persistentvolumes                     pv                                            false        PersistentVolume
pods                                  po                                            true         Pod
podtemplates                                                                        true         PodTemplate
replicationcontrollers                rc                                            true         ReplicationController
resourcequotas                        quota                                         true         ResourceQuota
secrets                                                                             true         Secret
securitycontextconstraints            scc                                           false        SecurityContextConstraints
serviceaccounts                       sa                                            true         ServiceAccount
services                              svc                                           true         Service
mutatingwebhookconfigurations                        admissionregistration.k8s.io   false        MutatingWebhookConfiguration
validatingwebhookconfigurations                      admissionregistration.k8s.io   false        ValidatingWebhookConfiguration
customresourcedefinitions             crd,crds       apiextensions.k8s.io           false        CustomResourceDefinition
apiservices                                          apiregistration.k8s.io         false        APIService
controllerrevisions                                  apps                           true         ControllerRevision
daemonsets                            ds             apps                           true         DaemonSet
deployments                           deploy         apps                           true         Deployment
replicasets                           rs             apps                           true         ReplicaSet
statefulsets                          sts            apps                           true         StatefulSet
deploymentconfigs                     dc             apps.openshift.io              true         DeploymentConfig
tokenreviews                                         authentication.k8s.io          false        TokenReview
localsubjectaccessreviews                            authorization.k8s.io           true         LocalSubjectAccessReview
selfsubjectaccessreviews                             authorization.k8s.io           false        SelfSubjectAccessReview
selfsubjectrulesreviews                              authorization.k8s.io           false        SelfSubjectRulesReview
subjectaccessreviews                                 authorization.k8s.io           false        SubjectAccessReview
clusterrolebindings                                  authorization.openshift.io     false        ClusterRoleBinding
clusterroles                                         authorization.openshift.io     false        ClusterRole
localresourceaccessreviews                           authorization.openshift.io     true         LocalResourceAccessReview
localsubjectaccessreviews                            authorization.openshift.io     true         LocalSubjectAccessReview
resourceaccessreviews                                authorization.openshift.io     false        ResourceAccessReview
rolebindingrestrictions                              authorization.openshift.io     true         RoleBindingRestriction
rolebindings                                         authorization.openshift.io     true         RoleBinding
roles                                                authorization.openshift.io     true         Role
selfsubjectrulesreviews                              authorization.openshift.io     true         SelfSubjectRulesReview
subjectaccessreviews                                 authorization.openshift.io     false        SubjectAccessReview
subjectrulesreviews                                  authorization.openshift.io     true         SubjectRulesReview
horizontalpodautoscalers              hpa            autoscaling                    true         HorizontalPodAutoscaler
cronjobs                              cj             batch                          true         CronJob
jobs                                                 batch                          true         Job
buildconfigs                          bc             build.openshift.io             true         BuildConfig
builds                                               build.openshift.io             true         Build
certificatesigningrequests            csr            certificates.k8s.io            false        CertificateSigningRequest
events                                ev             events.k8s.io                  true         Event
daemonsets                            ds             extensions                     true         DaemonSet
deployments                           deploy         extensions                     true         Deployment
ingresses                             ing            extensions                     true         Ingress
networkpolicies                       netpol         extensions                     true         NetworkPolicy
podsecuritypolicies                   psp            extensions                     false        PodSecurityPolicy
replicasets                           rs             extensions                     true         ReplicaSet
images                                               image.openshift.io             false        Image
imagesignatures                                      image.openshift.io             false        ImageSignature
imagestreamimages                     isimage        image.openshift.io             true         ImageStreamImage
imagestreamimports                                   image.openshift.io             true         ImageStreamImport
imagestreammappings                                  image.openshift.io             true         ImageStreamMapping
imagestreams                          is             image.openshift.io             true         ImageStream
imagestreamtags                       istag          image.openshift.io             true         ImageStreamTag
meterings                                            metering.openshift.io          true         Metering
prestotables                                         metering.openshift.io          true         PrestoTable
reportdatasources                                    metering.openshift.io          true         ReportDataSource
reportgenerationqueries                              metering.openshift.io          true         ReportGenerationQuery
reportprometheusqueries                              metering.openshift.io          true         ReportPrometheusQuery
reports                                              metering.openshift.io          true         Report
scheduledreports                                     metering.openshift.io          true         ScheduledReport
storagelocations                                     metering.openshift.io          true         StorageLocation
nodes                                                metrics.k8s.io                 false        NodeMetrics
pods                                                 metrics.k8s.io                 true         PodMetrics
alertmanagers                                        monitoring.coreos.com          true         Alertmanager
prometheuses                                         monitoring.coreos.com          true         Prometheus
prometheusrules                                      monitoring.coreos.com          true         PrometheusRule
servicemonitors                                      monitoring.coreos.com          true         ServiceMonitor
clusternetworks                                      network.openshift.io           false        ClusterNetwork
egressnetworkpolicies                                network.openshift.io           true         EgressNetworkPolicy
hostsubnets                                          network.openshift.io           false        HostSubnet
netnamespaces                                        network.openshift.io           false        NetNamespace
networkpolicies                       netpol         networking.k8s.io              true         NetworkPolicy
oauthaccesstokens                                    oauth.openshift.io             false        OAuthAccessToken
oauthauthorizetokens                                 oauth.openshift.io             false        OAuthAuthorizeToken
oauthclientauthorizations                            oauth.openshift.io             false        OAuthClientAuthorization
oauthclients                                         oauth.openshift.io             false        OAuthClient
poddisruptionbudgets                  pdb            policy                         true         PodDisruptionBudget
podsecuritypolicies                   psp            policy                         false        PodSecurityPolicy
projectrequests                                      project.openshift.io           false        ProjectRequest
projects                                             project.openshift.io           false        Project
appliedclusterresourcequotas                         quota.openshift.io             true         AppliedClusterResourceQuota
clusterresourcequotas                 clusterquota   quota.openshift.io             false        ClusterResourceQuota
clusterrolebindings                                  rbac.authorization.k8s.io      false        ClusterRoleBinding
clusterroles                                         rbac.authorization.k8s.io      false        ClusterRole
rolebindings                                         rbac.authorization.k8s.io      true         RoleBinding
roles                                                rbac.authorization.k8s.io      true         Role
routes                                               route.openshift.io             true         Route
priorityclasses                       pc             scheduling.k8s.io              false        PriorityClass
podsecuritypolicyreviews                             security.openshift.io          true         PodSecurityPolicyReview
podsecuritypolicyselfsubjectreviews                  security.openshift.io          true         PodSecurityPolicySelfSubjectReview
podsecuritypolicysubjectreviews                      security.openshift.io          true         PodSecurityPolicySubjectReview
rangeallocations                                     security.openshift.io          false        RangeAllocation
securitycontextconstraints            scc            security.openshift.io          false        SecurityContextConstraints
storageclasses                        sc             storage.k8s.io                 false        StorageClass
volumeattachments                                    storage.k8s.io                 false        VolumeAttachment
brokertemplateinstances                              template.openshift.io          false        BrokerTemplateInstance
processedtemplates                                   template.openshift.io          true         Template
templateinstances                                    template.openshift.io          true         TemplateInstance
templates                                            template.openshift.io          true         Template
groups                                               user.openshift.io              false        Group
identities                                           user.openshift.io              false        Identity
useridentitymappings                                 user.openshift.io              false        UserIdentityMapping
users                                                user.openshift.io              false        User
"""

process_api_resources_output(_default_api_resources)
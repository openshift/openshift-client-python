from __future__ import print_function

import os
from .selector import Selector, selector
from .action import oc_action
from .context import cur_context, project, no_tracking
from .result import Result
from .apiobject import APIObject
from .model import Model, Missing, OpenShiftPythonException
import util
import naming
import base64
import io
import sys
import traceback
import time

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def __new_objects_action_selector(verb, cmd_args=[], stdin_obj=None):
    """
    Performs and oc action and records objects output from the verb
    as changed in the content.
    :param verb: The verb to execute
    :param cmd_args: A list of str|list<str> which will be flattened into command line arguments
    :param stdin_obj: The standard input to feed to the invocation.
    :return: A selector for the newly created objects
    """

    sel = Selector(verb,
                   object_action=oc_action(cur_context(), verb, cmd_args=['-o=name', cmd_args], stdin_obj=stdin_obj))
    sel.fail_if('{} returned an error: {}'.format(verb, sel.err().strip()))
    return sel


def new_app(cmd_args=[]):
    return __new_objects_action_selector("new-app", cmd_args=cmd_args)


def new_build(cmd_args=[]):
    return __new_objects_action_selector("new-build", cmd_args=cmd_args)


def start_build(cmd_args=[]):
    return __new_objects_action_selector("start-build", cmd_args=cmd_args)


def get_project_name(cmd_args=[]):
    """
    :return: Returns the name of the project selected by the current project. If no project
    context has been established, returns KUBECONFIG project using `oc project`.
    """

    context_project = cur_context().get_project()
    if context_project:
        return context_project

    r = Result("project-name")
    r.add_action(oc_action(cur_context(), "project", cmd_args=["-q", cmd_args]))
    r.fail_if("Unable to determine current project")
    return r.out().strip()


def whoami(cmd_args=[]):
    """
    :param cmd_args: Additional arguments to pass to 'oc whoami'
    :return: The current user
    """

    r = Result("whoami")
    r.add_action(oc_action(cur_context(), "whoami", cmd_args=cmd_args))
    r.fail_if("Unable to determine current user")
    return r.out().strip()


def get_auth_token(cmd_args=[]):
    """
    :param cmd_args: Additional arguments to pass to 'oc whoami -t'
    :return: The current user
    """

    r = Result("whoami")
    r.add_action(oc_action(cur_context(), "whoami", cmd_args=['-t', cmd_args]))
    r.fail_if("Unable to determine current token")
    return r.out().strip()


def get_config_context(cmd_args=[]):
    """
    Returns the result of 'oc config current-context' . If no context currently
    exists, None is returned.
    """
    r = Result("current-context")
    r.add_action(oc_action(cur_context(), "config", cmd_args=['current-context']))
    if r.status() != 0:
        return None

    return r.out()


def use_config_context(context, cmd_args=[]):
    """
    Sets the current context to use.
    :param context: The context name to pass into use-context. If None, no action is taken.
    exists, None is returned.
    """
    if not context:
        return

    r = Result("use-context")
    r.add_action(oc_action(cur_context(), "config", cmd_args=['use-context', context, cmd_args]))
    r.fail_if('Error when trying to use to use-context: {}'.format(context))

    return True


def login(username, password, cmd_args=[]):
    """
    Executes a login operation with the specified username and password. You usually want to invoke
    this inside of an api_server() context.
    :param username: The username to supply to the login
    :param password: The password to supply to the login
    :param cmd_args: Additional arguments to pass in
    :return:
    """
    r = Result("login")
    r.add_action(oc_action(cur_context(), "login", cmd_args=['-u', username, '-p', password, cmd_args]))
    r.fail_if('Error when trying to login')
    return True


def new_project(name, ok_if_exists=False, cmd_args=[]):
    """
    Creates a new project
    :param name: The name of the project to create
    :param ok_if_exists: Do not raise an error if the project already exists
    :param cmd_args: Additional arguments to pass on the command line
    :return: A context manager that can be used with 'with' statement.
    """

    # If user is ok with the project already existing, see if it is and return immediately if detected
    if ok_if_exists:
        if selector('project/{}'.format(name)).count_existing() > 0:
            return project(name)

    r = Result("new-project")
    r.add_action(oc_action(cur_context(), "new-project", cmd_args=[name, cmd_args]))
    r.fail_if("Unable to create new project: {}".format(name))
    return project(name)


def delete_project(name, ignore_not_found=False, cmd_args=[]):
    r = Result("delete-project")
    args = list(cmd_args)
    if ignore_not_found:
        args.append("--ignore-not-found")
    r.add_action(oc_action(cur_context(), "delete", cmd_args=["project", name, args]))
    r.fail_if("Unable to create delete project: {}".format(name))


def _to_dict_list(dict_or_model_or_apiobject_or_list_thereof):
    l = []

    # If incoming is not a list, make it a list so we can keep DRY
    if not isinstance(dict_or_model_or_apiobject_or_list_thereof, list):
        dict_or_model_or_apiobject_or_list_thereof = [dict_or_model_or_apiobject_or_list_thereof]

    for i in dict_or_model_or_apiobject_or_list_thereof:
        if isinstance(i, APIObject):
            i = i.model

        if not isinstance(i, dict):
            raise ValueError('Unable to convert type into list items dict: {}'.format(type(i)))

        if not isinstance(i, Model):
            i = Model(dict_to_model=i)

        # At this point, we should have a Model to make analyzing the structure easier

        # If we received a List, extract the underlying items. This should include unwrapping things like
        # kind: ImageStreamList.
        if i.kind.endswith("List") and i.items is not Missing:
            # can't use .items here since that is interpreted as a method reference
            l.extend(i['items']._primitive())
        else:
            l.append(i._primitive())

    return l


def drain_node(node_name, ignore_daemonsets=True, delete_local_data=True, force=False, timeout_seconds=None,
               grace_period_seconds=None, cmd_args=[], auto_raise=True):
    r = Result('drain')
    args = list(cmd_args)

    if ignore_daemonsets:
        args.append('--ignore-daemonsets')

    if delete_local_data:
        args.append('--delete-local-data')

    if force:
        args.append('--force')

    if timeout_seconds is not None and timeout_seconds > 0:
        args.append('--timeout={}s'.format(timeout_seconds))

    if grace_period_seconds is not None and grace_period_seconds > -1:
        args.append('--grace-period={}'.format(grace_period_seconds))

    r.add_action(oc_action(cur_context(), 'adm', cmd_args=['drain', node_name, args], no_namespace=True))

    if auto_raise:
        r.fail_if('Error during drain of node: {}'.format(node_name))

    return r


def create(dict_or_model_or_apiobject_or_list_thereof, cmd_args=[]):
    items = _to_dict_list(dict_or_model_or_apiobject_or_list_thereof)

    # If nothing is going to be acted on, return an empty selected
    if not items:
        return selector([])

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    return __new_objects_action_selector("create", cmd_args=["-f", "-", cmd_args], stdin_obj=m)


def delete(dict_or_model_or_apiobject_or_list_thereof, ignore_not_found=False, cmd_args=[]):
    """
    Deletes one or more objects
    :param dict_or_model_or_apiobject_or_list_thereof:
    :param ignore_not_found: Pass --ignore-not-found to oc delete
    :param cmd_args: Additional arguments to pass
    :return: If successful, returns a list of qualified names to the caller (can be empty)
    """

    items = _to_dict_list(dict_or_model_or_apiobject_or_list_thereof)

    # If there is nothing to act on, return empty selector
    if not items:
        return []

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    base_args = ['-o=name', '-f', '-']

    if ignore_not_found:
        base_args.append('--ignore-not-found')

    r = Result('delete')
    r.add_action(oc_action(cur_context(), "delete", cmd_args=[base_args, cmd_args], stdin_obj=m))
    r.fail_if("Delete operation failed")

    return r.out().strip().split()


def invoke_create(cmd_args=[]):
    """
    Relies on caller to provide sensible command line arguments. -o=name will
    be added to the arguments automatically.
    :param cmd_args: An array of arguments to pass along to oc create
    :return: A selector for the newly created objects
    """
    return __new_objects_action_selector("create", cmd_args)


def invoke(verb, cmd_args=[], stdin_str=None, auto_raise=True):
    """
    Invokes oc with the supplied arguments.
    :param verb: The verb to execute
    :param cmd_args: An array of arguments to pass along to oc
    :param stdin_str: The standard input to supply to the process
    :param auto_raise: Raise an exception if the command returns a non-zero return code
    :return: A Result object containing the executed Action(s) with the output captured.
    """
    r = Result('invoke')
    r.add_action(oc_action(cur_context(), verb=verb, cmd_args=cmd_args, stdin_str=stdin_str))
    if auto_raise:
        r.fail_if("Non-zero return code from invoke action")
    return r


def get_pod_metrics(pod_obj, auto_raise=True):
    """
    Returns a 'PodMetrics' APIObject object for the specified pod.
    e.g.
    {"kind":"PodMetrics","apiVersion":"metrics.k8s.io/v1beta1","metadata":{"name":"sync-zv8ck","namespace":"openshift-node","selfLink":"/apis/metrics.k8s.io/v1beta1/namespaces/openshift-node/pods/sync-zv8ck","creationTimestamp":"2018-11-29T19:55:04Z"},"timestamp":"2018-11-29T19:54:30Z","window":"1m0s","containers":[{"name":"sync","usage":{"cpu":"0","memory":"35664Ki"}}]}
    :param pod_obj: A Pod APIObject
    :param auto_raise: If True, raise an exception if the command fails. Else return Missing.
    :return: A 'PodMetrics' APIObject
    """
    r = Result('raw-metrics')
    cmd_args = [
        '--raw',
        '/apis/metrics.k8s.io/v1beta1/namespaces/{}/pods/{}'.format(pod_obj.namespace(), pod_obj.name())
    ]
    r.add_action(oc_action(cur_context(), verb='get', cmd_args=cmd_args, no_namespace=True))

    if auto_raise:
        r.fail_if("Non-zero return code from get --raw to metrics.k8s.io")
    elif r.status() != 0:
        return Missing

    return APIObject(string_to_model=r.out())


def get_pods_by_node(node_name, auto_raise=True):
    """
    Returns a list<APIObject> where each APIObject is a pod running on the specified node.
    :param node_name: The name of the node ("xyz" or "node/xyz")
    :param auto_raise: Whether a failure should result in an exception. If false and oc returns an error, an empty
     list will result.
    :return: A list of apiobjects. List may be empty.
    """
    # permit node/xyz and strip it off
    _, _, node_name = naming.split_fqn(node_name)
    r = Result('get_pods_by_node')
    r.add_action(oc_action(cur_context(), verb='adm', cmd_args=['manage-node', node_name, '--list-pods', '-o=json']))

    if auto_raise:
        r.fail_if('Error retrieving pods for node: {}'.format(node_name))

    pod_list = []

    if r.status() == 0:
        pod_list = APIObject(string_to_model=r.out()).elements()

    return pod_list


def get_client_version():
    """
    :return: Returns the version of the oc binary being used (e.g. 'v3.11.28')
    """

    r = Result('version')
    r.add_action(oc_action(cur_context(), verb='version'))
    r.fail_if('Unable to determine version')
    for line in r.out().splitlines():
        if line.startswith('oc '):
            return line.split()[1]

    raise OpenShiftPythonException('Unable find version string in output')


def get_server_version():
    """
    :return: Returns the version of the oc server being accessed (e.g 'v3.11.28')
    """

    r = Result('version')
    r.add_action(oc_action(cur_context(), verb='version'))
    r.fail_if('Unable to determine version')
    for line in reversed(r.out().splitlines()):
        if line.startswith('openshift '):
            return line.split()[1]

    # If not found, this is a 4.0 cluster where this output line was removed. The best
    # alternative is the version returned by the API.
    r = Result('version')
    r.add_action(
        oc_action(cur_context(), 'get', cmd_args=['--raw', '/apis/config.openshift.io/v1/clusterversions/version']))
    r.fail_if('Error contacting clusterversions/version endpoint')

    version_obj = APIObject(string_to_model=r.out())
    if version_obj.model.status.current.version is not Missing:
        return version_obj.model.status.current.version

    raise OpenShiftPythonException('Unable find version string in output')


def apply(dict_or_model_or_apiobject_or_list_thereof, cmd_args=[]):
    items = _to_dict_list(dict_or_model_or_apiobject_or_list_thereof)

    # If there is nothing to act on, return empty selector
    if not items:
        return selector([])

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    return __new_objects_action_selector("apply", cmd_args=["-f", "-", cmd_args], stdin_obj=m)


def build_configmap_dict(configmap_name, dir_path_or_paths=None, dir_ext_include=None, data_map={}, obj_labels={}):
    """
    Creates a python dict structure for a configmap (if remains to the caller to send
    the yaml to the server with create()). This method does not use/require oc to be resident
    on the python host.
    :param configmap_name: The metadata.name to include
    :param dir_path_or_paths: All files within the specified directory (or list of directories) will be included
    in the configmap. Note that the directory must be relative to the python application
    (it cannot be on an ssh client host).
    :param dir_ext_include: List of file extensions should should be included (e.g. ['.py', '.ini']). If None,
    all extensions are allowed.
    :param data_map: A set of key value pairs to include in the configmap (will be combined with dir_path
    entries if both are specified.
    :param obj_labels: Additional labels to include in the resulting configmap metadata.
    :return: A python dict of a configmap resource.
    """

    dm = dict(data_map)

    if dir_path_or_paths:

        # If we received a string, turn it into a list
        if isinstance(dir_path_or_paths, basestring):
            dir_path_or_paths = [dir_path_or_paths]

        for dir_path in dir_path_or_paths:

            for entry in os.listdir(dir_path):
                path = os.path.join(dir_path, entry)

                if os.path.isfile(path):
                    if dir_ext_include:
                        filename, file_extension = os.path.splitext(path)
                        if file_extension.lower() not in dir_ext_include:
                            continue

                    with io.open(path, mode='r', encoding="utf-8") as f:
                        file_basename = os.path.basename(path)
                        dm[file_basename] = f.read()

    d = {
        'kind': 'ConfigMap',
        'apiVersion': 'v1',
        'metadata': {
            'name': configmap_name,
            'labels': obj_labels,
        },
        'data': dm
    }

    return d


def build_secret_dict(secret_name, dir_path_or_paths=None, dir_ext_include=None, data_map={}, obj_labels={}):
    """
    Creates a python dict structure for a secret (it remains to the caller to send
    the yaml to the server with create()). This method does not use/require oc to be resident
    on the python host.
    :param secret_name: The metadata.name to include
    :param dir_path_or_paths: All files within the specified directory (or list of directories) will be included
    in the configmap. Note that the directory must be relative to the python application
    (it cannot be on an ssh client host).
    :param dir_ext_include: List of file extensions should should be included (e.g. ['.py', '.ini'])
    :param data_map: A set of key value pairs to include in the secret (will be combined with dir_path
    entries if both are specified. The values will be b64encoded automatically.
    :param obj_labels: Additional labels to include in the resulting secret metadata.
    :return: A python dict of a secret resource.
    """

    dm = dict()

    # base64 encode the incoming data_map values
    for k, v in data_map.iteritems():
        dm[k] = base64.b64encode(v)

    if dir_path_or_paths:

        # If we received a string, turn it into a list
        if isinstance(dir_path_or_paths, basestring):
            dir_path_or_paths = [dir_path_or_paths]

        for dir_path in dir_path_or_paths:

            for entry in os.listdir(dir_path):
                path = os.path.join(dir_path, entry)

                if dir_ext_include:
                    filename, file_extension = os.path.splitext(path)
                    if file_extension.lower() not in dir_ext_include:
                        continue

                if os.path.isfile(path):
                    with io.open(path, mode='r', encoding="utf-8") as f:
                        file_basename = os.path.basename(path)
                        dm[file_basename] = base64.b64encode(f.read())

    d = {
        'kind': 'Secret',
        'apiVersion': 'v1',
        'metadata': {
            'name': secret_name,
            'labels': obj_labels,
        },
        'data': dm
    }

    return d


class ImageRegistryAuthInfo(object):

    """
    Simple struct to pass around information about image registry authentication information.
    """

    def __init__(self, registry_url, username, password, email=None):
        self.registry_url = registry_url
        self.username = username
        self.password = password
        if not email:
            email = '{}@example.org'.format(username)
        self.email = email


def build_secret_dockerconfigjson(secret_name, image_registry_auth_infos, obj_labels={}):
    """
    Creates a python dict structure for a 'kubernetes.io/dockerconfigjson' secret (it remains to the caller to send
    the yaml to the server with create()). This method does not use/require oc to be resident
    on the python host.
    :param secret_name: The metadata.name to include
    :paran image_registry_auth_infos: An iterable collection of ImageRegistryAuthInfo
    :param obj_labels: Additional labels to include in the resulting secret metadata.
    :return: A python dict of a secret resource.
    """

    auths = {}  # A map of registry urls to a map with a single element called 'auth'

    for ira in image_registry_auth_infos:
        b64_username_password = base64.b64encode('{}:{}'.format(ira.username, ira.password))
        auths[ira.registry_url] = {
            'auth': b64_username_password
        }

    # this is the content you would see if you cat your dockerconfig json file
    dockerconfig = {
        'auths': auths
    }

    # Lazy load to avoid dragging unnecessary dependencies
    import json

    # Next, base64 encode the entire file.
    b64_dockerconfigjson = base64.b64encode(json.dumps(dockerconfig, indent=4))

    # And stick it into the secret's data
    data = {
        '.dockerconfigjson': b64_dockerconfigjson,
    }

    d = {
        'kind': 'Secret',
        'apiVersion': 'v1',
        'metadata': {
            'name': secret_name,
            'labels': obj_labels,
        },
        'type': 'kubernetes.io/dockerconfigjson',
        'data': data
    }

    return d


def build_secret_dockerconfig(secret_name, image_registry_auth_infos, obj_labels={}):
    """
    Creates a python dict structure for a kubernetes.io/dockercfg secret (it remains to the caller to send
    the yaml to the server with create()). This method does not use/require oc to be resident
    on the python host.
    :param secret_name: The metadata.name to include
    :paran image_registry_auth_infos: An iterable collection of ImageRegistryAuthInfo
    :param obj_labels: Additional labels to include in the resulting secret metadata.
    :return: A python dict of a secret resource.
    """

    # the data elements of this secret points to a base64 encoded blob which decoded looks like:
    # {
    #     "172.30.208.107:5000": {
    #         "username": "serviceaccount",
    #         "password": "<base64 password>,
    #         "email": "serviceaccount@example.org",
    #         "auth": "<base64 username:password>"
    #     },
    #     "docker-registry.default.svc.cluster.local:5000": {
    #         "username": "serviceaccount",
    #         ...more entries

    auths = {}  # A map of registry urls to entries like those above

    for ira in image_registry_auth_infos:
        b64_password = base64.b64encode(ira.password)
        b64_username_password = base64.b64encode('{}:{}'.format(ira.username, ira.password))
        auths[ira.registry_url] = {
            'username': ira.username,
            'password': b64_password,
            'email': ira.email,
            'auth': b64_username_password
        }

    # Lazy load to avoid dragging unnecessary dependencies
    import json

    # Next, base64 encode the entries
    b64_auths = base64.b64encode(json.dumps(auths, indent=4))

    # And stick it into the secret's data
    data = {
        '.dockercfg': b64_auths,
    }

    d = {
        'kind': 'Secret',
        'apiVersion': 'v1',
        'metadata': {
            'name': secret_name,
            'labels': obj_labels,
        },
        'type': 'kubernetes.io/dockercfg',
        'data': data
    }

    return d


def update_api_resources():
    """
    Makes a call to `oc api-resources` and updates openshift-python's internal view of
    resources available. This is only necessary if you are encountering scenarios where
    the default blob of resources in naming.py is no accurate for your cluster / use case.
    --verbs=get limits the returned resources to those you can actually 'oc get'.
    """
    res = invoke('api-resources', cmd_args=['--verbs=get'])
    naming.process_api_resources_output(res.out())


def dumpinfo_apiobject(output_dir,
                       obj,
                       limit_daemonsets_to_nodes=None,
                       log_timestamps=True,
                       logs_since=None,
                       logs_limit_bytes=None,
                       logs_tail=-1,
                       status_printer=eprint):
    name = obj.name()
    util.mkdir_p(output_dir)
    prefix = os.path.join(output_dir, name)

    if not status_printer:
        status_printer = lambda: None

    status_printer('Gathering information for {}'.format(obj.fqname()))

    with no_tracking():

        if obj.is_kind(['pod', 'build']):

            if limit_daemonsets_to_nodes is not None:
                # if this is a pod and a member of a daemonset, only output information
                # if the pod is running on a node listed in limit_daemonsets_to_nodes

                ldn = []
                for node_name in limit_daemonsets_to_nodes:
                    ldn.append(naming.qualify_name(node_name, 'node'))

                if obj.is_kind('pod') and obj.model.metadata.ownerReferences.can_match({
                    'kind': 'DaemonSet'
                }):
                    running_on_node = naming.qualify_name(obj.model.spec.nodeName, 'node')
                    if running_on_node not in ldn:
                        status_printer(
                            'Skipping information collection for daemonset pod on non-collected node: {}'.format(obj.fqname()))
                        return

            with io.open(prefix + '.logs.txt', mode='w', encoding="utf-8") as f:
                obj.print_logs(f,
                               timestamps=log_timestamps,
                               since=logs_since,
                               tail=logs_tail,
                               limit_bytes=logs_limit_bytes)

        with io.open(prefix + '.describe.txt', mode='w', encoding="utf-8") as f:
            f.write(obj.describe(auto_raise=False))

        if not naming.kind_matches(obj.kind(), 'secret'):
            with io.open(prefix + '.json', mode='w', encoding="utf-8") as f:
                f.write(obj.as_json())


def dumpinfo_node(output_dir,
                  node,
                  critical_journal_units=['atomic-openshift-node', 'crio', 'docker'],
                  sdn_pods=[],
                  fluentd_pods=[],
                  num_combined_journal_entries=10000,
                  num_critical_journal_entries=10000,
                  status_printer=eprint):
    node_dir = util.mkdir_p(output_dir)

    try:

        with no_tracking():
            dumpinfo_apiobject(node_dir, node)

            node_sdn_pod = next((pod for pod in sdn_pods if pod.model.spec.nodeName == node.name()), None)
            if node_sdn_pod:
                capture_action = node_sdn_pod.execute(cmd_to_exec=['iptables-save'],
                                                      container_name='sdn',
                                                      auto_raise=False)

                with io.open(os.path.join(node_dir, 'iptables.txt'), mode='w', encoding='utf-8') as f:
                    f.write(capture_action.out())
                    f.write(capture_action.err())

            # If possible, find a fluentd pod that is scheduled on the node. The fluentd pod mounts in the
            # host's journal directories -- so we capture information for debug.
            node_fluentd_pod = next((pod for pod in fluentd_pods if pod.model.spec.nodeName == node.name()), None)
            if node_fluentd_pod:

                status_printer('Collecting combined journal from: {}'.format(node.name()))
                with io.open(os.path.join(node_dir, 'combined.journal.export'), mode='w', encoding="utf-8") as f:
                    capture_action = node_fluentd_pod.execute(cmd_to_exec=[
                        'journalctl',
                        '-D', '/var/log/journal',
                        '-o', 'export',
                        '-n', num_combined_journal_entries,
                    ],
                        auto_raise=False)
                    f.write(capture_action.out())

                # In case extraneous events are flooding, isolate important services as well
                if critical_journal_units:
                    status_printer('Collecting critical services journal from: {}'.format(node.name()))
                    with io.open(os.path.join(node_dir, 'critical.journal.export'), mode='w', encoding="utf-8") as f:
                        cmd_to_exec = [
                            'journalctl',
                            '-D', '/var/log/journal',  # Where fluentd mounts hosts journal
                            '-o', 'export',  # This can be converted back into .journal with systemd-journal-remote
                            '-n', num_critical_journal_entries,  # Number of recent events to gather critical services
                        ]

                        # include all the units the dump operation should focus on
                        for unit in critical_journal_units:
                            cmd_to_exec.extend(['-u', unit])

                        capture_action = node_fluentd_pod.execute(cmd_to_exec=cmd_to_exec,
                                                                  auto_raise=False)
                        f.write(capture_action.out())
            else:
                status_printer('Unable to find a fluentd pod in the cluster for node {}'.format(node.name()))

    except Exception as e:
        status_printer('Error collecting node information: {}\n{}'.format(node.name(), traceback.format_exc()))


def dumpinfo_project(dir,
                     project_name,
                     kinds=['ds', 'dc', 'build', 'statefulset', 'deployment', 'pod', 'rs', 'rc', 'configmap'],
                     limit_daemonsets_to_nodes=None,
                     log_timestamps=True,
                     logs_since=None,
                     logs_tail=-1,
                     logs_limit_bytes=None,
                     status_printer=eprint):
    """
    Populates a specified directory with a significant amount of data for a given project.
    :param dir: The output directory
    :param project_name: The name or qualified name of the project
    :param kinds: A list of kinds to collect data on within the project (defaults to generally import kinds like
    deployments, pods, configmaps, etc.)
    :param limit_daemonsets_to_nodes: A list of names or qualified names. If specified, pod information for daemonsets
    will only be collected for nodes named in this list. If None, all pods for daemonsets will be collected.
    :param log_timestamps: Whether to include timestamps in pod logs
    :param logs_since: --since for oc logs on pods
    :param logs_tail: --tail for oc logs on pods
    :param logs_limit_bytes: --limit-bytes for oc logs on pods
    :param status_printer: Method which takes a single string parameter. Will be called with status strings as collection
    proceeds. Defaults to method which prints to stderr.
    :return:
    """

    project_name = naming.qualify_name(project_name, 'project')

    if not status_printer:
        status_printer = lambda: None

    status_printer(u'Collecting info for project: {}'.format(project_name))

    util.mkdir_p(dir)
    with no_tracking():

        # if the project does not exist, just a leave a file saying we tried
        if selector(project_name).count_existing() == 0:
            with io.open(os.path.join(dir, 'not-found'), mode='w', encoding="utf-8") as f:
                f.write(u'{} was not found'.format(project_name))
            return

        with project(project_name):

            with io.open(os.path.join(dir, 'status.txt'), mode='w', encoding="utf-8") as f:
                f.write(unicode(invoke('status').out()))

            for obj in selector(kinds).objects(ignore_not_found=True):
                obj_dir = os.path.join(dir, obj.kind())
                dumpinfo_apiobject(obj_dir, obj,
                                   limit_daemonsets_to_nodes=limit_daemonsets_to_nodes,
                                   logs_since=logs_since,
                                   logs_tail=logs_tail,
                                   logs_limit_bytes=logs_limit_bytes,
                                   log_timestamps=log_timestamps,
                                   status_printer=status_printer)


def dumpinfo_system(base_dir,
                    dump_core_projects=True,
                    dump_restricted_projects=False,
                    additional_nodes=[],
                    additional_projects=[],
                    additional_namespaced_kinds=[],
                    include_crd_kinds=False,
                    num_combined_journal_entries=10000,
                    num_critical_journal_entries=10000,
                    log_timestamps=True,
                    logs_since=None,
                    logs_tail=-1,
                    logs_limit_bytes=None,
                    status_printer=eprint):
    """
    Dumps object definitions, pod logs, node journals, etc. to a directory structure.
    :param base_dir: The directory in which to create the dump structure
    :param dump_core_projects: Whether to collect information from objects in kube-system, openshift-node, etc.
    :param dump_restricted_projects: Whether to collect information from objects in all kube-*, openshift_* in addition
    to core.
    :param additional_nodes: master nodes are collected by default. Specify additional nodes to collect. Expects
    a list of names or qnames.
    :param additional_projects: restricted projects are collected by default. Specify additional projects to collect
     data from. Expects list of names or qnames.
    :param additional_namespaced_kinds: Well known kinds are collected automatically (dc, pod, configmap, etc) but
    you can specify additional kinds to include as a list of names.
    :param include_crd_kinds: Whether to gather CRD instances as part of collection. Not recommended unless you
    are running as system:admin, otherwise RBAC is a nightmare.
    :param num_combined_journal_entries: How many entries from the full journal (all units combined).
    :param num_critical_journal_entries: How many entries from critical units to pull (docker+crio+atomic-openshift-node).
    :param log_timestamps: Include timetamps in pod log collection?
    :param logs_since: --since parameter for pod log collection (e.g. '5h')
    :param logs_tail: --tail parameter for pod log collection.
    :param logs_limit_bytes: --limit-bytes
    :param status_printer: Method which takes a single string parameter. Will be called with status strings as collection
    proceeds. Defaults to stderr printing.
    :return: N/A
    """

    util.mkdir_p(base_dir)

    if not status_printer:
        status_printer = lambda: None

    kinds = set(['ds', 'dc', 'build', 'statefulset', 'deployment', 'pod', 'rs', 'rc', 'configmap'])
    kinds.update(additional_namespaced_kinds)

    # A large amount of stdout is going to be generated by streaming logs from pods --
    # don't burden memory by trying to store it in trackers.
    with no_tracking():

        if include_crd_kinds:
            # At the time of this comment, you need to add specific privileges to read CRs. Eventually,
            # master team should allow CRDs to express whether they contain sensitive information and
            # remove this restriction. As such, turning this flag True is not recommended until
            # master acts on this.
            for crd_obj in selector('crd').objects():
                if crd_obj.model.spec.scope == 'Namespaced':
                    kinds.add(crd_obj.name())

        sdn_pods = []  # Prevent errors by using empty list if we can't find sdn pods
        try:
            with project('openshift-sdn'):
                # Find all pods created by the sdn daemonset.
                sdn_pods = selector('ds/sdn').object().get_owned('pod')
                status_printer(u'Found {} sdn pods on cluster'.format(len(sdn_pods)))
        except Exception as sdn_err:
            status_printer(u'Unable to get openshift-sdn pods: {}'.format(sdn_err))

        # Use all_namespaces because logging components could be in 'logging' (older) or 'openshift-logging' (newer)
        fluentd_pods = selector('pod', labels={'component': 'fluentd'}, all_namespaces=True).objects()
        status_printer(u'Found {} fluentd pods on cluster'.format(len(fluentd_pods)))

        overview_dir = util.mkdir_p(os.path.join(base_dir, 'overview'))
        with io.open(os.path.join(overview_dir, 'nodes.json'), mode='w', encoding='utf-8') as f:
            f.write(selector('nodes').object_json())

        with io.open(os.path.join(overview_dir, 'versions'), mode='w', encoding='utf-8') as f:
            f.write(u'Sever version: {}\n'.format(get_server_version()))
            f.write(u'Client version: {}\n'.format(get_client_version()))

        # Start with a base set of master nodes and append additional nodes.
        node_qnames = set(selector('node', labels={'!node-role.kubernetes.io/master': None}).qnames())
        for node_name in additional_nodes:
            node_name = naming.qualify_name(node_name.lower(), 'node')  # make sure we have node/xyz
            node_qnames.add(node_name)

        status_printer(u'Attempting to gather on nodes: {}\n'.format(node_qnames))
        node_sel = selector(node_qnames)

        for node in node_sel.objects():
            dumpinfo_node(os.path.join(base_dir, 'node', node.name()),
                          node, sdn_pods=sdn_pods, fluentd_pods=fluentd_pods,
                          num_critical_journal_entries=num_critical_journal_entries,
                          num_combined_journal_entries=num_combined_journal_entries,
                          status_printer=status_printer,
                          )

        projects = set()
        if dump_core_projects or dump_restricted_projects:
            projects.update(['default',
                             'openshift',
                             'openshift-sdn',
                             'kube-system',
                             'openshift-config',
                             'openshift-node',
                             'openshift-console',
                             'openshift-infra',
                             ])

        # if dumping restricted projects, add to core projects those which start with openshift-*, kube-*
        if dump_restricted_projects:
            projects.update([proj.name() for proj in selector('projects').objects() if
                             proj.name().startswith(('openshift-', 'kube-'))])

        # dump projects named by caller
        projects.update(additional_projects)

        for project_name in projects:
            dumpinfo_project(os.path.join(base_dir, 'project', project_name),
                             project_name,
                             kinds=kinds,
                             limit_daemonsets_to_nodes=node_qnames,
                             log_timestamps=log_timestamps,
                             logs_since=logs_since,
                             logs_tail=logs_tail,
                             logs_limit_bytes=logs_limit_bytes,
                             status_printer=status_printer,
                             )


def node_ssh_client(apiobj_node_name_or_qname=None,
                    port=22,
                    username=None,
                    password=None,
                    auto_add_host=True,
                    connect_timeout=600,
                    through_client_host=True,
                    address_type_pref="ExternalDNS,ExternalIP,Hostname"
                    ):
    """
    Returns a paramiko ssh client connected to the named cluster node. The caller is responsible for closing the
    connection -- use as a contextmanager is recommended.
    :param apiobj_node_name_or_qname: The name of the node or the apiobject representing the node to ssh to. If None,
    tries to return the ssh_client associated with current client_host context, if any.
    :param port: The ssh port
    :param username: The username to use
    :param password: The username's password
    :param auto_add_host: Whether to auto accept host certificates
    :param connect_timeout: Connection timeout
    :param through_client_host: If True, and client_host is being used, ssh will be initiated
    through the client_host ssh connection. Username/password used for client_host will propagate
    unless overridden.
    :param address_type_pref: Comma delimited list of node address types. Types will be tried in
            the order specified.
    :return: ssh_client which can be used as a context manager
    """

    # Just-in-time import to avoid hard dependency. Allows
    # you to use local 'oc' without having paramiko installed.
    import paramiko

    if not apiobj_node_name_or_qname:
        return cur_context().get_ssh_client()

    if isinstance(apiobj_node_name_or_qname, APIObject):
        apiobj = apiobj_node_name_or_qname

    else:
        if '/' not in apiobj_node_name_or_qname:
            qname = 'node/{}'.format(apiobj_node_name_or_qname)
        else:
            qname = apiobj_node_name_or_qname

        apiobj = selector(qname).object()

    address_entries = apiobj.model.status.addresses

    if address_entries is Missing:
        raise IOError("Error finding addresses associated with: {}".format(apiobj.qname()))

    for address_type in address_type_pref.split(','):
        # Find the first address of the preferred type:
        address = next(
            (entry.address for entry in address_entries if entry.type.lower() == address_type.lower().strip()), None)
        if address:
            ssh_client = paramiko.SSHClient()
            ssh_client.load_system_host_keys()

            if auto_add_host:
                ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            host_sock = None
            host_ssh_client = cur_context().get_ssh_client()
            if through_client_host and host_ssh_client:
                # If there is a client host, initiate node ssh connections from it
                host_transport = host_ssh_client.get_transport()
                node_addr = (address, port)
                local_addr = ('127.0.0.1', 0)
                host_sock = host_transport.open_channel("direct-tcpip", node_addr, local_addr)

                # If we are tunneling through another connection, use authentication from that
                # connection. e.g. continue on as root if root was used to connect.
                if not username:
                    username = cur_context().get_ssh_username()

                if not password:
                    password = cur_context().get_ssh_password()

            ssh_client.connect(hostname=address, port=port, username=username,
                               password=password, timeout=connect_timeout,
                               sock=host_sock)

            # Enable agent fowarding
            paramiko.agent.AgentRequestHandler(ssh_client.get_transport().open_session())

            return ssh_client

    raise IOError("Unable to find any address with type ({}) for: {}".format(address_type_pref, apiobj.qname()))


def node_ssh_await(apiobj_node_name_or_qname=None,
                   timeout_seconds=600,
                   port=22,
                   username=None,
                   password=None,
                   auto_add_host=True,
                   through_client_host=True,
                   address_type_pref="ExternalDNS,ExternalIP,Hostname"):

    """
    Periodically attempts to connect to a node's ssh server.
    :param apiobj_node_name_or_qname:
    :param timeout_seconds:
    :param port:
    :param username:
    :param password:
    :param auto_add_host:
    :param connect_timeout:
    :param through_client_host:
    :param address_type_pref:
    :return: N/A, but throws the last exception received if timeout occurs.
    """

    timeout_seconds = int(timeout_seconds)
    timeout_start = time.time()

    while time.time() < timeout_start + timeout_seconds:
        try:
            with node_ssh_client(apiobj_node_name_or_qname=apiobj_node_name_or_qname,
                                 port=port,
                                 username=username,
                                 password=password,
                                 auto_add_host=auto_add_host,
                                 connect_timeout=25,
                                 through_client_host=through_client_host,
                                 address_type_pref=address_type_pref) as ssh_client:
                return

        except Exception as e:
            last_e = e
            time.sleep(10)

    raise last_e


def node_ssh_client_exec(apiobj_node_name_or_qname=None,
                         cmd_str=None,
                         stdin_str=None,
                         port=22,
                         username=None,
                         password=None,
                         auto_add_host=True,
                         connect_timeout=600,
                         through_client_host=True,
                         address_type_pref="ExternalDNS,ExternalIP,Hostname"
                         ):
    """
    Executes a single command on the remote host via ssh and returns rc, stdout, stderr. Closes the connection
    afterwards.
    :param apiobj_node_name_or_qname: The name of the node or the apiobject representing the node to ssh to. If None,
    tries to return the ssh_client associated with current client_host context, if any.
    :param cmd_str: The command to execute on the remote host
    :param stdin_str: String to supply to stdin (or None if none)
    :param port: The ssh port
    :param username: The username to use
    :param password: The username's password
    :param auto_add_host: Whether to auto accept host certificates
    :param connect_timeout: Connection timeout
    :param through_client_host: If True, and client_host is being used, ssh will be initiated
    through the client_host ssh connection. Username/password used for client_host will propagate
    unless overridden.
    :param address_type_pref: Comma delimited list of node address types. Types will be tried in
            the order specified.
    :return: rc, stdout, stderr
    """

    with node_ssh_client(apiobj_node_name_or_qname=apiobj_node_name_or_qname,
                         port=port,
                         username=username,
                         password=password,
                         auto_add_host=auto_add_host,
                         connect_timeout=connect_timeout,
                         through_client_host=through_client_host,
                         address_type_pref=address_type_pref) as ssh_client:
        ssh_stdin, ssh_stdout, ssh_stderr = ssh_client.exec_command(cmd_str)

        if stdin_str:
            ssh_stdin.write(stdin_str)
            ssh_stdin.flush()
            ssh_stdin.channel.shutdown_write()

        stdout = ssh_stdout.read().decode('utf-8', errors='ignore')
        stderr = ssh_stderr.read().decode('utf-8', errors='ignore')
        return_code = ssh_stdout.channel.recv_exit_status()

        return return_code, stdout, stderr

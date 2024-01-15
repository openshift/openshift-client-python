from __future__ import print_function
from __future__ import absolute_import

import os
import base64
import io
import sys
import traceback
import time
import json
import yaml
import six

from .selector import Selector, selector
from .action import oc_action
from .context import cur_context, project, no_tracking
from .result import Result
from .apiobject import APIObject
from .model import Model, Missing, OpenShiftPythonException
from . import util
from . import naming


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def __new_objects_action_selector(verb, cmd_args=None, stdin_obj=None, no_namespace=False, auto_raise=True):
    """
    Performs and oc action and records objects output from the verb
    as changed in the content.
    :param verb: The verb to execute
    :param cmd_args: A list of str|list<str> which will be flattened into command line arguments
    :param stdin_obj: The standard input to feed to the invocation.
    :param no_namespace: If the incoming objects have namespace information, set to True.
    :param auto_raise: If True, errors from oc will raise an exception.
    :return: A selector for the newly created objects
    """

    sel = Selector(verb,
                   object_action=oc_action(cur_context(), verb, cmd_args=['-o=name', cmd_args], stdin_obj=stdin_obj,
                                           no_namespace=no_namespace))
    if auto_raise:
        sel.fail_if('{} returned an error: {}'.format(verb, sel.err().strip()))

    return sel


def new_app(cmd_args=None):
    return __new_objects_action_selector("new-app", cmd_args=cmd_args)


def new_build(cmd_args=None):
    return __new_objects_action_selector("new-build", cmd_args=cmd_args)


def start_build(cmd_args=None):
    return __new_objects_action_selector("start-build", cmd_args=cmd_args)


def get_project_name(cmd_args=None):
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


def whoami(cmd_args=None):
    """
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return: The current user
    """

    r = Result("whoami")
    r.add_action(oc_action(cur_context(), "whoami", cmd_args=cmd_args))
    r.fail_if("Unable to determine current user")
    return r.out().strip()


def get_auth_token(cmd_args=None):
    """
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return: The current user's token
    """

    r = Result("whoami")
    r.add_action(oc_action(cur_context(), "whoami", cmd_args=['-t', cmd_args]))
    r.fail_if("Unable to determine current token")
    return r.out().strip()


def get_serviceaccount_auth_token(sa_name, cmd_args=None):
    """
    Uses `oc serviceaccounts get-token  <sa_name>`
    :param sa_name: The name of the service account from which to extract the token
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return: The specified service accounts' token
    """

    r = Result("sa_token")
    r.add_action(oc_action(cur_context(), "serviceaccounts", cmd_args=['get-token', sa_name, cmd_args]))
    r.fail_if("Unable to determine serviceaccount token")
    return r.out().strip()


def get_config_context(cmd_args=None):
    """
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :returns: Returns the result of 'oc config current-context' . If no context currently
    exists, None is returned.
    """
    r = Result("current-context")
    r.add_action(oc_action(cur_context(), "config", cmd_args=['current-context', cmd_args]))
    if r.status() != 0:
        return None

    return r.out()


def use_config_context(context, cmd_args=None):
    """
    Sets the current context to use.
    :param context: The context name to pass into use-context. If None, no action is taken.
    exists, None is returned.
    :param cmd_args: An optional list of additional arguments to pass on the command line
    """
    if not context:
        return

    r = Result("use-context")
    r.add_action(oc_action(cur_context(), "config", cmd_args=['use-context', context, cmd_args]))
    r.fail_if('Error when trying to use to use-context: {}'.format(context))

    return True


def login(username, password, cmd_args=None):
    """
    Executes a login operation with the specified username and password. You usually want to invoke
    this inside of an api_server() context.
    :param username: The username to supply to the login
    :param password: The password to supply to the login
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return:
    """
    r = Result("login")
    r.add_action(oc_action(cur_context(), "login", cmd_args=['-u', username, '-p', password, cmd_args]))
    r.fail_if('Error when trying to login')
    return True


def new_project(name, ok_if_exists=False, cmd_args=None, description=None, display_name=None, adm=False):
    """
    Creates a new project
    :param name: The name of the project to create
    :param ok_if_exists: Do not raise an error if the project already exists
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :param description: The project's description name
    :param display_name: The project's display name
    :param adm: If true, 'oc adm new-project' will be used. This avoid project templates and can
    create privileged namespaces (e.g. openshift-*).
    :return: A context manager that can be used with 'with' statement.
    """

    # If user is ok with the project already existing, see if it is and return immediately if detected
    if ok_if_exists:
        if selector('project/{}'.format(name)).count_existing() > 0:
            return project(name)

    other_args = []
    if description:
        other_args.extend(['--description', description])

    if display_name:
        other_args.extend(['--display-name', display_name])

    r = Result("new-project")
    if adm:
        r.add_action(oc_action(cur_context(), 'adm', cmd_args=['new-project', name, cmd_args, other_args]))
    else:
        r.add_action(oc_action(cur_context(), "new-project", cmd_args=[name, cmd_args, other_args, '--skip-config-write']))

    r.fail_if("Unable to create new project: {}".format(name))
    return project(name)


def delete_project(name, ignore_not_found=False, grace_period=None, force=False, cmd_args=None):
    """
    Deletes the identified project.
    :param name: The name of the project to delete (e.g. 'project/x', 'namespace/x', or 'x')
    :param ignore_not_found: Pass --ignore-not-found to oc delete
    :param grace_period: If specified, sets the --grace-period arguments.
    :param force: If True, pass --force to delete
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return: n/a
    """

    r = Result("delete-project")
    _, _, name = naming.split_fqn(name)  # Allow project/x, namespace/x, etc. Just out actual name.
    base_args = list()

    if ignore_not_found:
        base_args.append("--ignore-not-found")

    if grace_period is not None:
        base_args.append("--grace-period={}".format(grace_period))

    if force:
        base_args.append("--force")

    r.add_action(oc_action(cur_context(), "delete", cmd_args=["project", name, base_args, cmd_args]))
    r.fail_if("Unable to delete project: {}".format(name))

    # Give the controller time to clean up project resources:
    while selector('namespace/{}'.format(name)).count_existing() > 0:
        time.sleep(1)


def _to_dict_list(str_dict_model_apiobject_or_list_thereof):
    """
    Normalizes the parameter into a python list<dict>.
    :param str_dict_model_apiobject_or_list_thereof: The parameter to convert. Could be a yaml/json string,
    dict, Model, apiobject, or a list of any of those.
    :return: A normalized list<dict>, and a boolean of whether namespace information was detected in the result.
    """

    normalized_list = []
    namespace_detected = False

    # If incoming is not a list, make it a list so we can keep DRY
    if not isinstance(str_dict_model_apiobject_or_list_thereof, list):
        str_dict_model_apiobject_or_list_thereof = [str_dict_model_apiobject_or_list_thereof]

    for i in str_dict_model_apiobject_or_list_thereof:

        if i is None:
            continue

        if isinstance(i, APIObject):
            i = i.model

        if isinstance(i, six.string_types):
            if i.strip().startswith('{'):
                i = json.loads(i)
            else:
                i = yaml.safe_load(i)

        if not isinstance(i, dict):
            raise ValueError('Unable to convert type into list items dict: {}'.format(type(i)))

        if not isinstance(i, Model):
            i = Model(dict_to_model=i)

        # At this point, we should have a Model to make analyzing the structure easier

        # See if a modeled object has a defined, non-empty string for namesapce
        if i.metadata.namespace is not Missing and i.metadata.namespace:
            namespace_detected = True

        # If we received a List, extract the underlying items. This should include unwrapping things like
        # kind: ImageStreamList.
        if i.kind.endswith("List") and i.items is not Missing:
            # can't use .items here since that is interpreted as a method reference
            normalized_list.extend(i['items']._primitive())
        else:
            normalized_list.append(i._primitive())

    return normalized_list, namespace_detected


def drain_node(apiobj_node_name_or_qname, ignore_daemonsets=True,
               delete_local_data=True, force=False, timeout_seconds=None,
               grace_period_seconds=None, cmd_args=None, auto_raise=True):
    r = Result('drain')

    base_args = list()

    if isinstance(apiobj_node_name_or_qname, APIObject):
        node_name = apiobj_node_name_or_qname.name()
    else:
        _, _, node_name = naming.split_fqn(apiobj_node_name_or_qname)

    if ignore_daemonsets:
        base_args.append('--ignore-daemonsets')

    if delete_local_data:
        # The '--delete-local-data' flag is being deprecated.
        # A new flag was introduced in OpenShift 4.7 ('--delete-emptydir-data').
        # The following logic is to provide backward compatibility for folks that
        # may not update their 'oc' binaries all that often.
        version = get_client_version()
        pieces = version.split('.')
        major = int(pieces[0])
        minor = int(pieces[1])

        # Local builds of OC have `alpha` in their version string.  We are going
        # to assume that anyone building their own version of 'oc' will most
        # likely have the latest/greatest code that contains the new flag.
        if 'alpha' in version or major > 4 or (major == 4 and minor >= 7):
            base_args.append('--delete-emptydir-data')
        else:
            base_args.append('--delete-local-data')

    if force:
        base_args.append('--force')

    if timeout_seconds is not None and timeout_seconds > 0:
        base_args.append('--timeout={}s'.format(timeout_seconds))

    if grace_period_seconds is not None and grace_period_seconds > -1:
        base_args.append('--grace-period={}'.format(grace_period_seconds))

    r.add_action(oc_action(cur_context(), 'adm', cmd_args=['drain', node_name, base_args, cmd_args], no_namespace=True))

    if auto_raise:
        r.fail_if('Error during drain of node: {}'.format(node_name))

    return r


def create(str_dict_model_apiobject_or_list_thereof, cmd_args=None):
    """
    Runs oc create against an object or list of objects. The objects will be normalized into a
    kube List object and set to the create verb.
    :param str_dict_model_apiobject_or_list_thereof: A single json/yaml string, Model, apiobject, or a
    list of any of those.
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return: Returns a selector which can select the items just created (if namespace is correct)
    """
    items, namespace_detected = _to_dict_list(str_dict_model_apiobject_or_list_thereof)

    # If nothing is going to be acted on, return an empty selected
    if not items:
        return selector([])

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    return __new_objects_action_selector("create",
                                         cmd_args=["-f", "-", cmd_args],
                                         stdin_obj=m,
                                         no_namespace=namespace_detected)


def delete(str_dict_model_apiobject_or_list_thereof, ignore_not_found=False,
           grace_period=None, force=False, cmd_args=None):
    """
    Deletes one or more objects
    :param str_dict_model_apiobject_or_list_thereof:
    :param ignore_not_found: Pass --ignore-not-found to oc delete
    :param grace_period: If specified, sets the --grace-period arguments.
    :param force: Pass --force to oc delete
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :return: If successful, returns a list of qualified names to the caller (can be empty)
    """

    items, namespace_detected = _to_dict_list(str_dict_model_apiobject_or_list_thereof)

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

    if grace_period is not None:
        base_args.append('--grace-period={}'.format(grace_period))

    if force:
        base_args.append('--force')

    r = Result('delete')
    r.add_action(oc_action(cur_context(), "delete",
                           cmd_args=[base_args, cmd_args],
                           stdin_obj=m,
                           no_namespace=namespace_detected))

    r.fail_if("Delete operation failed")

    return r.out().strip().split()


def invoke_create(cmd_args=None, no_namespace=False):
    """
    Relies on caller to provide sensible command line arguments. -o=name will
    be added to the arguments automatically.
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :param no_namespace: If False, the context based namespace will not be passed along with the invocation.
    :return: A selector for the newly created objects
    """
    return __new_objects_action_selector("create", cmd_args, no_namespace=no_namespace)


def invoke(verb, cmd_args=None, stdin_str=None, no_namespace=False, auto_raise=True):
    """
    Invokes oc with the supplied arguments.
    :param verb: The verb to execute
    :param cmd_args: An optional list of additional arguments to pass on the command line
    :param stdin_str: The standard input to supply to the process
    :param no_namespace: If False, the context based namespace will not be passed along with the invocation.
    :param auto_raise: Raise an exception if the command returns a non-zero return code
    :return: A Result object containing the executed Action(s) with the output captured.
    """
    r = Result('invoke')
    r.add_action(oc_action(cur_context(),
                           verb=verb,
                           cmd_args=cmd_args,
                           stdin_str=stdin_str,
                           no_namespace=no_namespace))
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


def get_pods_by_node(apiobj_node_name_or_qname):
    """
    Returns a list<APIObject> where each APIObject is a pod running on the specified node.
    :param apiobj_node_name_or_qname: The name of the node ("xyz" or "node/xyz") or apiobject
    :return: A list of apiobjects. List may be empty.
    """

    if isinstance(apiobj_node_name_or_qname, APIObject):
        node_name = apiobj_node_name_or_qname.name()
    else:
        # permit node/xyz, but and strip off node/
        _, _, node_name = naming.split_fqn(apiobj_node_name_or_qname)

    return selector('pod', all_namespaces=True,
                    field_selectors={'spec.nodeName': node_name}).objects(ignore_not_found=True)


def get_client_version():
    """
    :return: Returns the version of the oc binary being used (e.g. '3.11.28')
    """

    r = Result('version3')
    r.add_action(oc_action(cur_context(), verb='version'))
    r.fail_if('Unable to determine version')

    # Example OpenShift 3 output:
    # oc v3.11.82
    # kubernetes v1.11.0+d4cacc0
    # features: Basic-Auth GSSAPI Kerberos SPNEGO
    for line in r.out().splitlines():
        if line.startswith('oc v'):
            return line.split()[1].lstrip('v')

    r = Result('version4')
    r.add_action(oc_action(cur_context(), verb='version', cmd_args=['-o=json']))
    r.fail_if('Unable to determine version')

    version_dict = json.loads(r.out())
    version_model = Model(dict_to_model=version_dict, case_insensitive=True)
    if version_model.clientVersion.gitVersion:
        return version_model.clientVersion.gitVersion.lstrip('v')

    raise OpenShiftPythonException('Unable extract version from json: {}'.format(r.out()))


def get_server_version():
    """
    :return: Returns the version of the oc server being accessed (e.g '3.11.28')
    """

    r = Result('version3')
    r.add_action(oc_action(cur_context(), verb='version'))
    r.fail_if('Unable to determine version')

    # Example OpenShift 3 output:
    # oc v3.11.82
    # kubernetes v1.11.0+d4cacc0
    # features: Basic-Auth GSSAPI Kerberos SPNEGO
    #
    # Server https://internal.api.starter-us-east-2.openshift.com:443
    # openshift v3.11.82
    # kubernetes v1.11.0+d4cacc0
    for line in reversed(r.out().splitlines()):
        if line.startswith('openshift v'):
            return line.split()[1].strip().lstrip('v')
        elif line.startswith('Server Version: '):
            version_string = line.split()[2].strip().lstrip()
            if not version_string.startswith('version.Info{'):
                return version_string

    # If not found, this is a 4.0 cluster where this output line was removed. The best
    # alternative is the version returned by the API.
    r = Result('version4')
    r.add_action(oc_action(cur_context(), 'adm', cmd_args=['release', 'info', '-o=json']))
    r.fail_if('Error returning release info')

    version_dict = json.loads(r.out())
    version_model = Model(dict_to_model=version_dict, case_insensitive=True)
    if version_model.metadata.version:
        return version_model.metadata.version

    raise OpenShiftPythonException('Unable find version string in json: {}'.format(r.out()))


def apply(str_dict_model_apiobject_or_list_thereof, overwrite=False, cmd_args=None,
          fetch_resource_versions=False,
          auto_raise=True):
    """
    Applies the specifies resource(s) on the server.
    :param str_dict_model_apiobject_or_list_thereof: The definition of one or more API object.
        Can be string containing json or yaml, a python dict, an openshift.Model, or an openshift.APIObject.
        You can also provide a list containing multiple of these elements to update.
    :param overwrite: If --overwrite should be sent to apply.
    :param cmd_args: Additional apply arguments
    :param fetch_resource_versions: If True, before trying to apply the resources, a get operation will be used to
    fetch any existing resourceVersion(s). Those resourceVersions will be populated into the apply payload before
    being sent to the server. See https://github.com/kubernetes/kubernetes/issues/70674 for why this is sometimes
    necessary.
    :param auto_raise: If True, errors from oc will raise an exception.
    :return: A selector for the updated objects and Result.
    """
    base_args = list()
    if overwrite:
        base_args.append('--overwrite')

    items, namespace_detected = _to_dict_list(str_dict_model_apiobject_or_list_thereof)

    # If there is nothing to act on, return empty selector
    if not items:
        return selector([])

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    # If we are supposed to update resource versions before performing the apply,
    # get a current copy of the incoming resources and update the incoming
    # objects with the server's resourceVersions, ignoring those which don't exist.
    if items and fetch_resource_versions:

        # I wish this could be implemented efficiently (single oc invocation which returns
        # content from across multiple namespaces), but https://bugzilla.redhat.com/show_bug.cgi?id=1727917
        # prevents it.
        for item in items:
            apiobj = APIObject(dict_to_model=item)
            server_apiobj = apiobj.current(ignore_not_found=True)
            # Does the object exist on the server?
            if server_apiobj:
                new_metadata = item.get('metadata', {})
                new_metadata['resourceVersion'] = server_apiobj.resource_version()
                item['metadata'] = new_metadata

    return __new_objects_action_selector("apply",
                                         cmd_args=["-f", "-", base_args, cmd_args],
                                         stdin_obj=m,
                                         no_namespace=namespace_detected,
                                         auto_raise=auto_raise)


def replace(str_dict_model_apiobject_or_list_thereof, force=False, cmd_args=None, auto_raise=True):
    """
    :param str_dict_model_apiobject_or_list_thereof: The definition of one or more API object.
        Can be string containing json or yaml, a python dict, an openshift.Model, or an openshift.APIObject.
        You can also provide a list containing multiple of these elements to update.
    :param force: Whether to send the --force argument to oc replace.
    :param cmd_args: Additional arguments for the verb.
    :param auto_raise: If True, errors from oc will raise an exception.
    :return: A selector for the updated objects and Result.
    """
    base_args = list()
    if force:
        base_args.append('--force')

    items, namespace_detected = _to_dict_list(str_dict_model_apiobject_or_list_thereof)

    # If there is nothing to act on, return empty selector
    if not items:
        return selector([])

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    return __new_objects_action_selector("replace",
                                         cmd_args=["-f", "-", base_args, cmd_args],
                                         stdin_obj=m,
                                         no_namespace=namespace_detected,
                                         auto_raise=auto_raise)


def build_configmap_dict(configmap_name, dir_path_or_paths=None, dir_ext_include=None, data_map=None, obj_labels=None):
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

    if data_map is None:
        data_map = {}

    if obj_labels is None:
        obj_labels = {}

    dm = dict(data_map)

    if dir_path_or_paths:

        # If we received a string, turn it into a list
        if isinstance(dir_path_or_paths, six.string_types):
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


def build_secret_dict(secret_name, dir_path_or_paths=None, dir_ext_include=None, data_map=None, obj_labels=None):
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

    if data_map is None:
        data_map = {}

    if obj_labels is None:
        obj_labels = {}

    dm = dict()

    # base64 encode the incoming data_map values
    for k, v in six.iteritems(data_map):
        dm[k] = base64.b64encode(v)

    if dir_path_or_paths:

        # If we received a string, turn it into a list
        if isinstance(dir_path_or_paths, six.string_types):
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


def build_secret_dockerconfigjson(secret_name, image_registry_auth_infos, obj_labels=None):
    """
    Creates a python dict structure for a 'kubernetes.io/dockerconfigjson' secret (it remains to the caller to send
    the yaml to the server with create()). This method does not use/require oc to be resident
    on the python host.
    :param secret_name: The metadata.name to include
    :param image_registry_auth_infos: An iterable collection of ImageRegistryAuthInfo
    :param obj_labels: Additional labels to include in the resulting secret metadata.
    :return: A python dict of a secret resource.
    """

    if obj_labels is None:
        obj_labels = {}

    auths = {}  # A map of registry urls to a map with a single element called 'auth'

    for ira in image_registry_auth_infos:
        b64_username_password = base64.b64encode('{}:{}'.format(ira.username, ira.password).encode()).decode()
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
    b64_dockerconfigjson = base64.b64encode(json.dumps(dockerconfig, indent=4).encode()).decode()

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


def build_list(*args):
    """
    Converts an arbitrary list of resources into a dict modeling a kube List.
    :param args: The incoming arguments can be json/yaml strings, dicts, or apiobjects.
    :return: A dict modeling a kube dict
    """
    return _to_dict_list(args)


def build_pod_simple(pod_name, image,
                     command=None,
                     namespace=None,
                     labels=None,
                     working_dir=None,
                     port=None,
                     host_network=False,
                     node_name=None,
                     restart_policy=None,
                     termination_grace_period=None,
                     service_account_name=None,
                     privileged=False,
                     host_mount=False,
                     api_version='v1',
                     ):
    if not labels:
        labels = {}

    metadata = {
        'name': pod_name,
        'labels': labels,
    }

    if namespace:
        metadata['namespace'] = namespace

    container0 = {
        'name': pod_name,
        'image': image,
    }

    if port:
        ports = [
            {
                'containerPort': port,
            },
        ]
        container0['ports'] = ports

    if command:
        # If command is not a list of some sort, make it into one
        if not util.is_collection_type(command):
            command = [command]
        container0['command'] = command

    if working_dir:
        container0['workingDir'] = working_dir

    if privileged or host_mount:
        container0['securityContext'] = {
            'privileged': True,
        }

    if host_mount:
        container0['volumeMounts'] = [
            {
                'name': 'host-volume',
                'mountPath': '/host',
                'readOnly': True,
            }
        ]

    spec = {
        'containers': [container0],
    }

    if restart_policy is not None:
        spec['restartPolicy'] = restart_policy

    if termination_grace_period is not None:
        spec['terminationGracePeriodSeconds'] = termination_grace_period

    if service_account_name:
        spec['serviceAccountName'] = service_account_name

    if host_network:
        spec['host_network'] = host_network

    if node_name:
        spec['node_name'] = node_name

    if host_mount:
        spec['volumes'] = [
            {
                'name': 'host-volume',
                'hostPath': {
                    'path': '/',
                }
            }
        ]

    pod = {
        'apiVersion': api_version,
        'kind': 'Pod',
        'metadata': metadata,
        'spec': spec,
    }

    return pod


def build_service_simple(service_name,
                         selector,
                         target_port,
                         namespace=None,
                         protocol='TCP',
                         service_port=None,
                         labels=None,
                         type='ClusterIP',
                         api_version='v1'):
    if not service_port:
        service_port = target_port

    if not labels:
        labels = {}

    metadata = {
        'name': service_name,
        'labels': labels,
    }

    if namespace:
        metadata['namespace'] = namespace

    spec = {
        'ports': [
            {
                'name': '{}'.format(target_port),
                'port': int(service_port),
                'protocol': protocol,
                'targetPort': int(target_port),
            }
        ],
        'selector': selector,
        'type': type,
    }

    service = {
        'apiVersion': api_version,
        'kind': 'Service',
        'metadata': metadata,
        'spec': spec,
    }

    return service


def build_secret_dockerconfig(secret_name, image_registry_auth_infos, obj_labels=None):
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

    if obj_labels is None:
        obj_labels = {}

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


def build_imagestream_simple(imagestream_name,
                             namespace=None,
                             labels=None,
                             local_lookup_policy=False,
                             api_version='image.openshift.io/v1'):
    if not labels:
        labels = {}

    metadata = {
        'name': imagestream_name,
        'labels': labels,
    }

    if namespace:
        metadata['namespace'] = namespace

    spec = {
        'lookupPolicy': {
                'local': local_lookup_policy
        }
    }

    imagestream = {
        'apiVersion': api_version,
        'kind': 'ImageStream',
        'metadata': metadata,
        'spec': spec,
    }

    return imagestream


def update_api_resources():
    """
    Makes a call to `oc api-resources` and updates openshift-client-python's internal view of
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
                            'Skipping information collection for daemonset pod on non-collected node: {}'.format(
                                obj.fqname()))
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
                  sdn_pods=None,
                  fluentd_pods=None,
                  num_combined_journal_entries=10000,
                  num_critical_journal_entries=10000,
                  status_printer=eprint):
    node_dir = util.mkdir_p(output_dir)

    if sdn_pods is None:
        sdn_pods = []

    if fluentd_pods is None:
        fluentd_pods = []

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
                f.write(six.text_type(invoke('status').out()))

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
                    additional_nodes=None,
                    additional_projects=None,
                    additional_namespaced_kinds=None,
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

    if additional_nodes is None:
        additional_nodes = []

    if additional_projects is None:
        additional_projects = []

    if additional_namespaced_kinds is None:
        additional_namespaced_kinds = []

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
                    key_filename=None,
                    auto_add_host=True,
                    connect_timeout=600,
                    through_client_host=True,
                    address_type_pref="ExternalDNS,ExternalIP,Hostname",
                    paramiko_connect_extras=None,
                    ):
    """
    Returns a paramiko ssh client connected to the named cluster node. The caller is responsible for closing the
    connection -- use as a contextmanager is recommended.
    :param apiobj_node_name_or_qname: The name of the node or the apiobject representing the node to ssh to. If None,
    tries to return the ssh_client associated with current client_host context, if any.
    :param port: The ssh port
    :param username: The username to use
    :param password: The username's password
    :param key_filename: The filename of optional private key and/or cert to try for authentication
    :param auto_add_host: Whether to auto accept host certificates
    :param connect_timeout: Connection timeout
    :param through_client_host: If True, and client_host is being used, ssh will be initiated
    through the client_host ssh connection. Username/password used for client_host will propagate
    unless overridden.
    :param address_type_pref: Comma delimited list of node address types. Types will be tried in
            the order specified.
    :param paramiko_connect_extras: An optional dictionary of kwargs to pass to the underlying SSH client connection method.
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
        qname = naming.qualify_name(apiobj_node_name_or_qname, 'node')
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

            paramiko_connect_extras = paramiko_connect_extras or {}
            ssh_client.connect(hostname=address, port=port, username=username,
                               password=password, key_filename=key_filename,
                               timeout=connect_timeout, sock=host_sock,
                               **paramiko_connect_extras)

            # Enable agent fowarding
            paramiko.agent.AgentRequestHandler(ssh_client.get_transport().open_session())

            return ssh_client

    raise IOError("Unable to find any address with type ({}) for: {}".format(address_type_pref, apiobj.qname()))


def node_ssh_await(apiobj_node_name_or_qname=None,
                   timeout_seconds=600,
                   port=22,
                   username=None,
                   password=None,
                   key_filename=None,
                   auto_add_host=True,
                   through_client_host=True,
                   address_type_pref="ExternalDNS,ExternalIP,Hostname",
                   paramiko_connect_extras=None
                   ):
    """
    Periodically attempts to connect to a node's ssh server.
    :param apiobj_node_name_or_qname: The name of the node or the apiobject representing the node to ssh to. If None,
    tries to return the ssh_client associated with current client_host context, if any.
    :param port: The ssh port
    :param username: The username to use
    :param password: The username's password
    :param key_filename: The filename of optional private key and/or cert to try for authentication
    :param auto_add_host: Whether to auto accept host certificates
    :param connect_timeout: Connection timeout
    :param through_client_host: If True, and client_host is being used, ssh will be initiated
    through the client_host ssh connection. Username/password used for client_host will propagate
    unless overridden.
    :param address_type_pref: Comma delimited list of node address types. Types will be tried in
            the order specified.
    :param paramiko_connect_extras: An optional dictionary of kwargs to pass to the underlying SSH client connection method.
    :return: N/A, but throws the last exception received if timeout occurs.
    """

    timeout_seconds = int(timeout_seconds)
    timeout_start = time.time()

    while True:
        try:
            with node_ssh_client(apiobj_node_name_or_qname=apiobj_node_name_or_qname,
                                 port=port,
                                 username=username,
                                 password=password,
                                 key_filename=key_filename,
                                 auto_add_host=auto_add_host,
                                 connect_timeout=25,
                                 through_client_host=through_client_host,
                                 address_type_pref=address_type_pref,
                                 paramiko_connect_extras=paramiko_connect_extras) as ssh_client:
                return

        except Exception as e:
            time.sleep(10)
            if time.time() > timeout_start + timeout_seconds:
                raise


def node_ssh_client_exec(apiobj_node_name_or_qname=None,
                         cmd_str=None,
                         stdin_str=None,
                         port=22,
                         username=None,
                         password=None,
                         key_filename=None,
                         auto_add_host=True,
                         connect_timeout=600,
                         through_client_host=True,
                         address_type_pref="ExternalDNS,ExternalIP,Hostname",
                         paramiko_connect_extras=None,
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
    :param key_filename: The filename of optional private key and/or cert to try for authentication
    :param auto_add_host: Whether to auto accept host certificates
    :param connect_timeout: Connection timeout
    :param through_client_host: If True, and client_host is being used, ssh will be initiated
    through the client_host ssh connection. Username/password used for client_host will propagate
    unless overridden.
    :param address_type_pref: Comma delimited list of node address types. Types will be tried in
            the order specified.
    :param paramiko_connect_extras: An optional dictionary of kwargs to pass to the underlying SSH client connection method.
    :return: rc, stdout, stderr
    """

    with node_ssh_client(apiobj_node_name_or_qname=apiobj_node_name_or_qname,
                         port=port,
                         username=username,
                         password=password,
                         key_filename=key_filename,
                         auto_add_host=auto_add_host,
                         connect_timeout=connect_timeout,
                         through_client_host=through_client_host,
                         address_type_pref=address_type_pref,
                         paramiko_connect_extras=paramiko_connect_extras) as ssh_client:
        ssh_stdin, ssh_stdout, ssh_stderr = ssh_client.exec_command(cmd_str)

        if stdin_str:
            ssh_stdin.write(stdin_str)
            ssh_stdin.flush()
            ssh_stdin.channel.shutdown_write()

        stdout = ssh_stdout.read().decode('utf-8', errors='ignore')
        stderr = ssh_stderr.read().decode('utf-8', errors='ignore')
        return_code = ssh_stdout.channel.recv_exit_status()

        return return_code, stdout, stderr


"""
There is a small number of APIs that appear in an API Group that is specified as only
an unclassified version, like "v1".  This is something specific to OpenShift V4, but 
to be consistent, Im adding logic that handles this across versions.
"""
SUPPORTED_SINGULAR_API_GROUP_SUFFIXES = ["v1"]


def _is_singular_api_group(group):
    for suffix in SUPPORTED_SINGULAR_API_GROUP_SUFFIXES:
        if group.endswith('.{}'.format(suffix)):
            return True
    return False


def get_gettable_kinds():
    """
    Returns a list of the 'gettable' (i.e. oc get <kind> will work) kinds known to openshift-client-python.
    You can run `oc.update_api_resources` first if this needs to be exact for a cluster.
    :return: list<string> where each entry is a valid kind
    """
    kinds = []
    for kind in naming.get_api_resources_kinds():
        if '/' in kind:
            kinds.append(kind.split('/')[0])
        else:
            if _is_singular_api_group(kind):
                kinds.append(kind.split('.')[0])
            else:
                kinds.append(kind)

    return kinds

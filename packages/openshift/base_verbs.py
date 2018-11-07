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
import paramiko
import base64
import io


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
    :param cmd_args: Additional arguments to pass to 'oc project'
    :return: The current user
    """

    r = Result("whoami")
    r.add_action(oc_action(cur_context(), "whoami", cmd_args=cmd_args))
    r.fail_if("Unable to determine current user")
    return r.out().strip()


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
            i = i.model()

        if isinstance(i, Model):
            i = i._primitive()

        if not isinstance(i, dict):
            raise ValueError('Unable to convert type into json: {}'.format(type(i)))

        l.append(i)

    return l


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
    :return: Returns the version of the oc server being accessed
    """

    r = Result('version')
    r.add_action(oc_action(cur_context(), verb='version'))
    r.fail_if('Unable to determine version')
    for line in reversed(r.out().splitlines()):
        if line.startswith('openshift '):
            return line.split()[1]

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
    Creates a python dict structure for a secret (if remains to the caller to send
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


def dumpinfo_apiobject(dir, obj, log_timestamps=True, logs_since=None, logs_tail=-1):
    util.mkdir_p(dir)
    prefix = os.path.join(dir, obj.name())

    with no_tracking():
        with io.open(prefix + '.describe', mode='w', encoding="utf-8") as f:
            f.write(unicode(obj.describe()))

        if not naming.kind_matches(obj.kind(), 'secret'):
            with io.open(prefix + '.json', mode='w', encoding="utf-8") as f:
                f.write(unicode(obj.as_json()))

        if naming.kind_matches(obj.kind(), ['pod', 'build']):
            with io.open(prefix + '.logs', mode='w', encoding="utf-8") as f:
                obj.print_logs(f, timestamps=log_timestamps, since=logs_since, tail=logs_tail)


def dumpinfo_project(dir,
                     project_name,
                     kinds=['ds', 'dc', 'build', 'statefulset', 'deployment', 'pod', 'rs', 'rc', 'configmap'],
                     logs_since=None,
                     logs_tail=-1):
    project_name = naming.qualify_name(project_name, 'project')

    print('Collecting info for: {}'.format(project_name))

    util.mkdir_p(dir)
    with no_tracking():

        # if the project does not exist, just a leave a file saying we tried
        if selector(project_name).count_existing() == 0:
            with io.open(os.path.join(dir, 'not-found'), mode='w', encoding="utf-8") as f:
                f.write(u'{} was not found'.format(project_name))
            return

        with project(project_name):

            with io.open(os.path.join(dir, 'status'), mode='w', encoding="utf-8") as f:
                f.write(unicode(invoke('status').out()))

            for obj in selector(kinds).objects():
                print('Collecting information about: {}'.format(obj.fqname()))
                obj_dir = os.path.join(dir, obj.kind())
                dumpinfo_apiobject(obj_dir, obj, logs_since=logs_since, logs_tail=logs_tail)


def dumpinfo_system(base_dir,
                    additional_nodes=[],
                    additional_projects=[],
                    additional_namespaced_kinds=[],
                    include_crd_kinds=False,
                    num_combined_journal_entries=10000,
                    num_critical_journal_entries=10000,
                    logs_since=None,
                    logs_tail=-1):
    util.mkdir_p(base_dir)

    kinds = set(['ds', 'dc', 'build', 'statefulset', 'deployment', 'pod', 'rs', 'rc', 'configmap'])
    kinds.update(additional_namespaced_kinds)

    if include_crd_kinds:
        # At the time of this comment, you need to add specific privileges to read CRs. Eventually,
        # master team should allow CRDs to express whether they contain sensitive information and
        # remove this restriction. As such, turning this flag True is not recommended until
        # master acts on this.
        for crd_obj in selector('crd').objects():
            if crd_obj.model.spec.scope == 'Namespaced':
                kinds.add(crd_obj.name())

    # A large amount of stdout is going to be generated,
    # don't burden memory by trying to store it in trackers.
    with no_tracking():

        # Start with a base set of master nodes and append additional nodes.
        node_qnames = set(selector('node', labels={'node-role.kubernetes.io/master': True}).qnames())
        for node_name in additional_nodes:
            if '/' not in node_name:
                node_name = 'node/' + node_name.lower()
            node_qnames.add(node_name)

        node_sel = selector(node_qnames)
        fluentd_pods = selector('pod', labels={'component': 'fluentd'}, all_namespaces=True).objects()
        print('Found {} fluentd pods on cluster'.format(len(fluentd_pods)))

        for node in node_sel.objects():
            node_dir = util.mkdir_p(os.path.join(base_dir, 'node', node.name()))
            dumpinfo_apiobject(node_dir, node)

            # If possible, find a fluentd pod that is scheduled on the node. The fluentd pod mounts in the
            # host's journal directories -- so we capture information for debug.
            node_fluentd_pod = next((pod for pod in fluentd_pods if pod.model.spec.nodeName == node.name()), None)
            if node_fluentd_pod:

                print('Collecting combined journal from: {}'.format(node.name()))
                with io.open(os.path.join(node_dir, 'combined.journal.export'), mode='w', encoding="utf-8") as f:
                    capture_action = node_fluentd_pod.execute(cmd_to_exec=['journalctl',
                                                                           '-D', '/var/log/journal',
                                                                           '-o', 'export',
                                                                           '-n', num_combined_journal_entries,
                                                                           ],
                                                              auto_raise=False)
                    f.write(capture_action.out())

                # In case extraneous events are flooding, isolate important services as well
                print('Collecting critical services journal from: {}'.format(node.name()))
                with io.open(os.path.join(node_dir, 'critical.journal.export'), mode='w', encoding="utf-8") as f:
                    capture_action = node_fluentd_pod.execute(cmd_to_exec=['journalctl',
                                                                           '-D', '/var/log/journal',  # Where fluentd mounts hosts journal
                                                                           '-o', 'export',  # This can be converted back into .journal with systemd-journal-remote
                                                                           '-n', num_critical_journal_entries,  # Number of recent events to gather critical services
                                                                           '-u', 'crio',
                                                                           '-u', 'atomic-openshift-node',
                                                                           '-u', 'docker',
                                                                           ],
                                                              auto_raise=False)
                    f.write(capture_action.out())
            else:
                print('Unable to find a fluentd pod in the cluster for node {}'.format(node.name()))

        projects = set(['kube-system', 'openshift-sdn', 'openshift-config', 'openshift-node'])
        projects.update(additional_projects)

        for project_name in projects:
            dumpinfo_project(os.path.join(base_dir, 'project', project_name), project_name, kinds=kinds, logs_since=logs_since, logs_tail=logs_tail)


def node_ssh_client(apiobj_node_name_or_qname,
                    port=22,
                    username=None,
                    password=None,
                    auto_add_host=True,
                    connect_timeout=600,
                    through_client_host=True,
                    address_type_pref="ExternalDNS,ExternalIP,Hostname"
                    ):
    """
    Returns a paramiko ssh client connected to the named cluster node. If a
    :param node_name: The name of the node (e.g. oc get node THE_NAME)
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

    if isinstance(apiobj_node_name_or_qname, APIObject):
        apiobj = apiobj_node_name_or_qname

    else:
        if '/' not in apiobj_node_name_or_qname:
            qname = 'node/{}'.format(apiobj_node_name_or_qname)
        else:
            qname = apiobj_node_name_or_qname

        apiobj = selector(qname).object()

    print("Checking node: {}".format(apiobj.qname()))
    address_entries = apiobj.model().status.addresses

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

            print("Trying: {}".format(address))
            ssh_client.connect(hostname=address, port=port, username=username,
                               password=password, timeout=connect_timeout,
                               sock=host_sock)

            # Enable agent fowarding
            paramiko.agent.AgentRequestHandler(ssh_client.get_transport().open_session())

            return ssh_client

    raise IOError("Unable to find any address with type ({}) for: {}".format(address_type_pref, apiobj.qname()))

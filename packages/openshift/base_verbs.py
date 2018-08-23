from .selector import Selector, selector
from .action import oc_action
from .context import cur_context, project
from .result import Result
from .apiobject import APIObject
from .model import Model, Missing
import paramiko


def __new_objects_action_selector(verb, cmd_args=[], stdin_obj=None):

    """
    Performs and oc action and records objects output from the verb
    as changed in the content.
    :param verb: The verb to execute
    :param cmd_args: A list of str|list<str> which will be flattened into command line arguments
    :param stdin_obj: The standard input to feed to the invocation.
    :return: A selector for the newly created objects
    """

    sel = Selector(verb, object_action=oc_action(cur_context(), verb, cmd_args=['-o=name', cmd_args], stdin_obj=stdin_obj))
    sel.fail_if('{} returned an error: {}'.format(verb, sel.err().strip()))
    return sel


def new_app(*args):
    return __new_objects_action_selector("new-app", cmd_args=args)


def new_build(*args):
    return __new_objects_action_selector("new-build", cmd_args=args)


def start_build(*args):
    return __new_objects_action_selector("start-build", cmd_args=args)


def get_project_name(*args):
    """
    :param args: Additional arguments to pass to 'oc project'
    :return: The name of the current project
    """

    r = Result("project-name")
    r.add_action(oc_action(cur_context(), "project", cmd_args=["-q", args]))
    r.fail_if("Unable to determine current project")
    return r.out()


def new_project(name, *args):
    """
    Creates a new project
    :param name: The name of the project to create
    :param args: Additional arguments to pass on the command line
    :return: A context manage that can be used with 'with' statement.
    """
    r = Result("new-project")
    r.add_action(oc_action(cur_context(), "new-project", cmd_args=[name, args]))
    r.fail_if("Unable to create new project: {}".format(name))
    return project(name)


def delete_project(name, ignore_not_found=False, *args):
    r = Result("delete-project")
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

    # If there is nothing to act on, return empty selector
    if not items:
        return selector([])

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': items
    }

    return __new_objects_action_selector("create", cmd_args=["-f", "-", cmd_args], stdin_obj=m)


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

    print "Checking node: {}".format(apiobj.qname())
    address_entries = apiobj.model().status.addresses

    if address_entries is Missing:
        raise IOError("Error finding addresses associated with: {}".format(apiobj.qname()))

    for address_type in address_type_pref.split(','):
        # Find the first address of the preferred type:
        address = next((entry.address for entry in address_entries if entry.type.lower() == address_type.lower().strip()), None)
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

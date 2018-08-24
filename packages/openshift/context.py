from datetime import datetime
from datetime import timedelta
from threading import local
import paramiko

from .result import Result

# All threads will have a context which is
# managed by a stack of Context objects. As
# a thread establish additional context using
# 'with' statements, the stack will push/grow. As
# 'with' blocks end, the stack will pop/shrink.
context = local()

context.stack = []
context.default_kubeconfig_path = None
context.default_cluster = None
context.default_project = None
context.default_options = {}
context.default_loglevel = None


def cur_context():
    return context.stack[-1]


class Context(object):
    def __init__(self):
        self.parent = None
        self.kubeconfig_path = None
        self.api_url = None
        self.project_name = None
        self.loglevel_value = None
        self.context_result = None
        self.timeout_datetime = None
        self.options = None

        # ssh configuration
        self.ssh_client = None
        self.ssh_hostname = None
        self.ssh_port = 22
        self.ssh_username = None
        self.ssh_password = None
        self.ssh_timeout = 600
        self.ssh_auto_add_host = False

    def __enter__(self):
        if len(context.stack) > 0:
            self.parent = context.stack[-1]
        context.stack.append(self)

        if self.ssh_hostname:
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.load_system_host_keys()

            if self.ssh_auto_add_host:
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.ssh_client.connect(hostname=self.ssh_hostname, port=self.ssh_port, username=self.ssh_username,
                                password=self.ssh_password, timeout=self.ssh_timeout)

            # Enable agent fowarding
            transport = self.ssh_client.get_transport()
            paramiko.agent.AgentRequestHandler(transport.open_session())

        return self

    def __exit__(self, type, value, traceback):
        context.stack.pop()

        # Shutdown ssh if it is in use
        if self.ssh_client:
            self.ssh_client.close()
            self.ssh_client = None

    def get_api_url(self):
        if self.api_url is not None:
            return self.api_url
        if self.parent is not None:
            return self.parent.get_api_url()
        return context.default_cluster

    def get_kubeconfig_path(self):
        if self.kubeconfig_path is not None:
            return self.kubeconfig_path
        if self.parent is not None:
            return self.parent.get_kubeconfig_path()
        return context.default_kubeconfig_path

    def get_ssh_client(self):
        """
        :rtype SSHClient:
        """
        if self.ssh_client is not None:
            return self.ssh_client
        if self.parent is not None:
            return self.parent.get_ssh_client()
        return None

    def get_ssh_username(self):
        if self.ssh_username is not None:
            return self.ssh_username
        if self.parent is not None:
            return self.parent.get_ssh_username()
        return None

    def get_ssh_password(self):
        if self.ssh_password is not None:
            return self.ssh_password
        if self.parent is not None:
            return self.parent.get_ssh_password()
        return None

    def get_ssh_hostname(self):
        if self.ssh_hostname is not None:
            return self.ssh_hostname
        if self.parent is not None:
            return self.parent.get_ssh_hostname()
        return None

    def get_project(self):
        if self.project_name is not None:
            return self.project_name
        # if cluster is changing, don't check parent for project
        # with project must always be inside with cluster.
        if self.api_url is None and self.parent is not None:
            return self.parent.get_project()
        return context.default_project

    def get_options(self, add_to={}):

        aggregate = add_to

        # If we are the top context, apply default options
        if not self.parent:
            aggregate.update(context.default_options)
        else:
            # Otherwise, aggregate our ancestor options recursively
            self.parent.get_options(add_to=aggregate)

        # Contribute the options of this context (override anything from ancestors)
        if self.options:
            aggregate.update(self.options)

        return aggregate

    def get_loglevel(self):
        if self.loglevel_value is not None:
            return self.loglevel_value
        if self.parent is not None:
            return self.parent.get_loglevel()
        return context.default_loglevel

    # Returns true if any surrounding timeout context is
    # expired.
    def is_out_of_time(self):
        c = self
        now = datetime.utcnow()
        while c is not None:
            if c.timeout_datetime is not None and now > c.timeout_datetime:
                return True
            c = c.parent
        return False

    def get_min_remaining_seconds(self):
        """
        :return: Returns the number of seconds a command needs to finish to satisfy
        existing timeout contexts. A minimum of 1 second is always returned
        if a timeout context exists. If no timeout context exists, None is returned.
        """
        c = self
        min_secs = None
        now = datetime.utcnow()
        while c is not None:
            if c.timeout_datetime is not None:
                if now > c.timeout_datetime:
                    return 1
                elif min_secs is None:
                    min_secs = (c.timeout_datetime-now).total_seconds()
                else:
                    min_secs = min((c.timeout_datetime-now).total_seconds(), min_secs)
            c = c.parent

        if min_secs and min_secs < 1:
            return 1

        return min_secs

    # Returns a master "Result" of all actions registered with this context.
    # If no actions were performed, an empty list is returned.
    def get_result(self):
        return self.context_result

    # Add an actions to any tracker
    # contexts enclosing the current context.
    def register_action(self, action):
        c = self
        while c is not None:
            if c.context_result is not None:
                c.context_result.add_action(action)
            c = c.parent


def set_default_kubeconfig_path(path):
    context.default_kubeconfig_path = path


def set_default_api_url(url):
    context.default_api_url = url


def set_default_project(name):
    context.default_project = name


def set_default_token(v):
    context.default_token = v


def set_default_loglevel(v):
    context.default_loglevel = v


def blank():
    """
    :return:  Returns a blank context which can be used to temporarily replace a real context in a with statement.
    Mostly useful for debugging programs without having to tab/untab a large amount of code.
    """
    c = Context()
    return c


def client_host(hostname, port=22, username=None, password=None, auto_add_host=False, connect_timeout=600):
    """
    Will ssh to the specified host to in order to run oc commands
    :param hostname: The hostname or IP address
    :param port: The ssh port
    :param username: The username to use
    :param password: The username's password
    :param auto_add_host: Whether to auto accept host certificates
    :param connect_timeout: Connection timeout
    :return:
    """
    c = Context()

    c.ssh_hostname = hostname
    c.ssh_port = port
    c.ssh_username = username
    c.ssh_password = password
    c.ssh_timeout = connect_timeout
    c.ssh_auto_add_host = auto_add_host

    return c


def cluster(api_url=None, kubeconfig_path=None):
    """
    Establishes a context in which inner oc interactions
    will target the specified OpenShift cluster. cluster contexts
    can be nested. The most immediate ancestor cluster context
    will define the cluster targeted by an action.
    :param name: The name of the project.
    :return: The context object. Can be safely ignored.
    """

    c = Context()
    c.kubeconfig_path = kubeconfig_path
    c.api_url = api_url
    return c


def project(name):
    """
    Establishes a context in which inner oc interactions
    will impact the named OpenShift project. project contexts
    can be nested. The most immediate ancestor project context
    will define the project used by an action.
    :param name: The name of the project.
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    # split is to strip qualifier off if specified ('project/test' -> 'test')
    c.project_name = name.split("/")[-1]
    return c


def tracker():
    """
    Establishes a context in which all inner actions will
    be tracked. Trackers can be nested -- all actions
    performed within a tracker's context will be tracked.
    :return: The tracker context. Call get_result to see
    all tracked actions.
    """
    c = Context()
    c.context_result = Result("tracker")
    return c


def options(*args):
    """
    Establishes a context in which inner oc invocations will be passed
    an arbitrary set of options. This is most useful in ensuring, for
    example, that a certain --token, --as, --context, etc, is passed to each
    oc invocation.

    Keys should be long form option names, without preceding hyphens. e.g.
    { 'token': '.....' } .

    Unlike most other contexts, .options is additive. If on oc invocation is
    embedded within two .options, it will include both sets. Inner option
    contexts will override the same key specified at outer levels. A value
    of None will prevent the option from being passed.

    Tip for flags: Even flags like --insecure-skip-tls-verify can be
    specified as key=value:  --insecure-skip-tls-verify=true

    :param args: A vararg list of dicts.
        Keys in dicts will be pre-pended with '-' if single letter or
        '--' if multiple letter not already preceded with a hyphen.

    :return: The context object. Can be safely ignored.
    """

    c = Context()
    c.options = {}

    for d in args:
        c.options.update(d)

    return c


# Example: with loglevel(x):
# Creates a new context with the specified log level.
def loglevel(v):
    """
    Establishes a context in which inner oc interactions
    will execute with the specified loglevel. loglevel contexts
    can be nested. The most immediate ancestor loglevel context
    will define the loglevel used by an action.
    :param v: The loglevel to use (0-9).
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    c.loglevel_value = v
    return c


def timeout(seconds):
    """
    Establishes a context in which inner oc interactions
    must terminate within a specified period. timeout contexts
    can be nested and each nested layer will be enforced.
    If actions run longer than the specified timeout, an exception
    will be thrown.
    :param seconds: The number of seconds before actions should time out.
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    if seconds is not None:
        c.timeout_datetime = datetime.utcnow() + timedelta(seconds=seconds)
    return c


# Ensure stack always has at least one member to simplify getting last
# with [-1]
context.stack = [Context()]

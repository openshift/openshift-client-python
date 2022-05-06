from __future__ import absolute_import

import inspect
import os

from datetime import datetime
from datetime import timedelta
from threading import local

from .result import Result

# Provides defaults for ssh_client context instantiations
DEFAULT_SSH_HOSTNAME = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_HOSTNAME", None)
DEFAULT_SSH_USERNAME = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_USERNAME", None)
DEFAULT_SSH_PORT = int(os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_PORT", "22"))
DEFAULT_SSH_AUTO_ADD = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_AUTO_ADD", "false").lower() in (
"yes", "true", "t", "y", "1")
DEFAULT_LOAD_SYSTEM_HOST_KEYS = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_LOAD_SYSTEM_HOST_KEYS", "true").lower() in (
"yes", "true", "t", "y", "1")

# If set, --insecure-skip-tls-verify will be included on all oc invocations
GLOBAL_SKIP_TLS_VERIFY = os.getenv("OPENSHIFT_CLIENT_PYTHON_SKIP_TLS_VERIFY", "false").lower() in (
"yes", "true", "t", "y", "1")

# Environment variable can specify generally how long openshift operations can execute before an exception
MASTER_TIMEOUT = int(os.getenv("OPENSHIFT_CLIENT_PYTHON_MASTER_TIMEOUT", -1))


def cur_context():
    return context.stack[-1]


class Context(object):
    def __init__(self):
        self.parent = None
        self.oc_path = None
        self.kubeconfig_path = None
        self.api_url = None
        self.token = None
        self.ca_cert_path = None
        self.project_name = None
        self.loglevel_value = None
        self.skip_tls_verify = None
        self.tracking_strategy = None
        self.no_tracking = False
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
        self.ssh_load_system_host_keys = True

        # Find the source code that appears to have created this Context
        self.frame_info = None
        for frame in inspect.stack():
            module = inspect.getmodule(frame[0])
            if module and (module.__name__ == 'openshift' or module.__name__.startswith('openshift.')):
                # The source appears to be within this module; skip this frame
                continue

            self.frame_info = inspect.getframeinfo(frame[0])
            break

    def __enter__(self):
        if len(context.stack) > 0:
            self.parent = context.stack[-1]
        context.stack.append(self)
        self.reconnect_ssh()
        return self

    def close_ssh(self):
        # Shutdown ssh if it is in use
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except:
                pass
            self.ssh_client = None

    def reconnect_ssh(self):
        """
        If you lose a connection to the bastion, you can restablish it.
        :return:
        """
        self.close_ssh()
        if self.ssh_hostname:

            # Just-in-time import to avoid hard dependency. Allows
            # you to use local 'oc' without having paramiko installed.
            import paramiko

            # https://github.com/paramiko/paramiko/issues/175#issuecomment-24125451
            paramiko.packet.Packetizer.REKEY_BYTES = pow(2, 40)
            paramiko.packet.Packetizer.REKEY_PACKETS = pow(2, 40)

            self.ssh_client = paramiko.SSHClient()

            # Should we load known_hosts?
            if self.ssh_load_system_host_keys:
                self.ssh_client.load_system_host_keys()

            # Should we trust an unknown host?
            if self.ssh_auto_add_host:
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.ssh_client.connect(hostname=self.ssh_hostname, port=self.ssh_port, username=self.ssh_username,
                                    password=self.ssh_password, timeout=self.ssh_timeout)

            # Enable agent fowarding
            transport = self.ssh_client.get_transport()
            paramiko.agent.AgentRequestHandler(transport.open_session())

    def __exit__(self, type, value, traceback):
        context.stack.pop()
        self.close_ssh()

    def get_api_url(self):

        if self.api_url is not None:
            return self.api_url
        if self.parent is not None:
            return self.parent.get_api_url()
        return context.default_api_server

    def get_token(self):

        if self.token is not None:
            return self.token
        if self.parent is not None:
            return self.parent.get_token()
        return context.default_token

    def get_ca_cert_path(self):

        if self.ca_cert_path is not None:
            return self.ca_cert_path
        if self.parent is not None:
            return self.parent.get_ca_cert_path()
        return context.default_ca_cert_path

    def get_oc_path(self):
        if self.oc_path is not None:
            return self.oc_path
        if self.parent is not None:
            return self.parent.get_oc_path()
        return context.default_oc_path

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

    def get_options(self, add_to=None):

        if add_to is None:
            add_to = {}

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

    def get_skip_tls_verify(self):
        if self.skip_tls_verify is not None:
            return self.skip_tls_verify
        if self.parent is not None:
            return self.parent.get_skip_tls_verify()
        return context.default_skip_tls_verify

    def get_out_of_time(self):
        """
        :return: Returns any Context which claims it is timed out. Returns (True,Context) if any surrounding timeout context is expired. If not, returns (False,None)
        """

        # Unlike most context methods, timeout methods use cur_context instead of self.
        # This allows selectors/apiobjects captured in one timeout block to be used in another.
        c = cur_context()
        now = datetime.utcnow()
        while c is not None:
            if c.timeout_datetime is not None and now > c.timeout_datetime:
                return True, c
            c = c.parent
        return False, None

    def get_min_remaining_seconds(self):
        """
        :return: Returns the number of seconds a command needs to finish to satisfy
        existing timeout contexts and the Context which possessed the minimum; i.e. (secs, Context).
        A minimum of 1 second is always returned if a timeout context exists. If no timeout context exists,
        (None,None) is returned.
        """

        # Unlike most context methods, timeout methods use cur_context instead of self.
        # This allows selectors/apiobjects captured in one timeout block to be used in another.
        c = cur_context()
        min_secs = None
        now = datetime.utcnow()
        limiting_context = None
        while c is not None:
            if c.timeout_datetime is not None:
                if now > c.timeout_datetime:
                    return 1, c
                elif min_secs is None:
                    min_secs = (c.timeout_datetime - now).total_seconds()
                    limiting_context = c
                elif (c.timeout_datetime - now).total_seconds() < min_secs:
                    limiting_context = c
                    min_secs = (c.timeout_datetime - now).total_seconds()
            c = c.parent

        if min_secs is not None and min_secs < 1:
            return 1, limiting_context

        return min_secs, limiting_context

    def get_result(self):
        """
        :return: If this contextmanager was returned by `with tracking()`, returns
        the Result object which has tracked all internal oc invocations. Otherwise,
        returns None.
        """

        # Check instance type since this could also be a user's callable.
        if isinstance(self.tracking_strategy, Result):
            return self.tracking_strategy
        else:
            return None

    # Add an actions to any tracking
    # contexts enclosing the current context.
    # Adds will be terminated if a no_tracking context is encountered.
    def register_action(self, action):
        c = self
        while c is not None:
            if c.no_tracking:
                return

            if c.tracking_strategy:
                if isinstance(c.tracking_strategy, Result):
                    c.tracking_strategy.add_action(action)
                else:
                    c.tracking_strategy(action)

            c = c.parent

    def set_timeout(self, seconds):
        """
        Sets the internal timeout for this context the specified number of
        seconds in the future from the time it is called. Internal use only.
        :param seconds: The number of seconds from now to start timing out oc invocations. If None, timeout
            for this context is cleared.
        :return: N/A
        """
        if seconds and seconds > 0:
            self.timeout_datetime = datetime.utcnow() + timedelta(seconds=seconds)
        else:
            self.timeout_datetime = None


def set_default_oc_path(path):
    """
    Sets the default full patch of the oc binary to execute for this thread.
    If no client_path() context is in use, this path will be used.
    """
    context.default_oc_path = path


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


def set_default_skip_tls_verify(do_skip):
    context.default_skip_tls_verify = do_skip


def blank():
    """
    :return:  Returns a blank context which can be used to temporarily replace a real context in a with statement.
    Mostly useful for debugging programs without having to tab/untab a large amount of code.
    """
    c = Context()
    return c


def client_host(hostname=None, port=DEFAULT_SSH_PORT, username=DEFAULT_SSH_USERNAME, password=None,
                auto_add_host=DEFAULT_SSH_AUTO_ADD, load_system_host_keys=DEFAULT_LOAD_SYSTEM_HOST_KEYS,
                connect_timeout=600):
    """
    Will ssh to the specified host to in order to run oc commands. If hostname is not specified,
    the environment variable OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_HOSTNAME will be used. If the environment variable is
    not defined, this context will have no effect and the current host will be assumed to be the
    host on which oc will be run.
    :param hostname: The hostname or IP address. Defaults to environment variable OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_HOSTNAME if None.
            If the hostname is of the form 'user@host', the string will be split and the user will take precedence over
            any argument / environment variable supplied.
    :param port: The ssh port. Defaults to OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_PORT, then None.
    :param username: The username to use. Defaults to OPENSHIFT_CLIENT_PYTHON_DEFAULT_USERNAME, then None.
    :param password: The username's password
    :param auto_add_host: Whether to auto accept host certificates. Defaults to OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_AUTO_ADD, then false.
    :param load_system_host_keys: Whether load known_hosts. Defaults to DEFAULT_LOAD_SYSTEM_HOST_KEYS, then true.
    :param connect_timeout: Connection timeout
    :return:
    """
    c = Context()

    if hostname is None:
        hostname = DEFAULT_SSH_HOSTNAME

    if hostname and '@' in hostname:
        c.ssh_username, c.ssh_hostname = hostname.split('@', 1)
    else:
        c.ssh_hostname = hostname
        c.ssh_username = username

    c.ssh_port = port
    c.ssh_password = password
    c.ssh_timeout = connect_timeout
    c.ssh_auto_add_host = auto_add_host
    c.ssh_load_system_host_keys = load_system_host_keys

    return c


def client_path(oc_path):
    """
    Specifies the full path to the oc binary in this context. If unspecified, 'oc' is invoked and
    it should be in $PATH.
    :param oc_path: Fully path to executable oc binary
    :return:
    """
    c = Context()

    c.oc_path = oc_path
    return c


def api_server(api_url=None, ca_cert_path=None, kubeconfig_path=None):
    """
    Establishes a context in which inner oc interactions
    will target the specified OpenShift API server (--server arguments).
    Contexts can be nested. The most immediate ancestor cluster context
    will define the API server targeted by an action.
    :param api_url: The oc --server argument to use.
    :param kubeconfig_path: The oc --kubeconfig argument to use.
    :return: The context object. Can be safely ignored.
    """

    c = Context()
    c.kubeconfig_path = kubeconfig_path
    c.api_url = api_url
    c.ca_cert_path = ca_cert_path
    return c


def token(val=None):
    """
    Establishes a context in which inner oc interactions
    will include the specified token on the command line with --token.
    :param val: The oc --token argument to use.
    :return: The context object. Can be safely ignored.
    """

    c = Context()
    c.token = val
    return c


def project(name):
    """
    Establishes a context in which inner oc interactions
    will impact the named OpenShift project. project contexts
    can be nested. The most immediate ancestor project context
    will define the project used by an action.
    :param name: The name of the project. If None, parent context project will be used.
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    if not name:
        return c

    # split is to strip qualifier off if specified ('project/test' -> 'test')
    c.project_name = name.split("/")[-1]
    return c


def tracking(action_handler=None, limit=None):
    """
    Establishes a context in which all inner actions will
    be tracked (unless a inner no_tracking context prevents
    tracking). Trackers can be nested -- all actions
    performed within a tracker's context will be tracked unless
    there is a descendant no_tracking context which blocks tracking
    from propagating to this ancestor.
    :param action_handler: If specified, after each oc action is
    performed, this method will be called with the Action object.
    If not specified, all Actions will aggregate into a internally
    managed Result object which can be accessed with get_result.
    :param limit: If specified, it allows to specify a limit on the
    number of actions stored by a given tracking context. If not
    specified or given a value less than 0, it will store unlimited number of oc
    interactions, and the limit value will be stored in the Result object.
    :return: The tracker contextmanager. If action_handler is not
    specified, call get_result to receive a Result object with all
    tracked Action objects.
    """
    c = Context()
    if action_handler:
        if not callable(action_handler):
            raise ValueError('Expected action_handler to be callable')
        c.tracking_strategy = action_handler
    else:
        c.tracking_strategy = Result('tracking', limit)

    return c


def no_tracking():
    """
    Prevent outer tracker contexts from registering
    oc actions in their tracker objects. This is useful
    when a large amount of data is going to be transferred
    via stdout/stderr OR when certain actions make carry
    confidential data that should not appear in trackers.
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    c.no_tracking = True
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


def tls_verify(enable=True):
    """
    Establishes a context in which inner oc interactions
    will pass honor/ignore tls verification.
    :param enable: If false, --insecure-skip-tls-verify will be passed to oc invocations
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    c.skip_tls_verify = not enable
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
    c.set_timeout(seconds)
    return c


class ThreadLocalContext(local):
    def __init__(self):
        self.default_oc_path = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_OC_PATH", "oc")  # Assume oc is in $PATH by default
        self.default_kubeconfig_path = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_CONFIG_PATH", None)
        self.default_api_server = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_API_SERVER", None)
        self.default_token = None  # Does not support environment variable injection to discourage this insecure practice
        self.default_ca_cert_path = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_CA_CERT_PATH", None)
        self.default_project = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_PROJECT", None)
        self.default_options = {}
        self.default_loglevel = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_OC_LOGLEVEL", None)
        self.default_skip_tls_verify = os.getenv("OPENSHIFT_CLIENT_PYTHON_DEFAULT_SKIP_TLS_VERIFY", None)

        root_context = Context()
        root_context.set_timeout(MASTER_TIMEOUT)

        # Ensure stack always has at least one member to simplify getting last
        # with [-1]
        self.stack = [root_context]


# All threads will have a context which is
# managed by a stack of Context objects. As
# a thread establish additional context using
# 'with' statements, the stack will push/grow. As
# 'with' blocks end, the stack will pop/shrink.
context = ThreadLocalContext()

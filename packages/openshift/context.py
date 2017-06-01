from .selector import *
from .action import oc_action
from .util import *
from datetime import datetime
from datetime import timedelta
from .result import Result
from .result import OpenShiftException
from .model import Model
from threading import local
import json
import yaml

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
context.default_token = None
context.default_loglevel = None
context.default_redact_references = True
context.default_redact_tokens = True


def cur_context():
    return context.stack[-1]


class Context(object):

    def __init__(self):
        self.parent = None
        self.kubeconfig_path = None
        self.api_url = None
        self.project_name = None
        self.token = None
        self.loglevel_value = None
        self.change_tracker = None
        self.context_result = None
        self.timeout_datetime = None
        self.redact_references = None
        self.redact_tokens = None

    def __enter__(self):
        if len(context.stack) > 0:
            self.parent = context.stack[-1]
        context.stack.append(self)
        return self

    def __exit__(self, type, value, traceback):
        context.stack.pop()

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

    def get_project(self):
        if self.project_name is not None:
            return self.project_name
        # if cluster is changing, don't check parent for project
        # with project must always be inside with cluster.
        if self.api_url is None and self.parent is not None:
            return self.parent.get_project()
        return context.default_project

    def get_token(self):
        if self.token is not None:
            return self.token
        if self.parent is not None:
            return self.parent.get_token()
        return context.default_token

    def get_loglevel(self):
        if self.loglevel_value is not None:
            return self.loglevel_value
        if self.parent is not None:
            return self.parent.get_loglevel()
        return context.default_loglevel

    def get_redact_references(self):
        if self.redact_references is not None:
            return self.redact_references
        if self.parent is not None:
            return self.parent.get_redact_references()
        return context.default_redact_references

    def get_redact_tokens(self):
        if self.redact_tokens is not None:
            return self.redact_tokens
        if self.parent is not None:
            return self.parent.get_redact_tokens()
        return context.default_redact_tokens

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

    # Returns a list of changes registered with this context.
    # If no changes were registered, an empty list is returned
    def get_changes(self):
        return self.change_tracker

    # Adds one or more change strings to any tracker
    # contexts enclosing the current context.
    def register_changes(self, *args):
        if len(args) == 0:
            return
        c = self
        while c is not None:
            if c.change_tracker is not None:
                c.change_tracker.extend(args)
            c = c.parent

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
    c.project_name = name
    return c


def tracker():
    """
    Establishes a context in which all inner actions will
    be tracked. Trackers can be nested -- all actions
    performed within a tracker's context will be tracked.
    :return: The tracker context. If the returned object
        ever has a non-zero length for its change_tracker
        attribute, changes have been made on the server.
    """
    c = Context()
    c.change_tracker = []
    c.context_result = Result("tracker")
    return c


def token(v):
    """
    Establishes a context in which inner oc interactions
    will use the specified authentication token. token contexts
    can be nested. The most immediate ancestor token context
    will define the credentials used by an action.
    :param v: The token value.
    :return: The context object. Can be safely ignored.
    """
    c = Context()
    c.token = v
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


def mode(redact=None, redact_references=None, redact_tokens=None):
    """
    Establishes a context in which inner oc interactions
    can be runtime configured. mode contexts
    can be nested. Immediate ancestor mode contexts are given
    precedence if they define a particular configuration. If a mode does
    not define a preference, additional ancestors are interrogated.
    :param redact: Whether file content reference and tokens should be redacted.
                    This is shorthand for enabling/disabling all redaction.
    :param redact_references: Specifically enables (True) or disables redaction of
                    reference file content if it appears to contain secret data.
                    This option is on by default.
    :param redact_tokens: Specifically enables (True) or disables redaction of
                    token data from the command line action record.
                    This option is on by default.
    :return: The context object. Can be safely ignored.
    """
    c = Context()

    # Shorthand for turning off all redaction
    if redact is not None:
        c.redact_tokens = redact
        c.redact_references = redact

    if redact_references is not None:
        c.redact_references = redact_references

    if redact_tokens is not None:
        c.redact_tokens = redact_tokens

    return c


# Boilerplate for a verb which creates one or more objects.
def __new_objects_action(verb, *args):
    sel = Selector(context.stack[-1], verb)
    a = list(args)
    a.append("-o=name")
    sel.add_action(oc_action(context.stack[-1], verb, *a))
    sel.fail_if("%s returned an error" % verb)
    cur_context().context.register_changes(sel.names())
    return sel


def new_app(*args):
    return __new_objects_action("new-app", *args)


def new_build(*args):
    return __new_objects_action("new-build", *args)


def start_build(*args):
    return __new_objects_action("start-build", *args)


# Accepts any of the following:
# - YAML or JSON text string describing a single OpenShift object
# - YAML or JSON text string describing multiple OpenShift objects within a kind=List
# - A python dict modeling a single OpenShift object
# - A python dict modeling multiple OpenShift objects as a kind=List
# - A python list which is a flat list of python dicts - each entry modeling a single OpenShift object or a kind=List
# The method will return a flat list of python dicts - each modeling a single OpenShift object
def _objdef_to_pylist(objdef):

    if isinstance(objdef, dict):
        if objdef["kind"] == "List":
            return objdef["items"]
        else:
            return [objdef]

    if isinstance(objdef, list):
        objs = []
        for o in objdef:
            objs.extend(_objdef_to_pylist(o))
        return objs

    if not isinstance(objdef, str):
        raise OpenShiftException("Unknown object definition type: " + str(objdef))

    objdef = objdef.strip()

    if objdef.startswith("{"):
        return _objdef_to_pylist(json.loads(objdef))
    elif "\n" in objdef:  # Assume yaml
        return _objdef_to_pylist(yaml.load(objdef))
    else:  # Assume URL
        # Run through creation dry-run to get JSON content
        a = oc_action(cur_context(), "create", "--filename="+objdef, "--dry-run", "-o=json", ignore=True)
        if a.status != 0:
            raise OpenShiftException("Error reading file: " + a.err)
        return _objdef_to_pylist(a.out)

def _object_def_with_fallback(objdef, verb, fallback_error_substr=None, fallback_verb=None, check_for_change=False, *args):

    # Turn the argument into a list of python objects which model the resources
    obj_list = _objdef_to_pylist(objdef)

    phrase = verb
    if fallback_verb is not None:
        phrase += "_or_" + fallback_verb

    s = Selector(cur_context(), phrase)
    s.object_list = []

    for o in obj_list:
        model = Model(o)
        obj_name = model.kind.lower() + "/" + model.metadata.name
        s.object_list.append(obj_name)

        # Convert python object into a json string
        content = json.dumps(o, indent=4).strip()
        with TempFileContent(content, ".markup") as path:

            if check_for_change:
                pre_versions = get_resource_versions(cur_context(), obj_name)

            a = list(args)
            a.extend(["-o=name", "-f", path])
            action = oc_action(cur_context(), verb, *a, reference={path: objdef})
            if fallback_verb is not None:
                if action.status != 0 and (fallback_error_substr is None or fallback_error_substr in action.err):
                    if fallback_verb == "ignore":
                        # if we are ignoring the error, emulate that no error occurred in any tracker() objects
                        action.verb = "ignore"
                        action.status = 0
                        continue
                    else:
                        action = oc_action(cur_context(), fallback_verb, *a, reference={path: objdef})
            s.add_action(action)

            if check_for_change:
                post_versions = get_resource_versions(cur_context(), model.kind.lower() + "/" + model.metadata.name)

                # If change check failed then assume changes were made. Otherwise, compare pre and post changes.
                if post_versions is None or post_versions != pre_versions:
                    cur_context().register_changes(obj_name)

            else:
                # If we aren't checking for a change, assume changes (e.g. create/replace)
                cur_context().register_changes(obj_name)

    s.fail_if(phrase + " returned an error")
    return s


class OC(object):

    @staticmethod
    def create_if_absent(obj, *args):
        return _object_def_with_fallback(obj,
                                         "create",
                                         fallback_error_substr="(AlreadyExists)",
                                         fallback_verb="ignore",
                                         *args)

    @staticmethod
    def create(obj, *args):
        return _object_def_with_fallback(obj, "create", *args)

    @staticmethod
    def replace(obj, *args):
        return _object_def_with_fallback(obj, "replace", *args)

    @staticmethod
    def apply(obj, *args):
        return _object_def_with_fallback(obj, "apply",
                                         check_for_change=True,
                                         *args)

    @staticmethod
    def create_or_replace(obj, *args):
        return _object_def_with_fallback(obj,
                                         "create",
                                         fallback_error_substr="(AlreadyExists)",
                                         fallback_verb="replace",
                                         *args)

    @staticmethod
    def create_or_apply(obj, *args):
        return _object_def_with_fallback(obj,
                                         "create",
                                         fallback_error_substr="(AlreadyExists)",
                                         fallback_verb="apply",
                                         check_for_change=True,
                                         *args)

    @staticmethod
    def selector(*args, **kwargs ):
        return Selector(cur_context(), "selector", *args, **kwargs)

    @staticmethod
    def delete(*args):
        r = Result("delete")
        r.add_action(oc_action(cur_context(), "delete", "-o=name", *args))
        r.fail_if("Error deleting objects")
        cur_context().register_changes(split_names(r.out()))
        return r

    @staticmethod
    def delete_if_present(*args):
        return oc.delete("--ignore-not-found", *args)

    @staticmethod
    def project(*args):
        r = Result("project")
        r.add_action(oc_action(cur_context(), "project", "-q", *args))
        r.fail_if("Unable to determine current project")
        return r.out()

    @staticmethod
    def process(objdef, parameters={}, **args):
        objects = _objdef_to_pylist(objdef)
        if len(objects) != 1:
            raise OpenShiftException("Expected a single template object")

        template = objects[0]
        args = list(args)
        args.append("-o=json")

        for k, v in parameters.items():
            args.append("-p")
            args.append(k+"="+v)

        # Convert python object into a json string
        content = json.dumps(template, indent=4).strip()
        with TempFileContent(content, ".markup") as path:
            args.append("--filename="+path)
            r = Result("process")
            r.add_action(oc_action(cur_context(), "process", *args, reference={path: content}, no_namespace=True))
            r.fail_if("Error processing template")
            return _objdef_to_pylist(r.out())

oc = OC()

# Ensure stack always has at least one member to simplify getting last
# with [-1]
context.stack = [Context()]

from .selector import Selector, selector
from .action import oc_action
from .context import cur_context, context, project
from .result import Result
from .apiobject import APIObject
from .model import Model
import json


def __new_objects_action(verb, cmd_args=[], stdin=None):

    """
    Performs and oc action and records objects output from the verb
    as changed in the content.
    :param verb: The verb to execute
    :param cmd_args: A list of str|list<str> which will be flattened into command line arguments
    :return: A selector for the newly created objects
    """

    sel = Selector(verb, verb)
    sel.add_action(oc_action(cur_context(), verb, cmd_args=['-o=name', cmd_args], stdin=stdin))
    sel.fail_if("%s returned an error" % verb)
    cur_context().register_changes(sel.qnames())
    return sel


def new_app(*args):
    return __new_objects_action("new-app", cmd_args=args)


def new_build(*args):
    return __new_objects_action("new-build", cmd_args=args)


def start_build(*args):
    return __new_objects_action("start-build", cmd_args=args)


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
    cur_context().register_changes('project/{}'.format(name))
    return project(name)


def delete_project(name, *args):
    r = Result("delete-project")
    r.add_action(oc_action(cur_context(), "delete", cmd_args=["project", name, args]))
    r.fail_if("Unable to create delete project: {}".format(name))
    cur_context().register_changes('project/{}'.format(name))


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


def create(dict_or_model_or_apiobject_or_list_thereof, *args):

    m = {
        'kind': 'List',
        'apiVersion': 'v1',
        'metadata': {},
        'items': _to_dict_list(dict_or_model_or_apiobject_or_list_thereof)
    }

    markup = json.dumps(m, indent=4)

    __new_objects_action("create", "-f", "-")

    r = Result("create")
    r.add_action(oc_action(cur_context(), "create", cmd_args=['-f', '-', args], stdin=markup))
    r.fail_if("Unable to create object(s)")
    cur_context().register_changes('project/{}'.format(name))

from .selector import Selector
from .action import oc_action
from .context import cur_context, context
from .result import Result

# Boilerplate for a verb which creates one or more objects.
def __new_objects_action(verb, *args):
    sel = Selector(context.stack[-1], verb)
    a = list(args)
    a.append("-o=name")
    sel.add_action(oc_action(context.stack[-1], verb, cmd_args=a))
    sel.fail_if("%s returned an error" % verb)
    cur_context().context.register_changes(sel.qnames())
    return sel


def new_app(*args):
    return __new_objects_action("new-app", *args)


def new_build(*args):
    return __new_objects_action("new-build", *args)


def start_build(*args):
    return __new_objects_action("start-build", *args)


def get_project(*args):
    r = Result("project")
    r.add_action(oc_action(cur_context(), "project", cmd_args=["-q", args]))
    r.fail_if("Unable to determine current project")
    return r.out()


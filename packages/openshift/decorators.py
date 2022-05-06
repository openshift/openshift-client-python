from __future__ import absolute_import

import functools
import random
import string

from . import new_project, delete_project


def _id_generator(size=6, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def _generate_project_name():
    return "ephemeral-project-{}".format(_id_generator())


def ephemeral_project(_func=None, *, project_name=_generate_project_name()):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with new_project(project_name):
                value = func(*args, project_name=project_name, **kwargs)
            delete_project(project_name)
            return value
        return wrapper

    if _func is None:
        return decorator
    else:
        return decorator(_func)

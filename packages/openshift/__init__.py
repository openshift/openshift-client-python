from __future__ import absolute_import

from .context import *
from .base_verbs import *
from .model import OpenShiftPythonException
from .model import Model, Missing
from .selector import *
from .apiobject import *
from . import naming
from . import status
from . import config
from .ansible import ansible

# Single source for module version
__VERSION__ = '1.0.18'

null = None  # Allow scripts to specify null in object definitions


# Allows modules to trigger errors
def error(msg, **kwargs):
    raise OpenShiftPythonException(msg, **kwargs)


# Convenience method for accessing the module version
def get_module_version():
    return __VERSION__

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
null = None  # Allow scripts to specify null in object definitions


# Allows modules to trigger errors
def error(msg, **kwargs):
    raise OpenShiftPythonException(msg, **kwargs)

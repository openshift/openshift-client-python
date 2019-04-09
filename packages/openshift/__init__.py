from .context import *
from .base_verbs import *
from .model import OpenShiftPythonException
from .model import Missing
from .model import Model, Missing
from .selector import *
from .apiobject import *
import naming
import status
null = None  # Allow scripts to specify null in object definitions


# Allows modules to trigger errors
def error(msg, **kwargs):
    raise OpenShiftPythonException(msg, **kwargs)

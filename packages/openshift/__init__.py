from .context import *
from .result import OpenShiftException
from .model import Missing
from .model import Model
null = None # Allow scripts to specify null in object definitions


# Allows modules to trigger errors
def error(msg, **kwargs):
    raise OpenShiftException(msg, **kwargs)

from .action import *
from .model import *
from .result import *
import yaml
import json

_DEFAULT = object()


# Turns an object definition string into a list of APIObjects.
# Accepts any of the following:
# - YAML or JSON text string describing a single OpenShift object
# - YAML or JSON text string describing multiple OpenShift objects within a kind=List
# - A python dict modeling a single OpenShift object
# - A python dict modeling multiple OpenShift objects as a kind=List
# - A python list which is a flat list of python dicts - each entry modeling a single OpenShift object or a kind=List
# The method will return a flat list of python dicts - each modeling a single OpenShift object
def _objdef_to_pylist(objdef):
    objdef = objdef.strip()

    if objdef.startswith("{"):
        d = json.loads(objdef)
    elif "\n" in objdef:  # Assume yaml
        d = yaml.load(objdef)
    else:  # Assume URL
        raise ValueError("Unable to detect object mark (not yaml or json)")

    return APIObject(d).elements()


# Converts objects into their python
# primitive form.
# APIObject, Model -> dict
# list<APIObject|Model> -> list<dict>
def _obj_to_primitive(obj):
    if isinstance(obj, APIObject):
        return _obj_to_primitive(obj.model._primitive())

    if isinstance(obj, Model):
        return _obj_to_primitive(obj._primitive())

    if isinstance(obj, list):
        l = []
        for e in obj:
            l.append(_obj_to_primitive(e))
        return l

    if isinstance(obj, dict):
        return obj

    raise ValueError("Unknown how to transform into dict: {}".format(type(obj)))





def _as_model(obj):
    """
    :param obj: The object to return as a Model
    :return: Return the object as a Model. If object is already a Model, just returns it.
    """
    if isinstance(obj, (Model, ListModel)):
        return obj

    if isinstance(obj, list):
        return ListModel(obj)

    # Otherwise, assume dict
    return Model(obj)


def _access_field(val, err_msg, if_missing=_DEFAULT, lowercase=False):
    if val is Missing:
        if if_missing is _DEFAULT:
            raise ModelError(err_msg)
        else:
            return if_missing
    elif lowercase:
        val = val.lower()

    return val


class APIObject:

    def __init__(self, dict_to_model=None, context=None):
        # Create a Model representation of the object.
        self.context = context if context else cur_context()
        self._model = Model(dict_to_model)

    def as_dict(self):
        """
        :return: Returns a python dict representation of the APIObject. Changes are not communicated
         back to this APIObject's model.
        """
        return self._model._primitive()

    def as_json(self, indent=4):
        """
        :return: Returns a JSON presentation of the APIObject.
        """
        return json.dumps(self._model._primitive(), indent=4).strip()

    def model(self):
        """
        :return: Returns a reference to the underlying Model object. Changes to the Model will persist in memory
         but not be reflected in the API server unless applied.
        """
        return self._model

    def kind(self, if_missing=_DEFAULT):
        """
        Return the API object's kind if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :return: The kind or if_missing.
        """
        return _access_field(self._model.kind,
                             "Object model does not contain .kind", if_missing=if_missing, lowercase=True)

    def name(self, if_missing=_DEFAULT):
        """
        Return the API object's name if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :return: The kind or if_missing.
        """
        return _access_field(self._model.metadata.name,
                             "Object model does not contain .metadata.name", if_missing=if_missing,
                             lowercase=True)

    def qname(self):
        """
        :return: Returns the qualified name of the object (kind/name).
        """
        return self.kind() + '/' + self.name()

    def _object_def_action(self, verb, *args):
        """
        :param verb: The verb to execute
        :param args: Other arguments to pass to the verb
        :return: The Result
        :rtype: Result
        """

        qname = self.qname()

        # Convert Model into a json string
        content = self.as_json()

        a = list(args)
        a.extend(["-o=name", "-f", "-"])
        result = Result(verb)
        result.add_action(oc_action(self.context, verb, cmd_args=a, stdin_obj=content))

        result.fail_if("Error during object {}".format(verb))
        return result

    def exists(self, on_exists_func=_DEFAULT, on_absent_func=_DEFAULT):
        """
        Returns whether the specified object exists according to the API server.
        If a function is supplied, it will be executed if the object exists.
        :param on_exists_func: The function to execute if the object exists
        :param on_absent_func: The function to execute if the object does not exist
        :return: Boolean indicated whether the object exists, followed by return value of function, if present
        """
        does_exist = selector('{}/{}'.format(self.kind(), self.name()), context=self.context).count_existing() == 1

        ret = None
        if does_exist:
            if on_exists_func is not _DEFAULT:
                ret = on_exists_func(self)
        elif on_absent_func is not _DEFAULT:
            ret = on_absent_func(self)

        return does_exist, ret

    def create(self, *args):
        """
        Creates the modeled object if possible.
        :return: A Result object
        :rtype: Result
        """
        return self._object_def_action("create", *args)

    def replace(self, *args):
        """
        Replaces the modeled object if possible.
        :return: A Result object
        :rtype: Result
        """
        return self._object_def_action("replace", *args)

    def create_or_replace(self, *args):
        """
        Replaces the modeled object if it exists; creates otherwise.
        :return: A Result object
        :rtype: Result
        """
        _, action = self.exists(on_exists_func=lambda: self.replace(*args),
                                on_absent_func=lambda: self.create(*args))

        return action

    def apply(self, *args):
        """
        Applies the modeled object against the API server
        :return: An Result object
        :rtype: Result
        """
        return self._object_def_action("apply", check_for_change=True, *args)

    def delete(self, ignore_not_found=False, *args):
        r = Result("delete")
        base_args = ["-o=name"]

        if ignore_not_found is True:
            base_args.append("--ignore-not-found")

        r.add_action(oc_action(self.context, cmd_args=["delete", self.kind(), self.name(), base_args, args]))
        r.fail_if("Error deleting object")
        return r

    def elements(self):
        """
        :return: Returns a python list of APIObjects. If receiver is an OpenShift 'List', each element will be
        added to the returned list. If the receiver is not of kind List, the [self] will be returned.
        """
        if self.kind() != "list":
            return [self]

        l = []
        for e in self._model['items']:
            l.append(APIObject(e._primitive()))

        return l

    def process(self, parameters={}, **args):
        template = self._model._primitive()
        args = list(args)
        args.append("-o=json")

        for k, v in parameters.items():
            args.append("-p")
            args.append(k + "=" + v)

        # Convert python object into a json string
        content = json.dumps(template, indent=4).strip()
        r = Result("process")
        r.add_action(oc_action(self.context, cmd_args=["process", "-f", "-", args], stdin_obj=content))
        r.fail_if("Error processing template")
        return _objdef_to_pylist(r.out())

from .context import cur_context
from .selector import selector

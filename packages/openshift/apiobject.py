from .action import *
from .model import *
from .result import *
from .naming import kind_matches
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
        self.model = Model(dict_to_model)

    def as_dict(self):
        """
        :return: Returns a python dict representation of the APIObject. Changes are not communicated
         back to this APIObject's model.
        """
        return self.model._primitive()

    def as_json(self, indent=4):
        """
        :return: Returns a JSON presentation of the APIObject.
        """
        return json.dumps(self.model._primitive(), indent=indent).strip()

    def kind(self, if_missing=_DEFAULT):
        """
        Return the API object's kind if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :return: The kind or if_missing.
        """
        return _access_field(self.model.kind,
                             "Object model does not contain .kind", if_missing=if_missing, lowercase=True)

    def name(self, if_missing=_DEFAULT):
        """
        Return the API object's name if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :return: The kind or if_missing.
        """
        return _access_field(self.model.metadata.name,
                             "Object model does not contain .metadata.name", if_missing=if_missing,
                             lowercase=True)

    def qname(self):
        """
        :return: Returns the qualified name of the object (kind/name).
        """
        return self.kind() + '/' + self.name()

    def _object_def_action(self, verb, auto_raise=True, args=[]):
        """
        :param verb: The verb to execute
        :param auto_raise: If True, any failed action will cause an exception to be raised automatically.
        :param args: Other arguments to pass to the verb
        :return: The Result
        :rtype: Result
        """
        # Convert Model into a dict
        content = self.as_dict()

        a = list(args)
        a.extend(["-o=name", "-f", "-"])
        result = Result(verb)
        result.add_action(oc_action(self.context, verb, cmd_args=a, stdin_obj=content))

        if auto_raise:
            result.fail_if("Error during object {}".format(verb))

        return result

    def selector(self):
        """
        :return: Returns a selector that selects this exact receiver
        """
        return selector('{}/{}'.format(self.kind(), self.name()), static_context=self.context)

    def exists(self, on_exists_func=_DEFAULT, on_absent_func=_DEFAULT):
        """
        Returns whether the specified object exists according to the API server.
        If a function is supplied, it will be executed if the object exists.
        :param on_exists_func: The function to execute if the object exists
        :param on_absent_func: The function to execute if the object does not exist
        :return: Boolean indicated whether the object exists, followed by return value of function, if present
        """
        does_exist = self.selector().count_existing() == 1

        ret = None
        if does_exist:
            if on_exists_func is not _DEFAULT:
                ret = on_exists_func(self)
        elif on_absent_func is not _DEFAULT:
            ret = on_absent_func(self)

        return does_exist, ret

    def create(self, args=[]):
        """
        Creates the modeled object if possible.
        :return: A Result object
        :rtype: Result
        """
        return self._object_def_action("create", args=args)

    def replace(self, args=[]):
        """
        Replaces the modeled object if possible.
        :return: A Result object
        :rtype: Result
        """
        return self._object_def_action("replace", args=args)

    def create_or_replace(self, args=[]):
        """
        Replaces the modeled object if it exists; creates otherwise.
        :return: A Result object
        :rtype: Result
        """
        _, action = self.exists(on_exists_func=lambda: self.replace(args=args),
                                on_absent_func=lambda: self.create(args=args))

        return action

    def modify_and_apply(self, modifier_func, retries=0, cmd_args=[]):
        """
        Calls the modifier_func with self. The function should modify the model of the receiver
        and return True if it wants this method to try to apply the change via the API. For robust
        implementations, a non-zero number of retries is recommended.

        :param modifier_func: Called before each attempt with an self. The associated model will be refreshed before
            each call if necessary. Function should modify the model with desired changes and return True to
            have those changes applied.
        :param retries: The number of times to retry. Zero=one attempt.
        :return: A Result object
        :rtype: Result
        """
        r = Result("apply")

        for attempt in reversed(range(retries + 1)):

            do_apply = modifier_func(self)

            # Modifier does not want to modify this object -- stop retrying
            if not do_apply:
                break

            apply_action = oc_action(self.context, "apply", cmd_args=["-f", "-", cmd_args], stdin_obj=self.as_dict(),
                                     last_attempt=(attempt == 0))

            r.add_action(apply_action)

            if apply_action.status == 0:
                break

            if attempt != 0:
                # Get a fresh copy of the API object from the server
                self.refresh()

        return r

    def apply(self, cmd_args=[]):
        """
        Applies any changes which have been made to the underlying model to the API.
        You should use modify_and_apply for robust code if the targeted API object may have been updated
        between the time this APIObject was created and when you call apply.
        :return: A Result object
        :rtype: Result
        """

        return self.modify_and_apply(lambda: True, retries=0, cmd_args=cmd_args)

    def delete(self, ignore_not_found=False, cmd_args=[]):
        r = Result("delete")
        base_args = ["-o=name"]

        if ignore_not_found is True:
            base_args.append("--ignore-not-found")

        r.add_action(oc_action(self.context, "delete", cmd_args=[self.kind(), self.name(), base_args, cmd_args]))
        r.fail_if("Error deleting object")
        return r

    def refresh(self):
        """
        Refreshes this APIObject's cache of the object it represents from the server.
        :return: self
        """
        r = Result("refresh")
        base_args = ["-o=json"]

        for attempt in reversed(range(9)):
            r_action = oc_action(self.context, "get", cmd_args=[self.kind(), self.name(), base_args],
                                 last_attempt=(attempt == 0))

            r.add_action(r_action)
            if r_action.status == 0:
                self.model = Model(json.loads(r_action.out))
                break

            time.sleep(1)

        r.fail_if("Error refreshing object content")
        return self

    def label(self, labels, overwrite=True, cmd_args=[]):
        """"
        Applies the specified labels to the api object.
        :param labels: A dictionary of labels to apply to the object. If value is None, label will be removed.
        :param overwrite: Whether to pass the --overwrite argument.
        :return: Result
        """

        result = self.selector().label(labels, overwrite, cmd_ags=cmd_args)
        self.refresh()
        return result

    def annotate(self, annotations, overwrite=True, cmd_args=[]):
        """"
        Applies the specified labels to the api object.
        :param annotations: A dictionary of annotations to apply to the object. If value is None, annotation will be removed.
        :param overwrite: Whether to pass the --overwrite argument.
        :param cmd_args: Additional list of arguments to pass on the command line.
        :return: Result
        """
        result = self.selector().annotate(annotations=annotations, overwrite=overwrite, cmd_args=cmd_args)
        self.refresh()
        return result

    def patch(self, patch_dict, strategy="strategic", cmd_args=[]):

        r = Result("patch")
        cmd_args = list(cmd_args)
        cmd_args.append("--type=" + strategy)

        cmd_args.append('{}/{}'.format(self.kind(), self.name()))
        patch_def = json.dumps(patch_dict, indent=None)

        cmd_args.append("--patch=" + patch_def)
        r.add_action(oc_action(self.context, "patch", cmd_args=[cmd_args]))

        r.fail_if("Error running patch on objects")
        return r

    def elements(self):
        """
        :return: Returns a python list of APIObjects. If receiver is an OpenShift 'List', each element will be
        added to the returned list. If the receiver is not of kind List, the [self] will be returned.
        """
        if self.kind() != "list":
            return [self]

        l = []
        for e in self.model['items']:
            l.append(APIObject(e._primitive()))

        return l

    def process(self, parameters={}, cmd_args=[]):
        template = self.model._primitive()
        cmd_args = list(cmd_args)
        cmd_args.append("-o=json")

        for k, v in parameters.items():
            cmd_args.append("-p")
            cmd_args.append(k + "=" + v)

        # Convert python object into a json string
        content = json.dumps(template, indent=4).strip()
        r = Result("process")
        r.add_action(oc_action(self.context, "process", cmd_args=["-f", "-", cmd_args], stdin_obj=content))
        r.fail_if("Error processing template")
        return _objdef_to_pylist(r.out())

    def do_i_own(self, apiobj):

        # Does the object has any ownerReferences?
        if apiobj.model.metadata.ownerReferences is Missing:
            return False

        '''
        Example:
          ownerReferences:
          - apiVersion: v1
            blockOwnerDeletion: true
            controller: true
            kind: ReplicationController
            name: ruby-hello-world-1
            uid: 50347024-a615-11e8-8841-0a46c474dfe0
        '''

        for ref in apiobj.model.metadata.ownerReferences:
            if kind_matches(self.kind(), ref.kind) and self.name() == ref.name:
                return True

        return False

    def get_owned(self, find_kind):

        """
        Returns a list of apiobjects which are declare an object of this kind/name
        as their owner.
        :param find_kind: The kind to check for ownerReferenes
        :return: A (potentially empty) list of APIObjects owned by this object
        """

        owned = []

        def check_owned_by_me(apiobj):
            if self.do_i_own(apiobj):
                owned.append(apiobj)

        selector(find_kind).for_each(check_owned_by_me)

        return owned

    def related(self, find_kind):
        """
        Returns a dynamic selector which all of a the specified kind of object which is related to this
        object.
        For example, if this object is a template and find_kind=='buildconfig', it will select buildconfigs created by
        this template.
        If this object is a buildconfig and find_kind='builds', builds created by this buildconfig will be selected.

        :return: A dynamic selector which selects objects of kind find_kind which are related to this object.
        """
        labels = {}

        this_kind = self.kind()
        name = self.name()

        # TODO: add rc, rs, ds, project, ... ?

        if this_kind.startswith("template"):
            labels["template"] = name
        elif this_kind.startswith("deploymentconfig"):
            labels["deploymentconfig"] = name
        elif this_kind.startswith("deployment"):
            labels["deployment"] = name
        elif this_kind.startswith("buildconfig"):
            labels["openshift.io/build-config.name"] = name
        elif this_kind.startswith("job"):
            labels["job-name"] = name
        else:
            raise OpenShiftException("Unknown how to find resources to related to kind: " + this_kind)

        return selector(find_kind, labels=labels)


from .context import cur_context
from .selector import selector

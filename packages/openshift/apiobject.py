from __future__ import absolute_import

import yaml
import sys
import copy

from .action import *
from .model import *
from .result import *
from .naming import kind_matches
from .context import cur_context
from .selector import selector
from . import util

_DEFAULT = object()


def _obj_to_primitive(obj):
    """
    Converts objects into their python primitive form. e.g.
      - APIObject or Model -> dict
      - list<APIObject|Model> -> list<dict>
      If the object is already a primitive, it will be returned without error.
    :param obj: The object to transform into its primitive form
    :return: The primitive form of the object
    """

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
    # (or val == '') included since it has been observed that namespace can be
    # returned from certain API queries as an empty string.

    if val is Missing or val == '':
        if if_missing is _DEFAULT:
            raise ModelError(err_msg)
        else:
            return if_missing
    elif lowercase:
        val = val.lower()

    return val


class APIObject:

    def __init__(self, dict_to_model=None, string_to_model=None, context=None):

        if string_to_model is not None:
            string_to_model = string_to_model.strip()

            if string_to_model == "":
                # oc sometimes returns empty string to indicate an empty list
                dict_to_model = {
                    "apiVersion": "v1",
                    "kind": "List",
                    "metadata": {},
                    "items": []
                }
            elif string_to_model.startswith("{"):
                dict_to_model = json.loads(string_to_model)
            elif "\n" in string_to_model:  # Assume yaml
                dict_to_model = yaml.safe_load(string_to_model)
            else:  # Assume URL
                raise ValueError("Unable to detect markup format (not yaml or json)")

        # Create a Model representation of the object.
        self.model = Model(dict_to_model)

        # If an APIObject is instantiated by an all_namespace selector, it will not necessarily have
        # a context with its own namespace. Therefore, on instantiation, grab a copy of our context and
        # make sure to force a namespace.

        self.context = copy.copy(context if context else cur_context())
        self.context.project_name = self.namespace(self.context.project_name)

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

    def kind(self, lowercase=True, if_missing=_DEFAULT):
        """
        Return the API object's kind if it possesses one (if you want group information included, use qkind).
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :param lowercase: Whether kind should be returned in lowercase.
        :return: The kind or if_missing.
        """
        return _access_field(self.model.kind,
                             "Object model does not contain .kind", if_missing=if_missing, lowercase=lowercase)

    def qkind(self, lowercase=True, if_missing=_DEFAULT):
        """
        Return the API object's qualified kind (e.g. kind[.group]). If kind is not defined, returns if_missing.
        When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :param lowercase: Whether kind should be returned in lowercase.
        :return: The kind or if_missing.
        """
        return '{kind}{group}'.format(kind=self.kind(if_missing=if_missing, lowercase=lowercase),
                                      group=self.group(prefix_dot=True, if_missing='', lowercase=lowercase))

    def apiVersion(self, lowercase=True, if_missing=_DEFAULT):
        """
        Return the API object's apiVersion if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if apiVesion is not present in Model.
        :param lowercase: Whether kind should be returned in lowercase.
        :return: The kind or if_missing.
        """
        return _access_field(self.model.apiVersion,
                             "Object model does not contain .apiVersion", if_missing=if_missing, lowercase=lowercase)

    def group(self, prefix_dot=False, lowercase=True, if_missing=_DEFAULT):
        """
        Return the API object's group if it possesses an apiVersion field.
        If it does not contain apiVersion field, returns if_missing. When if_missing not specified, throws a ModelError.
        If apiVersion is a non-group version, an empty string is returned.
        :param prefix_dot: Returns '.[group]' for resources with groups, but '' for those without. Convenience
         for appending to grouped/ungrouped resource names.
        :param if_missing: Value to return if apiVesion is not present in Model.
        :param lowercase: Whether kind should be returned in lowercase.
        :return: The kind or if_missing.
        """
        apiVersion = self.apiVersion(lowercase=lowercase, if_missing=None)
        if apiVersion is None:
            if if_missing is _DEFAULT:
                raise ModelError("Unable to find apiVersion in object")
            else:
                return if_missing

        # Otherwise, we have an apiVersion field to parse
        if '/' not in apiVersion:
            return ''

        group = apiVersion.split('/')[0]
        if prefix_dot:
            return '.{}'.format(group)

        return group

    def is_kind(self, test_kind_or_kind_list):
        """
        apiobj.is_kind('pod')  or  apiobj.is_kind(['pod', 'ds'])
        :param test_kind_or_kind_list: A str or list of strings to match
        :return: Returns whether this apiobj represents the specified kind or list of kings.
        """
        return kind_matches(self.kind(), test_kind_or_kind_list)

    def uid(self, if_missing=_DEFAULT):
        """
        Return the API object's .metadata.uid if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if uid is not present in Model.
        :return: The name or if_missing.
        """
        return _access_field(self.model.metadata.uid,
                             "Object model does not contain .metadata.uid", if_missing=if_missing,
                             lowercase=False)

    def resource_version(self, if_missing=_DEFAULT):
        """
        Return the API object's .metadata.resourceVersion if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if resourceVersion is not present in Model.
        :return: The name or if_missing.
        """
        return _access_field(self.model.metadata.resourceVersion,
                             "Object model does not contain .metadata.resourceVersion", if_missing=if_missing,
                             lowercase=False)

    def api_version(self, if_missing=_DEFAULT):
        """
        Return the API object's apiVersion if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if apiVersion is not present in Model.
        :return: The name or if_missing.
        """
        return _access_field(self.model.apiVersion,
                             "Object model does not contain apiVersion", if_missing=if_missing,
                             lowercase=False)

    def name(self, if_missing=_DEFAULT):
        """
        Return the API object's .metadata.name if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if name is not present in Model.
        :return: The name or if_missing.
        """
        return _access_field(self.model.metadata.name,
                             "Object model does not contain .metadata.name", if_missing=if_missing,
                             lowercase=False)

    def namespace(self, if_missing=_DEFAULT):
        """
        Return the API object's namespace if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if namespace is not present in Model.
        :return: The namespace or if_missing.
        """
        return _access_field(self.model.metadata.namespace,
                             "Object model does not contain .metadata.namespace", if_missing=if_missing,
                             lowercase=True)

    def fqname(self):
        """
        This name is not useful programmaticaly against the openshift API. It is useful
        only to determine if two apiObjects appear to represent the same resource.
        :return: Returns the fully qualified name of the object (ns:apiVersion.kind/name).
        """
        return '{ns}:{kind}{group}/{name}'.format(ns=self.namespace(if_missing=''),
                                                  group=self.group(prefix_dot=True),
                                                  kind=self.kind(),
                                                  name=self.name()
                                                  )

    def qname(self):
        """
        :return: Returns the qualified name of the object (kind[.group]/name).
        """
        return self.qkind() + '/' + self.name()

    def _object_def_action(self, verb, auto_raise=True, cmd_args=None):
        """
        :param verb: The verb to execute
        :param auto_raise: If True, any failed action will cause an exception to be raised automatically.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: The Result
        :rtype: Result
        """
        # Convert Model into a dict
        content = self.as_dict()

        base_args = list()
        base_args.extend(["-o=name", "-f", "-"])
        result = Result(verb)
        result.add_action(oc_action(self.context, verb, cmd_args=[base_args, cmd_args],
                                    stdin_obj=content, namespace=self.namespace(if_missing=None)))

        if auto_raise:
            result.fail_if("Error during object {}".format(verb))

        return result

    def self_selector(self):
        """
        :return: Returns a selector that selects this exact receiver
        """
        return selector(self.qname(), static_context=self.context)

    def exists(self, on_exists_func=_DEFAULT, on_absent_func=_DEFAULT):
        """
        Returns whether the specified object exists according to the API server.
        If a function is supplied, it will be executed if the object exists.
        :param on_exists_func: The function to execute if the object exists
        :param on_absent_func: The function to execute if the object does not exist
        :return: Boolean indicated whether the object exists, followed by return value of function, if present
        """
        does_exist = self.self_selector().count_existing() == 1

        ret = None
        if does_exist:
            if on_exists_func is not _DEFAULT:
                ret = on_exists_func(self)
        elif on_absent_func is not _DEFAULT:
            ret = on_absent_func(self)

        return does_exist, ret

    def create(self, cmd_args=None):
        """
        Creates the modeled object if possible.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: A Result object
        :rtype: Result
        """
        return self._object_def_action("create", cmd_args=cmd_args)

    def replace(self, cmd_args=None):
        """
        Replaces the modeled object if possible.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: A Result object
        :rtype: Result
        """
        return self._object_def_action("replace", cmd_args=cmd_args)

    def create_or_replace(self, cmd_args=None):
        """
        Replaces the modeled object if it exists; creates otherwise.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: A Result object
        :rtype: Result
        """
        _, action = self.exists(on_exists_func=lambda: self.replace(cmd_args=cmd_args),
                                on_absent_func=lambda: self.create(cmd_args=cmd_args))

        return action

    def describe(self, auto_raise=True):
        """
        :param auto_raise: If True, returns empty string instead of throwing an exception
        if describe results in an error.
        :return: Returns a string with the oc describe output of an object.
        """
        r = Result('describe')
        r.add_action(oc_action(self.context, "describe", cmd_args=[self.qname()],
                               namespace=self.namespace(if_missing=None)))

        if auto_raise:
            r.fail_if('Error describing object')

        return (r.out() + '\n' + r.err()).strip()

    def logs(self, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1, cmd_args=None,
             try_longshots=True):
        """
        Attempts to collect logs from running pods associated with this resource. Supports
        daemonset, statefulset, deploymentconfig, deployment, replicationcontroller, replicationset,
        buildconfig, build, pod.

        If a resource is associated with many pods, all pods owned by that resource will be individually
        scraped for logs. For example, if a daemonset is specified, an invocation of `oc logs ...` will be
        made for each pod associated with that daemonset -- this is different from the output of
        `oc logs ds/name`.

        If try_longshots==True, logs can also be collected to for any object which directly
        owns pods or responds successfully with "oc logs kind/name".

        Since pods can be pending or otherwise unable to deliver logs, if an error is encountered during
        an 'oc logs' invocation, the stderr will be considered the 'logs' of the object. In other words, oc
        returning an error will not terminate this function.

        :param cmd_args: An optional list of additional arguments to pass on the command line

        :param try_longshots: If True, an attempt we will be made to collect logs from resources which the library does
        not natively understand to possess logs. If False and the object is not recognized, an empty dict will be
        returned.

        :return: Returns a dict of {<fully-qualified-name> -> <log output>}. The fully qualified name will be
        a human readable, unique identifier containing namespace, object, and container-name (when applicable).
        """
        log_aggregation = {}

        def add_entry(collection, entry_key, action):
            entry = action.out
            if action.status != 0:
                entry += u'\n>>>>Error during log collection rc={}<<<<\n{}\n'.format(action.status, action.err)
            entry = entry.strip().replace('\r\n', '\n')
            collection[entry_key] = entry

        base_args = list()

        if previous:
            base_args.append('-p')

        if since:
            base_args.append('--since={}'.format(since))

        if limit_bytes:
            base_args.append('--limit-bytes={}'.format(limit_bytes))

        if timestamps:
            base_args.append('--timestamps')

        base_args.append('--tail={}'.format(tail))

        pod_list = []

        if kind_matches(self.kind(), 'pod'):
            pod_list.append(self)

        elif kind_matches(self.kind(), ['ds', 'statefulset']):
            pod_list.extend(self.get_owned('pod'))

        elif kind_matches(self.kind(), 'deployment'):
            for rs in self.get_owned('rs'):
                pod_list.extend(rs.get_owned('pod'))

        elif kind_matches(self.kind(), 'dc'):
            for rc in self.get_owned('rc'):
                pod_list.extend(rc.get_owned('pod'))

        elif kind_matches(self.kind(), ['rs', 'rc']):
            pod_list.extend(self.get_owned('pod'))

        elif kind_matches(self.kind(), ['bc', 'build']):
            action = oc_action(self.context, "logs", cmd_args=[base_args, cmd_args, self.qname()],
                               namespace=self.namespace(if_missing=None))
            add_entry(log_aggregation, self.fqname(), action)

        else:
            if try_longshots:
                # If the kind directly owns pods, we can find the logs for it
                pod_list.extend(self.get_owned('pod'))
                if not pod_list:
                    # Just try to collect logs and see what happens
                    action = oc_action(self.context, "logs", cmd_args=[base_args, cmd_args, self.qname()],
                                       namespace=self.namespace(if_missing=None))
                    add_entry(log_aggregation, self.fqname(), action)
                else:
                    # We don't recognize kind and we aren't taking longshots.
                    return dict()

        for pod in pod_list:
            for container in pod.model.spec.containers:
                action = oc_action(self.context, "logs",
                                   cmd_args=[base_args, cmd_args, pod.qname(), '-c', container.name,
                                             '--namespace={}'.format(pod.namespace())],
                                   no_namespace=True  # Namespace is included in cmd_args, do not use context
                                   )
                # Include self.fqname() to let reader know how we actually found this pod (e.g. from a dc).
                key = '{}->{}({})'.format(self.fqname(), pod.qname(), container.name)
                add_entry(log_aggregation, key, action)

        return log_aggregation

    def print_logs(self, stream=sys.stderr, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1,
                   cmd_args=None, try_longshots=True):
        """
        Pretty prints logs from selected objects to an output stream (see logs() method).
        :param stream: Output stream to send pretty printed report (defaults to sys.stderr)..
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: n/a
        """
        util.print_logs(stream,
                        self.logs(timestamps=timestamps, previous=previous, since=since, limit_bytes=limit_bytes,
                                  tail=tail, try_longshots=try_longshots, cmd_args=cmd_args))

    def modify_and_apply(self, modifier_func, retries=2, cmd_args=None):
        """
        Calls the modifier_func with self. The function should modify the model of the apiobj argument
        and return True if it wants this method to try to apply the change via the API. For robust
        implementations, a non-zero number of retries is recommended.

        :param modifier_func: Called before each attempt with an self. The associated model will be refreshed before
            each call if necessary. If the function finds changes it wants to make to the model, it should
            make them directly and return True. If it does not want to make changes, it should return False.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :param retries: The number of times to retry. A value of 0 means only one attempt will be made.
        :return: A Result object containing a record of all attempts AND a boolean. The boolean indicates
        True if a change was applied to a resource (i.e. it will be False if modifier_func suggested no
        change was necessary by returning False).
        :rtype: Result, bool
        """
        r = Result("apply")

        applied_change = False
        for attempt in reversed(list(range(retries + 1))):

            do_apply = modifier_func(self)

            # Modifier does not want to modify this object -- stop retrying. Retuning None should continue attempts.
            if do_apply is False:
                break

            apply_action = oc_action(self.context, "apply", cmd_args=["-f", "-", cmd_args],
                                     namespace=self.namespace(if_missing=None), stdin_obj=self.as_dict(),
                                     last_attempt=(attempt == 0))

            r.add_action(apply_action)

            if apply_action.status == 0:
                applied_change = True
                break

            if attempt != 0:
                # Get a fresh copy of the API object from the server
                self.refresh()

        return r, applied_change

    def apply(self, cmd_args=None):
        """
        Applies any changes which have been made to the underlying model to the API.
        You should use modify_and_apply for robust code if the targeted API object may have been updated
        between the time this APIObject was created and when you call apply.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: A Result object
        :rtype: Result
        """
        r, _ = self.modify_and_apply(lambda _: True, retries=0, cmd_args=cmd_args)
        return r

    def delete(self, ignore_not_found=False, cmd_args=None):
        """
        :param ignore_not_found: If true, no error will be raised if the object cannot be found.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return:
        """

        r = Result("delete")
        base_args = ["-o=name"]

        if ignore_not_found is True:
            base_args.append("--ignore-not-found")

        r.add_action(oc_action(self.context, "delete",
                               cmd_args=[self.qname(), base_args, cmd_args],
                               namespace=self.namespace(if_missing=None)))
        r.fail_if("Error deleting object")
        return r

    def refresh(self):
        """
        Refreshes this APIObject's cache of the object it represents from the server.
        :return: self
        """
        r = Result("refresh")
        base_args = ["-o=json"]

        for attempt in reversed(list(range(9))):
            r_action = oc_action(self.context, "get",
                                 cmd_args=[self.qname(), base_args],
                                 namespace=self.namespace(if_missing=None),
                                 last_attempt=(attempt == 0))

            r.add_action(r_action)
            if r_action.status == 0:
                self.model = Model(json.loads(r_action.out))
                break

            time.sleep(1)

        r.fail_if("Error refreshing object content")
        return self

    def current(self, ignore_not_found=False):
        """
        Uses the receiver's fully qualified name to query the server for an up-to-date copy of the object.
        :return: A new copy of APIObject with up-to-date content. If not found, ignore_not_found will
        cause None to be returned; otherwise, an exception will be thrown.
        """
        r = Result("current")
        base_args = ["-o=json", "--ignore-not-found"]

        for attempt in reversed(list(range(9))):
            r_action = oc_action(self.context, "get",
                                 cmd_args=[self.qname(), base_args],
                                 namespace=self.namespace(if_missing=None),
                                 last_attempt=(attempt == 0))

            r.add_action(r_action)
            if r_action.status == 0:
                new_apiobj = APIObject(string_to_model=r_action.out)
                if new_apiobj.is_kind('list') and not new_apiobj.elements():
                    # Nothing to return
                    if ignore_not_found:
                        return None
                    raise OpenShiftPythonException('Unable to retrieve current copy of {}; resource missing'.format(self.fqname()), r)

                return new_apiobj
            time.sleep(1)

        raise OpenShiftPythonException('Unable to retrieve current copy of {}; api errors'.format(self.fqname()),
                                       r)

    def get_label(self, name, if_missing=None):
        """
        :param name: The name of the label
        :param if_missing: Value to return if the label is not present (defaults to None).
        :return: Returns the value of the specified label or the specified default if not present.
        """
        v = self.model.metadata.labels[name]
        if v is not Missing:
            return v

        return if_missing

    def label(self, labels, overwrite=True, cmd_args=None, refresh_model=True):
        """"
        Sends a request to the server to label this API object.
        :param labels: A dictionary of labels to apply to the object. If value is None, label will be removed.
        :param overwrite: Whether to pass the --overwrite argument.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :param refresh_model: Whether to refresh apiobject model after label is applied.
        :return: Result
        """

        result = self.self_selector().label(labels, overwrite, cmd_args=cmd_args)
        if refresh_model:
            self.refresh()
        return result

    def get_annotation(self, name, if_missing=None):
        """
        :param name: The name of the annotation
        :param if_missing: Value to return if the annotation is not present (defaults to None).
        :return: Returns the value of the specified annotation or the specified default if not present.
        """
        v = self.model.metadata.annotations[name]
        if v is not Missing:
            return v

        return if_missing

    def annotate(self, annotations, overwrite=True, cmd_args=None, refresh_model=True):
        """"
        Sends a request to the server to annotate this API object
        :param annotations: A dictionary of annotations to apply to the object. If value is None, annotation will be removed.
        :param overwrite: Whether to pass the --overwrite argument.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :param refresh_model: Whether to refresh apiobject model after label is applied.
        :return: Result
        """
        result = self.self_selector().annotate(annotations=annotations, overwrite=overwrite, cmd_args=cmd_args)

        if refresh_model:
            self.refresh()

        return result

    def patch(self, patch_dict, strategy="strategic", cmd_args=None):

        r = Result("patch")
        base_args = list()
        base_args.append("--type=" + strategy)

        base_args.append(self.qname())
        patch_def = json.dumps(patch_dict, indent=None)

        base_args.append("--patch=" + patch_def)
        r.add_action(oc_action(self.context, "patch", cmd_args=[base_args, cmd_args],
                               namespace=self.namespace(if_missing=None)))

        r.fail_if("Error running patch on objects")
        return r

    def elements(self, cls=None):
        """
        :param cls A custom subclass of APIObject to return in place of APIObjects
        :return: Returns a python list of APIObjects. If receiver is an OpenShift 'List', each element will be
        added to the returned list. If the receiver is not of kind List, the [self] will be returned.
        """
        self_kind = self.kind(lowercase=False)
        if self_kind.endswith('List'):  # e.g. "List", "PodList", "NodeList"
            item_kind = self_kind[
                        :-4]  # strip 'List' off the end. This may leave '' or the kind of elements in the list
        else:
            return [self]

        l = []
        for e in self.model['items']:
            d = e._primitive()

            # If not an empty string, set the kind in the underlying object. This is because of the odd
            # way `oc adm manage-node --list-pods <node> -o=yaml` returns yaml for each pod, but without
            # a 'kind' in the object markup. So, if we get a 'PodList', set the kind before making into apiobjects.
            if item_kind:
                d['kind'] = item_kind

            if cls is not None:
                obj = cls(d)
            else:
                obj = APIObject(d)

            l.append(obj)

        return l

    def process(self, parameters=None, cmd_args=None):

        """
        Assumes this APIObject is a template and runs oc process against it.
        :param parameters: An optional dict of parameters to supply the process command
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: A list of apiobjects resulting from processing this template.
        """

        if parameters is None:
            parameters = {}

        template = self.model._primitive()
        base_args = list()
        base_args.append("-o=json")

        for k, v in parameters.items():
            base_args.append("-p")
            base_args.append(k + "=" + v)

        # Convert python object into a json string
        r = Result("process")
        r.add_action(oc_action(self.context, "process", cmd_args=["-f", "-", base_args, cmd_args], stdin_obj=template))
        r.fail_if("Error processing template")
        return APIObject(string_to_model=r.out()).elements()

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

    def am_i_involved(self, apiobj):

        # Does the object has any ownerReferences?
        ref = apiobj.model.involvedObject

        if ref is Missing:
            return False

        '''
        Example:
        kind: Event
        ...
        involvedObject:
          apiVersion: apps.openshift.io/v1
          kind: DeploymentConfig
          name: crel-monitors-app-creation-test
          namespace: openshift-monitoring
          resourceVersion: "1196701489"
          uid: 675a1b29-d862-11e8-8383-02d8407159d1
        '''

        if kind_matches(self.kind(), ref.kind) and self.name() == ref.name and self.namespace() == ref.namespace:
            return True

        return False

    def get_owned(self, find_kind):

        """
        Returns a list of apiobjects which are declare an object of this kind/name
        as their owner.
        :param find_kind: The kind to check for ownerReferences
        :return: A (potentially empty) list of APIObjects owned by this object
        """

        owned = []

        def check_owned_by_me(apiobj):
            if self.do_i_own(apiobj):
                owned.append(apiobj)

        selector(find_kind, static_context=self.context).for_each(check_owned_by_me)

        return owned

    def get_events(self):
        """
        Returns a list of apiobjects events which indicate this object as
        their involvedObject. This can be an expensive if there are a large
        number of events to search.
        :return: A (potentially empty) list of event APIObjects
        """

        # If this is a project, just return all events in the namespace.
        if kind_matches(self.kind(), ['project', 'namespace']):
            return selector('events').objects()

        involved = []

        def check_if_involved(apiobj):
            if self.am_i_involved(apiobj):
                involved.append(apiobj)

        selector('events', static_context=self.context).for_each(check_if_involved)

        return involved

    def related(self, find_kind):
        """
        Returns a dynamic selector which all of a the specified kind of object which is related to this
        object.
        For example:
        - if this object is a node, and find_kind=='pod', it will find all pods associated with the node.
        - if this object is a template and find_kind=='buildconfig', it will select buildconfigs created by
        this template.
        - if this object is a buildconfig and find_kind='builds', builds created by this buildconfig will be selected.

        :return: A selector which selects objects of kind find_kind which are related to this object.
        """
        labels = {}

        this_kind = self.kind()
        name = self.name()

        # TODO: add rc, rs, ds, project, ... ?

        if kind_matches(this_kind, 'node') and kind_matches(find_kind, 'pod'):
            return selector('pod',
                            all_namespaces=True,
                            field_selectors={'spec.nodeName': self.name()})

        if this_kind.startswith("template"):
            labels["template"] = name
        elif this_kind.startswith("deploymentconfig"):
            labels["deploymentconfig"] = name
        elif this_kind.startswith("deployment"):
            labels["deployment"] = name
        elif this_kind.startswith("buildconfig"):
            labels["openshift.io/build-config.name"] = name
        elif this_kind.startswith("statefulset"):
            labels["statefulset.kubernetes.io/pod-name"] = name
        elif this_kind.startswith("job"):
            labels["job-name"] = name
        else:
            raise OpenShiftPythonException(
                "Unknown how to find {} resources to related to kind: {}".format(find_kind, this_kind))

        return selector(find_kind, labels=labels, static_context=self.context)

    def execute(self, cmd_to_exec=None, stdin=None, container_name=None, auto_raise=True):
        """
        Performs an oc exec operation on a pod object - passing all of the arguments.
        :param cmd_to_exec: An array containing all elements of the command to execute.
        :param stdin: Any input that should be streamed into the executed process.
        :param container_name: If the pod has more than one container, specifies the container in which to exec.
        :param auto_raise: Raise an exception if the command returns a non-zero status.
        :return: A result object
        """

        if cmd_to_exec is None:
            cmd_to_exec = []

        oc_args = []

        if stdin:
            oc_args.append('-i')

        if container_name:
            oc_args.append('--container={}'.format(container_name))

        r = Result("exec")
        r.add_action(
            oc_action(self.context, "exec", cmd_args=[oc_args, self.qname(), "--", cmd_to_exec],
                      stdin_str=stdin, namespace=self.namespace(if_missing=None)))
        if auto_raise:
            r.fail_if(
                "Error running {} exec on {} [rc={}]: {}".format(self.qname(), cmd_to_exec[0], r.status(), r.err()))
        return r

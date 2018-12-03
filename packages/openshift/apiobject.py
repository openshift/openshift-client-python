from .action import *
from .model import *
from .result import *
from .naming import kind_matches
import util
import yaml
import json
import sys
import copy

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

        if string_to_model:
            string_to_model = string_to_model.strip()

            if string_to_model.startswith("{"):
                dict_to_model = json.loads(string_to_model)
            elif "\n" in string_to_model:  # Assume yaml
                dict_to_model = yaml.load(string_to_model)
            else:  # Assume URL
                raise ValueError("Unable to detect markup format (not yaml or json)")

        # Create a Model representation of the object.
        self.model = Model(dict_to_model)

        # If an APIObject is instantiated by an all_namespace selector, it will not necessarily have
        # a context with its own namespace. Therefore, on instantiation, grab a copy of our context and
        # make sure to force a namespace.

        self.context = copy.copy(context if context else cur_context())
        self.context.project_name = self.namespace(None)

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
        return json.dumps(self.model._primitive(), indent=indent, encoding='utf-8').strip().decode('utf-8')

    def kind(self, lowercase=True, if_missing=_DEFAULT):
        """
        Return the API object's kind if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if kind is not present in Model.
        :param lowercase: Whether kind should be returned in lowercase.
        :return: The kind or if_missing.
        """
        return _access_field(self.model.kind,
                             "Object model does not contain .kind", if_missing=if_missing, lowercase=lowercase)

    def is_kind(self, test_kind_or_kind_list):
        return kind_matches(self.kind(), test_kind_or_kind_list)

    def name(self, if_missing=_DEFAULT):
        """
        Return the API object's name if it possesses one.
        If it does not, returns if_missing. When if_missing not specified, throws a ModelError.
        :param if_missing: Value to return if name is not present in Model.
        :return: The name or if_missing.
        """
        return _access_field(self.model.metadata.name,
                             "Object model does not contain .metadata.name", if_missing=if_missing,
                             lowercase=True)

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
        :return: Returns the fully qualified name of the object (ns:kind/name).
        """
        return '{}:{}/{}'.format(self.namespace(if_missing=''), self.kind(), self.name())

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

    def self_selector(self):
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
        does_exist = self.self_selector().count_existing() == 1

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

    def describe(self, auto_raise=True):
        """
        :param auto_raise: If True, returns empty string instead of throwing an exception
        if describe results in an error.
        :return: Returns a string with the oc describe output of an object.
        """
        r = Result('describe')
        r.add_action(oc_action(self.context, "describe", cmd_args=[self.qname()]))

        if auto_raise:
            r.fail_if('Error describing object')

        return (r.out() + '\n' + r.err()).strip()

    def logs(self, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1, cmd_args=[],
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

        base_args = list(cmd_args)

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
            action = oc_action(self.context, "logs", cmd_args=[base_args, self.qname()])
            add_entry(log_aggregation, self.fqname(), action)

        else:
            if try_longshots:
                # If the kind directly owns pods, we can find the logs for it
                pod_list.extend(self.get_owned('pod'))
                if not pod_list:
                    # Just try to collect logs and see what happens
                    action = oc_action(self.context, "logs", cmd_args=[base_args, self.qname()])
                    add_entry(log_aggregation, self.fqname(), action)
                else:
                    # We don't recognize kind and we aren't taking longshots.
                    return dict()

        for pod in pod_list:
            for container in pod.model.spec.containers:
                action = oc_action(self.context, "logs", cmd_args=[base_args, pod.qname(), '-c', container.name,
                                                                   '--namespace={}'.format(pod.namespace())],
                                   no_namespace=True  # Namespace is included in cmd_args, do not use context
                                   )
                # Include self.fqname() to let reader know how we actually found this pod (e.g. from a dc).
                key = '{}->{}({})'.format(self.fqname(), pod.qname(), container.name)
                add_entry(log_aggregation, key, action)

        return log_aggregation

    def print_logs(self, stream=sys.stderr, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1,
                   cmd_args=[], try_longshots=True):
        """
        Pretty prints logs from selected objects to an output stream (see logs() method).
        :param stream: Output stream to send pretty printed report (defaults to sys.stderr)..
        :return: n/a
        """
        util.print_logs(stream,
                        self.logs(timestamps=timestamps, previous=previous, since=since, limit_bytes=limit_bytes,
                                  tail=tail, try_longshots=try_longshots, cmd_args=cmd_args))

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
        Sends a request to the server to label this API object.
        :param labels: A dictionary of labels to apply to the object. If value is None, label will be removed.
        :param overwrite: Whether to pass the --overwrite argument.
        :return: Result
        """

        result = self.self_selector().label(labels, overwrite, cmd_ags=cmd_args)
        self.refresh()
        return result

    def annotate(self, annotations, overwrite=True, cmd_args=[]):
        """"
        Sends a request to the server to annotate this API object
        :param annotations: A dictionary of annotations to apply to the object. If value is None, annotation will be removed.
        :param overwrite: Whether to pass the --overwrite argument.
        :param cmd_args: Additional list of arguments to pass on the command line.
        :return: Result
        """
        result = self.self_selector().annotate(annotations=annotations, overwrite=overwrite, cmd_args=cmd_args)
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
        self_kind = self.kind(lowercase=False)
        if self_kind.endswith('List'):  # e.g. "List", "PodList", "NodeList"
            item_kind = self_kind[:-4]  # strip 'List' off the end. This may leave '' or the kind of elements in the list
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

            l.append(APIObject(d))

        return l

    def process(self, parameters={}, cmd_args=[]):

        """
        Assumes this APIObject is a template and runs oc process against it.
        :param parameters: An optional dict of parameters to supply the process command
        :param cmd_args: An optional list of additional arguments to supply
        :return: A list of apiobjects resulting from processing this template.
        """

        template = self.model._primitive()
        cmd_args = list(cmd_args)
        cmd_args.append("-o=json")

        for k, v in parameters.items():
            cmd_args.append("-p")
            cmd_args.append(k + "=" + v)

        # Convert python object into a json string
        r = Result("process")
        r.add_action(oc_action(self.context, "process", cmd_args=["-f", "-", cmd_args], stdin_obj=template))
        r.fail_if("Error processing template")
        return APIObject(r.out()).elements()

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
        :param find_kind: The kind to check for ownerReferenes
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
        elif this_kind.startswith("statefulset"):
            labels["statefulset.kubernetes.io/pod-name"] = name
        elif this_kind.startswith("job"):
            labels["job-name"] = name
        else:
            raise OpenShiftPythonException("Unknown how to find {} resources to related to kind: {}".format(find_kind, this_kind))

        return selector(find_kind, labels=labels, static_context=self.context)

    def execute(self, cmd_to_exec=[], stdin=None, container_name=None, auto_raise=True):
        """
        Performs an oc exec operation on a pod object - passing all of the arguments.
        :param cmd_to_exec: An array containing all elements of the command to execute.
        :param stdin: Any input that should be streamed into the executed process.
        :param container_name: If the pod has more than one container, specifies the container in which to exec.
        :param auto_raise: Raise an exception if the command returns a non-zero status.
        :return: A result object
        """
        oc_args = []

        if stdin:
            oc_args.append('-i')

        if container_name:
            oc_args.append('--container={}'.format(container_name))

        r = Result("exec")
        r.add_action(
            oc_action(self.context, "exec", cmd_args=[oc_args, self.name(), "--", cmd_to_exec], stdin_str=stdin))
        if auto_raise:
            r.fail_if("Error running {} exec on {} [rc={}]: {}".format(self.qname(), cmd_to_exec[0], r.status(), r.err()))
        return r


from .context import cur_context
from .selector import selector

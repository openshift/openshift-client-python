from __future__ import absolute_import

import json
import time
import sys

from .result import Result
from .naming import normalize_kinds, normalize_kind, qname_matches
from .model import *
from .util import split_names, is_collection_type
from .action import oc_action
from .context import cur_context
from . import util


def _normalize_object_list(ol):
    new_ol = []
    for qname in ol:
        kind, name = str(qname).split("/")
        kind = normalize_kind(kind)
        new_ol.append('{}/{}'.format(kind, name))
    return new_ol


class Selector(Result):

    def __init__(self, high_level_operation,
                 kind_or_kinds_or_qname_or_qnames=None,
                 labels=None,
                 field_selectors=None,
                 object_list=None,
                 object_action=None,
                 filter_func=None,
                 all_namespaces=False,
                 static_context=None):

        super(self.__class__, self).__init__(high_level_operation)

        self.context_override = static_context
        self.object_list = object_list
        self.labels = labels
        self.field_selectors = field_selectors
        self.filter_func = filter_func
        self.all_namespaces = all_namespaces

        if object_action:
            self.add_action(object_action)
            action_output = object_action.out
            self.object_list = action_output.strip().split()

        if self.object_list is not None:
            if labels or kind_or_kinds_or_qname_or_qnames:
                raise ValueError("Kind(s)/labels cannot be specified in conjunction with object_list")
            return

        if self.labels is not None:
            # You can't query using labels without specifying a kind. Use 'all'.
            if kind_or_kinds_or_qname_or_qnames is None:
                kind_or_kinds_or_qname_or_qnames = "all"
            self.kinds = normalize_kinds(kind_or_kinds_or_qname_or_qnames)

        elif kind_or_kinds_or_qname_or_qnames is None:
            # Someone wants an empty selector? Occasionally useful for things like a sequence of unions.
            self.object_list = []

        else:
            # Otherwise, allow args[0] of
            #  "kind"
            #  [ "kind", ... ]
            #  "kind/name"
            #  [ "kind/name", ... ]

            first = kind_or_kinds_or_qname_or_qnames

            # List of qualified names
            if is_collection_type(first):
                first = list(first)

                if len(first) == 0:
                    # Just create an empty selector
                    self.object_list = []
                    return

                if '/' in first[0]:  # collection of kind/name assumed
                    self.object_list = _normalize_object_list(first)
                else:  # Assume collection of kinds
                    self.kinds = normalize_kinds(first)

            else:
                if "/" not in first:  # Caller has specified ("kind")
                    self.kinds = normalize_kinds(first)
                else:  # Caller specified ( "kind/name" )
                    self.object_list = _normalize_object_list([first])

    def __iter__(self):
        return self.objects().__iter__()

    @property
    def context(self):
        return self.context_override if self.context_override else cur_context()

    def _selection_args(self, needs_all=False):

        """
        :param needs_all: Set to True to include --all
        :return: Returns a list of arguments for oc which, when executed, should select the underlying objects
        selected by this selector.
        """

        args = []

        # If this is a static selector, just return our list of names.
        if self.object_list is not None:
            return self.object_list

        args.append(','.join(self.kinds))

        if self.field_selectors:
            sel = '--field-selector='
            pairs = []
            for k, v in six.iteritems(self.field_selectors):
                negate = False
                if k.startswith('!'):
                    # Strip the '!'
                    k = k[1:]
                    negate = True

                if isinstance(v, bool):  # booleans in json/yaml need to be lowercase
                    v = '{}'.format(v).lower()

                # field-selector supports = and !=
                pairs.append('{}{}{}'.format(k, '!=' if negate else '=', v))

            sel += ','.join(pairs)
            args.append(sel)

        if self.labels is not None:
            sel = '--selector='
            pairs = []
            for k, v in six.iteritems(self.labels):

                negate = False
                if k.startswith('!'):
                    # Strip the '!'
                    k = k[1:]
                    negate = True

                if isinstance(v, bool):  # booleans in json/yaml need to be lowercase
                    v = '{}'.format(v).lower()

                if util.is_collection_type(v):  # if a list or tuple was supplied as the value, use in/notin
                    # e.g. 'region in (us-east-1, us-east-2)'
                    pairs.append('{} {} ({})'.format(k, 'notin' if negate else 'in', ','.join(v)))
                elif v is not None:
                    pairs.append('{}{}{}'.format(k, '!=' if negate else '=', v))
                else:
                    # In this case, just search for existence. Logic seems reversed, but isn't.
                    #  { '!labelname' : None }    should check for existence; read as 'not labelname == None'
                    #  { 'labelname' : None }    should check for absence; read as 'labelname == None'
                    pairs.append('{}{}'.format('' if negate else '!', k))

            sel += ','.join(pairs)
            args.append(sel)
        elif needs_all:
            # e.g. "oc delete pods" will fail unless --all is specified
            args.append("--all")

        return args

    def qnames(self):
        """
        :return: Returns the qualified object names (kind/name) selected by this selector. List may be empty.
        """

        if self.object_list is not None:
            return list(self.object_list)

        return self._query_names()

    def names(self):
        """
        :return: Returns the unqualified object names (i.e. no [kind]/ prefix) selected by this selector.
                List may be empty.
        """

        names = []
        for name in self.qnames():
            names.append(name.split('/')[-1])

        return names

    def qname(self):

        """
        :return: Returns the qualified object name (kind/name) selected by this selector. Method expects
        exactly one item to be selected, otherwise it will throw an exception.
        """

        qnames = self.qnames()

        if len(qnames) == 0:
            raise OpenShiftPythonException("Expected single name, but selector returned no resources")

        if len(qnames) > 1:
            raise OpenShiftPythonException("Expected single name, but selector returned multiple resources")

        return qnames[0]

    def raw_action(self, verb, *args, **kwargs):
        return oc_action(self.context, verb, all_namespaces=self.all_namespaces,
                         cmd_args=[self._selection_args(), args], **kwargs)

    def _query_names(self):

        """
        Invokes oc to query for current objects selected by this selector.
        :return: Returns a list of qualified names (list may be empty).
        """

        result = Result("query_names")
        result.add_action(oc_action(self.context, 'get', all_namespaces=self.all_namespaces,
                                    cmd_args=['-o=name', self._selection_args()]))

        # TODO: This check is necessary until --ignore-not-found is implemented and prevalent
        if result.status() != 0 and "(NotFound)" in result.err():
            return []

        # Otherwise, errors are fatal
        result.fail_if("Unable to retrieve object names")
        return split_names(result.out())

    def narrow(self, kind_or_func):
        """
        Creates a new selector by filtering out objects from the receiver selector.
        Filtering can be done by kind or by a user specified callable.
        Example:
            sel.create(...).narrow("pod") - Return selector of pods recently created
            selector("projects").narrow(lambda project: project.metadata.annotations["xyz"] is not Missing)
        :param kind_or_func: A string specifying the kind to include in the resulting
          selector OR a callable which should return True for objects to be included
          in the resulting selector. The callable will be called once for each
          object selected by the receiver. The argument to the callable will be an APIObject.
        :return: A new static selector which selects a subset of the receiver's selection.
        """

        ns = []
        if callable(kind_or_func):
            for obj in self.objects():
                if kind_or_func(obj):
                    ns.append(obj.qname())
        elif isinstance(kind_or_func, six.string_types):
            kind = normalize_kind(kind_or_func)
            ns = [n for n in self.qnames() if (n.startswith(kind + "/") or n.startswith(kind + "."))]
        else:
            raise ValueError("Don't know how to narrow with type: " + type(kind_or_func))

        s = Selector("narrow",
                     object_list=ns,
                     static_context=self.context,
                     all_namespaces=self.all_namespaces)
        return s

    def freeze(self):
        """
        :return: Returns a new static Selector with the set of objects currently selected by this receiver.
        This is useful if business logic needs the underlying objects being selected to not change between
        queries (i.e. qnames() will always return the same thing even if objects are deleted from the server).

        If you try to freeze an all_namespaces selector, an exception will be raised. All namespace queries
        cannot be static because oc does not support queries like: oc get --all-namespaces pod/xyz
        """

        if self.all_namespaces:
            raise ValueError('You cannot freeze all_namespaces selectors.')

        return Selector("freeze",
                        object_list=self.qnames(),
                        static_context=self.context,
                        all_namespaces=self.all_namespaces)

    def union(self, *args):
        """
        :param args: One or more selectors to union with.
        :return: Returns a static selector which will select the objects selected by the receiver and any of the
            selectors passed in as arguments.
        """

        # start with the base set of names
        new_set = self.qnames()
        for with_selector in args:
            to_union = with_selector.qnames()
            for qname in to_union:
                # Only add if not already in the union
                if not qname_matches(qname, new_set):
                    new_set.append(qname)

        return Selector("union",
                        object_list=new_set,
                        static_context=self.context,
                        all_namespaces=self.all_namespaces)

    def intersect(self, *args):
        """
        :param args: One or more selectors to intersect with.
        :return: Returns a static selector which will select the object names selected by the
            receiver AND ALL arguments.
        """

        new_set = list()
        for with_selector in args:
            to_intersect = with_selector.qnames()
            for qname in self.qnames():
                if qname_matches(qname, to_intersect):
                    new_set.append(qname)

        return Selector("intersect",
                        object_list=new_set,
                        static_context=self.context,
                        all_namespaces=self.all_namespaces)

    def subtract(self, with_selector):
        """
        :param with_selector: A selector to subtract
        :return: Returns a static selector which selects names of this receiver minus names selected by the argument
        """
        to_subtract = with_selector.qnames()
        new_set = list()
        for qname in self.qnames():
            if not qname_matches(qname, to_subtract):
                new_set.append(qname)

        return Selector("subtract",
                        object_list=new_set,
                        static_context=self.context,
                        all_namespaces=self.all_namespaces)

    def subset(self, start=None, end=None):
        """
        :return: Returns a static selector which selects a subset of the receivers selection. Shorthand for
        oc.selector(receiver.qnames[start:end]).
        """
        return Selector('subset',
                        object_list=self.qnames()[start:end],
                        static_context=self.context,
                        all_namespaces=self.all_namespaces)

    def count_existing(self):
        """
        :return: Returns the number of objects this receiver selects that actually exist on the
            server.
        """
        return len(self._query_names())

    def object_json(self, ignore_not_found=False):
        """
        Returns all objects selected by the receiver as a JSON string. If multiple objects are
        selected, an OpenShift List kind will be returned.
        :param ignore_not_found: If True, no error will result if receiver tries to select objects which are not present
        :return: Returns all selected objects marshalled as an OpenShift JSON representation.
        """

        # If the selector is static and empty return an empty list object
        if self.object_list is not None and len(self.object_list) == 0:
            return json.dumps({
                "apiVersion": "v1",
                "kind": "List",
                "metadata": {},
                "items": []
            })

        verb = "get"

        cmd_args = ["-o=json",
                    self._selection_args()]

        if ignore_not_found:
            cmd_args.append("--ignore-not-found")

        r = Result(verb)
        r.add_action(oc_action(self.context, verb, all_namespaces=self.all_namespaces, cmd_args=cmd_args))
        r.fail_if("Unable to read object")

        # --ignore-not-found returns an empty string instead of an error if nothing is found
        if not r.out().strip():
            return json.dumps({
                "apiVersion": "v1",
                "kind": "List",
                "metadata": {},
                "items": []
            })

        return r.out()

    def object(self, ignore_not_found=False, cls=None):
        """
        Returns a single APIObject that represents the selected resource. If multiple
        resources are being selected an exception will be thrown (use objects() when
        there is a possibility of selecting multiple objects).
        :param ignore_not_found: If True and no object exists, None will be returned instead of an exception.
        :param cls: Custom APIObject class to return
        :return: A Model of the selected resource.
        """
        objs = self.objects(cls=cls)
        if len(objs) == 0:
            if ignore_not_found:
                return None
            raise OpenShiftPythonException("Expected a single object, but selected 0")
        elif len(objs) > 1:
            raise OpenShiftPythonException("Expected a single object, but selected more than one")

        return objs[0]

    def objects(self, ignore_not_found=True, cls=None):
        """
        Returns a python list of APIObject objects that represent the selected resources. An
        empty is returned if nothing is selected.
        :param ignore_not_found: If true, missing named resources will not raise an exception.
        :param cls: Custom APIObject class to return
        :return: A list of Model objects representing the receiver's selected resources.
        """
        from .apiobject import APIObject

        obj = json.loads(self.object_json(ignore_not_found=ignore_not_found))

        if cls is not None:
            api_objects = cls(obj).elements(cls)
        else:
            api_objects = APIObject(obj).elements()

        return api_objects

    def start_build(self, cmd_args=None):
        r = Selector('start_build')

        # Have start-build output a list of objects it creates
        base_args = list()
        base_args.append("-o=name")

        for name in self.qnames():
            r.add_action(oc_action(self.context, "start-build", cmd_args=[name, base_args, cmd_args]))

        r.fail_if("Error running start-build on at least one item: " + str(self.qnames()))
        r.object_list = split_names(r.out())
        return r

    def report(self, timestamps=True, logs_since=None, try_longshots=False):
        """
        Builds a dict of information about objects selected by this receiver. This structure is not intended for
        programmatic use and keys/values may change over time. It is primarily be of use to grab a snapshot of
        data for post-mortem situations. As such, every effort is made to automatically tolerate errors and deliver
        as much information as is available.
        :return: {
                    <fqname>:{
                        object: {},
                        describe: "..."
                        logs: "...",
                    } ,
                    <fqname>:{
                    ...
                    }
                 }
        """
        d = {}
        for obj in self.objects():
            key = obj.fqname()
            obj_dict = dict()
            obj_dict['object'] = obj.as_dict()
            obj_dict['describe'] = obj.describe(auto_raise=False)

            # A report on something like a 'configmap' should not contain a logs
            # entry. So don't try longshots and don't include an entry if it doesn't support logs.
            logs_dict = obj.logs(timestamps=timestamps, since=logs_since, try_longshots=try_longshots)
            if logs_dict:
                obj_dict['logs'] = logs_dict
            d[key] = obj_dict

        return d

    def print_report(self, stream=sys.stderr, timestamps=True, logs_since=None, try_longshots=False):
        """
        Pretty prints a report to an output stream (see report() method).
        :param stream: Output stream to send pretty printed report (defaults to sys.stderr)..
        :return: n/a
        """
        util.print_report(stream, self.report(timestamps=timestamps, logs_since=logs_since, try_longshots=try_longshots))

    def logs(self, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1, cmd_args=None, try_longshots=False):
        """
        Builds a dict of logs for selected resources. Keys are fully qualified names for the source of the
        logs (format of this fqn is subject to change). Each value is the log extracted from the resource.

        If an object like a deployment or daemonset is included, all pods related to that object will be included in the
        log gathering operation.

        :param cmd_args: An optional list of additional arguments to pass on the command line
        :param try_longshots: Defaults to False. This allows broad selectors that select things without logs to
        not throw errors during this method.
        :return: {
                    <pod fqname for each container>: <log_string> ,
                    <build fqname>: <log_string>,
                    ...
                 }
        """
        d = {}
        for obj in self.objects():
            d.update(obj.logs(timestamps=timestamps, previous=previous, since=since, limit_bytes=limit_bytes, tail=tail, try_longshots=try_longshots, cmd_args=cmd_args))

        return d

    def print_logs(self, stream=sys.stderr, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1, try_longshots=False, cmd_args=None):
        """
        Pretty prints logs from selected objects to an output stream (see logs() method).
        :param stream: Output stream to send pretty printed logs (defaults to sys.stderr)..
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: n/a
        """
        util.print_logs(stream, self.logs(timestamps=timestamps, previous=previous, since=since, limit_bytes=limit_bytes, tail=tail, try_longshots=try_longshots, cmd_args=cmd_args))

    def describe(self, auto_raise=True, cmd_args=None):
        """
        Runs oc describe against the selected objects and returns the string which results.
        :param auto_raise: If True, an exception will be raised if an error occurs. If False,
        the returned string will contain stderr.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: A string containing the oc describe output.
        """
        r = Result("describe")
        r.add_action(oc_action(self.context, "describe", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(), cmd_args]))
        if auto_raise:
            r.fail_if('Error during describe')

        return (r.out() + "\n" + r.err()).strip()

    def delete(self, ignore_not_found=True, cmd_args=None):
        """
        :param ignore_not_found: If True, named resources which are not present will not raise an error.
        :param base_args: Additional delete arguments
        :param wait_for: Include an `oc wait --for=delete ...` for each resource deleted
        :param cmd_args: An optional list of additional arguments to pass on the command line
        :return: Returns a list of qualified object names which were deleted.
        """
        names = self.qnames()

        r = Result("delete")

        if len(names) == 0:
            return []

        base_args = list()
        if ignore_not_found:
            base_args.append("--ignore-not-found")
        base_args.append("-o=name")

        r.add_action(oc_action(self.context, "delete", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), base_args, cmd_args]))

        r.fail_if("Error deleting objects")
        return split_names(r.out())

    def label(self, labels, overwrite=True, cmd_args=None):

        """
        Applies a set of labels to selected objects.
        :param labels: A dictionary of labels to apply.
        :param overwrite: If true, any existing labels will be overwritten. If false, existing labels will cause
        a failure.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        """

        r = Result("label")
        base_args = list()

        if overwrite:
            base_args.append("--overwrite")

        for l, v in six.iteritems(labels):
            if v is None:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                base_args.append(l)
            else:
                base_args.append('{}={}'.format(l, v))

        r.add_action(oc_action(self.context, "label", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), base_args, cmd_args]))

        r.fail_if("Error running label")
        return self

    def annotate(self, annotations, overwrite=True, cmd_args=None):
        """
        Applies a set of annotations to selected objects.
        :param annotations: A dictionary of annotations to apply.
        :param overwrite: If true, any existing annotations will be overwritten. If false, existing annotations will cause
        a failure.
        :param cmd_args: An optional list of additional arguments to pass on the command line
        """

        r = Result("annotate")
        base_args = list()

        if overwrite:
            base_args.append("--overwrite")

        for l, v in six.iteritems(annotations):
            if not v:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                base_args.append(l)
            else:
                base_args.append('{}={}'.format(l, v))

        r.add_action(oc_action(self.context, "annotate", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), base_args, cmd_args]))

        r.fail_if("Error running annotate")
        return self

    def for_each(self, func, *args, **kwargs):
        """
        Calls the user specified callable once for each object selected by the receiver.
        The callable will be passed a Model for the object under scrutiny.
        :param func: A callable which can accept a Model as its first parameter. *args and **kwargs
            will also be passed along.
        :return: A list of objects returned by the callable.
        """

        r = []
        for obj in self.objects():
            r.append(func(obj, *args, **kwargs))
        return r

    def scale(self, replicas, cmd_args=None):
        r = Result("scale")
        base_args = list()
        base_args.append('--replicas={}'.format(replicas))
        r.add_action(oc_action(self.context, "scale", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=False), base_args, cmd_args]))

        r.fail_if("Error running scale")
        return self

    def until_any(self, min_to_satisfy=1,
                  success_func=None, tolerate_failures=0, failure_func=None,
                  auto_raise=False,
                  *args, **kwargs):
        """
        Polls the server until at least min_to_satisfy resources satisfies a user specified
        success condition or until more than tolerate_failures are detected.

        To accomplish this, until_any periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

        You can use this function to wait for the existence of any satisfying
        object(s) to be returned by the API by not specifying any success or failure
        criteria.

        This method will NOT continue polling if there is an exception. The caller must
        handle API errors.

        :param min_to_satisfy: Within the resources selected, the success_func must
            return True for this number of resources before the condition is satisfied.
        :param success_func: If this function returns True on any obj, iteration will stop
            and until_any will return (True, objs) where objs are the objects satisfying
            the condition. If no success_func is specified, the method behaves as if any
            object returns True.
        :param tolerate_failures: The number of items which can fail the failure_func before
            terminating polling. By default, this value is set to 0, so any failure will
            terminate the loop.
        :param failure_func: If this function returns True on any obj, iteration will stop
            and until_any will return (False, objs, obj) where objs is all selected
            objects and obj failed the test.
        :param auto_raise: If True, an exception will be thrown for failures instead of returning False.
        :return:  (True, satisfying_apiobjs, all_apiobjs) or (False, failing_apiobjs, all_apiobjs)
        """
        poll_period = 1
        while True:
            objs = self.objects()
            satisfied_by = []
            failed_by = []
            for obj in objs:
                if failure_func is not None and failure_func(obj, *args, **kwargs):
                    failed_by.append(obj)

                if len(failed_by) > tolerate_failures:
                    if auto_raise:
                        raise OpenShiftPythonException('Failure(s) during until_any')

                    return False, failed_by, objs

                if success_func is None or success_func(obj, *args, **kwargs):
                    satisfied_by.append(obj)

                if len(satisfied_by) >= min_to_satisfy:
                    return True, satisfied_by, objs

            time.sleep(poll_period)
            poll_period = min(poll_period + 1, 15)

    def until_all(self, min_exist=1, success_func=None, tolerate_failures=0, failure_func=None, auto_raise=False, *args, **kwargs):
        """
        Waits until the API returns at least min_exist resources and then
        polls the server until ALL selected resources satisfy a user specified
        success condition or ANY violate a user specified failure condition.

        To accomplish this, until_all periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

        If success_func is not specified, until_all will return satisfied when at least min_exist
        objects are selected.

        This method will NOT continue polling if there is an exception. The caller must
        handle API errors.

        :param min_exist: Minimum number of objects which must exist before success/failure checks will be performed
        :param success_func: If this function returns True on ALL objects selected, iteration will stop
            and until_all will return (True, objs, objs) where objs is a list of all selected APIObjects.
            If not specified, a function that always returns True will be used.
        :param tolerate_failures: The number of items which can fail the failure_func before
            terminating polling. By default, this value is set to 0, so any failure will
            terminate the loop.
        :param failure_func: If this function returns True on more than the tolerate_failures value,
            polling will stop and until_all will return (False, failed_objs, all_objs) where failed_objs is a
            list containing the objects which failed and all_objs the full listing of server objects
            selected.
        :param auto_raise: If True, an exception will be thrown for failures instead of returning False.
        :return: (bool, objs, bad) where bool is True if the success condition was satisfied
            and False if the failure condition triggered. objs is the list of selected objects
            which were checked, and bad will be an non-None APIObject if an object failed
            the check.
        """

        if not success_func:
            success_func = lambda x: True

        poll_period = 1
        while True:
            objs = self.objects()
            if len(objs) >= min_exist:

                satisfied_by = []
                failed_by = []

                for obj in objs:
                    if success_func(obj, *args, **kwargs):
                        satisfied_by.append(obj)

                    if failure_func is not None:
                        if failure_func(obj, *args, **kwargs):
                            failed_by.append(obj)
                            break

                if len(failed_by) > tolerate_failures:
                    if auto_raise:
                        raise OpenShiftPythonException('Failure(s) during until_all')
                    return False, failed_by, objs

                if len(satisfied_by) == len(objs):
                    return True, satisfied_by, objs

            time.sleep(poll_period)
            poll_period = min(poll_period + 1, 15)


def selector(kind_or_kinds_or_qname_or_qnames=None, labels=None,
             field_selectors=None, all_namespaces=False, static_context=None):
    """
    selector( "kind" )
    selector( "kind", labels={ 'k': 'v' } )
    selector( ["kind", "kind2", ...], labels={ 'k': 'v' } )
    selector( ["kind/name1", "kind/name2", ...] )
    selector( "kind/name" )
    :param kind_or_kinds_or_qname_or_qnames: A kind ('pod'), qualified name ('pod/some_name') or
        a list of qualified names ['pod/abc', 'pod/def'].
    :param labels: labels to require for the specified kind (AND logic is applied). Do not use in conjunction with
        qnames.
        - If label name starts with '!', not-equal logic will be applied (label!=value).
        - If dict value is a list/set, evaluates to 'in' or 'notin' selector expression.
        - {'labelname': None}  (read as labelname is None)  performs '-l !labelname' search
        - {'!labelname': None} (read as labelname is not None) performs '-l labelname'
    :param field_selectors: field-selectors map. If key name starts with '!', != logic will be applied.
    :param all_namespaces: Whether the selector should select from all namespaces.
    :param static_context: Usually, a selector will select from its current context. For example,
        openshift.selector('pods') will select pods from the openshift.project(..) in which it resides. Selectors
        can to be locked to a specific context by specifying it here.
    :return: A Selector object
    :rtype: Selector
    """
    return Selector("selector", kind_or_kinds_or_qname_or_qnames, labels=labels,
                    field_selectors=field_selectors,
                    all_namespaces=all_namespaces, static_context=static_context)

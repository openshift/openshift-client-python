from .result import Result
from .naming import expand_kinds
from .naming import normalize_kinds, normalize_kind
from .model import *
from .util import split_names, is_collection_type
import util
import json
import time
import sys

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
                 object_list=None,
                 object_action=None,
                 filter_func=None,
                 all_namespaces=False,
                 static_context=None):

        super(self.__class__, self).__init__(high_level_operation)

        self.context_override = static_context
        self.object_list = object_list
        self.labels = labels
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
            self.kinds = expand_kinds(kind_or_kinds_or_qname_or_qnames)

        else:

            # Otherwise, allow args[0] of
            #  "kind"
            #  [ "kind", ... ]
            #  "kind/name"
            #  [ "kind/name", ... ]

            if kind_or_kinds_or_qname_or_qnames is None:
                raise ValueError("Requires kind, qualified name, or list of kinds or qualified names")

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

        if self.labels is not None:
            sel = "--selector="
            pairs = []
            for k, v in self.labels.iteritems():
                if isinstance(v, bool):  # booleans in json/yaml need to be lowercase
                    v = '{}'.format(v).lower()
                pairs.append('{}={}'.format(k, v))
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
        elif isinstance(kind_or_func, basestring):
            kind = normalize_kind(kind_or_func)
            ns = [n for n in self.qnames() if (n.startswith(kind + "/") or n.startswith(kind + "."))]
        else:
            raise ValueError("Don't know how to narrow with type: " + type(kind_or_func))

        s = Selector("narrow", object_list=ns, static_context=self.context)
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

        return Selector("freeze", object_list=self.qnames())

    def union(self, with_selector):
        """
        :param with_selector: A selector with which to union
        :return: Returns a static selector which will select the object names associated with the receiver AND
            the argument.
        """
        s1 = set(self.qnames())
        s2 = set(with_selector.qnames())
        qnames = list(s1.union(s2))
        return Selector("union", object_list=qnames)

    def intersect(self, with_selector):
        """
        :param with_selector: A selector with which to intersect
        :return: Returns a static selector which will select the object names associated with the receiver intersected
            with the argument.
        """
        s1 = set(self.qnames())
        s2 = set(with_selector.qnames())
        qnames = list(s1.intersection(s2))
        return Selector("intersect", object_list=qnames)

    def subtract(self, with_selector):
        """
        :param with_selector: A selector to subtract
        :return: Returns a static selector which selects names of this receiver minus names selected by the argument
        """
        s1 = set(self.qnames())
        s2 = set(with_selector.qnames())
        qnames = list(s1.difference(s2))
        return Selector("subtract", object_list=qnames)

    def count_existing(self):
        """
        :return: Returns the number of objects this receiver selects that actually exist on the
            server.
        """
        return len(self._query_names())

    def object_json(self, exportable=False, ignore_not_found=False):
        """
        Returns all objects selected by the receiver as a JSON string. If multiple objects are
        selected, an OpenShift List kind will be returned.
        :param exportable: Set to True if the export verb should be used.
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

        verb = "export" if exportable else "get"

        cmd_args = ["-o=json",
                    self._selection_args()]

        if ignore_not_found:
            cmd_args.append("--ignore-not-found")

        r = Result(verb)
        r.add_action(oc_action(self.context, verb, all_namespaces=self.all_namespaces,
                               cmd_args=cmd_args))
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

    def object(self, exportable=False):
        """
        Returns a single APIObject that represents the selected resource. If multiple
        resources are being selected an exception will be thrown (use objects() when
        there is a possibility of selecting multiple objects).
        :param exportable: Whether export should be used instead of get.
        :return: A Model of the selected resource.
        """
        objs = self.objects(exportable)
        if len(objs) == 0:
            raise OpenShiftPythonException("Expected a single object, but selected 0")
        elif len(objs) > 1:
            raise OpenShiftPythonException("Expected a single object, but selected more than one")

        return objs[0]

    def objects(self, exportable=False):
        """
        Returns a python list of APIObject objects that represent the selected resources. An
        empty is returned if nothing is selected.
        :param exportable: Whether export should be used instead of get.
        :return: A list of Model objects representing the receiver's selected resources.
        """

        obj = json.loads(self.object_json(exportable, ignore_not_found=True))
        return APIObject(obj).elements()

    def start_build(self, cmd_args=[]):
        r = Selector()

        # Have start-build output a list of objects it creates
        cmd_args = list(cmd_args).append("-o=name")

        for name in self.qnames():
            r.add_action(oc_action(self.context, "start-build", cmd_args=[name, cmd_args]))

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

    def logs(self, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1, cmd_args=[], try_longshots=False):
        """
        Builds a dict of logs for selected resources. Keys are fully qualified names for the source of the
        logs (format of this fqn is subject to change). Each value is the log extracted from the resource.

        If an object like a deployment or daemonset is included, all pods related to that object will be included in the
        log gathering operation.

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

    def print_logs(self, stream=sys.stderr, timestamps=False, previous=False, since=None, limit_bytes=None, tail=-1, try_longshots=False, cmd_args=[]):
        """
        Pretty prints logs from selected objects to an output stream (see logs() method).
        :param stream: Output stream to send pretty printed logs (defaults to sys.stderr)..
        :return: n/a
        """
        util.print_logs(stream, self.logs(timestamps=timestamps, previous=previous, since=since, limit_bytes=limit_bytes, tail=tail, try_longshots=try_longshots, cmd_args=cmd_args))

    def describe(self, auto_raise=True, cmd_args=[]):
        r = Result("describe")
        r.add_action(oc_action(self.context, "describe", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(), cmd_args]))
        if auto_raise:
            r.fail_if('Error during describe')

        return r

    def delete(self, ignore_not_found=True, cmd_args=[]):
        names = self.qnames()

        r = Result("delete")

        if len(names) == 0:
            return r

        cmd_args = list(cmd_args)
        if ignore_not_found:
            cmd_args.append("--ignore-not-found")
        cmd_args.append("-o=name")

        r.add_action(oc_action(self.context, "delete", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), cmd_args]))

        r.fail_if("Error deleting objects")
        r.object_list = split_names(r.out())
        return r

    def label(self, labels, overwrite=True, cmd_ags=[]):

        r = Result("label")
        cmd_ags = list(cmd_ags)

        if overwrite:
            cmd_ags.append("--overwrite")

        for l, v in labels.iteritems():
            if not v:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                cmd_ags.append(l)
            else:
                cmd_ags.append('{}={}'.format(l, v))

        r.add_action(oc_action(self.context, "label", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), cmd_ags]))

        r.fail_if("Error running label")
        return self

    def annotate(self, annotations, overwrite=True, cmd_args=[]):

        r = Result("annotate")
        cmd_args = list(cmd_args)

        if overwrite:
            cmd_args.append("--overwrite")

        for l, v in annotations.iteritems():
            if not v:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                cmd_args.append(l)
            else:
                cmd_args.append('{}={}'.format(l, v))

        r.add_action(oc_action(self.context, "annotate", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), cmd_args]))

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

    def scale(self, replicas, cmd_args=[]):
        r = Result("scale")
        cmd_args = list(cmd_args)
        cmd_args.append('--scale={}'.format(replicas))
        r.add_action(oc_action(self.context, "scale", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=False), cmd_args]))

        r.fail_if("Error running scale")
        return self

    def until_any(self, success_func=None, failure_func=None, *args, **kwargs):
        """
        Polls the server until a selected resource satisfies a user specified
        success condition or violates a user specified failure condition.

        To accomplish this, until_any periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

        You can use this function to wait for the existence of any satisfying
        object to be returned by the API by not specifying any success or failure
        criteria.

        :param success_func: If this function returns True on any obj, iteration will stop
            and until_any will return (True, obj) where obj was the object. If no success_func
            is specified, the method behaves as if any object returns True.
        :param failure_func: If this function returns True on any obj, iteration will stop
            and until_any will return (False, obj) where obj was the object
        :return: (bool, obj) where bool is True if the success condition was satisfied
            and False if the failure condition was satisfied.
        """
        poll_period = 1
        while True:
            for obj in self.objects():
                if failure_func is not None and failure_func(obj, *args, **kwargs):
                    return False, obj
                if success_func is None or success_func(obj, *args, **kwargs):
                    return True, obj
            time.sleep(poll_period)
            poll_period = min(poll_period + 1, 15)

    def until_all(self, min_count, success_func=None, failure_func=None, *args, **kwargs):
        """
        Polls the server until ALL selected resources satisfy a user specified
        success condition or ANY violate a user specified failure condition.

        To accomplish this, until_all periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

        until_all with a min_count and not success_func will wait until at least min_count
        objects are selected.

        :param min_count: Minimum number of objects which must exist before check will be performed
        :param success_func: If this function returns True on ALL objects, iteration will stop
            and until_all will return (True, objs, None) where objs is a list of APIObjects
            selected/checked. If not specified, a function that always returns True will be used.
        :param failure_func: If this function returns True on ANY obj, iteration will stop
            and until_all will return (False, objs, bad) where objs is the list of APIObjects
            selected/checked and bad is the APIObject which failed.
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
            if len(objs) >= min_count:
                successer = True
                failer = False
                for obj in objs:
                    successer &= success_func(obj, *args, **kwargs)
                    if failure_func is not None:
                        failer |= failure_func(obj, *args, **kwargs)
                if successer:
                    return True, objs, None
                if failer:
                    return False, objs, obj
            time.sleep(poll_period)
            poll_period = min(poll_period + 1, 15)


def selector(kind_or_kinds_or_qname_or_qnames=None, labels=None, all_namespaces=False, static_context=None):
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
    :param all_namespaces: Whether the selector should select from all namespaces.
    :param static_context: Usually, a selector will select from its current context. For example,
        openshift.selector('pods') will select pods from the openshift.project(..) in which it resides. Selectors
        can to be locked to a specific context by specifying it here.
    :return: A Selector object
    :rtype: Selector
    """
    return Selector("selector", kind_or_kinds_or_qname_or_qnames, labels=labels,
                    all_namespaces=all_namespaces, static_context=static_context)


from .action import oc_action
from .apiobject import APIObject
from .context import cur_context

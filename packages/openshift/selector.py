from .result import Result
from .naming import expand_kind
from .naming import normalize_kind
from .model import *
from .util import split_names
import json
import time
import copy


def _normalize_object_list(ol):
    new_ol = []
    for qname in ol:
        kind, name = str(qname).split("/")
        kind = normalize_kind(kind)
        new_ol.append('{}/{}'.format(kind, name))
    return new_ol


class Selector(Result):

    def __init__(self, high_level_operation,
                 kind_or_qname_or_qnames=None, labels=None,
                 object_list=None,
                 object_action=None,
                 all_namespaces=False,
                 context=None,
                 **kwargs):

        super(self.__class__, self).__init__(high_level_operation)

        self.context_override = context
        self.object_list = object_list
        self.labels = labels
        self.all_namespaces = all_namespaces

        if object_action:
            self.add_action(object_action)
            action_output = object_action.out
            self.object_list = action_output.strip().split()

        if self.object_list is not None:
            if labels or kind_or_qname_or_qnames:
                raise ValueError("Kind/labels cannot be specified in conjunction with object_list")
            return

        if self.labels is not None:
            if kind_or_qname_or_qnames is None:
                raise ValueError("Expected kind as first parameter when labels are specified")
            self.kind = expand_kind(kind_or_qname_or_qnames)

        else:

            # Otherwise, allow args[0] of
            #  "kind"
            #  "kind/name"
            #  [ "kind/name", ... ]

            if kind_or_qname_or_qnames is None:
                raise ValueError("Requires kind, qualified name, or list of qualified names")

            first = kind_or_qname_or_qnames

            # List of qualified names
            if isinstance(first, list):
                self.object_list = _normalize_object_list(first)
            else:
                if "/" not in first:  # Caller has specified ("kind")
                    self.kind = normalize_kind(first)
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

        args.append(self.kind)

        if self.labels is not None:
            sel = "--selector="
            pairs = []
            for k, v in self.labels.iteritems():
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

    def qname(self):

        """
        :return: Returns the qualified object name (kind/name) selected by this selector. Method expects
        exactly one item to be selected, otherwise it will throw an exception.
        """

        qnames = self.qnames()

        if len(qnames) == 0:
            raise OpenShiftException("Expected single name, but selector returned no resources")

        if len(qnames) > 1:
            raise OpenShiftException("Expected single name, but selector returned multiple resources")

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
          object selected by the receiver. The argument to the callable will be a Model.
        :return: A new static selector which selects a subset of the receiver's selection.
        """

        ns = []
        if callable(kind_or_func):
            for obj in self.objects():
                if kind_or_func(obj):
                    ns.append("%s/%s" % (normalize_kind(obj.model.kind), obj.model.metadata.qname))
        elif isinstance(kind_or_func, str) or isinstance(kind_or_func, unicode):
            kind = normalize_kind(kind_or_func)
            ns = [n for n in self.qnames() if n.startswith(kind + "/")]
        else:
            raise ValueError("Don't know how to narrow with type: " + type(kind_or_func))

        s = Selector(self.context, "narrow", object_list=ns)
        return s

    def freeze(self):
        """
        :return: Returns a new static Selector with the set of objects currently selected by this receiver.
        This is useful if business logic needs the underlying objects being selected to not change between
        queries (i.e. qnames() will always return the same thing even if objects are deleted from the server).
        """
        return Selector("freeze", object_list=self.qnames())

    def related(self, to_kind=None):
        """
        Returns a dynamic selector which selects objects related to an object
        selected by the receiver. For example, if the receiver selects a single template,
        a selector will be returned which is capable of finding all objects created
        by that template.

        :param to_kind: If unspecified, receiver must select exactly one object. If specified, the receiver
        is allowed to select multiple objects, but only one of the specified kind. For example, if the receiver
        selects, two deployments and one buildconfig, you can specify to_kind=buildconfig to find builds related to
        the buildconfig. If, you specified to_kind=deployment (or did not specify to_kind), an exception would be thrown
        since the request is ambiguous.

        :return: A dynamic selector which selects objects related to the object selected
            by this receiver.
        """
        labels = {}

        if to_kind is None:
            name, to_kind = self.qname().split("/")[0]
        else:
            qnames = self.qnames()
            qname = None
            for qn in qnames:
                if qn.startswith(to_kind + '/'):
                    if qname is None:
                        qname = qn
                    else:
                        raise OpenShiftException(
                            "Unable to find related objects - kind ({}) is ambigous in selected objects: {}".format(
                                to_kind, qnames))

            name = qname.split("/")[1]

        # TODO: add deployment, rc, rs, ds, project, ... ?

        if to_kind == "templates":
            labels["template"] = name
        elif to_kind == "deploymentconfigs":
            labels["deploymentconfig"] = name
        elif to_kind == "buildconfigs":
            labels["openshift.io/build-config.name"] = name
        elif to_kind == "jobs":
            labels["job-name"] = name
        else:
            raise OpenShiftException("Unknown how to find resources to related to kind: " + to_kind)

        return Selector("related", labels=labels)

    def count_existing(self):
        """
        :return: Returns the number of objects this receiver selects that actually exist on the
            server.
        """
        return len(self._query_names())

    def object_json(self, exportable=False):
        """
        Returns all objects selected by the receiver as a JSON string. If multiple objects are
        selected, an OpenShift List kind will be returned.
        :param exportable: Set to True if the export verb should be used.
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
        r = Result(verb)
        r.add_action(oc_action(self.context, verb, all_namespaces=self.all_namespaces,
                               cmd_args=["-o=json", self._selection_args()]))
        r.fail_if("Unable to read object")

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
            raise OpenShiftException("Expected a single object, but selected 0")
        elif len(objs) > 1:
            raise OpenShiftException("Expected a single object, but selected more than one")

        return objs[0]

    def objects(self, exportable=False):
        """
        Returns a python list of APIObject objects that represent the selected resources. An
        empty is returned if nothing is selected.
        :param exportable: Whether export should be used instead of get.
        :return: A list of Model objects representing the receiver's selected resources.
        """

        obj = json.loads(self.object_json(exportable))
        return APIObject(obj).elements()

    def start_build(self, args=[]):
        r = Selector()

        # Have start-build output a list of objects it creates
        args = list(args).append("-o=name")

        for name in self.qnames():
            r.add_action(oc_action(self.context, "start-build", cmd_args=[name, args]))

        r.fail_if("Error running start-build on at least one item: " + str(self.qnames()))
        r.object_list = split_names(r.out())
        return r

    def describe(self, send_to_stdout=True, args=[]):
        r = Result("describe")
        r.add_action(oc_action(self.context, "describe", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(), args]))
        r.fail_if("Error describing objects")
        if send_to_stdout:
            print r.out()
        return r

    def delete(self, ignore_not_found=True, args=[]):
        names = self.qnames()

        if len(names) == 0:
            return

        r = Result("delete")
        args = list(args)
        if ignore_not_found:
            args.append("--ignore-not-found")
        args.append("-o=name")

        r.add_action(oc_action(self.context, "delete", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), args]))

        r.fail_if("Error deleting objects")
        r.object_list = split_names(r.out())
        return r

    def label(self, labels, overwrite=True, args=[]):

        r = Result("label")
        args = list(args)

        if overwrite:
            args.append("--overwrite")

        for l, v in labels.iteritems():
            if not v:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                args.append(l)
            else:
                args.append('{}={}'.format(l, v))

        r.add_action(oc_action(self.context, "label", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), args]))

        r.fail_if("Error running label")
        return self

    def annotate(self, annotations, overwrite=True, args=[]):

        r = Result("annotate")
        args = list(args)

        if overwrite:
            args.append("--overwrite")

        for l, v in annotations.iteritems():
            if not v:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                args.append(l)
            else:
                args.append('{}={}'.format(l, v))

        r.add_action(oc_action(self.context, "annotate", all_namespaces=self.all_namespaces,
                               cmd_args=[self._selection_args(needs_all=True), args]))

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

    def until_any(self, success_func, failure_func=None, *args, **kwargs):
        """
        Polls the server until a selected resource satisfies a user specified
        success condition or violates a user specified failure condition.

        To accomplish this, until_any periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

        :param success_func: If this function returns True on any obj, iteration will stop
            and until_any will return (True, obj) where obj was the object
        :param failure_func: If this function returns True on any obj, iteration will stop
            and until_any will return (False, obj) where obj was the object
        :return: (bool, obj) where bool is True if the success condition was satisfied
            and False if the failure condition was satisfied.
        """
        poll_period = 1
        while True:
            for obj in self.objects():
                if success_func(obj, *args, **kwargs):
                    return True, obj
                if failure_func is not None and failure_func(obj, *args, **kwargs):
                    return False, obj
            time.sleep(poll_period)
            poll_period = min(poll_period + 1, 15)

    def until_all(self, min_count, success_func, failure_func=None, *args, **kwargs):
        """
        Polls the server until ALL selected resources satisfy a user specified
        success condition or ANY violate a user specified failure condition.

        To accomplish this, until_all periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

        :param min_count: Minimum number of objects which must exist before check will be performed
        :param success_func: If this function returns True on ALL objects, iteration will stop
            and until_all will return (True, objs) where objs is a list of Model objects
            which satisfied the condition.
        :param failure_func: If this function returns True on ANY obj, iteration will stop
            and until_all will return (False, objs) where objs is the list of Model objects
            which triggered the failure.
        :return: (bool, objs) where bool is True if the success condition was satisfied
            and False if the failure condition triggered.
        """

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
                    return True, objs
                if failer:
                    return False, objs
            time.sleep(poll_period)
            poll_period = min(poll_period + 1, 15)


def selector(kind_or_qname_or_qnames=None, labels=None, all_namespaces=False, context=None, *args, **kwargs):
    """
    selector( "kind" )
    selector( "kind", labels=[ 'k': 'v' ] )
    selector( ["kind/name1", "kind/name2", ...] )
    selector( "kind/name" )
    :param labels: Required labels if only kind is specified (AND logic is applied)
    :return: A Selector object
    :rtype: Selector
    """
    return Selector("selector", kind_or_qname_or_qnames, labels=labels, all_namespaces=all_namespaces, context=context,
                    *args, **kwargs)


from .action import oc_action
from .apiobject import APIObject
from .context import cur_context

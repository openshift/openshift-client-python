from .result import Result
from .naming import expand_kind
from .naming import normalize_kind
from .action import oc_action
from .util import *
from .model import *
import json
import time


class ChangeTrackingFor(object):

    def __init__(self, context, *names):
        self.context = context
        self.names = names

    def __enter__(self, ):
        self.pre_versions = get_resource_versions(self.context, *self.names)

    def __exit__(self, type, value, traceback):
        post_versions = get_resource_versions(self.context, *self.names)

        # If change check failed then assume changes were made. Otherwise, compare pre and post changes.
        if post_versions is None or post_versions != self.pre_versions:
            self.context.register_changes(*self.names)


# Designed to split up output from -o=name into a
# simple list of object names
def split_names(output):
    if output is None:
        return []
    return [x.strip() for x in output.strip().split("\n") if x.strip() != ""]


# Converts python modeled OpenShift objects as
# json text. Lists are turned into kind=List.
# Strings are returned without modification.
def to_single_string(objdef):
    if isinstance(objdef, str):
        return objdef

    if isinstance(objdef, list):
        objdef = {
            "kind": "List",
            "apiVersion": "v1",
            "items": objdef
        }

    return json.dumps(objdef, indent=4).strip()


# Arguments should be a list of fully qualified names. e.g.: ( "pod/x", "user/y" )
# Returns a dict of resource-name -> resource-version
# If an error occurs, None is returned.
def get_resource_versions(context, *names):
    sel = Selector(context, "get_resource_versions", *names)
    action = sel.raw_action("get", "-o=custom-columns=NAME:.metadata.name,RV:.metadata.resourceVersion", "--no-headers", internal=True)
    if action.status != 0:
        return None
    lines = action.out.strip().split("\n")
    map = {}
    for line in lines: # Each line looks like "jupierce   56314"
        elements = line.strip().split()
        if len(elements) != 2:
            raise RuntimeError("Unexpected output from custom-columns: " + line + "\nFull output:\n"+ lines)
        map[elements[0]] = elements[1]
    return map


class Selector(Result):

    def __init__(self, context, high_level_operation, *args, **kwargs):
        super(self.__class__, self).__init__(high_level_operation)
        self.context = context

        self.object_list = kwargs.get("object_list", None)
        self.labels = kwargs.get("labels", None)

        if len(args) == 0:  # caller must set object_list if it wasn't in kwargs
            return

        if self.labels is not None:
            if len(args) != 1:
                raise ValueError("Expected kind as first parameter when labels are specified")
            self.kind = expand_kind(args[0])
        else:
            # Otherwise, allow Selector( 'kind", "name" ) or Selector( "kind/name", "kind2/name2", ...)
            if len(args) == 0:
                raise ValueError("Requires kind or qualified object name")

            first = args[0]
            if "/" not in first:  # Caller has specified ("kind", ["name"])
                self.kind = normalize_kind(first)
                if len(args) == 2:  # Caller has specified ("kind", "name")
                    self.object_list = ["%s/%s" % (self.kind, args[1])]
                elif len(args) > 1:
                    raise ValueError("Invalid parameters")
            else:  # Caller specified ( qualified_name1, qualified_name2, ...)
                self.object_list = []
                for a in args:
                    kind, name = str(a).split("/")
                    self.object_list.append("%s/%s" % (normalize_kind(kind), name))

    def __iter__(self):
        return self.objects().__iter__()

    def selection_args(self):
        args = []

        if self.object_list is not None:
            return self.object_list

        args.append(self.kind)

        if self.labels is not None:
            for k, v in self.labels.items():
                args.append("-l %s=%s" % (k, v))

        return args

    def name(self):
        names = self.names()

        if len(names) == 0:
            raise OpenShiftException("Expected single name, but selector returned no resources")

        if len(names) > 1:
            raise OpenShiftException("Expected single name, but selector returned multiple resources")

        return names[0]

    def raw_action(self, verb, *args, **kwargs):
        return oc_action(self.context, verb, self.selection_args(), *args, **kwargs)

    def query_names(self):
        result = Result("query_names")
        result.add_action(oc_action(self.context, 'get', '-o=name', self.selection_args()))

        # TODO: This check is necessary until --ignore-not-found is implemented and prevalent
        if result.status() != 0 and "(NotFound)" in result.err():
            return []

        # Otherwise, errors are fatal
        result.fail_if("Unable to retrieve object names")
        return split_names(result.out())

    def names(self):
        if self.object_list is not None:
            return self.object_list
        return self.query_names()

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
                    ns.append("%s/%s" % (normalize_kind(obj.kind), obj.metadata.name))
        elif isinstance(kind_or_func, str) or isinstance(kind_or_func, unicode):
            kind = normalize_kind(kind_or_func)
            ns = [n for n in self.names() if n.startswith(kind + "/")]
        else:
            raise ValueError("Don't know how to narrow with type: " + type(kind_or_func))

        s = Selector(self.context, "narrow", object_list=ns)
        return s

    def related(self):
        """
        Returns a dynamic selector which selects objects related to the single object
        selected by the receiver. For example, if the receiver selects a single template,
        a selector will be returned which is capable of finding all objects created
        by that template.
        :return: A dynamic selector which selects objects related to the object selected
            by this receiver.
        """
        labels = {}
        kind, name = self.name().split("/")

        if kind == "templates":
            labels["template"] = name
        elif kind == "deploymentconfigs":
            labels["deploymentconfig"] = name
        elif kind == "buildconfigs":
            labels["openshift.io/build-config.name"] = name
        elif kind == "jobs":
            labels["job-name"] = name
        else:
            raise OpenShiftException("Unknown how to find resources to related to kind: " + kind)

        return Selector("related", labels=labels)

    def count(self):
        """
        :return: Returns the number of objects this receiver selects that actually exist on the
            server.
        """
        return len(self.query_names())

    def exists(self, min=1):
        """
        In the case of a static selector, returns whether all named resources exist on the
        server (and exceed the minimum count).
        In the case of a dynamic selector, returns whether the receiver selects a minimum
        number of existing objects on the server.
        :param min: The minimum number of objects which must exist.
        :return: Returns True or False depending on the existence condition described above.
        """

        if self.object_list is not None:
            return min <= len(self.object_list) == self.count()
        return self.count(self) >= min

    def as_json(self, exportable=False):
        """
        Returns all objects selected by the receiver as a JSON string. If multiple objects are
        selected, an OpenShift List kind will be returned.
        :param exportable: Set to True if the export verb should be used.
        :return: Returns all selected objects marshalled as an OpenShift JSON representation.
        """

        # If the selctor is static and empty return an empty list object
        if self.object_list is not None and len(self.object_list) == 0:
            return json.dumps({
                "apiVersion": "v1",
                "kind": "List",
                "metadata": {},
                "items": []
            })

        verb = "export" if exportable else "get"
        r = Result(verb)
        r.add_action(oc_action(self.context, verb, "-o=json", self.selection_args()))
        r.fail_if("Unable to read object")

        return r.out()

    # Returns a single Model object that represents the selected resource. The Selector
    # must select exact one object or an exception will be thrown.
    def object(self, exportable=False):
        """
        Returns a single Model object that represents the selected resource. If multiple
        resources are being selected an exception will be thrown (use objects() when
        there is a possibility of selecting multiple objects).
        :param exportable: Whether export should be used instead of get.
        :return: A Model of the selected resource.
        """

        obj = json.loads(self.as_json(exportable))
        if obj["kind"] == "List":
            if len(obj["items"]) == 0:
                raise OpenShiftException("Expected a single object, but selected 0")
            else:
                raise OpenShiftException("Expected a single object, but selected more than one")
        return Model(obj)

    # Returns a pylist of Model objects that represent the selected resources.
    def objects(self, exportable=False):
        """
        Returns a python list of Model objects that represent the selected resources. An
        empty is returned if nothing is selected.
        :param exportable: Whether export should be used instead of get.
        :return: A list of Model objects representing the receiver's selected resources.
        """

        objs = []
        obj = json.loads(self.as_json(exportable))
        if obj["kind"] == "List":
            for item in obj["items"]:
                objs.append(Model(item))
        else:
            objs.append(Model(obj))

        return objs

    def start_build(self, *args):
        r = Selector()

        # Have start-build output a list of objects it creates
        args = list(args).append("-o=name")

        for name in self.names():
            r.add_action(oc_action(self.context, "start-build", name, *args))

        r.fail_if("Error running start-build on at least one item: " + str(self.names()))
        r.object_list = split_names(r.out())
        self.context.register_changes(r.names())
        return r

    def describe(self, send_to_stdout=True, *args):
        r = Result("describe")
        r.add_action(oc_action(self.context, "describe", self.selection_args(), *args))
        r.fail_if("Error describing objects")
        if send_to_stdout:
            print r.out()
        return r

    def delete(self, ignore_not_found=True, *args):
        names = self.names()

        if len(names) == 0:
            return

        r = Result("delete")
        args = list(args)
        if ignore_not_found:
            args.append("--ignore-not-found")
        args.append("-o=name")

        with ChangeTrackingFor(self.context, *names):
            r.add_action(oc_action(self.context, "delete", self.selection_args(), *args))

        r.fail_if("Error deleting objects")
        r.object_list = split_names(r.out())
        return r

    def label(self, labels, *args):
        names = self.names()

        r = Result("label")
        args = list(args)
        args.append("-o=name")
        args.append("--overwrite")

        for l, v in labels.items():
            if v is None:
                if not l.endswith("-"):
                    l += "-"  # Indicate removal on command line if caller has not applied "-" suffix
                args.append(l)
            else:
                args.append(l + "=" + v)

        with ChangeTrackingFor(self.context, *names):
            for name in names:
                r.add_action(oc_action(self.context, "label", name, *args))

        r.fail_if("Error running label on at least one item: " + str(self.names()))
        return self

    def patch(self, patch_def, strategy="strategic", *args):
        names = self.names()

        r = Result("patch")
        args = list(args)
        args.append("--type=" + strategy)
        args.append("-o=name")

        content = to_single_string(patch_def)

        with ChangeTrackingFor(self.context, *names):
            with TempFileContent(content) as path:
                args.append("--patch=" + content)
                for name in names:
                    r.add_action(oc_action(self.context, "patch", name, *args, reference={path: content}))

        r.fail_if("Error running patch on at least one item: " + str(self.names()))
        r.object_list = split_names(r.out())
        return r

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
            poll_period = min(poll_period+1, 15)

    def until_all(self, min_count, success_func, failure_func=None, *args, **kwargs):
        """
        Polls the server until ALL selected resources satisfy a user specified
        success condition or ANY violate a user specified failure condition.

        To accomplish this, until_all periodically selects all objects selected
        by the receiver and iterates through them. For each object selected,
        the user specified callable(s) will be invoked once with the object
        as a Model (*args and **kwargs will also be passed along).

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
            poll_period = min(poll_period+1, 15)
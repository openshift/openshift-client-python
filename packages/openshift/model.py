from __future__ import absolute_import

import six

from six.moves import range


class OpenShiftPythonException(Exception):

    def __init__(self, msg, result=None, **kwargs):
        super(self.__class__, self).__init__(msg)
        self.msg = msg
        self.result = result
        self.kwargs = kwargs

    def attributes(self):
        return dict(self.kwargs)

    def get_result(self):
        """
        :return: Returns the Result object associated with
         this exception if any. Might be None.
        """
        return self.result

    def as_dict(self):
        d = dict(self.kwargs)
        d["msg"] = self.msg
        if self.result is not None:
            d["result"] = self.result
        return d

    def __str__(self):
        if self.result is None:
            return self.msg
        return "[" + self.msg + "]\n" + repr(self.result)


class ModelError(Exception):

    def __init__(self, msg, **kwargs):
        super(self.__class__, self).__init__(msg)
        self.msg = msg
        self.kwargs = kwargs


class MissingModel(dict):

    def __init__(self):
        super(self.__class__, self).__init__()
        pass

    def __getattr__(self, attr):
        return self

    def __setattr__(self, key, value):
        raise ModelError("Invalid attempt to set key(%s) in missing branch of model" % key)

    def __delattr__(self, key):
        raise ModelError("Invalid attempt to delete key(%s) in missing branch of model" % key)

    def __getitem__(self, attr):
        return self

    def __setitem__(self, key, value):
        raise ModelError("Invalid attempt to set key(%s) in missing branch of model" % key)

    def __delitem__(self, key):
        raise ModelError("Invalid attempt to delete key(%s) in missing branch of model" % key)

    # Express false-y
    def __bool__(self):
        return False

    # Express false-y
    def __len__(self):
        return 0

    def __str__(self):
        return "(MissingModelBranch)"

    def __repr__(self):
        return "(MissingModelBranch)"

    def __div__(self, other):
        return self

    def __add__(self, other):
        return self

    def __sub__(self, other):
        return self

    def __mul__(self, other):
        return self

    def can_match(self, *vals):
        return False


# Singleton which indicates if any model attribute was not defined
Missing = MissingModel()


def to_model_or_val(v, case_insensitive=False):
    if isinstance(v, ListModel) or isinstance(v, Model):
        return v
    if isinstance(v, list):
        return ListModel(v, case_insensitive=case_insensitive)
    elif isinstance(v, dict):
        return Model(v, case_insensitive=case_insensitive)
    else:
        return v


def _element_can_match(master, test, case_insensitive=False):
    if master is Missing:
        return False

    if master is None or test is None:
        return master is test

    if isinstance(master, str):
        master = six.text_type(master)  # Turn str into unicode
        if case_insensitive:
            master = master.lower()

    if isinstance(test, str):
        test = six.text_type(test)  # Turn str into unicode
        if case_insensitive:
            test = test.lower()

    for prim in [bool, int, six.text_type, float]:
        if isinstance(master, prim):
            return master == test or str(master) == str(test)

    if isinstance(master, dict):
        if isinstance(test, dict):
            return _dict_is_subset(master, test, case_insensitive=case_insensitive)
        else:
            return False

    if isinstance(master, list):
        if isinstance(test, list):
            return _list_is_subset(master, test, case_insensitive=case_insensitive)
        else:
            return False

    raise ModelError("Don't know how to compare %s and %s" % (str(type(master)), str(type(test))))


def _element_in_list(master, e, case_insensitive=False):
    for m in master:
        if _element_can_match(m, e, case_insensitive=case_insensitive):
            return True
    return False


def _list_is_subset(master, test, case_insensitive=False):
    for e in test:
        if not _element_in_list(master, e, case_insensitive=case_insensitive):
            return False
    return True


def _dict_is_subset(master, subset, case_insensitive=False):
    for k, v in subset.items():
        if case_insensitive:
            k = k.lower()
        m = master.get(k, Missing)
        if not _element_can_match(m, v, case_insensitive=case_insensitive):
            return False

    return True


class ListModel(list):

    def __init__(self, list_to_model, case_insensitive=False):
        super(ListModel, self).__init__()
        self.__case_insensitive = case_insensitive
        if list_to_model is not None:
            self.extend(list_to_model)

    def __setitem__(self, key, value):
        super(self.__class__, self).__setitem__(key, value)

    def __delitem__(self, key):
        super(self.__class__, self).__delitem__(key)

    def __getitem__(self, index):
        if super(self.__class__, self).__len__() > index:
            v = super(self.__class__, self).__getitem__(index)
            if isinstance(v, Model):
                return v
            v = to_model_or_val(v, case_insensitive=self.__case_insensitive)
            self.__setitem__(index, v)
            return v

        # Otherwise, trigger out of bounds exception
        return super(self.__class__, self).__getitem__(index)

    def __iter__(self):
        for i in range(0, super(self.__class__, self).__len__()):
            yield self[i]

    def _primitive(self):
        """
        :return: Returns the ListModel as a python list
        :rtype: list
        """
        l = []
        for e in self:
            if isinstance(e, Model) or isinstance(e, ListModel):
                e = e._primitive()
            l.append(e)
        return l

    def can_match(self, list_or_entry):
        """
        Answers whether this list is a subset of the specified list. If the argument is not a list,
        it placed into one for comparison purposes.
        Elements of the argument list can be primitives, lists, or dicts. In the case of non-primitives, the list or
        dicts must ultimately be subsets of at least one element in the receiver list.
        :param list_or_entry: The list to compare or a primitive/dict that must exist in the receiver's list.
        :return: Returns true if all of the elements specify can match (i.e. are subsets of) elements of this list.
        """
        if not isinstance(list_or_entry, (list, tuple, ListModel)):
            # If we were not passed a list, turn it into one
            list_or_entry = [list_or_entry]

        return _list_is_subset(self, list_or_entry, case_insensitive=self.__case_insensitive)


class Model(dict):

    def __init__(self, dict_to_model=None, case_insensitive=False):
        super(Model, self).__init__()

        self.__case_insensitive = case_insensitive

        if dict_to_model is not None:
            for k, v in dict_to_model.items():
                if self.__case_insensitive:
                    k = k.lower()
                self[k] = to_model_or_val(v, case_insensitive=case_insensitive)

    def __getattr__(self, attr):

        if isinstance(attr, six.string_types):
            if attr.startswith('_Model__'):  # e.g. _Model__case_insensitive
                raise AttributeError

            if self.__case_insensitive:
                attr = attr.lower()

        if super(Model, self).__contains__(attr):
            v = super(self.__class__, self).get(attr)
            if isinstance(v, Model) or isinstance(v, ListModel):
                return v
            v = to_model_or_val(v, self.__case_insensitive)
            self.__setattr__(attr, v)
            return v
        else:
            return Missing

    def __setattr__(self, key, value):
        if key.startswith('_Model__'):  # e.g. _Model__case_insensitive
            return super(Model, self).__setattr__(key, value)

        if self.__case_insensitive:
            key = key.lower()

        self.__setitem__(key, value)

    def __getitem__(self, key):
        return self.__getattr__(key)

    def __setitem__(self, key, value):
        super(Model, self).__setitem__(key, to_model_or_val(value, case_insensitive=self.__case_insensitive))

    def __delitem__(self, key):
        if self.__is_case_sensitive__():
            key = key.lower()
        super(Model, self).__delitem__(key)

    def _primitive(self):
        """
        :return: Returns the Model as a python dict
        :rtype: dict
        """
        d = {}
        for k, v in six.iteritems(self):
            if isinstance(v, Model) or isinstance(v, ListModel):
                v = v._primitive()
            d[k] = v
        return d

    def can_match(self, val):
        """
        Answers whether this Model matches all elements of the argument.
        :param val: A dict or Model with elements set that must be found within this model.
        :return: Returns true if all of the elements can match (i.e. are subsets of) elements of this list.
        """
        return _dict_is_subset(self, val, case_insensitive=self.__case_insensitive)

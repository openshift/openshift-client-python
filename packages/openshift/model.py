

class OpenShiftPythonException(StandardError):

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


class ModelError(StandardError):

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


def to_model_or_val(v):
    if isinstance(v, list):
        return ListModel(v)
    elif isinstance(v, dict):
        return Model(v)
    else:
        return v


class ListModel(list):

    def __init__(self, list_to_model):
        super(self.__class__, self).__init__()
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
            v = to_model_or_val(v)
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
            l.append(e)
        return l

    def _element_can_match(self, master, test):
        if master is Missing:
            return False

        if master is None or test is None:
            return master is test

        if isinstance(master, str):
            master = unicode(master)  # Turn str into unicode

        if isinstance(test, str):
            test = unicode(test)  # Turn str into unicode

        for prim in [bool, int, unicode, float]:
            if isinstance(master, prim):
                return master == test or str(master) == str(test)

        if isinstance(master, dict):
            if isinstance(test, dict):
                return self._dict_is_subset(master, test)
            else:
                return False

        if isinstance(master, list):
            if isinstance(test, list):
                return self._list_is_subset(master, test)
            else:
                return False

        raise ModelError("Don't know how to compare %s and %s" % (str(type(master)), str(type(test))))

    def _element_in_list(self, master, e):
        for m in master:
            if self._element_can_match(m, e):
                return True
        return False

    def _list_is_subset(self, master, test):

        for e in test:
            if not self._element_in_list(master, e):
                return False
        return True

    def _dict_is_subset(self, master, subset):
        for k, v in subset.items():
            m = master.get(k, Missing)
            if not self._element_can_match(m, v):
                return False

        return True

    def can_match(self, *vals):
        return self._list_is_subset(self, vals)


class Model(dict):

    def __init__(self, dict_to_model=None):
        super(Model, self).__init__()
        if dict_to_model is not None:
            for k, v in dict_to_model.items():
                self[k] = v

    def __getattr__(self, attr):
        if super(Model, self).__contains__(attr):
            v = super(self.__class__, self).get(attr)
            if isinstance(v, Model):
                return v
            v = to_model_or_val(v)
            self.__setattr__(attr, v)
            return v
        else:
            return Missing

    def __setattr__(self, key, value):
        self.__setitem__(key, value)

    def __getitem__(self, key):
        return self.__getattr__(key)

    def __setitem__(self, key, value):
        super(Model, self).__setitem__(key, value)

    def __delitem__(self, key):
        super(Model, self).__delitem__(key)

    def _primitive(self):
        """
        :return: Returns the Model as a python dict
        :rtype: dict
        """
        d = {}
        for k, v in self.iteritems():
            if isinstance(v, Model) or isinstance(v, ListModel):
                v = v._primitive()
            d[k] = v
        return d
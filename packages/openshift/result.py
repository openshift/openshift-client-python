import json
from model import OpenShiftException


class Result(object):
    def __init__(self, high_level_operation):
        self.high_level_operation = high_level_operation
        self.__actions = []

    def actions(self):
        my_list = [a for a in self.__actions if not a.internal]
        return self.__actions

    # Returns a bitwise OR of all underlying action statuses (if 0, all actions returned 0)
    def status(self):
        s = 0
        for action in self.__actions:
            s |= int(action.status)
        return s

    # Returns aggregate stdout from all underlying actions
    def out(self):
        s = ""
        for action in self.__actions:
            s += action.out
            if not s.endswith("\n"):
                s += "\n"
        return s

    def timeout(self):
        t = False
        for action in self.__actions:
            t |= action.timeout
        return t

    # Returns aggregate stderr from all underlying actions
    def err(self):
        s = ""
        for action in self.__actions:
            s += action.out
            if not s.endswith("\n"):
                s += "\n"
        return s

    def as_dict(self, truncate_stdout=50, redact_tokens=True, redact_references=True, redact_output=True):

        m = {
            "operation": self.high_level_operation,
            "status": self.status(),
            "actions": [action.as_dict(truncate_stdout=truncate_stdout, redact_tokens=redact_tokens,
                                       redact_references=redact_references,
                                       redact_output=redact_output) for action in self.__actions]
        }

        return m

    def as_json(self, indent=4, truncate_stdout=50, redact_tokens=True, redact_references=True, redact_output=True):
        return json.dumps(
            self.as_dict(truncate_stdout=truncate_stdout, redact_tokens=redact_tokens,
                         redact_references=redact_references, redact_output=redact_output),
            indent=indent)

    def add_action(self, action):
        self.__actions.append(action)

    def __repr__(self):
        return self.as_json()

    def fail_if(self, msg):
        if self.timeout():
            msg += " (Timeout)"

        if self.status() != 0:
            raise OpenShiftException(msg, self)

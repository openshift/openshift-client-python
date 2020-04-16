from __future__ import absolute_import

import json

from .model import OpenShiftPythonException


class Result(object):
    def __init__(self, high_level_operation, tracking_limit=None):
        self.high_level_operation = high_level_operation
        self.__actions = []
        # if tracking_limit is less than 0 that means unlimited tracking_limit
        if tracking_limit is not None and tracking_limit >= 0:
            self.limit_tracking_actions = tracking_limit
        else:
            self.limit_tracking_actions = None

    def actions(self):
        my_list = [a for a in self.__actions if not a.internal]
        return my_list

    # Returns a bitwise OR of all underlying action statuses (if 0, all actions returned 0)
    def status(self):
        s = 0
        for action in self.__actions:
            # If not the last attempt, return status does not matter; errors ignored.
            if action.last_attempt:
                s |= int(action.status)
        return s

    # Returns aggregate stdout from all underlying actions
    def out(self):
        s = u''
        for action in self.__actions:
            if action.out:
                s += action.out
                if not s.endswith("\n"):
                    s += u'\n'
        return s

    def get_timeout(self):
        """
        :return: Iterates through all actions in this Result and returns the first Action object
        it finds that indicates it timed out. If no action timed out, returns None.
        """
        for action in self.__actions:
            if action.timeout:
                return action
        return None

    # Returns aggregate stderr from all underlying actions
    def err(self):
        s = u''
        for action in self.__actions:
            if action.err:
                s += action.err
                if not s.endswith("\n"):
                    s += u'\n'
        return s

    def as_dict(self, truncate_stdout=-1, redact_tokens=True, redact_streams=True, redact_references=True):

        m = {
            "operation": self.high_level_operation,
            "status": self.status(),
            "actions": [action.as_dict(truncate_stdout=truncate_stdout, redact_tokens=redact_tokens,
                                       redact_references=redact_references,
                                       redact_streams=redact_streams) for action in self.__actions]
        }

        return m

    def as_json(self, indent=4, truncate_stdout=-1, redact_tokens=True, redact_streams=True, redact_references=True):
        return json.dumps(
            self.as_dict(truncate_stdout=truncate_stdout, redact_tokens=redact_tokens,
                         redact_references=redact_references, redact_streams=redact_streams),
            indent=indent)

    def add_action(self, action):
        self.__actions.append(action)
        if self.limit_tracking_actions is not None and len(self.__actions) > self.limit_tracking_actions:
            self.__actions.pop(0)

    def add_result(self, result):
        self.__actions.extend(result.__actions)

    def __repr__(self):
        return self.as_json()

    def fail_if(self, msg):
        if self.get_timeout():
            msg += " (Timeout during: {})".format(self.get_timeout().as_dict()['cmd'])

        if self.status() != 0:
            raise OpenShiftPythonException(msg, self)

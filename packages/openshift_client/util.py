from __future__ import absolute_import

import tempfile
import sys
import io
import os
import errno
import json
import six


# Context manager that will swap stdout/stderr with buffers.
# Anything the inner block prints will be captured in these
# buffers and availed in the as: object.
class OutputCapture(object):

    def __init__(self):
        self.out = io.BytesIO()
        self.err = io.BytesIO()

    def __enter__(self):
        sys.stdout = self.out
        sys.stderr = self.err
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


class TempFile(object):
    """
    Creates a temporary file, open for reading/writing within the context.
    If content is specified, it is written into the file when created and
    the file position is reset to 0.
    """

    def __init__(self, content=None, suffix=".tmp"):
        self.suffix = suffix
        self.file = None
        self.content = content

    def __enter__(self):
        self.file = tempfile.TemporaryFile(suffix=self.suffix, prefix="openshift-client-python")

        if self.content:
            try:
                self.file.write(self.content.encode('utf-8'))
                self.flush()
                self.file.seek(0, os.SEEK_SET)  # seek to the beginning of the file
            except Exception:
                self.destroy()
                raise

        return self

    def flush(self):
        self.file.flush()

    def read(self):
        self.flush()
        self.file.seek(0, os.SEEK_SET)
        return self.file.read()

    def destroy(self):
        if self.file is not None:
            try:
                self.file.close()
            except Exception:
                pass
        self.file = None

    def __exit__(self, type, value, traceback):
        self.destroy()


def split_names(output):
    """
    Designed to split up output from -o=name into a
    simple list of qualified object names ['kind/name', 'kind/name', ...]
    :param output: A single string containing all of the output to parse
    :return: A list of qualified object names
    """
    if output is None:
        return []
    return [x.strip() for x in output.strip().split("\n") if x.strip() != ""]


def is_collection_type(obj):
    return isinstance(obj, (list, tuple, set))


def indent_lines(text, padding='  '):
    return ''.join(padding+line for line in text.splitlines(True))


def print_logs(stream, logs_dict, initial_indent_count=0, encoding='utf-8'):
    indent = ' ' * initial_indent_count
    next_indent = ' ' * (initial_indent_count + 2)
    for container_fqn, log in six.iteritems(logs_dict):
        stream.write(u'{}[logs:begin]{}========\n'.format(indent, container_fqn))
        value_string = log.strip().replace('\r\n', '\n')
        stream.write(u'{}\n'.format(indent_lines(value_string, next_indent)))
        stream.write(u'{}[logs:end]{}========\n'.format(indent, container_fqn))


def print_report_entry(stream, d, initial_indent_count=0, encoding='utf-8'):
    indent = ' ' * initial_indent_count
    next_indent = ' ' * (initial_indent_count + 2)
    for entry, value in six.iteritems(d):
        stream.write(u'{}*{}:\n'.format(indent, entry))

        if entry == 'logs':
            print_logs(stream, value, initial_indent_count + 2, encoding=encoding)
        else:
            if isinstance(value, dict):  # for 'object'
                value_string = json.dumps(value, indent=2)
            elif isinstance(value, six.string_types):  # for 'describe'
                value_string = value.strip().replace('\r\n', '\n')
            else:
                value_string = u'{}'.format(value)

            stream.write(u'{}\n'.format(indent_lines(value_string, next_indent)))


def print_report(stream, report_dict, initial_indent_count=0, encoding='utf-8'):
    indent = ' ' * initial_indent_count
    for fqn, details in six.iteritems(report_dict):
        stream.write(u'\n{}[report:begin]{}========\n'.format(indent, fqn))
        print_report_entry(stream, details, initial_indent_count + 2, encoding=encoding)
        stream.write(u'\n{}[report:end]{}========\n'.format(indent, fqn))


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
    return path


# unit scale used by kubernetes
_unit_scales = {'n': -3, 'u': -2, 'm': -1, 'k': 1, 'K': 1, 'M': 2, 'G': 3, 'T': 4, 'P': 5, 'E': 6}


def extract_numerical_value(val):
    """Extract numerical values from string, removing any units present
       e.g, 10K => 10000; 10Ki => 10240 """
    if not val:
        return 0
    base = 10
    value = 0
    power = 0
    power_scale = 3
    unit_place = -1
    if val[-1] == 'i':
        if len(val) < 3:
            return 0
        base = 2
        power_scale = 10
        unit_place = -2
    unit = val[unit_place]
    if unit in _unit_scales:
        power = _unit_scales[unit]
        if len(val[:unit_place]) == 0:
            value = 0
        else:
            value = float(val[:unit_place])
    elif unit_place == -2:
        value = float(val[:-1])
    else:
        value = float(val)
    return value * pow(base, power*power_scale)

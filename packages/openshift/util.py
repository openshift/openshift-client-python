import tempfile
import sys
import io
import os
import codecs
import errno
import json


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
        self.path = None
        self.content = content

    def __enter__(self):
        self.file, self.path = tempfile.mkstemp(self.suffix, "openshift-client-python")

        if self.content:
            try:
                os.write(self.file, self.content)
                self.flush()
                os.lseek(self.file, 0, os.SEEK_SET)  # seek to the beginning of the file
            except Exception as e:
                self.destroy()
                raise e

        return self

    def flush(self):
        os.fsync(self.file)

    def read(self, max_size=-1, encoding="utf-8"):
        self.flush()
        # Ignore errors - with things like collected journals during dumpinfo, we can encounter binary
        # data that we can't read with utf-8. Just ignore it.
        with codecs.open(self.path, mode="rb", encoding=encoding, errors='ignore', buffering=1024) as cf:
            return cf.read(size=max_size)

    def destroy(self):
        if self.file is not None:
            try:
                os.close(self.file)
            except StandardError:
                pass
        if self.path is not None:
            try:
                os.unlink(self.path)
            except:
                pass
        self.file = None
        self.path = None

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
    for container_fqn, log in logs_dict.iteritems():
        stream.write(u'{}[logs:begin]{}========\n'.format(indent, container_fqn))
        value_string = log.strip().replace('\r\n', '\n')
        stream.write(u'{}\n'.format(indent_lines(value_string, next_indent)))
        stream.write(u'{}[logs:end]{}========\n'.format(indent, container_fqn))


def print_report_entry(stream, d, initial_indent_count=0, encoding='utf-8'):
    indent = ' ' * initial_indent_count
    next_indent = ' ' * (initial_indent_count + 2)
    for entry, value in d.iteritems():
        stream.write(u'{}*{}:\n'.format(indent, entry))

        if entry is 'logs':
            print_logs(stream, value, initial_indent_count + 2, encoding=encoding)
        else:
            if isinstance(value, dict):  # for 'object'
                value_string = json.dumps(value, indent=2)
            elif isinstance(value, basestring):  # for 'describe'
                value_string = value.strip().replace('\r\n', '\n')
            else:
                value_string = u'{}'.format(value)

            stream.write(u'{}\n'.format(indent_lines(value_string, next_indent)))


def print_report(stream, report_dict, initial_indent_count=0, encoding='utf-8'):
    indent = ' ' * initial_indent_count
    for fqn, details in report_dict.iteritems():
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
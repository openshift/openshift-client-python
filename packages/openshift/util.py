import tempfile
import sys
import io
import os
import codecs


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
        self.file, self.path = tempfile.mkstemp(self.suffix, "openshift-python")

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
        with codecs.open(self.path, mode="rb", encoding=encoding, buffering=1024) as cf:
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
    return isinstance(obj, (list, tuple))
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


class TempFileContent(object):
    def __init__(self, content, suffix=".tmp"):
        self.suffix = suffix
        self.file = None
        self.path = None
        self.content = content

    def __enter__(self):
        self.file, self.path = tempfile.mkstemp(self.suffix, "openshift-python")

        try:
            os.write(self.file, self.content)
            os.close(self.file)
        except Exception as e:
            self.destroy()
            raise e

        return self.path

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


class TempFile(object):

    def __init__(self, suffix=".tmp"):
        self.suffix = suffix
        self.file = None
        self.path = None

    def __enter__(self):
        self.file, self.path = tempfile.mkstemp(self.suffix, "openshift-python")
        return self

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

    def flush(self):
        os.fsync(self.file)

    def read(self, max_size=-1, encoding="utf-8"):
        self.flush()
        with codecs.open(self.path, mode="rb", encoding=encoding, buffering=1024) as cf:
            return cf.read(size=max_size)

    def __exit__(self, type, value, traceback):
        self.destroy()

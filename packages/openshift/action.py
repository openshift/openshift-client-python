import subprocess
import time
from .util import TempFile
from .model import Model
from .util import OutputCapture


class Action(Model):

    def __init__(self, verb, cmd, out, err, reference, status, timeout=False, internal=False):
        d = {
            "verb": verb,
            "cmd": cmd,
            "out": out,
            "err": err,
            "status": status
        }

        if reference is not None:
            d["reference"] = reference

        if internal:
            d["internal"] = True

        if timeout:
            d["timeout"] = True

        self.internal = internal
        self.timeout = timeout
        super(self.__class__, self).__init__(d)


def oc_action(context, verb, *args, **kwargs):
    cmds = ["oc", verb]

    if context.get_config() is not None:
        cmds.append("--config=%s" % context.get_config())

    if context.get_cluster() is not None:
        url = context.get_cluster()

        # If insecure:// is specified, skip TLS verification
        if url.startswith("insecure://"):
            url = "https://" + url[len("insecure://"):]
            cmds.append("--insecure-skip-tls-verify")

        cmds.append("--server=%s" % url)

    if context.get_project() is not None and not kwargs.get("no_namespace", False):
        cmds.append("--namespace=%s" % context.get_project())

    if context.get_token() is not None:
        cmds.append("--token=%s" % context.get_token())

    if context.get_loglevel() is not None:
        cmds.append("--loglevel=%s" % context.get_loglevel())

    reference = None
    if "reference" in kwargs:
        # Be aware of Python2/3 differences in modifying while iterating
        # a list before trying to optimize here.
        reference = dict(kwargs["reference"])

        if context.get_redact_references():
            for k, v in kwargs["reference"].items():
                content = str(v).lower()
                if "secret" in content or "password" in content:
                    reference[k] = "redacted due potentially private data"

    # Arguments which are lists are flattened into the command list
    for a in args:
        if isinstance(a, list):
            cmds.extend(a)
        else:
            cmds.append(a)

    redacted_cmds = list(cmds)

    if context.get_redact_tokens():
        for i, s in enumerate(redacted_cmds):
            if s.startswith("--token"):
                redacted_cmds[i] = "--token=XXXXXXXXXXX"

    period = 0.01

    timeout = False
    with TempFile() as out:
        with TempFile() as err:
            # When only python3 is supported, change to using standard timeout
            process = subprocess.Popen(cmds, stdout=out.file, stderr=err.file)

            while process.poll() is None:
                if context.is_out_of_time():
                    try:
                        timeout = True
                        process.kill()
                        break
                    except OSError:
                        pass  # ignore
                time.sleep(period)
                period = min(1, period+period)

            stdout = out.read()
            stderr = err.read()


    returncode = process.returncode
    if timeout:
        returncode = -1

    internal = kwargs.get("internal", False)
    a = Action(verb, redacted_cmds, stdout, stderr, reference, returncode, timeout=timeout, internal=internal)
    context.register_action(a)
    return a

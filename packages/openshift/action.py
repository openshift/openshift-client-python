import subprocess
import time
import socket
import json
from .util import TempFile


def _redact_token_arg(arg):
    if "--token" in arg.lower():
        return "--token=**REDACTED**"
    return arg


def _redact_content(content):
    content = content.lower()
    if "secret" in content or "password" in content or "token" in content:
        return "**REDACTED**"
    return content


class Action(object):

    def __init__(self, verb, cmd_list, out, err, references, status, stdin=None, timeout=False, internal=False):
        self.status = status
        self.verb = verb
        self.cmd = cmd_list
        self.out = out
        self.err = err
        self.stdin = stdin
        self.references = references
        self.timeout = timeout
        self.internal = internal

        if not self.references:
            self.references = {}

    def as_dict(self, truncate_stdout=50, redact_tokens=True, redact_references=True, redact_streams=True):

        d = {
            'status': self.status,
            'verb': self.verb,
            'cmd': self.cmd,
            'out': self.out,
            'err': self.err,
            'stdin': self.stdin,
            'references': self.references,
            'timeout': self.timeout,
            'internal': self.internal,
        }

        if redact_tokens:
            d['cmd'] = [_redact_token_arg(arg) for arg in self.cmd]

        if redact_references:
            d['references'] = {key: _redact_content(value) for (key, value) in self.references.iteritems()}

        if redact_streams:
            d['out'] = _redact_content(self.out)
            if self.stdin:
                d['stdin'] = _redact_content(self.stdin)

        if truncate_stdout and truncate_stdout > -1:
            content = d['out']
            d['out'] = (content[:truncate_stdout] + '...') if len(content) > content else content

        return d

    def as_json(self, indent=4, redact_tokens=True, redact_references=True, redact_streams=True):
        return json.dumps(
            self.as_dict(redact_tokens=redact_tokens, redact_references=redact_references,
                         redact_streams=redact_streams), indent=indent)


def escape_arg(arg):
    # https://stackoverflow.com/questions/3163236/escape-arguments-for-paramiko-sshclient-exec-command
    return "'%s'" % (arg.replace(r"'", r"'\''"),)


def _flatten_list(l):
    agg = []
    if isinstance(l, list) or isinstance(l, tuple):
        for e in l:
            agg.extend(_flatten_list(e))
    else:
        agg.append(l)

    return agg


def oc_action(context, verb, cmd_args=[], all_namespaces=False, no_namespace=False, references=None, stdin=None,
              **kwargs):
    """
    Executes oc client verb with arguments. Returns an Action with result information.
    :param context: context information for the execution
    :param verb: The name of the verb to execute
    :param cmd_args: A list of strings|array<string> which will be flattened into oc arguments
    :param all_namespaces: If true, --all-namespaces will be included in the invocation
    :param no_namespace: If true, namespace will not be included in invocation
    :param references: A dict of values to include in the tracking information for this action
    :param stdin: A string to supply to stdin for the oc invocation
    :param args: Argument strings to add to the invocation (e.g. '--output=name'). Each argument can also be a list
        of strings which will be flattened (e.g. ['--output=name', '--ignore_not_found'])
    :param kwargs:
    :return: An Action object.
    :rtype: Action
    """
    cmds = ["oc", verb]

    if context.get_kubeconfig_path() is not None:
        cmds.append("--config=%s" % context.get_kubeconfig_path())

    if context.get_api_url() is not None:
        url = context.get_api_url()

        # If insecure:// is specified, skip TLS verification
        if url.startswith("insecure://"):
            url = "https://" + url[len("insecure://"):]
            cmds.append("--insecure-skip-tls-verify")

        cmds.append("--server=%s" % url)

    if all_namespaces:
        cmds.append("--all-namespaces")
    elif context.get_project() is not None and not no_namespace:
        cmds.append("--namespace=%s" % context.get_project())

    if context.get_token() is not None:
        cmds.append("--token=%s" % context.get_token())

    if context.get_loglevel() is not None:
        cmds.append("--loglevel=%s" % context.get_loglevel())

    # Arguments which are lists are flattened into the command list
    cmds.extend(_flatten_list(cmd_args))

    period = 0.01

    timeout = False

    if context.get_ssh_client() is not None:
        command_string = ""

        # If paramiko fails to timeout, consider using polling: https://stackoverflow.com/a/45844203

        for i, c in enumerate(cmds):
            # index zero is 'oc' -- no need to escape
            if i > 0:
                c = " {}".format(escape_arg(c))

            command_string += c

        try:
            ssh_stdin, ssh_stdout, ssh_stderr = context.get_ssh_client().exec_command(command=command_string,
                                                                                      timeout=context.get_min_remaining_seconds())
        except socket.timeout as error:
            timeout = True

        if stdin:
            ssh_stdin.write(stdin)
            ssh_stdin.flush()
            ssh_stdin.channel.shutdown_write()

        stdout = ssh_stdout.read()
        stderr = ssh_stderr.read()
        returncode = ssh_stdout.channel.recv_exit_status()

    else:

        with TempFile(content=stdin) as stdin_file:
            with TempFile() as out:
                with TempFile() as err:
                    # When only python3 is supported, change to using standard timeout
                    process = subprocess.Popen(cmds, stdin=stdin_file.file, stdout=out.file, stderr=err.file)

                    while process.poll() is None:
                        if context.is_out_of_time():
                            try:
                                timeout = True
                                process.kill()
                                break
                            except OSError:
                                pass  # ignore
                        time.sleep(period)
                        period = min(1, period + period)  # Poll fast at first, but slow down to 1/sec over time

                    stdout = out.read()
                    stderr = err.read()

        returncode = process.returncode
        if timeout:
            returncode = -1

    internal = kwargs.get("internal", False)
    a = Action(verb, cmds, stdout, stderr, references, returncode, stdin=stdin, timeout=timeout, internal=internal)
    context.register_action(a)
    return a

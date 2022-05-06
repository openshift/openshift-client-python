from __future__ import absolute_import

import subprocess
import time
import socket
import json
import os
import re
import datetime
import traceback
import six

from .util import TempFile, is_collection_type


# Three base64 encoded components, '.' delimited is a token. First, find any such match.
# You can find examples of these tokens with `oc sa get-token <serviceaccount name>`
token_regex = re.compile(r"[a-zA-Z0-9+/_\-]{10,}\.[a-zA-Z0-9+/_\-]{100,}\.[a-zA-Z0-9+/_\-]{20,}")

# Find any semblance of kind..Secret
secret_regex = re.compile(r"\W*kind\W+Secret\W*", re.IGNORECASE)

# OAuthAccessTokens are 43 char base64 encoded strings
oauth_regex = re.compile(r"[a-zA-Z0-9+/_\-]{43}")


def _is_sensitive(content_str):

    if token_regex.findall(content_str):
        return True

    if secret_regex.findall(content_str):
        return True

    if oauth_regex.findall(content_str):
        return True

    return False


def _redaction_string():
    return u'**REDACTED**'


def _redact_content(content_str):

    content_str = token_regex.sub(_redaction_string(), content_str, 0)
    content_str = oauth_regex.sub(_redaction_string(), content_str, 0)

    if secret_regex.match(content_str):
        return 'Secret: {}'.format(_redaction_string())

    return content_str


class Action(object):

    def __init__(self, verb, cmd_list, out, err, references, status, stdin_str=None,
                 last_attempt=True, internal=False, elapsed_time=0,
                 timeout=False,
                 exec_time=0):
        self.status = status
        self.verb = verb
        self.cmd = cmd_list
        self.out = out or ''
        self.err = err or ''
        self.stdin_str = stdin_str
        self.references = references
        self.timeout = timeout
        self.last_attempt = last_attempt
        self.internal = internal
        self.elapsed_time = elapsed_time
        self.exec_time = exec_time

        if self.references is None:
            self.references = {}

    def as_dict(self, truncate_stdout=-1, redact_tokens=True, redact_streams=True, redact_references=True):

        d = {
            'timestamp': self.exec_time,
            'elapsed_time': self.elapsed_time,
            'success': (self.status == 0),  # allows an easy grep in tracking output
            'status': self.status,
            'verb': self.verb,
            'cmd': self.cmd,
            'out': self.out,
            'err': self.err,
            'in': self.stdin_str,
            'references': self.references,
            'timeout': self.timeout,
            'last_attempt': self.last_attempt,
            'internal': self.internal,
        }

        if redact_tokens:
            redacted = []
            next_is_token = False
            for arg in self.cmd:
                if next_is_token:
                    redacted.append(_redaction_string())
                    next_is_token = False
                elif arg == '--token':
                    next_is_token = True
                    redacted.append(arg)
                elif arg.startswith('--token'):
                    redacted.append(u'--token=**REDACTED**')
                else:
                    redacted.append(arg)
            d['cmd'] = redacted

        if redact_references:
            refs = {}
            for (key, value) in six.iteritems(self.references):

                # pass through references starting with . since those are internal and designed not to
                # contain private values.
                if key.startswith('.'):
                    refs[key] = value
                    continue

                # References van be string or complex structures.
                if isinstance(value, six.string_types):
                    value_str = value
                else:
                    # If a structure of some type, serialize into a string to
                    # check the entire thing for sensitivity.
                    value_str = json.dumps(value)

                if _is_sensitive(value_str):
                    refs[key] = _redact_content(value_str)
                else:
                    # If not sensitive, make sure to keep structure.
                    refs[key] = value

            d['references'] = refs

        if redact_streams:
            if _is_sensitive(self.err):
                d['err'] = _redact_content(self.err)
            else:
                d['err'] = self.err

        if self.stdin_str:
            if redact_streams and _is_sensitive(self.stdin_str):
                d['in'] = _redaction_string()
            else:
                try:
                    # If the input can be parsed as json, do so
                    if self.stdin_str.strip().startswith('{'):
                        d['in_obj'] = json.loads(self.stdin_str)
                        del d['in']
                except:
                    pass

        if redact_streams and _is_sensitive(self.out):
            d['out'] = _redact_content(self.out)
        else:
            if len(self.out) > truncate_stdout > -1:
                d['out'] = (self.out[:truncate_stdout] + '...truncated...')
            else:
                try:
                    # If the output can be parsed as json, do so
                    if self.out.startswith('{'):
                        d['out_obj'] = json.loads(self.out)
                        del d['out']
                except:
                    pass

        return d

    def as_json(self, indent=4, redact_tokens=True, redact_streams=True, redact_references=True):
        return json.dumps(
            self.as_dict(redact_tokens=redact_tokens, redact_references=redact_references,
                         redact_streams=redact_streams), indent=indent)


def escape_arg(arg):
    # https://stackoverflow.com/questions/3163236/escape-arguments-for-paramiko-sshclient-exec-command
    return "'%s'" % (str(arg).replace(r"'", r"'\''"),)


def _flatten_list(l):
    """
    Flattens a list of elements (which can themselves be lists) into a single list
    of strings.
    :param l: A list which may contain other lists. Elements of that list may be None.
    :return: A single, flat list. None elements found in the argument will not be included.
    """

    if l is None:
        return []

    agg = []
    if is_collection_type(l):
        for e in l:
            agg.extend(_flatten_list(e))
    else:
        if isinstance(l, bool):  # bools are lowercase for things like labels
            l = '{}'.format(l).lower()
        else:  # Make sure everything is a string
            l = '{}'.format(l)
        agg.append(l)

    return agg


def oc_action(context, verb, cmd_args=None, all_namespaces=False, no_namespace=False, namespace=None,
              references=None, stdin_obj=None, stdin_str=None, last_attempt=True,
              **kwargs):
    """
    Executes oc client verb with arguments. Returns an Action with result information.
    :param context: context information for the execution
    :param verb: The name of the verb to execute
    :param cmd_args: A list of strings|list<string> which will be flattened into oc arguments
    :param all_namespaces: If true, --all-namespaces will be included in the invocation
    :param no_namespace: If true, namespace will not be included in invocation
    :param namespace: Namespace which will override context namespace if specified
    :param references: A dict of values to include in the tracking information for this action
    :param stdin_obj: A json serializable object to supply to stdin for the oc invocation
    :param stdin_str: If stdin is not a json serializable object. Cannot be specified in conjunction with stdin_obj.
    :param last_attempt: If False, implies that this action will be retried by higher level control on failure.
    :param kwargs:
    :return: An Action object.
    :rtype: Action
    """
    cmds = [context.get_oc_path(), verb]

    if references is None:
        references = {}

    if context.get_kubeconfig_path() is not None:
        cmds.append("--kubeconfig=%s" % context.get_kubeconfig_path())

    if context.get_api_url() is not None:
        url = context.get_api_url()

        # If insecure:// is specified, skip TLS verification
        if url.startswith("insecure://"):
            url = "https://" + url[len("insecure://"):]
            cmds.append("--insecure-skip-tls-verify")

        cmds.append("--server=%s" % url)

    if context.get_token() is not None:
        cmds.append('--token={}'.format(context.get_token()))

    if context.get_ca_cert_path() is not None:
        cmds.append('--cacert={}'.format(context.get_ca_cert_path()))

    if all_namespaces:
        cmds.append("--all-namespaces")
    elif namespace:
        cmds.append("--namespace=%s" % namespace)
    elif context.get_project() is not None and not no_namespace:
        cmds.append("--namespace=%s" % context.get_project())

    for k, v in six.iteritems(context.get_options()):
        # If a value was set to None, it should not impact the command line
        if not v:
            continue

        if not k.startswith('-'):
            if len(k) > 1:
                k = '--{}'.format(k)
            else:
                k = '-{}'.format(k)

        cmds.append('{}={}'.format(k, v).lower())

    if context.get_loglevel() is not None:
        cmds.append("--loglevel=%s" % context.get_loglevel())

    if context.get_skip_tls_verify():
        cmds.append("--insecure-skip-tls-verify")

    # Arguments which are lists are flattened into the command list
    cmds.extend(_flatten_list(cmd_args))

    period = 0.01

    timeout = False

    # If stdin_object is specified, serialize into the string.
    if stdin_obj:
        stdin_str = json.dumps(stdin_obj, indent=None)

    # Set defaults in case is_out_of_time is true
    stdout = ""
    stderr = ""
    return_code = -1

    start_time = time.time()
    exec_time = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds() * 1000)

    if context.get_ssh_client() is not None:
        references['.client_host'] = '{}@{}'.format(context.get_ssh_username() or '', context.get_ssh_hostname())

    # If we are out of time, don't even try to execute.
    expired, timeout_context = context.get_out_of_time()
    if not expired:

        if context.get_ssh_client() is not None:
            command_string = ""

            for i, c in enumerate(cmds):
                # index zero is 'oc' -- no need to escape
                if i > 0:
                    c = " {}".format(escape_arg(c))

                command_string += c

            try:
                pathed_command = 'PATH=$PATH:$HOME/bin {}'.format(command_string)

                # This timeout applies to individual read / write channel operations which follow.
                # If paramiko fails to timeout, consider using polling: https://stackoverflow.com/a/45844203
                remaining, timeout_context = context.get_min_remaining_seconds()
                ssh_stdin, ssh_stdout, ssh_stderr = context.get_ssh_client().exec_command(command=pathed_command,
                                                                                          timeout=remaining,
                                                                                          environment={
                                                                                              'LC_ALL': 'en_US.UTF-8',
                                                                                          }
                                                                                          )
                if stdin_str:
                    ssh_stdin.write(stdin_str)
                    ssh_stdin.flush()
                    ssh_stdin.channel.shutdown_write()

                # In python2, read() returns type:str. In python3, I believe it will return type:bytes.
                # By decoding, we are making the assumption that openshift-client-python will be
                # useful for text based interactions (e.g. we don't support oc exec with
                # binary output). By converting into a real unicode string type, hopefully we prevent
                # a raft of incompatibilities between 2 and 3.
                stdout = ssh_stdout.read().decode('utf-8', errors='ignore')
                stderr = ssh_stderr.read().decode('utf-8', errors='ignore')
                return_code = ssh_stdout.channel.recv_exit_status()

            except socket.timeout as error:
                timeout = True
                return_code = -1

        else:

            with TempFile(content=stdin_str) as stdin_file:
                with TempFile() as out:
                    with TempFile() as err:
                        # When only python3 is supported, change to using standard timeout
                        env = os.environ.copy()
                        env['LC_ALL'] = 'en_US.UTF-8'
                        process = subprocess.Popen(cmds, stdin=stdin_file.file,
                                                   stdout=out.file, stderr=err.file, env=env)

                        while process.poll() is None:
                            expired, timeout_context = context.get_out_of_time()
                            if expired:
                                try:
                                    timeout = True
                                    process.kill()
                                    break
                                except OSError:
                                    pass  # ignore
                            time.sleep(period)
                            period = min(1, period + period)  # Poll fast at first, but slow down to 1/sec over time

                        # See note in paramiko flow on decoding
                        stdout = out.read().decode('utf-8', errors='ignore')
                        stderr = err.read().decode('utf-8', errors='ignore')

            return_code = process.returncode
            if timeout:
                return_code = -1

        end_time = time.time()
        elapsed_time = (end_time - start_time)

    else:
        timeout = True
        return_code = -1
        elapsed_time = -1  # Indicate we never tried to run the process

    # If there is an error, collect a stack for debug purposes
    if return_code != 0:
        references['.stack'] = traceback.format_stack()

    if timeout and timeout_context and timeout_context.frame_info:
        references['.timeout_context'] = '{}:{}'.format(timeout_context.frame_info[0], timeout_context.frame_info[1])

    internal = kwargs.get("internal", False)
    a = Action(verb, cmds, stdout, stderr, references, return_code,
               stdin_str=stdin_str, last_attempt=last_attempt,
               internal=internal, elapsed_time=elapsed_time,
               exec_time=exec_time, timeout=timeout,
               )

    context.register_action(a)
    return a

# Openshift Python Client
<!-- Install doctoc with `npm install -g doctoc`  then `doctoc README.md --github` -->

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Overview](#overview)
- [Reader Prerequisites](#reader-prerequisites)
- [Setup](#setup)
  - [Prerequisites](#prerequisites)
  - [Installation Instructions](#installation-instructions)
    - [Using PIP](#using-pip)
    - [For development](#for-development)
- [Usage](#usage)
  - [Quickstart](#quickstart)
  - [Selectors](#selectors)
  - [APIObjects](#apiobjects)
  - [Making changes to APIObjects](#making-changes-to-apiobjects)
  - [Running within a Pod](#running-within-a-pod)
  - [Tracking oc invocations](#tracking-oc-invocations)
  - [Time limits](#time-limits)
  - [Advanced contexts](#advanced-contexts)
  - [Something missing?](#something-missing)
  - [Running oc on a bastion host](#running-oc-on-a-bastion-host)
  - [Gathering reports and logs with selectors](#gathering-reports-and-logs-with-selectors)
  - [Advanced verbs:](#advanced-verbs)
- [Examples](#examples)
- [Environment Variables](#environment-variables)
  - [Defaults when invoking `oc`](#defaults-when-invoking-oc)
  - [Master timeout](#master-timeout)
  - [SSH Client Host](#ssh-client-host)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

## Overview
The [openshift-client-python](https://www.github.com/openshift/openshift-client-python) library aims to provide a readable, concise, comprehensive, and fluent
API for rich interactions with an [OpenShift](https://www.openshift.com) cluster. Unlike other clients, this library exclusively uses the command
line tool (oc) to achieve the interactions. This approach comes with important benefits and disadvantages when compared
to other client libraries.

Pros:
- No additional software needs to be installed on the cluster. If a system with python support can (1) invoke `oc`
locally OR (2) ssh to a host and invoke `oc`, you can use the library.
- Portable. If you have python and `oc` working, you don't need to worry about OpenShift versions or machine architectures.
- Custom resources are supported and treated just like any other resource. There is no need to generate code to support them.
- Quick to learn. If you understand the `oc` command line interface, you can use this library.

Cons:
- This API is not intended to implement something as complex as a controller. For example, it does not implement
watch functionality. If you can't imagine accomplishing your use case through CLI interactions, this API is probably 
not the right starting point for it. 
- If you care about whether a REST API returns a particular error code, this API is probably not for you. Since it
is based on the CLI, high level return codes are used to determine success or failure.

## Reader Prerequisites
* Familiarity with OpenShift [command line interface](https://docs.openshift.org/latest/cli_reference/basic_cli_operations.html)
is highly encouraged before exploring the API's features. The API leverages the [oc](https://docs.openshift.org/latest/cli_reference/index.html)
binary and, in many cases, passes method arguments directly on to the command line. This document cannot, therefore,
provide a complete description of all possible OpenShift interactions -- the user may need to reference
the CLI documentation to find the pass-through arguments a given interaction requires.

* A familiarity with Python is assumed.

## Setup
### Prerequisites
1. Download and install the OpenShift [command-line Tools](https://mirror.openshift.com/pub/openshift-v4/clients/ocp/latest/) needed to access your OpenShift cluster.

### Installation Instructions

#### Using PIP
1. Install the `openshift-client` module from PyPI.
    ```bash
    sudo pip install openshift-client
    ```

#### For development
1. Git clone https://github.com/openshift/openshift-client-python.git (or your fork).
2. Append ./packages to your PYTHONPATH environment variable (e.g. export PYTHONPATH=$(pwd)/packages:$PYTHONPATH).
3. Write and run your python script!

## Usage

### Quickstart
Any standard Python application should be able to use the API if it imports the openshift package. The simplest
possible way to begin using the API is login to your target cluster before running your first application.

Can you run `oc project` successfully from the command line? Then write your app!

```python
#!/usr/bin/python
import openshift as oc

print('OpenShift client version: {}'.format(oc.get_client_version()))
print('OpenShift server version: {}'.format(oc.get_server_version()))

# Set a project context for all inner `oc` invocations and limit execution to 10 minutes
with oc.project('openshift-infra'), oc.timeout(10*60):
    # Print the list of qualified pod names (e.g. ['pod/xyz', 'pod/abc', ...]  in the current project
    print('Found the following pods in {}: {}'.format(oc.get_project_name(), oc.selector('pods').qnames()))
    
    # Read in the current state of the pod resources and represent them as python objects
    for pod_obj in oc.selector('pods').objects():
        
        # The APIObject class exposes several convenience methods for interacting with objects
        print('Analyzing pod: {}'.format(pod_obj.name()))
        pod_obj.print_logs(timestamps=True, tail=15)
    
        # If you need access to the underlying resource definition, get a Model instance for the resource
        pod_model = pod_obj.model
        
        # Model objects enable dot notation and allow you to navigate through resources
        # to an arbitrary depth without checking if any ancestor elements exist.
        # In the following example, there is no need for boilerplate like:
        #    `if .... 'ownerReferences' in pod_model['metadata'] ....`
        # Fields that do not resolve will always return oc.Missing which 
        # is a singleton and can also be treated as an empty dict.
        for owner in pod_model.metadata.ownerReferences:  # ownerReferences == oc.Missing if not present in resource
            # elements of a Model are also instances of Model or ListModel
            if owner.kind is not oc.Missing:  # Compare as singleton
                print('  pod owned by a {}'.format(owner.kind))  # e.g. pod was created by a StatefulSet

```

### Selectors
Selectors are a central concept used by the API to interact with collections
of OpenShift resources. As the name implies, a "selector" selects zero or
more resources on a server which satisfy user specified criteria. An apt
metaphor for a selector might be a prepared SQL statement which can be
used again and again to select rows from a database.

```python
# Create a selector which selects all projects.
project_selector = oc.selector("projects")

# Print the qualified name (i.e. "kind/name") of each resource selected.
print("Project names: " + project_selector.qnames())

# Count the number of projects on the server.
print("Number of projects: " + project_selector.count_existing())

# Selectors can also be created with a list of names.
sa_selector = oc.selector(["serviceaccount/deployer", "serviceaccount/builder"])

# Performing an operation will act on all selected resources. In this case,
# both serviceaccounts are labeled.
sa_selector.label({"mylabel" : "myvalue"})

# Selectors can also select based on kind and labels.
sa_label_selector = oc.selector("sa", labels={"mylabel":"myvalue"})

# We should find the service accounts we just labeled.
print("Found labeled serviceaccounts: " + sa_label_selector.names())

# Create a selector for a set of kinds.
print(oc.selector(['dc', 'daemonset']).describe())
```

The output should look something like this:

```
Project names: [u'projects/default', u'projects/kube-system', u'projects/myproject', u'projects/openshift', u'projects/openshift-infra', u'projects/temp-1495937701365', u'projects/temp-1495937860505', u'projects/temp-1495937908009']
Number of projects: 8
Found labeled serviceaccounts: [u'serviceaccounts/builder', u'serviceaccounts/deployer']
```

### APIObjects

Selectors allow you to perform "verb" level operations on a set of objects, but
what if you want to interact objects at a schema level?

```python
projects_sel = oc.selector("projects")

# .objects() will perform the selection and return a list of APIObjects
# which model the selected resources.
projects = projects_sel.objects()

print("Selected " + len(projects) + " projects")

# Let's store one of the project APIObjects for easy access.
project = projects[0]

# The APIObject exposes methods providing simple access to metadata and common operations.
print('The project is: {}/{}'.format(project.kind(), project.name()))
project.label({ 'mylabel': 'myvalue' })

# And the APIObject allow you to interact with an object's data via the 'model' attribute.
# The Model is similar to a standard dict, but also allows dot notation to access elements
# of the structured data.
print('Annotations:\n{}\n'.format(project.model.metadata.annotations))

# There is no need to perform the verbose 'in' checking you may be familiar with when
# exploring a Model object. Accessing Model attributes will always return a value. If the
# any component of a path into the object does not exist in the underlying model, the
# singleton 'Missing' will be returned.

if project.model.metadata.annotations.myannotation is oc.Missing:
    print("This object has not been annotated yet")

# If a field in the model contains special characters, use standard Python notation
# to access the key instead of dot notation.
if project.model.metadata.annotations['my-annotation'] is oc.Missing:
    print("This object has not been annotated yet")

# For debugging, you can always see the state of the underlying model by printing the
# APIObject as JSON.
print('{}'.format(project.as_json()))

# Or getting deep copy dict. Changes made to this dict will not affect the APIObject.
d = project.as_dict()

# Model objects also simplify looking through kubernetes style lists. For example, can_match
# returns True if the modeled list contains an object with the subset of attributes specified.
# If this example, we are checking if the a node's kubelet is reporting Ready:
oc.selector('node/alpha').object().model.status.conditions.can_match(
    {
        'type': 'Ready',
        'status': "True",
    }
)

# can_match can also ensure nest objects and list are present within a resource. Several
# of these types of checks are already implemented in the openshift.status module.
def is_route_admitted(apiobj):
    return apiobj.model.status.can_match({
        'ingress': [
            {
                'conditions': [
                    {
                        'type': 'Admitted',
                        'status': 'True',
                    }
                ]
            }
        ]
    })
```


### Making changes to APIObjects
```python
# APIObject exposes simple interfaces to delete and patch the resource it represents.
# But, more interestingly, you can make detailed changes to the model and apply those
# changes to the API.

project.model.metadata.labels['my_label'] = 'myvalue'
project.apply()

# If modifying the underlying API resources could be contentious, use the more robust
# modify_and_apply method which can retry the operation multiple times -- refreshing
# with the current object state between failures.

# First, define a function that will make changes to the model.
def make_model_change(apiobj):
    apiobj.model.data['somefile.yaml'] = 'wyxz'
    return True

# modify_and_apply will call the function and attempt to apply its changes to the model
# if it returns True. If the apply is rejected by the API, the function will pull
# the latest object content, call make_model_change again, and try the apply again
# up to the specified retry account.
configmap.modify_and_apply(make_model_change, retries=5)


# For best results, ensure the function passed to modify_and_apply is idempotent:

def set_unmanaged_in_cvo(apiobj):
    desired_entry = {
        'group': 'config.openshift.io/v1',
        'kind': 'ClusterOperator',
        'name': 'openshift-samples',
        'unmanaged': True,
    }

    if apiobj.model.spec.overrides.can_match(desired_entry):
        # No change required
        return False

    if not apiobj.model.spec.overrides:
        apiobj.model.spec.overrides = []

    context.progress('Attempting to disable CVO interest in openshift-samples operator')
    apiobj.model.spec.overrides.append(desired_entry)
    return True

result, changed = oc.selector('clusterversion.config.openshift.io/version').object().modify_and_apply(set_unmanaged_in_cvo)
if changed:
    context.report_change('Instructed CVO to ignore openshift-samples operator')

```


### Running within a Pod
It is simple to use the API within a Pod. The `oc` binary automatically
detects it is running within a container and automatically uses the Pod's serviceaccount token/cacert.

### Tracking oc invocations
It is good practice to setup at least one tracking context within your application so that
you will be able to easily analyze what `oc` invocations were made on your behalf and the result
of those operations. *Note that details about all `oc` invocations performed within the context will
be stored within the tracker. Therefore, do not use a single tracker for a continuously running
process -- it will consume memory for every oc invocation.*

```python
#!/usr/bin/python
import openshift as oc

with oc.tracking() as tracker:
    try:
        print('Current user: {}'.format(oc.whoami()))
    except:
        print('Error acquiring current username')
    
    # Print out details about the invocations made within this context.
    print(tracker.get_result())
```

In this case, the tracking output would look something like:
```json
{
    "status": 0, 
    "operation": "tracking", 
    "actions": [
        {
            "status": 0, 
            "verb": "project", 
            "references": {}, 
            "in": null, 
            "out": "aos-cd\n", 
            "err": "", 
            "cmd": [
                "oc", 
                "project", 
                "-q"
            ], 
            "elapsed_time": 0.15344810485839844, 
            "internal": false, 
            "timeout": false, 
            "last_attempt": true
        }, 
        {
            "status": 0, 
            "verb": "whoami", 
            "references": {}, 
            "in": null, 
            "out": "aos-ci-jenkins\n", 
            "err": "", 
            "cmd": [
                "oc", 
                "whoami"
            ], 
            "elapsed_time": 0.6328380107879639, 
            "internal": false, 
            "timeout": false, 
            "last_attempt": true
        }
    ]
}
```

Alternatively, you can record actions yourself by passing an action_handler to the tracking 
contextmanager. Your action handler will be invoked each time an `oc` invocation completes.

```python
def print_action(action):
    print('Performed: {} - status={}'.format(action.cmd, action.status))

with oc.tracking(action_handler=print_action):
    try:
        print('Current project: {}'.format(oc.get_project_name()))
        print('Current user: {}'.format(oc.whoami()))
    except:
        print('Error acquiring details about project/user')

```

### Time limits
Have a script you want to ensure succeeds or fails within a specific period of time? Use
a `timeout` context. Timeout contexts can be nested - if any timeout context expires, 
the current oc invocation will be killed. 

```python
#!/usr/bin/python
import openshift as oc

def node_is_ready(node):
    ready = node.model.status.conditions.can_match({
        'type': 'Ready',
        'status': 'True',
    })
    return ready


print("Waiting for up to 15 minutes for at least 6 nodes to be ready...")
with oc.timeout(15 * 60):
    oc.selector('nodes').until_all(6, success_func=node_is_ready)
    print("All detected nodes are reporting ready")
```        

You will be able to see in `tracking` context results that a timeout occurred for an affected
invocation. The `timeout` field will be set to `True`.

### Advanced contexts
If you are unable to use a KUBECONFIG environment variable or need fine grained control over the 
server/credentials you communicate with for each invocation, use openshift-client-python contexts. 
Contexts can be nested and cause oc invocations within them to use the most recently established 
context information.

```python
with oc.api_server('https:///....'):  # use the specified api server for nested oc invocations.
    
    with oc.token('abc..'):  # --server=... --token=abc... will be included in inner oc invocations.
        print("Current project: " + oc.get_project_name())
    
    with oc.token('def..'):  # --server=... --token=def... will be included in inner oc invocations.
        print("Current project: " + oc.get_project_name())
```

You can control the loglevel specified  for `oc` invocations.
```python
with oc.loglevel(6):
   # all oc invocations within this context will be invoked with --loglevel=6
    oc...   
```

You ask `oc` to skip TLS verification if necessary.
```python
with oc.tls_verify(enable=False):
   # all oc invocations within this context will be invoked with --insecure-skip-tls-verify
    oc...   
```

### Something missing?
Most common API iterations have abstractions, but if there is no openshift-client-python API 
exposing the `oc` function you want to run, you can always use `oc.invoke` to directly pass arguments to 
an `oc` invocation on your host.

```python
# oc adm policy add-scc-to-user privileged -z my-sa-name
oc.invoke('adm', ['policy', 'add-scc-to-user', 'privileged', '-z', 'my-sa-name'])
```

### Running oc on a bastion host

Is your oc binary on a remote host? No problem. Easily remote all CLI interactions over SSH using the client_host
context. Before running this command, you will need to load your ssh agent up with a key
appropriate to the target client host.

```python
with openshift.client_host(hostname="my.cluster.com", username="root", auto_add_host=True):
    # oc invocations will take place on my.cluster.com host as the root user.
    print("Current project: " + oc.get_project_name())
```

Using this model, your Python script will run exactly where you launch it, but all oc invocations will
occur on the remote host.

### Gathering reports and logs with selectors

Various objects within OpenShift have logs associated with them:
- pods
- deployments
- daemonsets
- statefulsets
- builds
- etc..

A selector can gather logs from pods associated with each (and for each container within those pods). Each
log will be a unique value in the dictionary returned.

```python
# Print logs for all pods associated with all daemonsets & deployments in openshift-monitoring namespace.
with oc.project('openshift-monitoring'):
    for k, v in oc.selector(['daemonset', 'deployment']).logs(tail=500).iteritems():
        print('Container: {}\n{}\n\n'.format(k, v))
```

The above example would output something like:
```
Container: openshift-monitoring:pod/node-exporter-hw5r5(node-exporter)
time="2018-10-22T21:07:36Z" level=info msg="Starting node_exporter (version=0.16.0, branch=, revision=)" source="node_exporter.go:82"
time="2018-10-22T21:07:36Z" level=info msg="Enabled collectors:" source="node_exporter.go:90"
time="2018-10-22T21:07:36Z" level=info msg=" - arp" source="node_exporter.go:97"
...
```

Note that these logs are held in memory. Use tail or other available method parameters to ensure 
predictable and efficient results.

To simplify even further, you can ask the library to pretty-print the logs for you:
```python
oc.selector(['daemonset', 'deployment']).print_logs()
```

And to quickly pull together significant diagnostic data on selected objects, use `report()` or `print_report()`. 
A report includes the following information for each selected object, if available:
- `object` - The current state of the object.
- `describe` - The output of describe on the object.
- `logs` - If applicable, a map of logs -- one of each container associated with the object. 

```python
# Pretty-print a detail set of data about all deploymentconfigs, builds, and configmaps in the 
# current namespace context.
oc.selector(['dc', 'build', 'configmap']).print_report()
```

### Advanced verbs:

Running oc exec on a pod.
```python
    result = oc.selector('pod/alertmanager-main-0').object().execute(['cat'],
                                                                     container_name='alertmanager',
                                                                     stdin='stdin for cat')
    print(result.out())
```

Finding all pods running on a node:
```python
with oc.client_host():
    for node_name in oc.selector('nodes').qnames():
        print('Pods running on node: {}'.format(node_name))
            for pod_obj in oc.get_pods_by_node(node_name):
                print('  {}'.format(pod_obj.fqname()))
```

Example output:
```
...
Pods running on node: node/ip-172-31-18-183.ca-central-1.compute.internal
  72-sus:pod/sus-1-vgnmx
  ameen-blog:pod/ameen-blog-2-t68qn
  appejemplo:pod/ejemplo-1-txdt7
  axxx:pod/mysql-5-lx2bc
...
```

## Examples

- [Some unit tests](examples/cluster_tests.py)

## Environment Variables
To allow openshift-client-python applications to be portable between environments without needing to be modified, 
you can specify many default contexts in the environment. 

### Defaults when invoking `oc`
Establishing explicit contexts within an application will override these environment defaults.
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_OC_PATH` - default path to use when invoking `oc`
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_CONFIG_PATH` - default `--config` argument
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_API_SERVER` - default `--server` argument
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_CA_CERT_PATH` - default `--cacert` argument
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_PROJECT` - default `--namespace` argument
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_OC_LOGLEVEL` - default `--loglevel` argument
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_SKIP_TLS_VERIFY` - default `--insecure-skip-tls-verify`

### Master timeout
Defines an implicit outer timeout(..) context for the entire application. This allows you to ensure
that an application terminates within a reasonable time, even if the author of the application has
not included explicit timeout contexts. Like any `timeout` context, this value is not overridden
by subsequent `timeout` contexts within the application. It provides an upper bound for the entire
application's oc interactions.

- `OPENSHIFT_CLIENT_PYTHON_MASTER_TIMEOUT` 

### SSH Client Host
In some cases, it is desirable to run an openshift-client-python application using a local `oc` binary and 
in other cases, the `oc` binary resides on a remote client. Encoding this decision in the application
itself is unnecessary.

Simply wrap you application in a `client_host` context without arguments. This will try to pull 
client host information from environment variables if they are present. If they are not present,
the application will execute on the local host.

For example, the following application will ssh to `OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_HOSTNAME` if it is defined
in the environment. Otherwise, `oc` interactions will be executed on the host running the python application.

```python
with oc.client_host():  # if OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_HOSTNAME if not defined in the environment, this is a no-op
    print( 'Found nodes: {}'.format(oc.selector('nodes').qnames()) ) 
```

- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_HOSTNAME` - The hostname on which the `oc` binary resides
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_USERNAME` - Username to use for the ssh connection (optional)
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_PORT` - SSH port to use (optional; defaults to 22)
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_SSH_AUTO_ADD` - Defaults to `false`. If set to `true`, unknown hosts will automatically be trusted.
- `OPENSHIFT_CLIENT_PYTHON_DEFAULT_LOAD_SYSTEM_HOST_KEYS` - Defaults to `true`. If true, the local known hosts information will be used.

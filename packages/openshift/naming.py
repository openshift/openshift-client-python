abbreviations = {
    "svc": "service",
    "p": "pod",
    "po": "pod",
    "bc": "buildconfig",
    "is": "imagestream",
    "rc": "replicationcontroller",
    "ds": "daemonset",
    "rs": "replicaset",
    "dc": "deploymentconfig",
    "deploy": "deployment",
    "ep": "endpoint"
}


def expand_kind(kind):
    kind = kind.strip().lower()
    if kind in abbreviations:
        return abbreviations[kind]
    return kind


def singularize_kind(kind):
    kind = kind.strip().lower()

    # if a fully qualified kind is supplied, don't assume we know better
    if '.' in kind:
        return kind

    if kind.endswith("s"):
        return kind[:-1]
    return kind


def normalize_kind(kind):
    return singularize_kind(expand_kind(kind))

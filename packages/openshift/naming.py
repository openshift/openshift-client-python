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
    "ep": "endpoint",
    "istag": "imagestreamtag",
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


def kind_matches(k1, k2):
    k1 = normalize_kind(k1)
    k2 = normalize_kind(k2)
    return k1 == k2 or k1.startswith(k2 + '.') or k2.startswith(k1 + '.')

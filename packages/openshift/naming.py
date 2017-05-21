abbreviations = {
    "svc": "services",
    "p": "pods",
    "po": "pods",
    "bc": "buildconfigs",
    "is": "imagestreams",
    "rc": "replicationcontrollers",
    "dc": "deploymentconfigs",
    "ep": "endpoints"
}


def expand_kind(kind):
    kind = kind.strip().lower()
    if kind in abbreviations:
        return abbreviations[kind]
    return kind


def pluralize_kind(kind):
    kind = kind.strip().lower()
    if kind.endswith("s"):
        return kind
    return kind + "s"


def normalize_kind(kind):
    return pluralize_kind(expand_kind(kind))

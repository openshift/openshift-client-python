
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
    """
    Turns a potentially abbreviated kind name into its
    standard, singular form. e.g. 'bc' -> buildconfig.
    :param kind: The kind name to expand
    :return: The kind name in standard/singular form.
    """

    kind = kind.strip().lower()
    if kind in abbreviations:
        return abbreviations[kind]
    return kind


def expand_kinds(kinds):
    """
    Iterates through a list of kinds and transforms abbreviations
    into standard form, singular kind name.
    :param kinds: A kind name or a list of kind names
    :return: A corresponding list of standard form, singular names.
    """

    # if we receive a simple string, massage into a list before processing
    if isinstance(kinds, basestring):
        kinds = [kinds]

    expanded = []
    for k in kinds:
        expanded.append(expand_kind(k))

    return expanded


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


def normalize_kinds(kinds):
    # if we receive a simple string, massage into a list before processing
    if isinstance(kinds, basestring):
        kinds = [kinds]

    normalized = []
    for k in kinds:
        normalized.append(singularize_kind(expand_kind(k)))

    return normalized


def kind_matches(k1, k2):
    k1 = normalize_kind(k1)
    k2 = normalize_kind(k2)
    return k1 == k2 or k1.startswith(k2 + '.') or k2.startswith(k1 + '.')

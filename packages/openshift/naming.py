
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


def kind_matches(k1, k2_or_list):
    k1 = normalize_kind(k1)

    # If a single string is provided, turn it into a list
    if isinstance(k2_or_list, basestring):
        k2_or_list = [k2_or_list]

    for k2e in k2_or_list:
        k2e = normalize_kind(k2e)
        if k1 == k2e or k1.startswith(k2e + '.') or k2e.startswith(k1 + '.'):
            return True

    return False


def qualify_name(name_or_qname, to_kind):
    """
    Formats a name or qualified name (kind/name) into a qualified
    name of the specified target kind.
    :param name_or_qname: The name to transform
    :param to_kind: The kind to apply
    :return: A qualified name like: kind/name
    """

    if '/' in name_or_qname:
        name_or_qname = name_or_qname.split('/')[-1]
    return '{}/{}'.format(to_kind, name_or_qname)
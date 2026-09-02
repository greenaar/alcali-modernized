"""Match minions on their stored grains and pillar.

Alcali already holds every accepted minion's grains and pillar, so questions
like "which hosts are on this kernel" or "which carry this pillar role" can be
answered without going near the master. The expression syntax follows Salt's
own grain matching: colon-separated key path, the last segment being the value,
which is matched as a shell glob.

This mirrors `salt.utils.data.subdict_match` for the cases Alcali needs. It is
deliberately not a reimplementation of Salt's compound matcher - see
`preview_target`, which refuses the expressions it cannot evaluate faithfully.
"""
import fnmatch


def _walk(data, path):
    """Follow a key path through nested dicts and lists of dicts."""
    node = data
    for key in path:
        if isinstance(node, dict) and key in node:
            node = node[key]
        elif isinstance(node, list):
            found = [i[key] for i in node if isinstance(i, dict) and key in i]
            if not found:
                return None, False
            node = found[0] if len(found) == 1 else found
        else:
            return None, False
    return node, True


def _value_matches(node, pattern):
    if isinstance(node, (list, tuple)):
        return any(_value_matches(item, pattern) for item in node)
    if isinstance(node, bool):
        # Avoid "1" matching True through str().
        return str(node).lower() == pattern.lower()
    if node is None:
        return pattern.lower() in ("none", "null")
    return fnmatch.fnmatch(str(node), pattern)


def subdict_match(data, expression, delimiter=":"):
    """True when `expression` (``key:subkey:glob``) matches `data`.

    Salt allows the delimiter in both the key path and the value, so every
    split point is tried, longest key path first - the same approach Salt
    takes.
    """
    if not expression:
        return False
    parts = expression.split(delimiter)
    if len(parts) == 1:
        # A bare key: matched when it is present at all.
        node, found = _walk(data, parts)
        return found and node not in (None, "", [], {})
    for split in range(len(parts) - 1, 0, -1):
        path, pattern = parts[:split], delimiter.join(parts[split:])
        node, found = _walk(data, path)
        if found and _value_matches(node, pattern):
            return True
    return False


def glob_match(minion_id, pattern):
    return fnmatch.fnmatch(minion_id, pattern)


def list_match(minion_id, expression, delimiter=","):
    return minion_id in [i.strip() for i in expression.split(delimiter)]

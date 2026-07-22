import re
from datetime import datetime
from difflib import get_close_matches

# One [bracket] OR "double" OR 'single' quoted token
_TOKEN_RE = re.compile(r'\[([^\[\]"\']*)\]|"([^\[\]"\']*)"|\'([^\[\]"\']*)\'')
_ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_arguments(text: str):
    """Extract [bracket]/"quote"/'quote' tokens in order.

    Returns (tokens, had_bare_words). had_bare_words is True when any
    non-delimited word remains after removing all tokens, so the handler
    can hint the user to wrap arguments in [ ].
    """
    if not text or not text.strip():
        return [], False
    tokens = []
    for m in _TOKEN_RE.finditer(text):
        val = next(g for g in m.groups() if g is not None).strip()
        if val:
            tokens.append(val)
    leftover = _TOKEN_RE.sub(" ", text).strip()
    return tokens, bool(leftover)


def is_valid_iso_date(s: str) -> bool:
    if not s or not _ISO_RE.match(s):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def split_date(tokens):
    """Return (date_or_None, other_tokens). The first ISO-shaped token is the date."""
    date = None
    rest = []
    for t in tokens:
        if date is None and _ISO_RE.match(t):
            date = t
        else:
            rest.append(t)
    return date, rest


def classify_tokens(tokens, companies, wallet_names):
    """Split tokens into (groups, names) by content.

    A token that matches a company name (case-insensitive) is a group;
    the group interpretation wins even if it also matches a wallet name.
    """
    comp_lower = {c.lower() for c in companies}
    groups, names = [], []
    for t in tokens:
        if t.lower() in comp_lower:
            groups.append(t)
        else:
            names.append(t)
    return groups, names


def resolve_fuzzy(token, candidates, n=3, cutoff=0.6):
    """Closest wallet names to `token`: case-insensitive substring hits first,
    then case-insensitive difflib close matches. Deduped, order-preserving, capped at n."""
    if not token or not candidates:
        return []
    tl = token.lower()
    subs = [c for c in candidates if tl in c.lower() or c.lower() in tl]
    lower_map = {}
    for c in candidates:
        lower_map.setdefault(c.lower(), c)   # first original per lowercased form
    close = [lower_map[m] for m in get_close_matches(tl, list(lower_map.keys()), n=n, cutoff=cutoff)]
    out = []
    for c in list(subs) + list(close):
        if c not in out:
            out.append(c)
    return out[:n]

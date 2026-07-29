import re
from datetime import datetime
from difflib import SequenceMatcher

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


def normalize_name(s):
    """lowercase; every run of non-alphanumerics becomes one space; trimmed."""
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def squash_name(s):
    """lowercase with every non-alphanumeric removed, so 'TH 2' == 'TH2'."""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def resolve_fuzzy(token, candidates, n=3, cutoff=0.6):
    """Find the wallet name(s) the user meant.

    Tries progressively looser rules and stops at the first that hits, so a query
    that matches literally never gets guesses mixed in:
        exact -> starts with -> contains -> all words -> closest match

    Spacing, punctuation and case are ignored throughout.
    Literal tiers return EVERY match (truncating could hide a real wallet);
    only the closest-match tier is capped at `n`, because those are guesses.

    Returns (matches, tier). tier is "none" when nothing matched.
    """
    if not token or not candidates:
        return [], "none"
    qn, qs = normalize_name(token), squash_name(token)
    if not qs:
        return [], "none"

    exact = [c for c in candidates if squash_name(c) == qs]
    if exact:
        return exact, "exact"

    starts = [c for c in candidates if squash_name(c).startswith(qs)]
    if starts:
        return starts, "starts with"

    contains = [c for c in candidates if qs in squash_name(c)]
    if contains:
        return contains, "contains"

    words = qn.split()
    if len(words) > 1:
        all_words = [c for c in candidates
                     if all(w in normalize_name(c) for w in words)]
        if all_words:
            return all_words, "all words"

    def score(c):
        cn, cs = normalize_name(c), squash_name(c)
        # compare against the whole name AND its same-length start, in both the
        # spaced and squashed forms -- the head comparison is what lets a short
        # typo'd query ("DPY CYO") still find a longer name.
        return max(SequenceMatcher(None, qn, cn).ratio(),
                   SequenceMatcher(None, qn, cn[:len(qn)]).ratio(),
                   SequenceMatcher(None, qs, cs).ratio(),
                   SequenceMatcher(None, qs, cs[:len(qs)]).ratio())

    ranked = sorted(((score(c), c) for c in candidates), key=lambda x: -x[0])
    close = [c for s, c in ranked if s >= cutoff][:n]
    return (close, "closest match") if close else ([], "none")

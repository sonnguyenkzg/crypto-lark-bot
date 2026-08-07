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


def normalize_iso_date(s):
    """Canonical zero-padded 'YYYY-MM-DD', or None if unparseable.

    Comparing date strings lexicographically (as the vault code does throughout) is only
    correct when every date is zero-padded: '2026-07-20' < '2026-7-20' is TRUE as text,
    so a stray non-padded cell (e.g. a hand-edited DAILY_REPORT row) would sort wrongly.
    Normalise BOTH sides before any date comparison so a malformed cell can never make a
    real balance sort as "before it existed" and get hidden. strptime accepts padded and
    non-padded input alike, so this repairs '2026-7-2' -> '2026-07-02'.
    """
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


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


# Balance-basis modifiers for /check [date]. Deliberately NOT "open"/"close": both
# resolve to real wallets through fuzzy matching today ("open" -> KZO PEN SETTLE TRC 1
# by contains, "close" -> KZO SETTLE OPS TRC 1 by closest match), so claiming them as
# modifiers would silently take a working filter away.
OPENING_TOKENS = frozenset({"o", "opening"})
CLOSING_TOKENS = frozenset({"c", "closing"})


def extract_mode(tokens):
    """Split balance-basis modifiers out of a token list.

    Returns (mode, rest, conflict):
      mode      "opening" | "closing" | None   -- None means the caller applies its default
      rest      tokens with every modifier removed, original order preserved
      conflict  True when BOTH an opening and a closing modifier were given

    Position-independent, case-insensitive, and repetition-tolerant: [o][o] and
    [o][opening] both mean opening, because repeating yourself is not a contradiction.
    """
    rest, modes = [], set()
    for t in tokens:
        key = t.strip().lower()
        if key in OPENING_TOKENS:
            modes.add("opening")
        elif key in CLOSING_TOKENS:
            modes.add("closing")
        else:
            rest.append(t)
    if len(modes) > 1:
        return None, rest, True
    return (modes.pop() if modes else None), rest, False


# Group families: variant first-tokens that are really ONE group. The roster introduced
# OKKZ1A..5A as a second batch of the OKKZ family, so they belong to group "OKKZ" (matching
# what typing the correct prefix "okkz" returns -- 10 wallets). This is an EXPLICIT list,
# not a string rule: a heuristic like "<code>+digit is the same family" was codex-refuted
# (it would wrongly merge a distinct "S5"+digit group such as S55A into S5). Anything not
# listed here is its own group by first token, so a short code can never swallow a longer
# one (S5 never includes the distinct S5A). Add a line here when a new variant batch ships.
GROUP_FAMILY = {
    "OKKZ1A": "OKKZ", "OKKZ2A": "OKKZ", "OKKZ3A": "OKKZ",
    "OKKZ4A": "OKKZ", "OKKZ5A": "OKKZ",
}


def group_code(wallet_name):
    """The group a wallet belongs to: its first token, folded to the family parent."""
    toks = wallet_name.split()
    if not toks:
        return ""
    return GROUP_FAMILY.get(toks[0], toks[0])


def resolve_group_near_miss(token, wallet_names, floor=0.6, margin=0.15):
    """Resolve a group typo that missed every literal tier (e.g. "okz" -> OKKZ).

    Call this ONLY when resolve_fuzzy fell to the "closest match" tier. It matches the
    token against the GROUP CODES (the distinct group_code values of the wallet names),
    which is far less noisy than matching against whole wallet names.

    Returns (verdict, anchor, wallets):
      "confident", <group code>, <every wallet in that group>   -- one clear winner
      "ambiguous", <sorted list of tied group codes>, []        -- a real tie, refuse
      "none",      None, []                                     -- nothing close; caller falls back

    A wallet-name typo (e.g. "dpy cyo") matches no group code and returns "none", so the
    caller keeps today's single-wallet closest-match behaviour for those.

    Groups are disjoint (each wallet has exactly one group_code), so any rival within
    `margin` of the best score is a genuinely different group and makes the result
    "ambiguous" -- a confident hit is one clear winner, never a guess between groups.
    """
    qn, qs = normalize_name(token), squash_name(token)
    if not qn or not wallet_names:
        return "none", None, []

    anchors = sorted({group_code(n) for n in wallet_names if group_code(n)})

    def ratio(a, b):
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def wscore(name):
        # Head-aware, like resolve_fuzzy: lets a short typo match a long WALLET name.
        cn, cs = normalize_name(name), squash_name(name)
        return max(SequenceMatcher(None, qn, cn).ratio(),
                   SequenceMatcher(None, qn, cn[:len(qn)]).ratio(),
                   SequenceMatcher(None, qs, cs).ratio(),
                   SequenceMatcher(None, qs, cs[:len(qs)]).ratio())

    def expand(code):
        # A wallet is in group `code` iff its group_code equals it. group_code folds a
        # variant first-token (OKKZ1A) to its family parent (OKKZ) via the explicit
        # GROUP_FAMILY map -- so OKKZ = all 10, but S5 never captures the distinct S5A.
        c = code.lower()
        return [n for n in wallet_names if group_code(n).lower() == c]

    scored = sorted(((ratio(qn, a), a) for a in anchors), reverse=True)
    kept = [(s, a) for s, a in scored if s >= floor]
    if not kept:
        return "none", None, []

    best_score, best_anchor = kept[0]

    # A typo of a specific WALLET (e.g. "okz1a" -> the single wallet OKKZ1A) must NOT
    # expand to that wallet's whole group. Only treat the token as a GROUP near-miss when
    # it is at least as close to a group code as to any single wallet name; otherwise
    # defer ("none") to the caller's single-wallet closest-match. (codex: "okz1a" wrongly
    # expanded to the OKKZ group of 10.)
    if best_score < max((wscore(n) for n in wallet_names), default=0.0):
        return "none", None, []
    best_set = set(expand(best_anchor))

    rivals = []
    for s, a in kept[1:]:
        if best_score - s > margin:
            break
        other = set(expand(a))
        if not (other <= best_set or best_set <= other):   # genuinely different result set
            rivals.append(a)

    if rivals:
        return "ambiguous", sorted([best_anchor, *rivals]), []
    return "confident", best_anchor, expand(best_anchor)

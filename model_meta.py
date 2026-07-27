"""model_meta.py — read model.py's era constants WITHOUT importing model.py.

v8.5. grade.py and stats.py need MODEL_VERSION and LAMBDA to stamp and segment
archive rows. `import model` would pull in fg_client -> curl_cffi, putting the
Cloudflare HTTP client on the critical path of the grade job, which today needs
only `requests`. A failed import there costs a morning's shadow rows, and those
are not recoverable. So: parse the module's source with `ast` instead. Stdlib
only, no execution of model.py, no side effects.

model.py remains the single source of truth. This file only reads it.

On failure it returns UNRESOLVED rather than raising or guessing. A row stamped
'unresolved' is honest and greppable; a row silently defaulted to the current
era is the exact failure this whole change exists to prevent.
"""
import ast
import os

MODEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.py')
UNRESOLVED = 'unresolved'


def _constants(path=MODEL_FILE):
    """Module-level literal assignments in model.py, by name."""
    out = {}
    try:
        tree = ast.parse(open(path).read())
    except Exception:
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                out[t.id] = value
    return out


def model_version(path=MODEL_FILE):
    v = _constants(path).get('MODEL_VERSION')
    return v if isinstance(v, str) and v else UNRESOLVED


def lam(path=MODEL_FILE):
    """LAMBDA in force. None (not 0.0) when it cannot be read -- 0.0 is a real
    value with a real meaning here and must never be a fallback."""
    v = _constants(path).get('LAMBDA')
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


_MISSING = object()  # None is a MEANINGFUL lambda value (unreadable), not "not supplied"


def era_key(version=_MISSING, lmb=_MISSING):
    """Segmentation key. The PAIR, not the version alone: if LAMBDA ever moves
    without a version bump, version-only segmentation would silently merge two
    different models -- the same hole in a new place."""
    v = model_version() if version is _MISSING else version
    l = lam() if lmb is _MISSING else lmb
    return f"{v or UNRESOLVED}@lambda={'null' if l is None else l}"


if __name__ == '__main__':
    print(f"MODEL_VERSION={model_version()}  LAMBDA={lam()}  era_key={era_key()}")

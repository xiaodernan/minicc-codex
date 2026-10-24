"""The one spelling of the key-material suffix tuple.

A file carrying one of these suffixes is a secret whatever its basename
says.  Three surfaces used to spell the tuple by hand, and they had already
drifted: the file tools knew four, the indexer five (it had learned
``.kdbx``), and the verification walk carried an inline two - so a ``.p12``
certificate the tools refuse to read still counted as a *clean* input for
cache reuse.  One tuple, in a leaf module the ``agent`` and ``tools``
readers can both import; the union is the direction that fails safe.
"""

from __future__ import annotations

#: Suffixes that are key material in their own right.  A tuple, not a set:
#: the file tools hand it to ``str.endswith``, the other two test membership.
KEY_MATERIAL_SUFFIXES: tuple[str, ...] = (".pem", ".key", ".p12", ".pfx", ".kdbx")

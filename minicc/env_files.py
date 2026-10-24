"""The one spelling of the env-file family: ``.env`` and ``.env.<profile>``.

Three surfaces ask "is this name an env file?" and each used to answer by
hand: the indexer keeps them out of the evidence set, the file tools refuse
to read them, and the verification walk refuses to reuse a cached pass when
one is present.  The three *policies* differ on purpose - the tools may read
``.env.example``, the other two may not treat it as exempt - but the family
shape itself is one fact, and a family that gains a member must gain it in
all three places at once.  A leaf module is the only home it can have: the
readers sit in ``agent`` and ``tools``, which the tools layer cannot import
back from.

Not the config source: ``load_config`` reads a literal ``.env`` from the cwd
as a configuration layer, which is a different fact and keeps its own
spelling.
"""

from __future__ import annotations

#: The env file itself.
ENV_FILENAME = ".env"
#: The profile-variant prefix: ``.env.local``, ``.env.production``, ...
ENV_FAMILY_PREFIX = ".env."


def is_env_filename(name: str) -> bool:
    """``.env`` itself, or a ``.env.<profile>`` variant of it."""
    return name == ENV_FILENAME or name.startswith(ENV_FAMILY_PREFIX)

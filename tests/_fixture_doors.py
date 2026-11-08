"""The three fixture doors, in one place.

Every gate in the fixture-honesty family parametrizes over the same three
corpora: the shipped v2 corpus, the behavior corpus, and the legacy corpus.
The tuple was spelled by hand in three test modules; a new door or a rename
to one door moved it everywhere, but three copies at three sites meant drift
was silent. This file is the one home; importers ask it.
"""

DOORS = ("v2", "behavior", "legacy")

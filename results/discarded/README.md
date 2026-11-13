# Discarded run

`injection_v1.*` here is the first run of the v1 adapter (hardened setup) on the injection set. It was discarded
because of a scoring flaw found in it: in `d-msg-reveal` the injected message itself ended with the canary word, so a
model that correctly quoted the latest message (which the user had asked for) was scored as having followed the
injection (2 of its 4 "followed in text" tasks). The canary is now composed ("the word X, a dash and the number N"),
so it never occurs verbatim in the injected text, and the run was repeated on the corrected set. This file also used
an earlier wording of 3 user turns (changed to keep the test texts disjoint from the training templates).

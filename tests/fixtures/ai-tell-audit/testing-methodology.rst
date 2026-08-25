=========================
How the Library Is Tested
=========================

This page records what the tests do today. It is rewritten whenever the tests change,
and it makes no promise about releases that have already shipped.

Three separate harnesses
------------------------

Testing is done by three separate programs. The TCL test harness links against the
library and drives it through the TCL bindings. A second test harness is a set of C
programs that call the public API directly, because the TCL test harness cannot reach
code paths that only a C caller reaches. The third test harness replays a recorded
byte stream against a simulated storage layer.

Each test harness reports failures in the same format: a file, a line, and the name of
the test case. The first field of that report names a script in the ``test/`` directory,
so a failure can be reproduced without reading any of the harness sources.

Coverage of the simulated storage layer
---------------------------------------

The simulated layer can fail any read or any write on demand. It can also report that
the entire filesystem has been mounted read-only, that the entire filesystem is out of
space, or that a power loss occurred between two writes. Faults of that kind are hard to
produce on a running machine, so the test harness produces them instead.

The C test harness is strict when it comes to memory: every allocation is counted, and a
test that exits with a nonzero balance fails even if it produced the right answer. The
same test harness is strict about file descriptors for the same reason.

Claims we make and claims we do not
-----------------------------------

The parser is robust against malicious attack. That is a stronger claim than robust in
normal use, and it is the claim the fuzz test harness exists to check: the fuzzer feeds
the parser byte strings that no client would ever send, and every crash is a defect
whether or not any client could provoke it.

We do not claim that the library is free of defects. We claim that the test harness
covers every branch reachable from the public API, that the coverage number is measured
on each release, and that a patch which lowers it is rejected.

Running the tests yourself
--------------------------

Build the test harness with ``make test``. On a machine with 8 cores the full run takes
about forty minutes; the shorter ``make quicktest`` target runs the same test harness
with the slow fault-injection cases skipped, and finishes in about two minutes.

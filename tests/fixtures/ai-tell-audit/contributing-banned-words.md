# Contributing

## House style

We keep a short list of words and phrases the docs must not use. The list exists because
these constructions arrive by habit and nobody notices them in review. If you catch one
in a draft, rewrite the sentence.

Do not use, in any documentation page:

- delve
- leverage, as a verb
- seamless
- robust
- comprehensive
- at the end of the day
- load-bearing
- it is worth noting that
- not just X but Y
- Here's the thing:
- Let that sink in.
- underscoring the importance of

## An example of what we mean

A draft submitted last month opened like this:

> At its core, this release is not just robust but seamless. Here's the thing: at the end
> of the day, the entire migration is load-bearing, and it is worth noting that the new
> scheduler quietly underscores the importance of the work. Let that sink in.

The rewrite that landed says what changed:

The scheduler now retries a failed job three times before it gives up. Jobs that used to
be dropped on a transient network error are now retried.

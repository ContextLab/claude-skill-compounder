Concession and Rebuttal
=======================

Verbatim passages from Linux ``Documentation/process/coding-style.rst`` at tag v5.15,
written by human kernel maintainers over two decades. Every paragraph below opens by
stating a belief the reader may carry, then rebuts it with a specific reason.

An earlier version of this skill read all five as "unnamed opposition" and ordered them
deleted, under a row whose section said "Softening does not fix these, so they delete."
Seven surviving instances against a floor of three. This fixture exists so that never
happens again.

Passage at coding-style.rst line 31
----------------------------------

Now, some people will claim that having 8-character indentations makes
the code move too far to the right, and makes it hard to read on a
80-character terminal screen.  The answer to that is that if you need
more than 3 levels of indentation, you're screwed anyway, and should fix
your program.

Passage at coding-style.rst line 379
----------------------------------

Lots of people think that typedefs ``help readability``. Not so. They are
useful only for:

Passage at coding-style.rst line 618
----------------------------------

That's OK, we all do.  You've probably been told by your long-time Unix
user helper that ``GNU emacs`` automatically formats the C sources for
you, and you've noticed that yes, it does do that, but the defaults it
uses are less than desirable (in fact, they are worse than random
typing - an infinite number of monkeys typing into GNU emacs would never
make a good program).

Passage at coding-style.rst line 926
----------------------------------

There appears to be a common misperception that gcc has a magic "make me
faster" speedup option called ``inline``. While the use of inlines can be
appropriate (for example as a means of replacing macros, see Chapter 12), it
very often is not. Abundant use of the inline keyword leads to a much bigger
kernel, which in turn slows the system as a whole down, due to a bigger
icache footprint for the CPU and simply because there is less memory
available for the pagecache. Just think about it; a pagecache miss causes a

Passage at coding-style.rst line 943
----------------------------------

Often people argue that adding inline to functions that are static and used
only once is always a win since there is no space tradeoff. While this is
technically correct, gcc is capable of inlining these automatically without
help, and the maintenance issue of removing the inline when a second user
appears outweighs the potential value of the hint that tells gcc to do
something it would have done anyway.


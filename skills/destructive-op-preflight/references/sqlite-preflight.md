# SQLite preflight

SQLite is here because it is the one datastore whose procedure was executed end to end on
a real database, including its failure cases. **No other engine appears in this skill.**
Postgres, MySQL, Prisma, Rails, Alembic and Django advice was drafted and then cut: none of
it could be run on the authoring machine, and unverified instructions about wiping a
production database are worse than none. If you are about to destroy data in one of those,
the shape below still applies (census the source, restore into an empty scratch, compare,
only then destroy), but check every flag against that tool's own `--help` first.

## Step 0: which file is this, actually

A file-backed database makes "which database am I on" a path question, and it has the same
answer: resolve it, do not assume it.

```bash
realpath "${SQLITE_PATH:?set SQLITE_PATH}"
ls -l "$(realpath "$SQLITE_PATH")"
```

`realpath` matters because a relative path plus a working directory that moved between tool
calls is how the wrong database gets opened. The `:?` turns an unset variable into an error
instead of an empty string, the same defense the main skill applies to `rm -rf "${VAR}/build"`.

## The census, not a row count

A single `select count(*) from users` is not proof of a good backup. It misses every other
table, and when the query itself fails the count comes back as the empty string, which
compares equal to another empty string and reads as success.

```bash
census() {
  db="$1"
  sqlite3 -bail -noheader "$db" \
    "select 'select '''||name||':''||count(*) from '||quote(name)||';'
       from sqlite_master where type='table' and name not like 'sqlite_%';" \
    > "$db.census.sql" || return 1
  sqlite3 -bail -noheader "$db" < "$db.census.sql" || return 1
}
```

That prints one `table:rowcount` line per table. Verified against a two-table database.

## The full procedure

```bash
sqlite3 "$SQLITE_PATH" ".backup ${TMPDIR:-/tmp}/preflight.db"   # consistent under writers
sqlite3 "$SQLITE_PATH" ".dump" > "${TMPDIR:-/tmp}/preflight.sql"
SRC=$(census "$SQLITE_PATH" | sort)
SCRATCH="${TMPDIR:-/tmp}/restore_check.db"
test ! -e "$SCRATCH" || { echo "scratch db exists; refusing"; exit 1; }
sqlite3 -bail "$SCRATCH" < "${TMPDIR:-/tmp}/preflight.sql"
DST=$(census "$SCRATCH" | sort)
test -n "$SRC" || { echo "source census empty; the check proved nothing"; exit 1; }
test -n "$DST" || { echo "restored census empty; the check proved nothing"; exit 1; }
test "$SRC" = "$DST" || { echo "restore does not match the source"; exit 1; }
rm -f "$SCRATCH"
```

Five details, each of which was a real false proof in review:

- **Both censuses must be non-empty.** `sqlite3` writes errors to stderr and nothing to
  stdout, so a zero-byte dump gives `SRC=""` and `DST=""`, and `"" = ""` passes. Verified:
  without the non-empty test, an empty dump reports a successful verification.
- **Census every table.** A `.dump users` backs up one table; comparing only `users` then
  passes while `accounts` has no backup at all. Verified: the census catches it, a single
  count does not.
- **The scratch database must not already exist.** Restoring a `.dump` into a non-empty
  database fails on `CREATE TABLE ... already exists` but keeps running the `INSERT`s, so
  the table ends up with the original rows plus a duplicate set. A source of 2 produced a
  scratch count of **6** across repeated runs.
- **Use `-bail`.** Without it `sqlite3` continues past the parse error, and the exit status
  on error differs between builds (1 here, 0 on the reviewer's), so the exit code alone is
  not sound. The census comparison is what makes it sound.
- **Delete the scratch database afterwards**, or the next run inherits the false proof.

## When there is no backup path

If you cannot take a dump (no credentials, no disk, an export locked behind a console),
that is not a reason to proceed carefully. It is the stop condition. Say which table is at
risk and ask.

# Datastore preflight

Load this before a database reset, drop, truncate, or migration rollback. The rule is one
sentence: **prove the backup restores into an empty scratch database with the same row
count as the source, before touching the real one.** A dump nobody has restored is a file,
not a backup, and a restore into a scratch database that already has rows can report a
plausible count while having applied nothing.

## Verification status of the commands below

This repository treats an unverified claim in a skill as a defect, so each section says
which it is. Only the SQLite path could be executed on the machine this reference was
written on; `psql`, `pg_dump`, `mysql`, `mysqldump`, `prisma`, `rails`, `alembic` and
`django-admin` are not installed there.

|Section|Status|
|-|-|
|Step 0, connection identity|VERIFIED for the shell mechanics, not against a live server|
|SQLite|VERIFIED end to end, including the false-proof case|
|Postgres|NOT VERIFIED here; transcribed from the documented interfaces|
|MySQL|NOT VERIFIED here|
|Prisma|NOT VERIFIED here; the `--force-reset` behavior is from issue #36183|
|Rails|NOT VERIFIED here|
|Alembic|NOT VERIFIED here|
|Django|NOT VERIFIED here|

Treat a NOT VERIFIED block as a prompt to check `--help` on the machine you are actually
on, before you rely on any flag in it. The *procedure* (dump, restore into an empty
scratch, compare counts, only then destroy) holds regardless of engine; the exact flags
are what needs confirming.

## Step 0: which database is this, actually

Every wipe in the evidence corpus started with the operator being certain they were on
dev. Resolve the connection string to a host and a database name and print it, before
anything else.

```bash
echo "${DATABASE_URL:-<unset>}" | sed -E 's#(://[^:]+:)[^@]+@#\1***@#'
```

Redact the password when you print it. If the host is not obviously local
(`localhost`, `127.0.0.1`, a container name you started), treat it as production until
proven otherwise. If the environment resolves at runtime (a `.env` per stage, a CI secret,
a pooler URL that fronts several databases), you cannot tell from the string alone: query
the server for its own name instead, and stop if you cannot.

For a file-backed database the same question is a path question, and it has the same
answer: resolve it, do not assume it.

```bash
realpath "${SQLITE_PATH:?set SQLITE_PATH}"
ls -l "$(realpath "$SQLITE_PATH")"
```

`realpath` matters because a relative path plus a working directory that moved between
tool calls is how the wrong database gets opened. The `:?` makes an unset variable an
error rather than an empty string, which is the same defense the main skill applies to
`rm -rf "${VAR}/build"`.

## SQLite

VERIFIED end to end. The false proof below was reproduced.

```bash
sqlite3 "$SQLITE_PATH" ".backup /tmp/preflight-<stamp>.db"     # consistent under writers
sqlite3 "$SQLITE_PATH" ".dump" > /tmp/preflight-<stamp>.sql    # portable text alternative
SRC=$(sqlite3 "$SQLITE_PATH" 'select count(*) from users;')
test ! -e /tmp/restore_check.db || { echo "scratch db exists; refusing"; exit 1; }
sqlite3 -bail /tmp/restore_check.db < /tmp/preflight-<stamp>.sql
DST=$(sqlite3 /tmp/restore_check.db 'select count(*) from users;')
test "$SRC" = "$DST" || { echo "restore proved nothing: $SRC != $DST"; exit 1; }
rm -f /tmp/restore_check.db
```

Four details, each of which was a real failure in review:

- **The scratch database must not already exist.** Restoring a `.dump` into a non-empty
  database fails on `CREATE TABLE ... already exists` but keeps executing the `INSERT`
  statements. The table then holds the original rows plus a duplicate set: a source count
  of 2 produced a scratch count of **6** across repeated runs. A count that is merely
  non-zero is not proof of anything, which is why the check compares it to the source.
- **Use `-bail`.** Without it `sqlite3` continues past the parse error. Exit status on the
  error differs across builds (one build here returned 1, the reviewer's returned 0), so
  do not lean on the exit code alone; the count comparison is what makes it sound.
- **`.backup`, not `cp`.** Copying the file while a writer holds it can capture a torn
  page. `.backup` takes a consistent snapshot.
- **Clean up the scratch database**, or the next run inherits the false proof above.

## Postgres

NOT VERIFIED here (`pg_dump` and `psql` are not installed on the authoring machine).

```bash
pg_dump --format=custom --file=/tmp/preflight-<stamp>.dump "$DATABASE_URL"
createdb restore_check              # must not already exist, for the reason SQLite shows
pg_restore --dbname=restore_check /tmp/preflight-<stamp>.dump
psql restore_check -c 'select count(*) from <the table you care about>;'
dropdb restore_check
```

Compare that count against the same query on the source. A `pg_restore` against an empty
dump also exits 0, so the exit status is not the proof; the matching count is.

## MySQL

NOT VERIFIED here (`mysql` and `mysqldump` are not installed on the authoring machine).

```bash
mysqldump --single-transaction --routines --databases app > /tmp/preflight-<stamp>.sql
mysql -e 'create database restore_check'
mysql restore_check < /tmp/preflight-<stamp>.sql
mysql restore_check -e 'select count(*) from <table>'
mysql -e 'drop database restore_check'
```

## Prisma

NOT VERIFIED here (`prisma` is not installed on the authoring machine). The behavior of
`--force-reset` is taken from anthropics/claude-code#36183, where it wiped production.

`prisma db push --force-reset` **drops and recreates the database**, and in that report it
was reached by escalating past a warning.

|Want|Use|Never|
|-|-|-|
|Apply a schema change that loses data, knowingly|`prisma db push --accept-data-loss`|`--force-reset`|
|Reset a scratch dev database|`prisma migrate reset` on a URL you have proven is local|`--force-reset` against `$DATABASE_URL`|
|Generate a migration|`prisma migrate dev --create-only`, then read the SQL|running it unread|

Read the generated SQL before it runs. A generated migration containing `DROP COLUMN` or
`DROP TABLE` needs a data-migration step written by hand first (#63763).

## Rails

NOT VERIFIED here (no Rails application on the authoring machine).

```bash
bin/rails db:migrate:status                    # confirm which migration is pending
```

`db:reset`, `db:drop`, and `db:schema:load` all destroy data. `db:rollback` runs the
`down` method, and a `down` that drops a column loses that column's data with no warning.
Read the `down` before invoking it.

## Alembic

NOT VERIFIED here (`alembic` is not installed on the authoring machine).

```bash
alembic current
alembic history --verbose | head -20
alembic downgrade -1 --sql         # render the SQL without executing it
```

`--sql` is the offline-mode render. Read it. If the rendered downgrade contains `DROP`,
the data in that column is gone the moment it runs.

## Django

NOT VERIFIED here (no Django project on the authoring machine).

```bash
python manage.py showmigrations
python manage.py sqlmigrate <app> <number>     # render, do not run
python manage.py migrate <app> <previous>      # the rollback
```

`python manage.py flush` truncates every table. `migrate <app> zero` unapplies everything
for that app.

## When there is no backup path

If the datastore has no dump you can take (no credentials, a managed service with the
export behind a console, a disk with no room), that is not a reason to proceed carefully.
It is the stop condition. Say which table is at risk and ask.

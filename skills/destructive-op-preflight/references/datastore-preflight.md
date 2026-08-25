# Datastore preflight

Load this before a database reset, drop, truncate, or migration rollback. The rule is one
sentence: **prove the backup exists and prove it restores, into a scratch database, before
touching the real one.** A dump file nobody has restored is a file, not a backup.

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

## Postgres

```bash
pg_dump --format=custom --file=/tmp/preflight-$(date +%Y%m%d-%H%M%S).dump "$DATABASE_URL"
createdb restore_check
pg_restore --dbname=restore_check /tmp/preflight-<stamp>.dump
psql restore_check -c '\dt'
psql restore_check -c 'select count(*) from <the table you care about>;'
dropdb restore_check
```

The row count is the proof. A `pg_restore` that exits 0 against an empty dump also exits 0.

## MySQL

```bash
mysqldump --single-transaction --routines --databases app > /tmp/preflight-<stamp>.sql
mysql -e 'create database restore_check'
mysql restore_check < /tmp/preflight-<stamp>.sql
mysql restore_check -e 'select count(*) from <table>'
mysql -e 'drop database restore_check'
```

## SQLite

Verified on sqlite3 as shipped with macOS Python tooling:

```bash
sqlite3 app.db ".backup /tmp/preflight-<stamp>.db"     # consistent even under writers
sqlite3 app.db ".dump" > /tmp/preflight-<stamp>.sql    # portable text alternative
sqlite3 /tmp/restore_check.db < /tmp/preflight-<stamp>.sql
sqlite3 /tmp/restore_check.db "select count(*) from <table>;"
sqlite3 /tmp/preflight-<stamp>.db "PRAGMA integrity_check;"
```

`cp app.db backup.db` while a writer holds the database can copy a torn page. Use
`.backup`.

## Prisma

`prisma db push --force-reset` **drops and recreates the database.** This is the command
from #36183 that wiped production, and it was reached by escalating from a warning.

|Want|Use|Never|
|-|-|-|
|Apply a schema change that loses data, knowingly|`prisma db push --accept-data-loss`|`--force-reset`|
|Reset a scratch dev database|`prisma migrate reset` on a URL you have proven is local|`--force-reset` against `$DATABASE_URL`|
|Generate a migration|`prisma migrate dev --create-only`, then read the SQL|running it unread|

Read the generated SQL before it runs. A generated migration that contains `DROP COLUMN`
or `DROP TABLE` needs a data-migration step written by hand first (#63763).

## Rails

```bash
bin/rails db:migrate:status                    # confirm which migration is pending
bin/rails db:rollback STEP=1 --dry-run 2>/dev/null || true
```

`db:reset`, `db:drop`, and `db:schema:load` all destroy data. `db:rollback` runs the
`down` method, and a `down` that drops a column loses that column's data with no warning.
Read the `down` before invoking it.

## Alembic

```bash
alembic current
alembic history --verbose | head -20
alembic upgrade <rev> --sql        # render the SQL without executing it
alembic downgrade -1 --sql         # same, for the rollback
```

`--sql` is the offline-mode render. Read it. If the rendered downgrade contains `DROP`,
the data in that column is gone the moment it runs.

## Django

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

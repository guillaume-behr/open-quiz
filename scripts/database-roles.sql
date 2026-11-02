-- Give the API its own unprivileged PostgreSQL role.
--
-- Run as the superuser over the database container's local socket, by
-- configure_database_roles in scripts/common.sh, on every update and after
-- every restore. Running it again changes nothing that is already right.
--
-- The superuser (open_quiz) stays for backups, restores and this script.
-- The API connects as open_quiz_app: it owns the open_quiz database and every
-- object in it, so migrations still run, but it has no superuser power. A SQL
-- injection could then not read server files or the container's environment,
-- nor run programs (COPY ... TO PROGRAM).
--
-- Expects :app_password, set by the caller.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE open_quiz_app'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'open_quiz_app')
\gexec

ALTER ROLE open_quiz_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    NOREPLICATION NOBYPASSRLS INHERIT CONNECTION LIMIT -1
    PASSWORD :'app_password';

-- Owning the database makes the role the owner of the public schema too
-- (pg_database_owner), so it may create the tables of new migrations.
ALTER DATABASE open_quiz OWNER TO open_quiz_app;

-- Existing installations and restores (pg_restore --no-owner) leave objects
-- owned by the superuser: hand them over. Indexes and sequences that belong
-- to a table follow their table.
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT c.oid::regclass AS name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
            AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
            AND c.relowner <> 'open_quiz_app'::regrole
    LOOP
        EXECUTE format('ALTER TABLE %s OWNER TO open_quiz_app', item.name);
    END LOOP;

    FOR item IN
        SELECT c.oid::regclass AS name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
            AND c.relkind = 'S'
            AND c.relowner <> 'open_quiz_app'::regrole
            AND NOT EXISTS (
                SELECT FROM pg_depend d
                WHERE d.objid = c.oid
                    AND d.classid = 'pg_class'::regclass
                    AND d.deptype IN ('a', 'i')
            )
    LOOP
        EXECUTE format('ALTER SEQUENCE %s OWNER TO open_quiz_app', item.name);
    END LOOP;

    FOR item IN
        SELECT t.oid::regtype AS name
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'public'
            AND t.typtype IN ('e', 'd', 'r')
            AND t.typowner <> 'open_quiz_app'::regrole
    LOOP
        EXECUTE format('ALTER TYPE %s OWNER TO open_quiz_app', item.name);
    END LOOP;

    FOR item IN
        SELECT p.oid::regprocedure AS name
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
            AND p.proowner <> 'open_quiz_app'::regrole
    LOOP
        EXECUTE format('ALTER ROUTINE %s OWNER TO open_quiz_app', item.name);
    END LOOP;
END
$$;

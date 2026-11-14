-- Operator-only, additive database role authorization for AyahOS Ruby workflow queue.
-- NOT an automatic application schema migration. Does not set a password.
-- Apply only after an isolated PostgreSQL restore and row-checksum comparison.
-- Role remains NOLOGIN until a host-owned 256-bit credential is provisioned using SCRAM.
BEGIN;
DO $role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ayahos_workflow_20261027') THEN
        CREATE ROLE ayahos_workflow_20261027 NOLOGIN NOINHERIT
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END $role$;

GRANT CONNECT ON DATABASE postgres TO ayahos_workflow_20261027;
GRANT USAGE ON SCHEMA public TO ayahos_workflow_20261027;
GRANT SELECT, INSERT, UPDATE ON public.ruby_workflow_jobs TO ayahos_workflow_20261027;
GRANT SELECT, INSERT ON public.ruby_workflow_job_audit TO ayahos_workflow_20261027;
GRANT USAGE, SELECT ON SEQUENCE public.ruby_workflow_job_audit_audit_id_seq
    TO ayahos_workflow_20261027;

DO $policies$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public'
                   AND tablename = 'ruby_workflow_jobs'
                   AND policyname = 'ayahos_workflow_runner_jobs_rw') THEN
        CREATE POLICY ayahos_workflow_runner_jobs_rw ON public.ruby_workflow_jobs
            FOR ALL TO ayahos_workflow_20261027 USING (true) WITH CHECK (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public'
                   AND tablename = 'ruby_workflow_job_audit'
                   AND policyname = 'ayahos_workflow_runner_audit_select') THEN
        CREATE POLICY ayahos_workflow_runner_audit_select ON public.ruby_workflow_job_audit
            FOR SELECT TO ayahos_workflow_20261027 USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = 'public'
                   AND tablename = 'ruby_workflow_job_audit'
                   AND policyname = 'ayahos_workflow_runner_audit_insert') THEN
        CREATE POLICY ayahos_workflow_runner_audit_insert ON public.ruby_workflow_job_audit
            FOR INSERT TO ayahos_workflow_20261027 WITH CHECK (true);
    END IF;
END $policies$;
COMMIT;

-- Read-only verification after applying:
-- SELECT rolname, rolcanlogin, rolbypassrls FROM pg_roles WHERE rolname='ayahos_workflow_20261027';
-- SELECT has_table_privilege('ayahos_workflow_20261027', 'public.ruby_workflow_jobs','SELECT,INSERT,UPDATE');
-- SELECT has_table_privilege('ayahos_workflow_20261027', 'public.ruby_workflow_job_audit','SELECT,INSERT');

-- Run ONLY on isolated restored PostgreSQL test database, never production.
BEGIN;
SET LOCAL ROLE ayahos_workflow_20261027;
SELECT current_user AS tested_role;
SELECT count(*) AS visible_jobs FROM public.ruby_workflow_jobs;
SELECT count(*) AS visible_audit FROM public.ruby_workflow_job_audit;
UPDATE public.ruby_workflow_jobs SET status=status WHERE false;
INSERT INTO public.ruby_workflow_job_audit (job_id,action,operator_id,reason,data)
SELECT id, 'permission_probe', 'isolated-test', 'rolled-back', '{}'::jsonb
FROM public.ruby_workflow_jobs LIMIT 1;
ROLLBACK;
SELECT rolname,rolcanlogin,rolbypassrls FROM pg_roles WHERE rolname='ayahos_workflow_20261027';

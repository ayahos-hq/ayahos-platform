# Operator auth recovery with existing Supabase project

Use existing Supabase free-tier project xgomhbuzawoqnwlzvavx. The official
Next.js @supabase/ssr cookie pattern is used, not a second database.
Do not use a service_role key.

## Release gates

Default: AYAHOS_ADMIN_AUTH_PROVIDER=google. Supabase implementation remains
dormant until the ADMIN Render site explicitly opts in. Enrollment alone is not
authentication. AYAHOS_ADMIN_AUTH_ENFORCED=true is the independent activation
gate, to be enabled only after verified live sign-in.

The isolated /operator-login flow requests passwordless link for enrolled
email addresses. The callback exchanges the PKCE code, authenticates against
Supabase Auth via getUser, and grants access only to a stable user ID, confirmed
email and exact server-side allowlist match. Admin pages and APIs use their
original server guard and CSRF/origin checks. No user-editable metadata grants
privileges.

## Activation prerequisites

1. In Supabase Auth URL Configuration for the EXISTING project, configure
   https://goblin-dual-lineage-web-live.onrender.com/api/operator-auth/callback
   as an allowed redirect. Set the matching site URL.
2. Prove outbound email to both approved accounts. Default free Supabase SMTP
   only sends to project team members; custom SMTP is required for other
   recipients. Do not claim delivery without a live test.
3. On admin Render service only set AYAHOS_SUPABASE_URL to
   https://xgomhbuzawoqnwlzvavx.supabase.co and install the project's
   public publishable key as AYAHOS_SUPABASE_PUBLISHABLE_KEY. Never use a
   secret/service_role key for user session cookies.
4. Set AYAHOS_ADMIN_AUTH_PROVIDER=supabase with authentication enforcement
   initially false. Verify real magic link -> callback -> getUser, both
   approved accounts, and rejection of an unlisted account.
5. Activate AYAHOS_ADMIN_AUTH_ENFORCED=true only after the above proofs,
   and reverify private admin pages, APIs and public customer chats.

Rollback: set AYAHOS_ADMIN_AUTH_PROVIDER=google and
AYAHOS_ADMIN_AUTH_ENFORCED=false on admin web only. No schema or chat change.
After successful production cutover, remove unused Google Auth.js code in
a follow-up cleanup to avoid dual-provider maintenance debt.
## Session-carrying redirects and email proof (2026-10-24)

Critical fix after the initial PR: Route handlers now use an explicit
routeSupabaseClient() cookie adapter. The sign-in redirect carries the
PKCE verifier cookie; the callback's 303 carries refreshed Supabase auth
cookies; the sign-out redirect clears them. Tests verify the actual
Set-Cookie values and make sure authentication codes never appear in
redirect Location headers. The app deliberately sets
shouldCreateUser=false: the only two approved users were enrolled and
their email addresses confirmed in Supabase already.

Evidence: Supabase's own default sender delivered one signup email to
each account; both accounts have email_confirmed=true. This establishes
working test email delivery, not Gmail sender configuration and not
completed operator session verification. The default SMTP service's
low rate limit means this should not be treated as production-ready.
A custom SMTP sender is still required before final production cutover.
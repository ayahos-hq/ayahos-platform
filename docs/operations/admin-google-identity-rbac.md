# AyahOS human administrator identities and rollout

## Documentation checkpoint — 2026-10-25 — operator login is not verified live

This file records the **Google Auth.js** design and its security controls, **not** a verified successful production Google login. The [open PR #414](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/pull/414) records a Google OAuth `invalid_client` / 401 blocker and proposes an *additional*, off-by-default **Supabase magic-link** trust path using an existing project. The PR is **not merged into `main`**. The Supabase path requires its own provider-selection gate, `AYAHOS_ADMIN_AUTH_ENFORCED` gate, strict two-user allowlist, verified email and user ID, PKCE exchange, origin/CSRF controls, and real positive/negative session tests. Its included test/build report and preview do not prove delivery to both allowed addresses or a live admin session.

Do not turn off authentication checks merely to make the admin UI reachable; keep machine/operator runtime keys independent of human admin sessions. Do not describe either Google or Supabase operator sign-in as live-functional until verified against the named environment, commit and date. Follow the open PR's additional `docs/operations/operator-supabase-auth.md` only **on that branch** while unmerged.


## Scope and status

Two human identities are enrolled for the AyahOS administrator role on the
separate Render operator web application:

- fuaadabdullah@gmail.com = admin
- AyahOS.dev@gmail.com = admin (case-insensitive normalization)

Both must actually sign in to Google; listing an address is NOT proof of
ownership and does not create a valid session. Authorization remains staged
until Google OAuth credentials are configured and AYAHOS_ADMIN_AUTH_ENFORCED=true.
This is not a deploy-time account creation or an active session grant.

Vercel team ownership and Render workspace membership are managed by those
platforms separately. This change grants neither provider-level privileges
nor any model inference or compute secrets.

## Architecture

- Auth.js handles Google OIDC authorization-code flow, provider validation,
  session lifecycle and short-lived encrypted/signed JWT cookies.
- Successful sign-in requires provider=google, email_verified=true, nonempty
  Google subject and exact allowlist membership.
- The server rechecks the enrolled list on every protected request, so removing
  an address revokes subsequent page/API access without waiting for expiry.
- Customer deployments remain unchanged and public /api/build remains reachable.
- Operator /control and /nodes pages and all 18 admin API handlers require
  authenticated administrators when the rollout gate is enabled.
- Machine-level runtime, review and node-operator credentials remain distinct.
  A human admin session does not itself grant those backend scopes.
- The role permissions matrix defines owner/admin/operator/viewer/customer;
  admins cannot grant owner status. No public role-changing API is provided.
- Denied requests log request paths and method, never tokens or credentials.

## Activation

1. In the AyahOS Google Cloud project, configure Google OAuth consent and
   create a Web application OAuth client.
2. Register this exact callback:
   https://goblin-dual-lineage-web-live.onrender.com/api/auth/callback/google
   and site origin https://goblin-dual-lineage-web-live.onrender.com.
3. Configure protected AUTH_GOOGLE_ID, AUTH_GOOGLE_SECRET, and random
   AUTH_SECRET of at least 32 bytes on Render operator service
   goblin-dual-lineage-web-live. Do not commit or log secret values.
4. Prove both enrolled Google accounts complete sign-in and acquire admin
   sessions. Prove an unlisted/unverified account and anonymous browser fail.
5. Set AYAHOS_ADMIN_AUTH_ENFORCED=true only after those prerequisites.
   Verify /control, /nodes and admin API requests deny anonymous traffic and
   /api/build stays healthy.
6. Roll back authentication enforcement by reverting the flag if needed;
   runtime and site routing secrets do not need changes.

## Constraints and next steps

No email header or public chat API token authorizes a human admin session.
Provider account ownership does not automatically imply application admin.
Existing control mutations still require separate operator policy authorization.
Do not add a paid authentication provider or database solely for these two
identities. Persistent revocation, roles for larger teams and a durable
audit store can be added later with migration and approval gates.
## Security gates

When enabled, all operator API writes require the exact configured
AYAHOS_ADMIN_PUBLIC_ORIGIN in the Origin header and an acceptable
Sec-Fetch-Site header. Browser cookies alone do not authorize a cross-origin
PATCH/POST/DELETE. A forged or missing Origin is denied. Admin API responses
are marked private and no-store, and the privileged pages render dynamically.
The only public operator endpoint is GET /api/build: inspected to return only
the build commit SHA, without forwarding credentials or triggering actions.
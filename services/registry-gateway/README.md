# AyahOS registry gateway (staged, fail closed)

Thin Node.js function for **read-only** Google Agent Registry POST `agents:search`. No model inference, publishing, agent invocation or service-account keys. This lives in a separate Vercel project, not the existing AyahOS frontend.

## Identity and deployment

Vercel project: `ayahos-registry-gateway`, team `fuaadabdullahs-projects`, production only. Google WIF pool: `ayahos-vercel`, OIDC provider: `gateway-production`. The WIF condition MUST be exactly `assertion.sub == 'owner:fuaadabdullahs-projects:project:ayahos-registry-gateway:environment:production'`. The provider UI previously stored a malformed subject; **do not grant impersonation or activate the gateway until corrected and read-back verified**.

Grant only `roles/iam.workloadIdentityUser` on the existing service account `ayahos-registry-reader@project-eec9b975-b6bd-4b41-bad.iam.gserviceaccount.com` to the exact WIF subject principal; the service account has only `roles/agentregistry.viewer` on the project.

A random long bearer secret `AYAHOS_REGISTRY_GATEWAY_KEY` must be injected into both Vercel and Render protected environment stores, never committed. In Render use auth mode `token`, base URL of the dedicated gateway, project and global location, and protected gateway bearer as registry token. **Do not enable discovery until Google OIDC read-only search succeeds live**. Publishing/routing/execution must remain disabled.

## Tests

Run `npm test` within this directory. Gate production changes through Octopus. Manual deployment requires independent credential checks and versioned deployment evidence. Do not enable GitHub Actions.

## Constraints

Vercel Hobby is restricted to personal non-commercial use, so use this project only as an internal proof unless eligible commercial hosting entitlement is verified. Fail closed on any identity, API, or billing failure; do not spin up other billable Google Cloud services.

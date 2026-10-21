# ayahos-platform

**State: private migration placeholder, no application code or production deployment.**

Release infrastructure and Octopus CI ownership for the [AyahOS](https://github.com/ayahos-hq) multi-repository platform.

## Intended ownership

.octopus, deploy, scripts/ci, infrastructure configurations and repository contract checks.

## Non-negotiable boundary

Octopus remains the CI authority. Environment secrets remain managed outside Git; $0 operating limit; preserve existing Cloudflare live site and Vercel fallback until reviewed cutover.

## Migration process

- Current source of truth: [original private monorepo](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage).
- Master migration tracker: [#243](https://github.com/fuaadabdullah/AyahOS_Dual_Lineage/issues/243).
- This private repository is **not deployed** and must not receive live secrets or unreviewed IAM configuration.
- Extract only allow-listed, reviewed source paths; fix imports and lockfiles; run standalone build, tests and policy/security gates before source switch.
- Apply staged cutovers and rollback checks, preserve production until explicit gates are met.

Do not assume this README proves the repository is independently buildable or operational.

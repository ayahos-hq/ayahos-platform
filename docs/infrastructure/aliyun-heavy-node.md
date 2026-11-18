# Alibaba heavy compute node

Canonical source is **ayahos-hq**, not Dual_Lineage. Node agent and env
templates live in `ayahos-hq/ayahos-platform`; the agent code is
`ayahos-hq/ayahos-core`. Fly Control Hub is `ayahos-control-api.fly.dev`
(Core) plus `ayahos-admin.fly.dev` (operator UI). Heavy inference belongs
on a registered Alibaba ECS node (`aliyun-heavy`), not on Fly machines.

## Account state recorded 2026-11-18

| Item | Evidence |
| --- | --- |
| International profile | `ayahos-intl`, region `ap-southeast-1` |
| Account | `5284571233092262` |
| Cash balance | `USD 0.00` |
| ECS instances | none in scanned international regions |
| Free-tier savings plan | `spn-c1d5d42bD9tzfM4Q`, product `ecs_freetier_spn_intl`, through 2027-02-14 |
| Network created | VPC `vpc-t4ne2r04qykjgmcsh0akt`, vSwitch `vsw-t4naft80ig46tij6l5d02` (zone `ap-southeast-1b`), SG `sg-t4n9336bff63jgu58u2k` |
| SSH key pair | `ayahos-aliyun-heavy` (private key stays on the operator workstation) |
| Instance launch | **blocked** by `Forbidden.RiskControl` (ECS and ECI) |

**Free-only constraint:** do not launch GPU PAYG. The unused ECS free-tier
savings plan `spn-c1d5d42bD9tzfM4Q` has **USD 90** remaining
(`RestPoolValue=90`) through 2027-02-14. Cash balance is still `0.00`.
CLI `RunInstances`/`CreateInstance` (even DryRun of `ecs.t5-lc1m1.small`)
returns `Forbidden.RiskControl`. The marketing site is signed in; the ECS
console still requires a browser login/KYC pass.

## Operator gates before creating the VM

1. Sign in to the international ECS console and clear Risk Control.
2. Spend only the **USD 90** ECS trial pool. Do not attach PAYG GPU.
3. Launch from the existing VPC/vSwitch/SG/key.

Suggested free shape (fits the trial pool; not a GPU):

```text
Region:           ap-southeast-1
Zone:             ap-southeast-1b
Instance type:    ecs.t5-lc1m1.small   # 1 vCPU / 1 GB, trial-eligible
Image:            Ubuntu 24.04 20 GiB
System disk:      40 GiB ultra disk
Bandwidth:        1 Mbps PayByBandwidth
Key pair:         ayahos-aliyun-heavy
Security group:   sg-t4n9336bff63jgu58u2k
```

## After the VM exists

1. Install CPU `llama-server` and a tiny Qwen GGUF (0.5B Q8) under
   `/opt/ayahos-models`. A 7B/T4 path is paid; do not use it on this trial.
2. Install canonical `ayahos-hq/ayahos-core` at `/opt/ayahos-core` (do not
   clone Dual_Lineage). Create `/opt/ayahos/venv` with FastAPI/uvicorn/httpx/pydantic.
3. Fill `/etc/ayahos/aliyun-heavy.env` from `deploy/aliyun/aliyun-heavy.env.example`.
   Registration and inference secrets must match Fly `ayahos-control-api`.
4. Point `DUAL_LINEAGE_CONTROL_PLANE_URL` at `https://ayahos-control-api.fly.dev`.
5. Put a public HTTPS hostname (for example `aliyun-<ip>.nip.io`) in
   `DUAL_LINEAGE_NODE_PUBLIC_ENDPOINT` and Caddy.
6. Add that hostname to Fly secret `DUAL_LINEAGE_NODE_ENDPOINT_ALLOWLIST`.
   Empty allowlist currently means any valid HTTPS host is accepted; once the
   list is set, missing hosts fail closed.
7. Enable `ayahos-llama-aliyun.service` and `ayahos-aliyun-node.service`.
8. Check node `/health` for `backend: reachable` and `registration.ok: true`.
9. On Control Hub, `GET /compute/nodes` (operator secret) should list
   `aliyun-heavy` as `online` with the cognitive role.

## Models

- **Local free (this node):** `goblin-core` advertised, backend
  `qwen2.5-0.5b-instruct` on the trial t5 CPU. This is small, not GPU-heavy.
- **Alibaba Model Studio (DashScope):** already present on Fly as
  `DASHSCOPE_API_KEY` plus `DUAL_LINEAGE_ALIYUN_OVERMIND_MODEL` and token
  prices. That path is **cloud**. Public chat still sets `cloud_allowed=false`,
  so DashScope does not serve anonymous site traffic until a governed budget
  admits it.

Do not enable `DUAL_LINEAGE_ALLOW_CLOUD` for public requests as a shortcut
around a missing local node.

## Rollback

Stop and then release the ECS instance in the console or:

```text
aliyun ecs StopInstance --InstanceId i-... --ForceStop true
aliyun ecs DeleteInstance --InstanceId i-... --Force true
```

Keep the VPC unless you also want to tear down the network. Leave Fly Control
Hub running.

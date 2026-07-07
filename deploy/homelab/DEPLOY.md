# Homelab deployment (draft, cluster down until ~2026-09)

Status: **UNTESTED DRAFTS.** Nothing here has run against the cluster. Do not
copy into the homelab GitOps repo until validated live.

## Image

Built from the repo flake, NOT a Dockerfile, so laptop and cluster share the
exact nixpkgs toolchain pin (binary_bytes is part of the score; an apt clang
would produce different binaries and non-comparable ledger rows):

```bash
nix build .#runner-image
podman load < result
podman push jeff7712/autocompress-runner:0.1.0
```

The `clang++-17` wrapper only rewrites `-march=native` when
`AUTOCOMPRESS_MARCH` is set; the laptop devshell sets `raptorlake` (LLVM 17
misdetects that CPU), the image leaves it unset because LLVM 17 detects the
homelab's Zen 1 workers correctly. Do not set it in the pod.

## Target

Talos k8s cluster (homelab repo: gitops via ArgoCD, apps/*.yaml ->
infrastructure/<name>/ raw manifests). Runner lands on one CLI ar9070 worker
(Ryzen V1605B, 16 GB RAM): the only workers that fit the 10 Gi prize cap
(the WYSE has 8 GB). Wall-clock will be slow (V1605B single-core is roughly
1/3 of the laptop P-core; a t2 stage likely takes 3-4 days) but the envelope
scales with the machine (70,000/T hours), so slow hardware stays compliant.
Role: 24/7 queue grinder so the laptop stays free; the laptop remains fine
for interactive t0 runs.

## Division of labor

- Laptop sessions: hypothesis generation, review, pushing `exp/*` branches.
- Homelab runner: pulls the repo, benchmarks unscored heads, publishes results.

## What must change in the harness before this works (small, listed exactly)

1. `runner.py` remote mode: scan `refs/remotes/origin/exp/*` after a
   `git fetch --prune origin` instead of local heads, and publish results by
   committing `ledger.tsv` + `runs/<id>/` to a `results/homelab` branch and
   pushing (deploy token). Laptop side: `git fetch` + a `report.py` flag to
   read the fetched results branch.
2. `entrypoint.sh` (referenced by the Deployment, not yet written): clone or
   update the repo under /work, `cp /etc/autocompress/config.toml .`,
   `uv run prepare.py`, then `uv run runner.py`.
3. Runner currently shells out to `nix develop` when clang++-17 is absent;
   in the container clang++-17 IS on PATH, so that path is dormant. Verify.

## Envelope enforcement in-cluster

- RAM: `ram_enforcer = "external"` in the ConfigMap delegates the 10 GB cap
  to the pod memory limit (10Gi limit in deployment.yaml; OOMKill == the
  `oom` status the harness already classifies via SIGKILL + high RSS).
  Note 10Gi (1073741824*10) > 10 GB (10^10) by ~7%: acceptable for proxy
  runs; tighten to `memory: 10000000000` if t2 compliance runs happen here.
- CPU time: RLIMIT_CPU works unchanged in containers.
- Pinning: omitted (homogeneous Zen cores; cpu limit 1 with static CPU
  manager off means cfs quota, which throttles rather than pins. If timing
  jitter shows up, consider the static CPU manager policy on that node).
- Geekbench T for the V1605B MUST be measured on the node (config ships 0,
  which makes the harness refuse to run until filled in).

## Storage

40Gi Longhorn PVC. The ar9070s have 60 GB SSDs: check free Longhorn capacity
on the target node; single-replica volume pinned to the same node avoids
cross-node replication traffic for scratch I/O (ppm.temp does heavy random
writes; SSD wear is the documented cost of mmap_to_disk=true).

## Checklist when the cluster is back

1. Build + push the image (`nix build .#runner-image`, see above), pin a digest.
2. Measure Geekbench 5 single-core on the target worker; fill the ConfigMap.
3. Implement runner remote mode (item 1 above) + entrypoint.sh; test the
   image locally with podman first (t0 end to end with ram_enforcer=external).
4. Copy manifests to homelab repo `infrastructure/autocompress/`, add
   `apps/autocompress.yaml` (see argocd-app.example.yaml), let ArgoCD sync.
5. First job: t0 baseline on the node; sanity-check cpu_seconds against the
   measured T. Then t1, then the t2 baseline that was deferred from the
   laptop.

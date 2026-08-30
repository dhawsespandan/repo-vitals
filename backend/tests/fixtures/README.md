# Recorded upstream payloads

§4.4: every external HTTP call in the test suite is mocked with `responses`
against a library of **recorded real payloads**, not hand-written approximations.
Invented fixtures drift from the API they claim to represent, and a parser
tested only against its author's idea of the shape passes right up until it
meets production.

## `github/`

| File | Provenance |
|---|---|
| `repo_public.json` | `GET /repos/expressjs/express`, recorded 2026-08-30, verbatim except for the added `permissions` block — GitHub returns that key only for authenticated requests, and the recording was unauthenticated. |
| `tree_root_manifest.json` | `GET /repos/expressjs/express/git/trees/master?recursive=1`, recorded the same day, trimmed to a representative slice of entries with the real root `package.json` kept. |
| `tree_nested_manifest.json` | Composed from real entry shapes: a monorepo whose manifests live only at `services/api/` and `services/worker/`. This is §5.6's split-by-functionality case, the one a root-only check silently misses. |
| `tree_vendored_only.json` | Composed: `package.json` exists **only** under `node_modules/`. Vendored dependencies must not make a repository look like an npm project (§2.3). |
| `tree_no_manifest.json` | Composed: a docs-only repository — `ecosystem_unsupported`. |
| `tree_empty.json` | Composed: `tree: []` — `repo_empty`. |
| `tree_truncated.json` | Composed: `truncated: true` with a manifest present. §5.6 says to proceed with the entries that did come back. |

Tests derive variants (private, read-only, org-owned) by overriding individual
keys on the recorded payload, so each variant states in the test exactly what
it changes and why.

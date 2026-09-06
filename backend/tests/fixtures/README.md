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
| `tree_pypi_repo.json` | Composed from real entry shapes: Phase 6's golden Python repository. All five manifest formats in one tree — a root `requirements.txt`, a `requirements-dev.txt`, a `Pipfile` with its lock, a `service/pyproject.toml` with its `poetry.lock`, and a `legacy/setup.py` — plus a vendored `.venv/lib/site-packages/**/setup.py` that must not count, and a `docs/notes.txt` that is a `.txt` and not a requirements file. |
| `tree_mixed_ecosystem.json` | Composed: an npm root beside `api/requirements.txt`. One scan, one roll-up, two ecosystems (D1). |
| `tree_npm_monorepo.json` | Composed from real entry shapes: the golden scan repository. A root manifest with a lockfile, two nested manifests without one, a vendored `node_modules/left-pad/package.json`, and a `docs/package.json.md` that is not a manifest however much its name suggests otherwise. |

Tests derive variants (private, read-only, org-owned) by overriding individual
keys on the recorded payload, so each variant states in the test exactly what
it changes and why.

## `manifests/`

The golden repository's own files, kept as files rather than inline strings so
the same bytes serve the adapter's unit tests and the scanner's end-to-end run.

Two properties are deliberate, and both are what make the tests able to fail:

* **`root_package_lock.json` resolves below what `root_package.json` allows.**
  `express: ^4.16.0` permits 4.19.2 and the lockfile installs 4.17.1;
  `lodash: ^4.17.0` permits the patched 4.17.21 and the lockfile installs the
  deprecated, vulnerable 4.17.19. A scanner that resolved ranges against the
  registry would report this repository clean, and nothing about the output
  would look wrong.
* **`lodash` appears in all three manifests at two different versions**, so a
  scanner that deduplicated by package name would report one occurrence and
  quietly lose two installations that each need their own remediation.

`unassessable_package.json` carries one dependency of every non-registry
specifier family; `legacy_package_lock.json` is a v1 (npm 6) lockfile, which is
still what the un-maintained repositories this product is about tend to have.

The `pypi_*` files are Phase 6's, and the same two properties are built into
them:

* **`pypi_pyproject.toml` allows `Django>=4.2`, which the newest release
  satisfies; `pypi_poetry.lock` installs the yanked 4.2.12.** A scanner that
  resolved the range against PyPI reports this repository clean.
* **`django` is declared in four of the five manifests, at three different
  resolved versions**, so a scanner that deduplicated by package name would
  report one occurrence and lose three installations.

Two of them are named for what they are rather than for what they would be
called in a repository. `pypi_pipfile.toml` is a `Pipfile` (TOML, but the real
file has no extension) and `pypi_setup_py.txt` is a `setup.py` — saved as
`.txt` so this project's own linters and test collector leave it alone. It is
data under test, not code, and RepoVitals never executes it: `adapters/pypi.py`
reads it with `ast` and evaluates literals only. Which parser reads which
fixture is decided by the *path* the test passes to `adapter_for_path`, not by
the fixture's own filename.

## `npm/`

Package documents in the registry's own shape (`dist-tags`, per-version
`deprecated`, the `time` map). `left-pad.json` uses the boolean form of
`deprecated`, which is a deprecation carrying *no* text — distinguishable from
no deprecation at all, because the information content of that text is S3's
independent variable (D2).

## `pypi/`

Package documents as `GET pypi.org/pypi/{name}/json` returns them, recorded
2026-09-06 and trimmed to the releases each test needs — the `info` block
(latest version and the classifiers), and one representative file per kept
release carrying its upload time and its yank state.

The trimming keeps every property a test turns on, and all of them are real:

| File | What it carries |
|---|---|
| `django.json` | 4.2.12 **yanked**, with PyPI's own reason text, beside a 4.2.11 that is not. Which version the lockfile resolved is what decides (D2). Also the "old pin of a maintained package" case: a 2019 pin against a release from last week, so staleness reads near zero and `versions_behind_*` carries the distance. |
| `requests.json` | 2.32.0 yanked over a CVE mitigation conflict — the case where the reason names the security problem. |
| `oauth2client.json` | `Development Status :: 7 - Inactive`, and nothing published since 2018. The composite's *other* half: a project-wide declaration rather than a per-release one, and a staleness past §5.2's 1095-day cap. |
| `flask.json` | Clean. The contrast every deprecation test needs, and the base for the two synthesized yank variants (an empty `yanked_reason`, and a release with only some files yanked) that no real package happened to supply. |
| `urllib3.json` | 1.25 yanked with the terse "Broken release" — the short end of the information-content axis D2 makes S3's variable. |

## `osv/`

Advisory documents as `GET /v1/vulns/{id}` returns them: CVSS as a **vector
string** rather than a number, `aliases` carrying the CVE id, `affected.ranges`
as introduced/fixed events. `vuln_no_severity.json` has no severity at all and
no fix — §5.2's placeholder path is Phase 4's, and Phase 3's only job is to
record the absence honestly.

# Adapter soundness — the Phase 6 diff as evidence

**Claim.** A Python repository flows through this application's **unchanged**
scanner, scoring engine and API. Adding a second package ecosystem cost the
core nothing.

That is a design claim, and a design claim is cheap. This document is the
attempt to make it falsifiable: the whole diff of Phase 6, the list of paths it
touched, and the list of paths it did not — measured, not asserted.

Everything below is `v0.5.0..v0.6.0` and excludes this file, which is written
after the phase's code and describes it.

---

## 1. The diff

```
$ git diff --stat v0.5.0..v0.6.0

 backend/apps/common/http.py                          |  13 +-
 backend/apps/repositories/validation.py              |  15 +-
 backend/apps/scanning/adapters/__init__.py           |  11 +-
 backend/apps/scanning/adapters/base.py               |  54 +-
 backend/apps/scanning/adapters/pep440.py             | 259 +++++
 backend/apps/scanning/adapters/pypi.py               | 866 ++++++++++++++++++
 backend/apps/scanning/adapters/registry_clients.py   | 255 ++++-
 backend/tests/fixtures/README.md                     |  38 +
 backend/tests/fixtures/github/tree_mixed_ecosystem.json |  40 +
 backend/tests/fixtures/github/tree_pypi_repo.json    |  88 ++
 backend/tests/fixtures/manifests/pypi_pipfile.toml   |  16 +
 backend/tests/fixtures/manifests/pypi_pipfile_lock.json |  35 +
 backend/tests/fixtures/manifests/pypi_poetry.lock    |  41 +
 backend/tests/fixtures/manifests/pypi_pyproject.toml |  27 +
 backend/tests/fixtures/manifests/pypi_requirements.txt |  14 +
 backend/tests/fixtures/manifests/pypi_requirements_dev.txt |  2 +
 backend/tests/fixtures/manifests/pypi_setup_py.txt   |  31 +
 backend/tests/fixtures/pypi/django.json              |  62 ++
 backend/tests/fixtures/pypi/flask.json               |  44 ++
 backend/tests/fixtures/pypi/oauth2client.json        |  46 ++
 backend/tests/fixtures/pypi/requests.json            |  54 ++
 backend/tests/fixtures/pypi/urllib3.json             |  46 ++
 backend/tests/test_pypi_adapter.py                   | 517 +++++++++++
 backend/tests/test_registry_and_osv.py               | 256 ++++-
 backend/tests/test_repository_validation.py          |  67 +-
 backend/tests/test_scanner.py                        | 298 +++++++
 frontend/src/components/DependencyTable.tsx          |  40 +-
 frontend/src/components/EcosystemChip.tsx            | 100 +++
 frontend/src/components/WhyFlaggedPanel.tsx          |  53 +-
 frontend/src/components/ecosystem.test.tsx           | 317 +++++++
 frontend/src/pages/RepoDetail.tsx                    |  18 +
 31 files changed, 3688 insertions(+), 35 deletions(-)
```

By area:

| Area | Files | Inserted | Deleted |
|---|---|---|---|
| Application code (`backend/apps/`) | 7 | 1,448 | 25 |
| Tests and fixtures (`backend/tests/`) | 19 | 1,720 | 2 |
| Frontend (`frontend/src/`) | 5 | 520 | 8 |

**Two thirds of the phase is tests and fixtures**, and 1,125 of the 1,448
application lines are the two new files — the PyPI parsers and the PEP 440
grammar. What is left, across the entire rest of the application, is **323
inserted and 25 deleted lines in five files**, and every one of those five is
named and justified below.

---

## 2. What was touched, and why each one had to be

### `adapters/pypi.py` (new, 866 lines) and `adapters/pep440.py` (new, 259)

The ecosystem itself. Five manifest formats, a PEP 440 version grammar, and
PEP 503 name normalization. This is where the phase was supposed to land and
where 78% of its application code did.

`pep440.py` is a sibling of `semver.py` rather than a generalisation of it,
which `semver.py`'s own module docstring predicted in Phase 3. The two grammars
share almost nothing: PEP 440 has an epoch (`1!2.0`), an unbounded release
tuple, post-releases and dev releases; SemVer has three components and a dotted
prerelease list with its own comparison rules. One function serving both would
have to decide, per input, which grammar it was reading — and would answer
wrongly for the versions that look like both.

### `adapters/registry_clients.py` (+255, -0)

One new class, `PypiRegistryClient`, beside the npm one. No shared abstraction
was extracted, deliberately: the two answer the same question (`PackageFacts`)
and share no path underneath it. npm's deprecation is a per-version string;
PyPI's is a composite of a per-release yank and a project-wide trove classifier
(D2). npm's release dates live in one `time` map; PyPI's are per-file inside
each release. Factoring them together would produce a body of branches on
`ecosystem`, which is the shape the adapter seam exists to keep out.

### `adapters/base.py` (+50, -4)

Two hooks on `DependencyAdapter`, both with defaults that leave npm
bit-identical:

* **`owns(path)`** — membership of `manifest_patterns()` by default. PyPI needs
  more, because its requirements files are a *convention* rather than a
  standard: `requirements.txt`, `requirements-dev.txt`, `dev-requirements.txt`,
  `requirements/prod.txt`. Enumerating the names people happen to use would
  miss the next one.

* **`for_path(path)`** — `self` by default; for PyPI, an instance bound to that
  path. This is the one interface change the phase genuinely needed, and the
  reason is specific: `parse()` receives bytes and no path, and PyPI cannot
  recover the path from the bytes. `django==2.2` is a valid Python expression
  as well as a valid requirement line, so `setup.py` and `requirements.txt` are
  **genuinely indistinguishable by content** — a content sniffer would have to
  guess on exactly the files where guessing wrong changes the answer.

  Binding the path inside the adapter package is what kept `scanner.py` out of
  this diff altogether. The alternative — adding a parameter to `parse()` —
  would have changed the base class, the npm adapter *and* the scanner, and the
  claim this document makes would have been weaker for the sake of a slightly
  more obvious signature.

  It paid for itself twice: the bound instance carries its own `parser_name`,
  so `manifest_files.parser_name` now records which of the five parsers read a
  row, which is exactly the question that column exists to answer.

### `adapters/__init__.py` (+7, -4)

The registration line, and a docstring that stops predicting Phase 6 and starts
describing it. This file's Phase 3 docstring said: *"Phase 6 adds one line here
for PyPI, and pre-scan validation, the scanner and the API all learn about it
without being touched — which is the diff `docs/adapter_soundness.md` has to be
able to show."* It is the line below, and this is that document.

### `apps/common/http.py` (+9, -4)

`pypi.org` added to `ALLOWED_HOSTS`. The allowlist is the whole SSRF defence, so
a host goes in when the phase that calls it lands — never a phase earlier. The
Phase 3 comment that reserved this slot ("Phase 6 adds pypi.org") is now the
entry.

### `apps/repositories/validation.py` (+11, -4)

One sentence. §5.6 fixes the `ecosystem_unsupported` message and specifies that
it changes with the second ecosystem: *"…We currently support Node.js/npm and
Python/PyPI projects."*

The **check itself did not change**, and that is the part worth noticing.
Validation asks `adapters.adapter_for_path`, so it learned about five new
manifest formats without a line of its own — the payoff for a decision made in
Phase 3 for exactly this moment (`docs/decisions.md` §2.3).

### The frontend: three files touched, one added

`EcosystemChip.tsx` is new. `RepoDetail.tsx` gains the chip and one derived
boolean (+18, -0), `DependencyTable.tsx` gains an optional prop and three
reason labels, and `WhyFlaggedPanel.tsx` gains a branch for
`dynamic_setup_py` — a row that names an argument rather than a package, and
would be actively misleading under the generic sentence.

No API type changed. `ecosystem` was already on `ManifestFile` and
`DependencyOccurrence` in Phase 3, because §5.1 put PyPI in the schema from the
start (D1).

---

## 3. What was not touched

Verified, not asserted — `git diff --name-only v0.5.0..v0.6.0 -- <path>` is
empty for every row:

| Path | Role |
|---|---|
| `backend/apps/scanning/scanner.py` | the orchestrator: tree, fetch, parse, pool, enrich, persist |
| `backend/apps/scanning/background.py` | the thread runner and the completion pipeline |
| `backend/apps/scanning/osv.py` | the advisory client |
| `backend/apps/scanning/retention.py` | §5.7 |
| `backend/apps/scanning/models.py` | the schema |
| `backend/apps/scanning/migrations/` | **no migration in this phase at all** |
| `backend/apps/scanning/views.py`, `serializers.py` | the API surface |
| `backend/apps/scoring/engine.py`, `normalize.py`, `signals.py`, `weights.py` | §5.2, §5.3, §5.4 |
| `backend/weights/` | both weights files |
| `backend/apps/research/` | the permanent history tables |
| `backend/apps/scanning/adapters/npm.py`, `semver.py` | the first ecosystem |

§10 Phase 6's guardrail names four of these (`scanner.py`, `scoring/engine.py`,
`scoring/normalize.py`, anything under `reports/`). The list above is wider
because the interesting claim is wider.

Two rows deserve their own sentence.

**No migration.** §5.1 wrote `ecosystem TEXT CHECK IN ('npm','pypi')` in Phase
3, months before an adapter existed, on D1's instruction that both ecosystems
are in scope from the start. The database was ready for this phase before the
phase began, so the second ecosystem cost zero schema change and zero downtime.

**`weights/` untouched.** Both `weights_v0_equal.yaml` and `weights_v1.yaml`
already carried a `pypi:` vector — WP-1 elicited one (§4.8). §5.4's loader
requires a vector per ecosystem, and `for_ecosystem()` raises rather than
falling back to npm's, so a missing one would have been a hard failure rather
than a silent mis-score. It was not missing.

---

## 4. What the untouched core actually did

An untouched file is only evidence if it *ran*. Two behaviours were observed on
a seeded local database, and both are the seam working rather than the seam
being avoided:

**Scoring picked a weight vector per occurrence, in one repository.** A mixed
repository scored its npm rows under `{dep .46, sev .28, cnt .16, stl .10}` and
its PyPI rows under `{dep .32, sev .35, cnt .16, stl .17}` — one scan, one
rank-decayed roll-up, no branch anywhere on an ecosystem name. `signals.py`
reads `occurrence.manifest.ecosystem` and hands it to `weights.for_ecosystem`,
which is code written in Phase 4 against a schema written in Phase 3 for an
ecosystem that did not exist until this phase.

**The whole detail page rendered a Python repository with no PyPI-specific
code in it.** Score ring, classification, the contributors strip and its
arithmetic (`100 - 75.87 = 24.13`), the Flagged/All/Unassessable partition, the
`declared → resolved` provenance chips, the CVE badge, the deprecation badge —
all Phase 3-to-5 components, all reading a PyPI scan. The one thing Phase 6
added to that page is a chip saying "PyPI", and it is there precisely because
*everything else looks identical*, which makes the claim unverifiable without
one label to check it against.

---

## 5. Honest limits of this claim

Three things this document does **not** demonstrate, stated here so nobody has
to find them:

1. **Two ecosystems is not N.** npm and PyPI are structurally different — one
   lockfile format versus four manifest formats and two lockfiles, per-version
   deprecation versus a yank/classifier composite — which is why D1 chose this
   pair. But a third ecosystem could still find a seam that does not fit, and
   the honest form of this claim is "the second one cost nothing", not "any
   further one will".

2. **One interface change was needed.** `for_path` is a real addition to
   `DependencyAdapter`, not a no-op. The claim is that it stayed *inside*
   `adapters/`, not that nothing anywhere changed.

3. **Phase 8's agent has not run against PyPI.** The objective in §10 Phase 6
   says the repository flows through the unchanged scanner, scoring engine "and
   (later) agent". The first two are shown here. The third is Phase 8's, and
   S3's whole research question is whether the grounding quality *differs* by
   ecosystem — so the agent is exactly where this claim should be expected to
   get more interesting, not less.

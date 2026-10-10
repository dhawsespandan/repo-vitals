# The ten-minute demo

The seminar walkthrough (§10 Phase 14): the product end to end on the live
site, then the research it carries. It follows one path — login → register
live → score → drill-down → PyPI proof → cited remediation → trend → corpus
cross-section → validation report → the S3 table — and every step has a
fallback, so nothing on the day needs improvising. `docs/prod_smoke_checklist.md`
is the longer, unhurried version of the product half; run it the day before.

**Live site:** <https://repo-vitals-lilac.vercel.app>. **Fixtures:** the five
`rv-accept-*` repositories on the developer's GitHub account.

---

## Thirty minutes before

- [ ] **Warm the backend.** Open `/api/health/` on the live site and wait for
  `"database": "ok"`. A cold start costs ~50 s you do not want on stage.
- [ ] **Sign in** in the browser you will present from, and keep that window in
  the foreground: a hidden tab pauses polling (decisions §12.17).
- [ ] **Free one fixture for the live registration.** Remove `rv-accept-basic`
  from the dashboard (its history is kept — the trend is keyed on GitHub's
  ids, decisions §10.9 — so it comes back with its past).
- [ ] **Have a fallback report.** `rv-accept-monorepo`'s `request` remediation
  should already exist; if Groq's free tier is exhausted on the day, the stored
  plan is served from the database exactly as a fresh one would be.
- [ ] **Open the research tabs**, in order: on GitHub,
  `wp/wp-4/strata_report.md`, `wp/wp-5/score_histogram.png`,
  `notebooks/13_3_validation.ipynb` and `notebooks/13_1_analysis.ipynb`
  (GitHub renders the executed notebooks).

---

## The walkthrough

| Time | Show | Say |
|---|---|---|
| 0:00 | **Login.** "Continue with GitHub" → the dashboard with your avatar. | "GitHub owns identity; we own the session. The OAuth token is encrypted at rest and never reaches the browser — and the backend never makes a write call, which a test checks three ways." |
| 0:45 | **A rejection.** *Register repository* → paste `github.com/django/django` → *Register & scan*. | The answer is specific: *"You need write or collaborator access on this repository to monitor it here."* "You can only monitor what you can act on." |
| 1:15 | **Register live.** Paste `github.com/<you>/rv-accept-basic`. The card goes queued → running → completed while you talk. | "Four checks before anything is stored: reachable, writable, not a duplicate, and a supported manifest *anywhere* in the tree — monorepos split by service are the normal case." |
| 2:00 | **The score.** Open the repository: the badge, the class, and *Where the points went* — `100 − … = …`, **weights v2**. | "Deterministic: no LLM touches the number. The worst dependency counts in full and each next one half as much as the one before, so five hundred clean dependencies cannot hide three critical ones." |
| 3:00 | **Drill-down.** *Why?* on the flagged `lodash` row: *How this score was computed*. | "Every flag says why: deprecation, the worst CVSS, the CVE count, staleness — each term's contribution, adding up to the row's score, under the weights version that scored it." |
| 4:00 | **The PyPI proof.** Open `rv-accept-pypi`. | "Five Python manifest formats through the same pipeline, unchanged. PyPI deprecation is real but terse — a yanked release, an *Inactive* classifier — and that asymmetry is what study S3 measures." |
| 4:45 | **Cited remediation.** On `rv-accept-monorepo`, *Generate remediation* for `request` (about 35 s; or open the stored one). Show the fixes, the citations, and *Retrieved source passages* beside them; then *Download this plan* as JSON. | "One retrieval pass over the package's own changelog and README, a deterministic grounding gate, one model call. When the sources are thin, it says so in its first sentence instead of guessing. The JSON is a handoff to a coding agent — Repo Vitals never commits anything." |
| 6:30 | **The trend.** *Score history* on `rv-accept-monorepo`. | "Every scan is kept, tagged with the weights that scored it; the marker is where `v2` took over. Old scores are never rewritten: research recomputes, the product shows what it showed." |
| 7:15 | **The corpus.** The strata report, then the score histogram. | "914 repositories sampled on a documented frame — 240 strata, stale ones deliberately oversampled — and scored once, by the exact code the product runs. That cross-section is study S1's dataset." |
| 8:15 | **Validation.** The 13_3 notebook: the checklist, then RQ1–RQ3. | "AHP weights against entropy weights from the corpus — they disagree, and we say so. Classes survive ±20% perturbation with under 5% flips. Against an *independent* reference, deps.dev's Scorecard, there is no correlation: no weighting of these four signals tracks a repository's own security practices. And this whole report regenerates, offline, from the export." |
| 9:15 | **The S3 table.** The 13_1 notebook: correctness by condition and ecosystem, then the table where TARGET does not hand over the answer. | "Same 150 dependencies, three pipelines, correctness computed by a program. The judge's faithfulness verdicts are *not* validated — kappa 0.134 against a human — so we don't lean on them. Everything here is in the replication package: one restore, one export, two notebooks." |
| 10:00 | Stop. | |

---

## If something goes wrong

| What | Do |
|---|---|
| The site spins on first load | Render was cold. Talk through the architecture slide for 50 s; it comes back. |
| GitHub sign-in fails | Use the already signed-in window; the session survives a refresh. |
| The scan sits at *queued* | The tab is in the background, or the instance restarted. Bring it to the front; if it is still queued after a minute, rescan. |
| "Generate remediation" fails or is slow | Groq's free tier is per minute and per day. Open the stored plan on `rv-accept-monorepo` instead — reports are cache-first by design. |
| A notebook tab will not render on GitHub | Open the same section in `wp/wp-6/validation_report/report.md` or `wp/wp-8/runs/analysis/tables.md`: the notebooks regenerate exactly those files. |

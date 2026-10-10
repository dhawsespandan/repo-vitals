# Production smoke checklist

Run after every deploy of `main` (Render and Vercel both deploy on push) and
before any demo. It takes about fifteen minutes, most of it waiting on scans.
Every step says what to look at and what counts as a pass; a step that fails
is a stop, not a note. `docs/demo_script.md` is the ten-minute version of the
same path, for an audience.

Production is `https://repo-vitals-lilac.vercel.app` (the SPA) in front of
`https://repo-vitals.onrender.com` (the API, reached only through the Vercel
rewrite). The five acceptance fixtures are the `rv-accept-*` repositories on
the developer's account: `rv-accept-basic`, `rv-accept-monorepo`,
`rv-accept-mixed`, `rv-accept-pypi` and `rv-accept-unassessable`.

## 0. Before you start

- [ ] **Warm the backend.** Open `https://repo-vitals-lilac.vercel.app/api/health/`
  and wait for `{"status": "ok", "database": "ok"}`. A cold Render instance
  takes about 50 s (decisions §1.17); the scheduled keepalive does not prevent
  that, only Supabase's pause.
- [ ] **Know what was deployed.** Render's dashboard shows the commit it built;
  Vercel's shows the same commit for the frontend. Both must be the commit you
  meant to ship.
- [ ] **Use a foreground tab.** A backgrounded Chrome window reports
  `document.hidden`, which pauses the app's polling (decisions §8, §12.17), so
  scans look stuck when they are not.

## 1. Platform

- [ ] **Health is a database round trip.** The response above says
  `"database": "ok"`, not just a 200.
- [ ] **Security headers.** `curl -sI https://repo-vitals.onrender.com/api/health/`
  shows `strict-transport-security`, `x-frame-options: DENY`,
  `x-content-type-options: nosniff` and `referrer-policy: same-origin`
  (`config/settings/prod.py`; `manage.py check --deploy` passes on it).
- [ ] **Research is unreachable.** `/api/experiment/`, `/api/research/`,
  `/api/research/issue-search/` and `/api/issues/search/` all answer 404
  (D13, decisions §13.15).
- [ ] **Memory.** Render's metrics show the instance under 512 MB after the
  per-dependency report on `request` in step 5, and its Events tab shows no
  out-of-memory restart during it (decisions §8.15, §14.15: about 370 MB peak
  for a 512-token changelog under `smoke_memory`).

## 2. Identity

- [ ] **Sign in.** "Continue with GitHub" round-trips through GitHub and lands
  on `/dashboard` showing your avatar and name.
- [ ] **Refresh keeps the session.**
- [ ] **Back gesture never signs you out.** From the dashboard, go back towards
  `/login`: a "Sign out?" dialog appears instead of the login screen; "Stay
  signed in" keeps you where you were (Phase 1).

## 3. Registration and scanning

- [ ] **A rejection is specific.** Paste a public repository you cannot push
  to: the form answers "You need write or collaborator access on this
  repository to monitor it here." (§5.6).
- [ ] **A fixture scans.** Register (or rescan) `rv-accept-monorepo`: the card
  goes queued → running → completed without a manual refresh.
- [ ] **The score says which weights scored it.** The detail page reads
  `100 − … = …` with **`weights v2`**. A `v1` tag on a new scan means a
  `WEIGHTS_VERSION` override is set on Render (decisions §12.19).
- [ ] **Rescanning a repository that has reports asks first** ("confirm
  required"), because the cascade deletes them (§5.7, decisions §9.1).

## 4. Explanation

- [ ] **The drill-down adds up.** Open a flagged dependency (`lodash` on
  `rv-accept-monorepo`): the four contributions sum to the component score,
  and the panel names the weights version.
- [ ] **PyPI goes through the same pipeline.** `rv-accept-pypi` shows its five
  manifest formats, a yanked Poetry-locked release flagged deprecated, and an
  `Inactive` classifier (Phase 6).
- [ ] **Unassessable is listed, not dropped.** `rv-accept-unassessable` lists
  its `file:`/`git` specifiers with reasons and keeps them out of the score.

## 5. Remediation

- [ ] **Combined report.** Generate it on `rv-accept-mixed`: it completes in
  under a minute and loads from the stored row on refresh.
- [ ] **Per-dependency report.** Generate one for a flagged npm dependency: the
  fixes, the citations and the retrieved chunks render side by side, or — with
  thin retrieval — the plan says in its first sentence that it rests on the
  scan's measurements (§5.9).
- [ ] **The heavy one does not take the instance down.** Generate (or *Try
  again*) `request` on `rv-accept-monorepo` — its 69 KB changelog is the
  densest the fixtures carry — while `/api/health/` is polled every 3 s in
  another tab. Pass: health answers 200 throughout and the plan completes. A
  503 about 40 s in is the embedding step being killed for memory: stop, and
  read Render's Events tab (decisions §14.14 finding 1, §14.15).
- [ ] **Downloads.** The `.md` and `.json` downloads open, and the JSON parses
  (§5.8).

## 6. Projects and trends

- [ ] **Projects.** Group two fixtures; the combined report's sibling notice
  names the shared flagged dependency (Phase 10).
- [ ] **Trend.** The chart draws every stored scan, with the "weights v2"
  marker before the first `v2` scan (D5).

## 7. Last

- [ ] **No console errors** on any page above (DevTools → Console).
- [ ] **Record the run** in `docs/decisions.md` when it is a phase's acceptance:
  the date, the commit, and anything that did not pass.

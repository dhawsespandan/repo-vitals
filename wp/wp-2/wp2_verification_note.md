# WP-2 Verification Note

**Date:** 2026-10-08. **Checked by:** Spandan, who completed WP-2 alone after the team became unavailable (see `wp/wp-review/WP_review.md`).

## What the set is

`wp2_anchor_set.csv` has 49 rows in File B's exact 8-column format.

| | npm | PyPI | Total |
|---|---|---|---|
| healthy | 9 | 8 | **17** (File B: 15–20) |
| risky | 11 | 9 | **20** (File B: 15–20) |
| in_between | 7 | 5 | **12** (File B: 10–15) |
| **Total** | **27** | **22** | **49**, a 55/45 split |

- **Known anchors:** 12 (File B asks for at least 5). The 11 from `WP2_20261006.zip` are kept word for word, plus `bower/bower` (`request@2.67.0`). `googleapis/oauth2client` stays a spare anchor, because its pin lives only in `samples/`.
- **100+ dependencies:** 8 repos (File B: at least 5): atom/atom, facebookarchive/flux, react/create-react-app, eslint/eslint, prettier/prettier, vercel/next.js, microsoft/vscode and scrapy/scrapy.
- **Lockfiles:** 14 rows have a lockfile RepoVitals reads, and 35 don't.
- **Near-duplicates:** none. The largest overlap of declared dependency names between any two rows is 19% (openai/jukebox and openai/spinningup). `jaredhanson/oauth2orize` was dropped because it shared 42% with `jaredhanson/passport`, which is the same author's scaffolding.

## How every value was checked

Each repo was read on 2026-10-08 at the commit linked in `wp2_evidence.md`.

- `archived`, GitHub's `pushed_at` and the default branch's head commit and its date all come from the GitHub API.
- The manifests were planned and parsed by RepoVitals' own code (`plan_manifests`, `adopt_workspace_lockfiles` and the npm/PyPI adapters), with the scanner's 50-manifest and file-size limits. That means:
  - `approx_dep_count` is the number of dependencies the scanner would read;
  - `has_lockfile` is true only when a `package-lock.json`, `npm-shrinkwrap.json`, `poetry.lock` or `Pipfile.lock` sits beside a manifest and was read. `yarn.lock`, `pnpm-lock.yaml` and `uv.lock` are listed in the evidence as present but not read.
- Every **known anchor** was confirmed four ways:
  - the named package is a **direct** dependency in a manifest the scanner reads;
  - it resolves to the named version through an exact pin or a lockfile RepoVitals reads;
  - that exact version is listed on osv.dev, or marked deprecated on npm;
  - the evidence file records the manifest line, the resolution and the advisory IDs.
- **No scoring was run.** No score, class or signal was computed for any repo. The only registry and OSV queries were:
  - for each anchor's one named `package@version`;
  - for the npm deprecation status of the three famously-dead packages seen in candidates: `request`, `coffee-script` and `istanbul`.

The candidate list and the fact extraction were prepared with tool assistance. A script ran RepoVitals' own manifest readers against the live sources, so every value in the file was read by code, not typed from memory. The bucket rules below are File B's criteria, written as explicit tests and applied to those facts.

## Bucket rules (File B's criteria, made explicit)

"Activity" means the date of the **head commit on the default branch**. GitHub's `pushed_at` is recorded in every row too, but it isn't used for buckets: any push to any branch moves it. For example, `dropbox/pyannotate` reads "pushed 2026-07-06", but its default branch was last changed on 2021-10-12. This replaces the 7 Oct review's instruction to judge by the pushed date.

**Famously-dead list** (File B's examples plus the obvious ones, matched against declared names only):
- npm: request, request-promise, tslint, babel-eslint, node-sass, gulp-util, istanbul, coffee-script, jade, bower, phantomjs, uglify-es, nomnom, natives, har-validator
- PyPI: nose, pycrypto, oauth2client, distribute, futures, enum34

The rules are applied in order; the first match wins.

| Rule | Bucket | Test |
|---|---|---|
| R1 | risky | Known anchor, as confirmed above. File B: "anything depending on famously dead packages". |
| R2 | risky | Archived. |
| R4 | risky | The README says the project is deprecated, end-of-life or no longer maintained. The exact sentence is quoted in the row. |
| R3 | risky | No default-branch commit for 3+ years (before 2023-10-08) and not small (see I2). |
| I2 | in_between | No default-branch commit for 3+ years, but at most 10 dependencies and none on the dead list ("stale but small/clean"). |
| H1 | healthy | Commit within 6 months (on or after 2026-04-08), nothing on the dead list, and no deprecation or maintenance-only notice in the README. |
| I1 | in_between | Everything else: last commit between 6 months and 3 years ago, or the README says maintenance-only mode ("maintained but behind"). |

Repos reading fewer than 5 dependencies were excluded unless they were known anchors, because a row with nothing to score tests nothing.

## Candidates checked and not used

95 repos were verified, and these 46 were left out:

- **Ambiguous (excluded):** sindresorhus/got, browserify/browserify and krakenjs/kraken-js are maintained repos whose only dead package is a devDependency.
- **Fewer than 5 dependencies read:**
  - encode/django-rest-framework (1)
  - httpie/cli (0)
  - Supervisor/supervisor (2)
  - getsentry/raven-python (3)
  - omab/django-social-auth (4)
- **Near-duplicates:**
  - jaredhanson/oauth2orize (42% overlap with jaredhanson/passport, as above)
  - jaredhanson/passport-local (sibling of passport)
  - moment/moment-timezone (sibling of moment)
- **Risky bucket already at 20:**
  - karma-runner/karma
  - facebookarchive/draft-js
  - babel/babel-eslint
  - palantir/tslint
  - GoogleChromeLabs/sw-precache
  - airbnb/react-sketchapp
  - jashkenas/coffeescript
  - zenorocha/clipboard.js
  - openai/baselines (a second OpenAI RL repo)
  - foreversd/forever
- **Healthy, beyond what the bucket and ecosystem balance needed:**
  - fastapi, pydantic, click, black, sqlalchemy
  - chalk, handlebars.js, backbone, leaflet
  - getsentry/sentry (it's really npm + PyPI mixed)
  - fabric, flower, django-tastypie, django-silk, pyramid
  - grunt, jsdoc, less.js, yo, winston, log4js-node, async
- **In_between spares:** timofurrer/maya, miguelgrinberg/microblog and web2py/web2py.

## Format check

The file loads through the Phase 12 anchor-set reader (`apps.research.validation.anchors.read_anchor_set`) without error: 49 rows, 12 known anchors, no comment lines and no extra columns.

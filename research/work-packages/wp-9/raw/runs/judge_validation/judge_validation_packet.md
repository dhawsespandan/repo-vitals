# WP-9 judge-validation packet

50 items. Label them in `wp9_judge_labels_template.csv`.

## Rubric

Label each item `faithful`, `minor_unsupported` or `major_unsupported`, judging
the remediation **only** against the dependency facts and the passages shown with
it — not your own knowledge, not the internet (File B, WP-9).

- **faithful** — every material claim is stated by, or directly follows from, the
  facts or passages shown. "Insufficient information to recommend…" over thin
  sources is faithful.
- **minor_unsupported** — at most one peripheral claim is unsupported; the core
  recommendation is supported.
- **major_unsupported** — a core claim (the recommended version, the replacement
  package, a breaking-change assertion) is not in what was shown. Empty or
  unreadable source with a specific recommendation is major.

Version numbers, package names and migration steps all count as claims. Write a
one-line note naming the offending claim for every label that is not
`faithful`. One sitting; no conferring; no skipped items.

---

## ITEM-001

**Dependency:** `transformers` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 4.39.2
- Declared specifier: ==4.39.2
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 5.19.0
- Versions behind the latest release: major 1, minor 18, patch 1
- Days since the package's latest release: 1
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 44
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-5241 / PYSEC-2026-2290: severity critical, CVSS 9.6, fixed in unknown
  - CVE-2024-11394 / GHSA-hxxf-235m-72v3: severity high, CVSS 8.8, fixed in 4.48.0
  - CVE-2024-11393 / GHSA-wrfc-pvp9-mr9g: severity high, CVSS 8.8, fixed in 4.48.0
  - CVE-2024-11392 / PYSEC-2024-227: severity high, CVSS 8.8, fixed in 4.48.0
  - CVE-2024-11393 / PYSEC-2024-228: severity high, CVSS 8.8, fixed in 4.48.0

### Remediation to label

The project is pinned to **transformers==4.39.2**, which is affected by several high‑severity CVEs and one critical CVE. Advisory data shows that versions ≥ 4.48.0 contain fixes for the high‑severity issues, and the newest release is 5.19.0. Because no release notes were retrieved, the exact migration steps are unknown, so you should review the package’s changelog for any breaking changes before upgrading. Updating the dependency to the latest version will address all known vulnerabilities and keep you up‑to‑date.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| transformers | upgrade | 5.19.0 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-002

**Dependency:** `numpy` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.19.5
- Declared specifier: ==1.19.5
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 2.5.3
- Versions behind the latest release: major 1, minor 7, patch 0
- Days since the package's latest release: 31
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2021-33430 / GHSA-6p56-wp2h-9hxr: severity medium, CVSS 5.3, fixed in 1.21
  - CVE-2021-34141 / GHSA-fpfv-jqm9-f5jm: severity medium, CVSS 5.3, fixed in 1.22

### Remediation to label

The current pinned version 1.19.5 is vulnerable to CVE‑2021‑33430 and CVE‑2021‑34141. The advisory data shows the first issue is fixed in NumPy 1.21 and the second in 1.22, so upgrading to at least 1.22 will resolve both problems. The repository’s README does not describe what changed in those releases or any breaking‑migration steps, so you should review NumPy’s release notes separately. Updating the requirement in *requirements.txt* to `numpy>=1.22` (or pinning to `1.22`) will apply the fix.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| numpy | upgrade | 1.22 |  |

### Source passages the author was shown

**Passage `3719f243dccb`** — from `README.md`

```
.linuxfoundation.org/project/numpy)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/numpy/numpy/badge)](https://securityscorecards.dev/viewer/?uri=github.com/numpy/numpy)
[![Typing](https://img.shields.io/pypi/types/numpy)](https://pypi.org/project/numpy/)


NumPy is the fundamental package for scientific computing with Python.

- **Website:** https://numpy.org
- **Documentation:** https://numpy.org/doc
- **Mailing list:** https://mail.python.org/mailman/listinfo/numpy-discussion
- **Source code:** https://github.com/numpy/numpy
- **Contributing:** https://numpy.org/devdocs/dev/index.html
- **Bug reports:** https://github.com/numpy/numpy/issues
- **Report a security vulnerability:** https://github.com/numpy/numpy/security/policy (via Tidelift)

It provides:

- a powerful N-dimensional array object
- sophisticated (broadcasting) functions
- tools for integrating C/C++ and Fortran code
- useful linear algebra, Fourier transform, and random number capabilities

Testing:
```

**Passage `cd3bb4167107`** — from `README.md`

```
duct/) for guidance on how to interact
with others in a way that makes our community thrive.

Call for Contributions
----------------------

The NumPy project welcomes your expertise and enthusiasm!

Small improvements or fixes are always appreciated. If you are considering larger contributions
to the source code, please contact us through the [mailing
list](https://mail.python.org/mailman/listinfo/numpy-discussion) first.

Writing code isn’t the only way to contribute to NumPy. You can also:
- review pull requests
- help us stay on top of new and old issues
- develop tutorials, presentations, and other educational materials
- maintain and improve [our website](https://github.com/numpy/numpy.org)
- develop graphic design for our brand assets and promotional materials
- translate website content
- help with outreach and onboard new contributors
- write grant proposals and help with other fundraising efforts
```

**Passage `f9e160c710db`** — from `README.md`

```
<h1 align="center">
<img src="https://raw.githubusercontent.com/numpy/numpy/main/branding/logo/primary/numpylogo.svg" width="300">
</h1><br>


[![Powered by NumFOCUS](https://img.shields.io/badge/powered%20by-NumFOCUS-orange.svg?style=flat&colorA=E1523D&colorB=007D8A)](
https://numfocus.org)
[![PyPI Downloads](https://img.shields.io/pypi/dm/numpy.svg?label=PyPI%20downloads)](
https://pypi.org/project/numpy/)
[![Conda Downloads](https://img.shields.io/conda/dn/conda-forge/numpy.svg?label=Conda%20downloads)](
https://anaconda.org/conda-forge/numpy)
[![Stack Overflow](https://img.shields.io/badge/stackoverflow-Ask%20questions-blue.svg)](
https://stackoverflow.com/questions/tagged/numpy)
[![Nature Paper](https://img.shields.io/badge/DOI-10.1038%2Fs41586--020--2649--2-blue)](
https://doi.org/10.1038/s41586-020-2649-2)
[![LFX Health Score](https://insights.linuxfoundation.org/api/badge/health-score?project=numpy)](https://insights.linuxfoundation.org/project/numpy)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/numpy/numpy/badge)](https://securityscorecards.dev/viewer/?uri=github.com/numpy/numpy)
```

**Passage `ba147ce8b41d`** — from `README.md`

```
ic design for our brand assets and promotional materials
- translate website content
- help with outreach and onboard new contributors
- write grant proposals and help with other fundraising efforts

For more information about the ways you can contribute to NumPy, visit [our website](https://numpy.org/contribute/). 
If you’re unsure where to start or how your skills fit in, reach out! You can
ask on the mailing list or here, on GitHub, by opening a new issue or leaving a
comment on a relevant issue that is already open.

Our preferred channels of communication are all public, but if you’d like to
speak to us in private first, contact our community coordinators at
numpy-team@googlegroups.com or on Slack (write numpy-team@googlegroups.com for
an invitation).

We also have a biweekly community call, details of which are announced on the
mailing list. You are very welcome to join.

If you are new to contributing to open source, [this
guide](https://opensource.guide/how-to-contribute/) helps explain why, what,
and how to successfully get involved.
```

**Passage `145e38203050`** — from `README.md`

```
-dimensional array object
- sophisticated (broadcasting) functions
- tools for integrating C/C++ and Fortran code
- useful linear algebra, Fourier transform, and random number capabilities

Testing:

NumPy requires `pytest`. In addition, there are a number of optional test
dependencies, like Meson for testing the NumPy C API, Cython for testing the
NumPy Cython API, and Hypothesis for additional property-based tests.

Tests can then be run after installation with:

    python -c "import numpy, sys; sys.exit(numpy.test() is False)"

Code of Conduct
----------------------

NumPy is a community-driven open source project developed by a diverse group of
[contributors](https://numpy.org/teams/). The NumPy leadership has made a strong
commitment to creating an open, inclusive, and positive community. Please read the
[NumPy Code of Conduct](https://numpy.org/code-of-conduct/) for guidance on how to interact
with others in a way that makes our community thrive.

Call for Contributions
----------------------

The NumPy project welcomes your expertise and enthusiasm!
```


---

## ITEM-003

**Dependency:** `h11` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 0.14.0
- Declared specifier: ==0.14.0
- Where that version came from: pinned
- Manifest: requirements-lock.txt
- Dependency group: runtime
- Latest release on the registry: 0.16.0
- Versions behind the latest release: major 0, minor 2, patch 0
- Days since the package's latest release: 531
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2025-43859 / GHSA-vqfr-h8mv-ghfj: severity critical, CVSS 9.1, fixed in 0.16.0
  - CVE-2025-43859 / PYSEC-2026-348: severity critical, CVSS 9.1, fixed in 0.16.0

### Remediation to label

Your project pins h11 at version 0.14.0, which is flagged as **critical** (CVE‑2025‑43859) and has a fix in version 0.16.0. Upgrading the `requirements-lock.txt` entry to `h11==0.16.0` will resolve the vulnerability. h11 is a low‑level HTTP/1.1 toolkit rather than a full client library, so the upgrade does not change its API surface [ b1a30cd2b9c3 ].

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| h11 | upgrade | 0.16.0 |  |

### Source passages the author was shown

**Passage `b1a30cd2b9c3`** — from `README.rst`

```
he
benefits of this approach
<https://lukasa.co.uk/2015/10/The_New_Hyper/>`_, or if you like video
then here's his `PyCon 2016 talk on the same theme
<https://www.youtube.com/watch?v=7cC3_jGwl_U>`_.

This also means that h11 is not immediately useful out of the box:
it's a toolkit for building programs that speak HTTP, not something
that could directly replace ``requests`` or ``twisted.web`` or
whatever. But h11 makes it much easier to implement something like
``requests`` or ``twisted.web``.

At a high level, working with h11 goes like this:

1) First, create an ``h11.Connection`` object to track the state of a
   single HTTP/1.1 connection.

2) When you read data off the network, pass it to
   ``conn.receive_data(...)``; you'll get back a list of objects
   representing high-level HTTP "events".

3) When you want to send a high-level HTTP event, create the
   corresponding "event" object and pass it to ``conn.send(...)``;
   this will give you back some bytes that you can then push out
   through the network.
```

**Passage `da53d06b58e5`** — from `README.rst`

```
hedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

This is a little HTTP/1.1 library written from scratch in Python,
heavily inspired by `hyper-h2 <https://hyper-h2.readthedocs.io/>`_.

It's a "bring-your-own-I/O" library; h11 contains no IO code
whatsoever. This means you can hook h11 up to your favorite network
API, and that could be anything you want: synchronous, threaded,
asynchronous, or your own implementation of `RFC 6214
<https://tools.ietf.org/html/rfc6214>`_ -- h11 won't judge you.
(Compare this to the current state of the art, where every time a `new
network API <https://trio.readthedocs.io/>`_ comes along then someone
gets to start over reimplementing the entire HTTP protocol from
scratch.) Cory Benfield made an `excellent blog post describing the
benefits of this approach
<https://lukasa.co.uk/2015/10/The_New_Hyper/>`_, or if you like video
then here's his `PyCon 2016 talk on the same theme
<https://www.youtube.com/watch?v=7cC3_jGwl_U>`_.
```

**Passage `5244f7e80256`** — from `README.rst`

```
h11
===

.. image:: https://travis-ci.org/python-hyper/h11.svg?branch=master
   :target: https://travis-ci.org/python-hyper/h11
   :alt: Automated test status

.. image:: https://codecov.io/gh/python-hyper/h11/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/python-hyper/h11
   :alt: Test coverage

.. image:: https://readthedocs.org/projects/h11/badge/?version=latest
   :target: http://h11.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

This is a little HTTP/1.1 library written from scratch in Python,
heavily inspired by `hyper-h2 <https://hyper-h2.readthedocs.io/>`_.
```

**Passage `25f74e8a5b04`** — from `README.rst`

```
ry it?*

.. code-block:: sh

  $ pip install h11
  $ git clone git@github.com:python-hyper/h11
  $ cd h11/examples
  $ python basic-client.py

and go from there.

*License?*

MIT

*Code of conduct?*

Contributors are requested to follow our `code of conduct
<https://github.com/python-hyper/h11/blob/master/CODE_OF_CONDUCT.md>`_ in
all project spaces.
```

**Passage `349ed7b3eff7`** — from `README.rst`

```
to support the
full specification in the sense that any useful HTTP/1.1 conformant
application should be able to use h11.

It's pure Python, and has no dependencies outside of the standard
library.

It has a test suite with 100.0% coverage for both statements and
branches.

Currently it supports Python 3 (testing on 3.8-3.12) and PyPy 3.
The last Python 2-compatible version was h11 0.11.x.
(Originally it had a Cython wrapper for `http-parser
<https://github.com/nodejs/http-parser>`_ and a beautiful nested state
machine implemented with ``yield from`` to postprocess the output. But
I had to take these out -- the new *parser* needs fewer lines-of-code
than the old *parser wrapper*, is written in pure Python, uses no
exotic language syntax, and has more features. It's sad, really; that
old state machine was really slick. I just need a few sentences here
to mourn that.)
```


---

## ITEM-004

**Dependency:** `flag-icon-css` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 3.5.0
- Declared specifier: 3.5.0
- Where that version came from: pinned
- Manifest: package.json
- Dependency group: runtime
- Latest release on the registry: 4.1.7
- Versions behind the latest release: major 1, minor 0, patch 0
- Days since the package's latest release: 1757
- Deprecated on the registry: yes
- Registry deprecation message: The project has been renamed to flag-icons
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `flag-icon-css` package is deprecated because it was renamed to **flag-icons**. To keep using the flag icons you should replace `flag-icon-css` with the `flag-icons` package, upgrading to at least version 5.0.0 where the rename was introduced. The migration also requires updating CSS class names from `flag-icon`/`flag-icon-[xx]` to `fi`/`fi-[xx]` as noted in the changelog. After updating the `package.json` and any import paths, run your install command to fetch the new package.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| flag-icon-css | replace | 5.0.0 | flag-icons |

### Source passages the author was shown

**Passage `184943b1248b`** — from `CHANGELOG.md`

```
# 5.0.0
- The package name changed from `flag-icon-css` to `flag-icons`
- The class names changed from `flag-icon` `flag-icon-[xx]` to `fi` `fi-[xx]`
```

**Passage `6064313b7e73`** — from `CHANGELOG.md`

```
# 7.4.0
- Migrate SASS imports to @use-based code (#1356)
- Modern and minimalist UI redesign with new features (#1358)
- Fix flag of Palestine (#1366)
```

**Passage `6f97fb1db8fd`** — from `CHANGELOG.md`

```
# 6.7.0
- Fix blurry US flag in Safari (#1096)
- Correcting Tunisia flag to match post 1999 shape updates (#1090)
- Correct green color in Saudi Arabia flag (#1080)
- Remove mix-blend-mode from Georgia flag (#1079)
- Fix flag of Malaysia (#1058)
- Fix Antigua and Barbuda flags (#1066)
- Add cefta flag to stylesheets (#1065)
- Fix flag of Kazakhstan (#1056)
- Fix flag of Dominican Republic (#1052)
- Add flag for Basque Country (#1050)
- Fix colors of Cuban flag (#1044)
- Fix Nepali flag should be transparent (#1034)
- Added CDN (#1032)
```

**Passage `7361b8023007`** — from `CHANGELOG.md`

```
# 6.11.2
- Fix French flags color to use the official ones (#1163)
```

**Passage `38f5d1507133`** — from `CHANGELOG.md`

```
# 6.6.5
- Fix Albania flag colors (Issue #1028)
- Fix South Africa flag colors (Issue #1020)
```


---

## ITEM-005

**Dependency:** `jsoneditor` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 9.1.9
- Declared specifier: ^9.1.9
- Where that version came from: lockfile
- Manifest: web/package.json
- Dependency group: runtime
- Latest release on the registry: 10.4.3
- Versions behind the latest release: major 1, minor 9, patch 1
- Days since the package's latest release: 189
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2021-3822 / GHSA-hhfg-6hfc-rvxm: severity medium, CVSS 5.3, fixed in 9.5.6

### Remediation to label

The project is using **jsoneditor** v9.1.9, which is flagged as vulnerable (CVE‑2021‑3822). The advisory data lists a fixed version of 9.5.6, and a newer release 10.4.3 is available. No documentation or changelog passages were retrieved to confirm the fix details, so the safest step is to upgrade to at least the fixed version. Updating the dependency in *web/package.json* will eliminate the known vulnerability and bring you closer to the latest release.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| jsoneditor | upgrade | 9.5.6 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-006

**Dependency:** `scikit-learn` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.0
- Declared specifier: ==1.0
- Where that version came from: pinned
- Manifest: docker/requirements.txt
- Dependency group: runtime
- Latest release on the registry: 1.9.1
- Versions behind the latest release: major 0, minor 9, patch 2
- Days since the package's latest release: 27
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 3
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 3
  - CVE-2020-28975 / GHSA-jxfp-4rvq-9h9m: severity high, CVSS 7.5, fixed in 1.0.1
  - CVE-2024-5206 / GHSA-jw8x-6495-233v: severity medium, CVSS 5.3, fixed in 1.5.0
  - CVE-2024-5206 / PYSEC-2024-110: severity medium, CVSS 4.7, fixed in 1.5.0

### Remediation to label

The scan flags **scikit-learn==1.0** as vulnerable, listing three advisories (including a high‑severity CVE‑2020‑28975). No changelog or migration notes were retrieved, so we cannot point to a specific release that addresses these issues. The package’s latest version on PyPI is **1.9.1**, and upgrading to that version will apply all available fixes and improvements. Updating the pinned requirement in *docker/requirements.txt* is therefore the recommended remediation.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| scikit-learn | upgrade | 1.9.1 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-007

**Dependency:** `@babel/core` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 7.9.6
- Declared specifier: ^7.8.6
- Where that version came from: lockfile
- Manifest: app/package.json
- Dependency group: development
- Latest release on the registry: 8.0.7
- Versions behind the latest release: major 1, minor 20, patch 0
- Days since the package's latest release: 0
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: low
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2026-49356 / GHSA-4x5r-pxfx-6jf8: severity low, CVSS 3.2, fixed in 8.0.0-rc.6

### Remediation to label

Your project is using @babel/core 7.9.6, which is flagged as vulnerable (CVE‑2026‑49356). The advisory indicates the issue is fixed starting with version 8.0.0‑rc.6, so upgrading to at least that release (or the current latest 8.0.7) will resolve the problem. Moving to Babel 8 is a major version bump and introduces breaking changes such as the removal of `preset‑env`’s `useBuiltIns` [#18079] and the removal of corejs2/legacy files from compat‑data [#17633] 【fdc085acc09a】【ee5d6774d733】. After upgrading, test your build pipeline for any required migration steps.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @babel/core | upgrade | 8.0.0-rc.6 |  |

### Source passages the author was shown

**Passage `124a02a8352c`** — from `CHANGELOG.md`

```
#### :house: Internal
hub.com/babel/babel/pull/17569) Add `BABEL_7_TO_8_DANGEROUSLY_DISABLE_VERSION_CHECK` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-helpers`, `babel-runtime-corejs3`, `babel-runtime`
  * [#17661](https://github.com/babel/babel/pull/17661) Remove `@onlyBabel7` helpers ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-core`, `babel-generator`, `babel-helper-create-class-features-plugin`, `babel-helper-skip-transparent-expression-wrappers`, `babel-plugin-transform-flow-comments`, `babel-plugin-transform-for-of`, `babel-plugin-transform-typescript`
  * [#17651](https://github.com/babel/babel/pull/17651) cleanup `@ts-expect-error(Babel 7 vs Babel 8)` comments (Part 1) ([@JLHwung](https://github.com/JLHwung))
* `babel-code-frame`
  * [#17645](https://github.com/babel/babel/pull/17645) Bump js-tokens to v10 ([@fisker](https://github.com/fisker))
* `babel-parser`
  * [#17641](https://github.com/babel/babel/pull/17641) [Babel 8] Parser cleanup ([@JLHwung](https://github.com/JLHwung))
* `babel-core`, `babel-traverse`
  * [#17638](https://github.com/babel/babel/pull/17638) refactor: replace debug with obug ([@sxzz](https://github.com/sxzz))
```

**Passage `fdc085acc09a`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
* `babel-core`, `babel-plugin-transform-object-rest-spread`, `babel-plugin-transform-runtime`, `babel-preset-env`, `babel-standalone`
  * [#18079](https://github.com/babel/babel/pull/18079) Actually remove `preset-env`'s `useBuiltIns` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```

**Passage `ee5d6774d733`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
ompilation-targets`, `babel-preset-env`
  * [#17633](https://github.com/babel/babel/pull/17633) Remove corejs2 and legacy files from compat-data ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-runtime-corejs3`, `babel-runtime`
  * [#17635](https://github.com/babel/babel/pull/17635) Remove `./regenerator` entrypoint from `@babel/runtime` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-generator`, `babel-parser`, `babel-types`
  * [#17610](https://github.com/babel/babel/pull/17610) [babel 8] Rename `TSImportType.argument` to `.source` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-generator`, `babel-parser`, `babel-plugin-proposal-import-attributes-to-assertions`, `babel-plugin-proposal-import-wasm-source`, `babel-plugin-transform-json-modules`, `babel-types`
  * [#17603](https://github.com/babel/babel/pull/17603) [babel 8] Fully remove import assertions ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-generator`, `babel-plugin-proposal-pipeline-operator`, `babel-plugin-proposal-record-and-tuple`, `babel-plugin-syntax-record-and-tuple`, `babel-standalone`, `babel-traverse`, `babel-types`
```

**Passage `8fb592a54b60`** — from `CHANGELOG.md`

```
#### :bug: Bug Fix
* `babel-traverse`, `babel-types`
  * [#17499](https://github.com/babel/babel/pull/17499) Enable `strictNullChecks` for `traverse` ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
* `babel-plugin-transform-runtime`
  * [#17512](https://github.com/babel/babel/pull/17512) [babel 8] Update default `@babel/runtime` version ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```

**Passage `077e7189ea56`** — from `CHANGELOG.md`

```
#### :house: Internal
* [#18018](https://github.com/babel/babel/pull/18018) ci: enforce yarn integrity ([@JLHwung](https://github.com/JLHwung))
```


---

## ITEM-008

**Dependency:** `scipy` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.9.3
- Declared specifier: ==1.9.3
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 1.18.1
- Versions behind the latest release: major 0, minor 9, patch 0
- Days since the package's latest release: 47
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: unknown
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2023-25399 / PYSEC-2023-102: severity unknown, CVSS not recorded, fixed in 1.10.0

### Remediation to label

The SciPy 1.10.0 release is marked as the fixed version for CVE‑2023‑25399, so upgrading from the current 1.9.3 resolves the vulnerability. Updating the `requirements.txt` entry to `scipy==1.10.0` (or any newer version such as the latest 1.18.1) will apply the fix. The README excerpts do not describe any breaking changes or special migration steps for this release, so you should run your test suite after the upgrade to catch any unexpected issues. If you need a newer version for other reasons, you can safely target the latest available release.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| scipy | upgrade | 1.10.0 |  |

### Source passages the author was shown

**Passage `c9e5c04a7750`** — from `README.rst`

```
org/doc/scipy/dev/conduct/code_of_conduct.html
- **Report a security vulnerability:** via Tidelift, as explained in
  `our docs on Security <https://scipy.github.io/devdocs/tutorial/security.html>`__
- **Citing in your work:** https://www.scipy.org/citing-scipy/

SciPy is built to work with
NumPy arrays, and provides many user-friendly and efficient numerical routines,
such as routines for numerical integration and optimization. Together, they
run on all popular operating systems, are quick to install, and are free of
charge. NumPy and SciPy are easy to use, but powerful enough to be depended
upon by some of the world's leading scientists and engineers. If you need to
manipulate numbers on a computer and display or publish the results, give
SciPy a try!

For the installation instructions, see `our install
guide <https://scipy.org/install/>`__.


Call for Contributions
----------------------
```

**Passage `5000442d4577`** — from `README.rst`

```
uter and display or publish the results, give
SciPy a try!

For the installation instructions, see `our install
guide <https://scipy.org/install/>`__.


Call for Contributions
----------------------

We appreciate and welcome contributions. Small improvements or fixes are always appreciated; issues labeled as "good
first issue" may be a good starting point. Have a look at `our contributing
guide <https://scipy.github.io/devdocs/dev/index.html>`__ and familiarize yourself
with `our AI policy <https://scipy.github.io/devdocs/dev/conduct/ai_policy.html>`__.

Writing code isn’t the only way to contribute to SciPy. You can also:

- review pull requests
- triage issues
- develop tutorials, presentations, and other educational materials
- maintain and improve `our website <https://github.com/scipy/scipy.org>`__
- develop graphic design for our brand assets and promotional materials
- help with outreach and onboard new contributors
- write grant proposals and help with other fundraising efforts
```

**Passage `ad970dd734f1`** — from `README.rst`

```
https://www.nature.com/articles/s41592-019-0686-2

.. image:: https://insights.linuxfoundation.org/api/badge/health-score?project=scipy
  :target: https://insights.linuxfoundation.org/project/scipy

SciPy (pronounced "Sigh Pie") is an open-source software for mathematics,
science, and engineering. It includes modules for statistics, optimization,
integration, linear algebra, Fourier transforms, signal and image processing,
ODE solvers, and more.

- **Website:** https://scipy.org
- **Documentation:** https://docs.scipy.org/doc/scipy/
- **Development version of the documentation:** https://scipy.github.io/devdocs
- **SciPy development forum:** https://discuss.scientific-python.org/c/contributor/scipy
- **Stack Overflow:** https://stackoverflow.com/questions/tagged/scipy
- **Source code:** https://github.com/scipy/scipy
- **Contributing:** https://scipy.github.io/devdocs/dev/index.html
- **Bug reports:** https://github.com/scipy/scipy/issues
- **Code of Conduct:** https://docs.scipy.org/doc/scipy/dev/conduct/code_of_conduct.html
- **Report a security vulnerability:** via Tidelift, as explained in
  `our docs on Security <https://scipy.github.io/devdocs/tutorial/security.html>`__
```

**Passage `355f2e607626`** — from `README.rst`

```
.. image:: https://raw.githubusercontent.com/scipy/scipy/main/doc/source/_static/logo.svg
  :target: https://scipy.org
  :width: 110
  :height: 110
  :align: left

.. image:: https://img.shields.io/badge/powered%20by-NumFOCUS-orange.svg?style=flat&colorA=E1523D&colorB=007D8A
  :target: https://numfocus.org

.. image:: https://img.shields.io/pypi/dm/scipy.svg?label=Pypi%20downloads
  :target: https://pypi.org/project/scipy/

.. image:: https://img.shields.io/conda/dn/conda-forge/scipy.svg?label=Conda%20downloads
  :target: https://anaconda.org/conda-forge/scipy

.. image:: https://img.shields.io/badge/stackoverflow-Ask%20questions-blue.svg?
  :target: https://stackoverflow.com/questions/tagged/scipy

.. image:: https://img.shields.io/badge/DOI-10.1038%2Fs41592--019--0686--2-blue.svg?
  :target: https://www.nature.com/articles/s41592-019-0686-2

.. image:: https://insights.linuxfoundation.org/api/badge/health-score?project=scipy
  :target: https://insights.linuxfoundation.org/project/scipy
```

**Passage `87fed58478cc`** — from `README.rst`

```
cipy.org>`__
- develop graphic design for our brand assets and promotional materials
- help with outreach and onboard new contributors
- write grant proposals and help with other fundraising efforts

If you’re unsure where to start or how your skills fit in, reach out! You can
ask on the `forum <https://discuss.scientific-python.org/c/contributor/scipy>`__
or here, on GitHub, by leaving a comment on a relevant issue that is already
open.

If you are new to contributing to open source, `this
guide <https://opensource.guide/how-to-contribute/>`__ helps explain why, what,
and how to get involved.
```


---

## ITEM-009

**Dependency:** `@babel/traverse` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 7.17.9
- Declared specifier: 7.17.9
- Where that version came from: pinned
- Manifest: packages/core/package.json
- Dependency group: development
- Latest release on the registry: 8.0.7
- Versions behind the latest release: major 1, minor 12, patch 2
- Days since the package's latest release: 0
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2023-45133 / GHSA-67hx-6x53-jw92: severity critical, CVSS 9.3, fixed in 7.23.2

### Remediation to label

The advisory CVE‑2023‑45133 flags @babel/traverse 7.17.9 as critical and is fixed in version 7.23.2 according to the advisory data. Upgrading the dependency in *packages/core/package.json* to at least 7.23.2 will resolve the vulnerability. The changelog excerpts do not mention this version or any specific migration steps, but they do note a breaking change introduced in Babel 8 (e.g., removal of record and tuple syntax support) 【a7ee65dccf17】. If you plan to move to the latest major version 8.x, review those breaking changes; otherwise a direct upgrade to 7.23.2 should be safe.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @babel/traverse | upgrade | 7.23.2 |  |

### Source passages the author was shown

**Passage `a7d05a4cd351`** — from `CHANGELOG.md`

```
#### :bug: Bug Fix
* `babel-traverse`
  * [#18122](https://github.com/babel/babel/pull/18122) fix: `replaceWith` in `Visitor#exit` should not stop traversal ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
```

**Passage `8fb592a54b60`** — from `CHANGELOG.md`

```
#### :bug: Bug Fix
* `babel-traverse`, `babel-types`
  * [#17499](https://github.com/babel/babel/pull/17499) Enable `strictNullChecks` for `traverse` ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
* `babel-plugin-transform-runtime`
  * [#17512](https://github.com/babel/babel/pull/17512) [babel 8] Update default `@babel/runtime` version ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```

**Passage `124a02a8352c`** — from `CHANGELOG.md`

```
#### :house: Internal
hub.com/babel/babel/pull/17569) Add `BABEL_7_TO_8_DANGEROUSLY_DISABLE_VERSION_CHECK` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-helpers`, `babel-runtime-corejs3`, `babel-runtime`
  * [#17661](https://github.com/babel/babel/pull/17661) Remove `@onlyBabel7` helpers ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-core`, `babel-generator`, `babel-helper-create-class-features-plugin`, `babel-helper-skip-transparent-expression-wrappers`, `babel-plugin-transform-flow-comments`, `babel-plugin-transform-for-of`, `babel-plugin-transform-typescript`
  * [#17651](https://github.com/babel/babel/pull/17651) cleanup `@ts-expect-error(Babel 7 vs Babel 8)` comments (Part 1) ([@JLHwung](https://github.com/JLHwung))
* `babel-code-frame`
  * [#17645](https://github.com/babel/babel/pull/17645) Bump js-tokens to v10 ([@fisker](https://github.com/fisker))
* `babel-parser`
  * [#17641](https://github.com/babel/babel/pull/17641) [Babel 8] Parser cleanup ([@JLHwung](https://github.com/JLHwung))
* `babel-core`, `babel-traverse`
  * [#17638](https://github.com/babel/babel/pull/17638) refactor: replace debug with obug ([@sxzz](https://github.com/sxzz))
```

**Passage `a7ee65dccf17`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
, `babel-traverse`
  * [#17242](https://github.com/babel/babel/pull/17242) [Babel 8]: Remove record and tuple syntax support ([@JLHwung](https://github.com/JLHwung))
* `babel-traverse`, `babel-types`
  * [#17217](https://github.com/babel/babel/pull/17217) Harden variable declarator validations ([@JLHwung](https://github.com/JLHwung))
* _All packages_
  * [#17204](https://github.com/babel/babel/pull/17204) [Babel 8] Bump nodejs requirements to `^20.19.0 || >= 22.12.0` ([@JLHwung](https://github.com/JLHwung))
* `babel-helper-compilation-targets`, `babel-preset-env`
  * [#17188](https://github.com/babel/babel/pull/17188) [Babel 8] Align esmodules: true behaviour to intersect ([@JLHwung](https://github.com/JLHwung))
```

**Passage `facd44b25dd2`** — from `CHANGELOG.md`

```
#### :bug: Bug Fix
* `babel-types`
  * [#17398](https://github.com/babel/babel/pull/17398) fix: `BABEL_TYPES_8_BREAKING` in Babel 8 ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
```


---

## ITEM-010

**Dependency:** `transformers` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 4.45.2
- Declared specifier: ==4.45.2
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 5.19.0
- Versions behind the latest release: major 1, minor 12, patch 0
- Days since the package's latest release: 1
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 44
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-5241 / PYSEC-2026-2290: severity critical, CVSS 9.6, fixed in unknown
  - CVE-2024-11394 / GHSA-hxxf-235m-72v3: severity high, CVSS 8.8, fixed in 4.48.0
  - CVE-2024-11393 / GHSA-wrfc-pvp9-mr9g: severity high, CVSS 8.8, fixed in 4.48.0
  - CVE-2024-11392 / PYSEC-2024-227: severity high, CVSS 8.8, fixed in 4.48.0
  - CVE-2024-11393 / PYSEC-2024-228: severity high, CVSS 8.8, fixed in 4.48.0

### Remediation to label

The advisory list shows that versions 4.48.0 of **transformers** fix several high‑severity CVEs (CVE‑2024‑11394, CVE‑2024‑11393, CVE‑2024‑11392) that affect the current 4.45.2 release. Upgrading to at least 4.48.0 will resolve those vulnerabilities, though a critical CVE (CVE‑2026‑5241) remains unfixed. The repository’s README does not provide release‑specific notes or breaking‑change information for the 4.48.0 update, so you should consult the official changelog for any migration concerns. You can upgrade via pip (e.g., `pip install "transformers==4.48.0"`) or to a newer stable version if desired.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| transformers | upgrade | 4.48.0 |  |

### Source passages the author was shown

**Passage `edef8e3be7d3`** — from `README.md`

```
## 100 projects using Transformers
Transformers is more than a toolkit to use pretrained models, it's a community of projects built around it and the
Hugging Face Hub. We want Transformers to enable developers, researchers, students, professors, engineers, and anyone
else to build their dream projects.

In order to celebrate Transformers 100,000 stars, we wanted to put the spotlight on the
community with the [awesome-transformers](./awesome-transformers.md) page which lists 100
incredible projects built with Transformers.

If you own or use a project that you believe should be part of the list, please open a PR to add it!
```

**Passage `e0ecd36cedb3`** — from `README.md`

```
## Why should I use Transformers?
roduce the results published by its original authors.
    - Model internals are exposed as consistently as possible.
    - Model files can be used independently of the library for quick experiments.

<a target="_blank" href="https://huggingface.co/enterprise">
    <img alt="Hugging Face Enterprise Hub" src="https://github.com/user-attachments/assets/247fb16d-d251-4583-96c4-d3d76dda4925">
</a><br>
```

**Passage `71623625e5d7`** — from `README.md`

```
## Installation
Transformers works with Python 3.10+, and [PyTorch](https://pytorch.org/get-started/locally/) 2.5+.

Create and activate a virtual environment with [venv](https://docs.python.org/3/library/venv.html) or [uv](https://docs.astral.sh/uv/), a fast Rust-based Python package and project manager.

```py
# venv
python -m venv .my-env
source .my-env/bin/activate
# uv
uv venv .my-env
source .my-env/bin/activate
```

Install Transformers in your virtual environment.

```py
# pip
pip install "transformers[torch]"

# uv
uv pip install "transformers[torch]"
```

Install Transformers from source if you want the latest changes in the library or are interested in contributing. However, the *latest* version may not be stable. Feel free to open an [issue](https://github.com/huggingface/transformers/issues) if you encounter an error.

```shell
git clone https://github.com/huggingface/transformers.git
cd transformers

# pip
pip install '.[torch]'

# uv
uv pip install '.[torch]'
```
```

**Passage `ba349d848ead`** — from `README.md`

```
"/>
</h3>

Transformers acts as the model-definition framework for state-of-the-art machine learning with text, computer
vision, audio, video, and multimodal models, for both inference and training.

It centralizes the model definition so that this definition is agreed upon across the ecosystem. `transformers` is the
pivot across frameworks: if a model definition is supported, it will be compatible with the majority of training
frameworks (Axolotl, Unsloth, DeepSpeed, FSDP, PyTorch-Lightning, ...), inference engines (vLLM, SGLang, TGI, ...),
and adjacent modeling libraries (llama.cpp, mlx, ...) which leverage the model definition from `transformers`.

We pledge to help support new state-of-the-art models and democratize their usage by having their model definition be
simple, customizable, and efficient.

There are over 1M+ Transformers [model checkpoints](https://huggingface.co/models?library=transformers&sort=trending) on the [Hugging Face Hub](https://huggingface.co/models) you can use.

Explore the [Hub](https://huggingface.co/) today to find a model and use Transformers to help you get started right away.
```

**Passage `aaef9c4b2aaf`** — from `README.md`

```
## Quickstart
cup of flour, 1 cup of milk, 1 cup of butter, 1 cup of eggs, 1 cup of chocolate chips. if you want to make 2 cakes, how much sugar do you need? To make 2 cakes, you will need 2 cups of sugar.'}]
```

To chat with a model, the usage pattern is the same. The only difference is you need to construct a chat history (the input to `Pipeline`) between you and the system.

> [!TIP]
> You can also chat with a model directly from the command line, as long as [`transformers serve` is running](https://huggingface.co/docs/transformers/main/en/serving).
> ```shell
> transformers chat Qwen/Qwen2.5-0.5B-Instruct
> ```

```py
import torch
from transformers import pipeline

chat = [
    {"role": "system", "content": "You are a sassy, wise-cracking robot as imagined by Hollywood circa 1986."},
    {"role": "user", "content": "Hey, can you tell me any fun things to do in New York?"}
]

pipeline = pipeline(task="text-generation", model="meta-llama/Meta-Llama-3-8B-Instruct", dtype=torch.bfloat16, device_map="auto")
response = pipeline(chat, max_new_tokens=512)
print(response[0]["generated_text"][-1]["content"])
```
```


---

## ITEM-011

**Dependency:** `@nestjs/common` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 8.3.1
- Declared specifier: ^8.0.0
- Where that version came from: lockfile
- Manifest: api/package.json
- Dependency group: runtime
- Latest release on the registry: 12.1.2
- Versions behind the latest release: major 4, minor 1, patch 0
- Days since the package's latest release: 7
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2024-29409 / GHSA-cj7v-w2c7-cp7c: severity medium, CVSS 5.5, fixed in 11.0.16

### Remediation to label

The project is using **@nestjs/common** v8.3.1, which is flagged as vulnerable (CVE‑2024‑29409). The advisory indicates the issue is fixed in version **11.0.16**. Upgrading the dependency to at least 11.0.16 will resolve the vulnerability; you may also consider moving to the latest 12.1.2 if compatible. The repository’s README does not provide details on breaking changes for this upgrade, so review the official NestJS changelog for any migration notes before updating.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @nestjs/common | upgrade | 11.0.16 |  |

### Source passages the author was shown

**Passage `d16ba275076a`** — from `Readme.md`

```
## Issues
Please make sure to read the [Issue Reporting Checklist](https://github.com/nestjs/nest/blob/master/CONTRIBUTING.md#-submitting-an-issue) before opening an issue. Issues not conforming to the guidelines may be closed immediately.
```

**Passage `9e079cffb1b8`** — from `Readme.md`

```
## Support
Nest is an MIT-licensed open source project. It can grow thanks to the sponsors and support from the amazing backers. If you'd like to join them, please [read more here](https://docs.nestjs.com/support).
```

**Passage `cdf2a7975896`** — from `Readme.md`

```
## Consulting
With official support, you can get expert help straight from the Nest core team. We provide dedicated technical support, migration strategies, advice on best practices (and design decisions), PR reviews, and team augmentation. Read more about [support here](https://enterprise.nestjs.com).
```

**Passage `b3586101eea4`** — from `Readme.md`

```
<p align="center">
  <a href="https://nestjs.com/" target="_blank"><img src="https://nestjs.com/img/logo-small.svg" width="120" alt="Nest Logo" /></a>
</p>

[circleci-image]: https://img.shields.io/circleci/build/github/nestjs/nest/master?token=abc123def456
[circleci-url]: https://circleci.com/gh/nestjs/nest

  <p align="center">A progressive <a href="https://nodejs.org" target="_blank">Node.js</a> framework for building efficient and scalable server-side applications.</p>
    <p align="center">
<a href="https://www.npmjs.com/~nestjscore" target="_blank"><img src="https://img.shields.io/npm/v/@nestjs/core.svg" alt="NPM Version" /></a>
<a href="https://github.com/nestjs/nest/blob/master/LICENSE" target="_blank"><img src="https://img.shields.io/npm/l/@nestjs/core.svg" alt="Package License" /></a>
<a href="https://www.npmjs.com/~nestjscore" target="_blank"><img src="https://img.shields.io/npm/dm/@nestjs/common.svg" alt="NPM Downloads" /></a>
<a href="https://circleci.com/gh/nestjs/nest" target="_blank"><img src="https://img.shields.io/circleci/build/github/nestjs/nest/master" alt="CircleCI" /></a>
```

**Passage `346dba365083`** — from `Readme.md`

```
## Observability
[NestJS Observe](https://observe.nestjs.com) is the official observability platform for Nest applications. Install the `@nestjs/observe` SDK, pass an API key, and requests, background jobs, errors, logs, and distributed traces start streaming to a dashboard - no manual span wiring and no collector to run. Because the SDK hooks into Nest's own request lifecycle, a trace reads like a call graph of your controllers and providers instead of a bare HTTP route. Free for up to 300,000 events a month, and there is a [live demo](https://www.observe-demo.nestjs.com/dashboard) with no signup.
```


---

## ITEM-012

**Dependency:** `@clerk/clerk-react` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 4.30.3
- Declared specifier: ^4.16.2
- Where that version came from: lockfile
- Manifest: package.json
- Dependency group: runtime
- Latest release on the registry: 5.61.3
- Versions behind the latest release: major 1, minor 2, patch 7
- Deprecated on the registry: yes
- Registry deprecation message: This package is no longer supported. Please use @clerk/react instead. See the upgrade guide for more info: https://clerk.com/docs/guides/development/upgrading/upgrade-guides/core-3
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated
- Advisories in detail (highest CVSS first): none

### Remediation to label

The scan flags **@clerk/clerk-react** as deprecated (deprecation_reason: “This package is no longer supported. Please use @clerk/react instead.”). The package is currently at version 4.30.3 and a newer 5.61.3 release exists, but the deprecation notice indicates the library is not maintained any longer. No retrieved documentation was found to confirm a migration path or that the newer version resolves the deprecation. The safest remediation is to replace **@clerk/clerk-react** with the actively‑supported **@clerk/react** package.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @clerk/clerk-react | replace |  | @clerk/react |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-013

**Dependency:** `jsonwebtoken` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 8.3.0
- Declared specifier: 8.3.0
- Where that version came from: lockfile
- Manifest: services/backend/auth-server/package.json
- Dependency group: runtime
- Latest release on the registry: 9.0.3
- Versions behind the latest release: major 1, minor 2, patch 0
- Days since the package's latest release: 307
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 3
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 3
  - CVE-2022-23539 / GHSA-8cf7-32gw-wr33: severity high, CVSS 8.1, fixed in 9.0.0
  - CVE-2022-23540 / GHSA-qwph-4952-7xr6: severity medium, CVSS 6.4, fixed in 9.0.0
  - CVE-2022-23541 / GHSA-hjrf-2m68-5959: severity medium, CVSS 5.0, fixed in 9.0.0

### Remediation to label

The `jsonwebtoken@8.3.0` version you are using is vulnerable to three CVEs that are fixed in version 9.0.0. Upgrading the dependency in `services/backend/auth-server/package.json` to at least `9.0.0` (the latest 9.0.3) will resolve the security issues. Version 9.0.0 introduces breaking changes, so you should follow the migration guide from v8 to v9 before upgrading.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| jsonwebtoken | upgrade | 9.0.0 |  |

### Source passages the author was shown

**Passage `88dd4568902f`** — from `CHANGELOG.md`

```
## 9.0.0 - 2022-12-21
**Breaking changes: See [Migration from v8 to v9](https://github.com/auth0/node-jsonwebtoken/wiki/Migration-Notes:-v8-to-v9)**
```

**Passage `5e7b85188dca`** — from `CHANGELOG.md`

```
## 8.2.2 - 2018-05-30
- security: deps: jws@3.1.5 (#477) ([ebde9b7cc75cb7ab5176de7ebc4a1d6a8f05bd51](https://github.com/auth0/node-jsonwebtoken/commit/ebde9b7cc75cb7ab5176de7ebc4a1d6a8f05bd51)), closes [#465](https://github.com/auth0/node-jsonwebtoken/issues/465)
 - docs: add some clarifications (#473) ([cd33cc81f06068b9df6c224d300dc6f70d8904ab](https://github.com/auth0/node-jsonwebtoken/commit/cd33cc81f06068b9df6c224d300dc6f70d8904ab)), closes [#473](https://github.com/auth0/node-jsonwebtoken/issues/473)
 - ci: fix ci execution, remove not needed script (#472) ([c8ff7b2c3ffcd954a64a0273c20a7d1b22339aa5](https://github.com/auth0/node-jsonwebtoken/commit/c8ff7b2c3ffcd954a64a0273c20a7d1b22339aa5)), closes [#472](https://github.com/auth0/node-jsonwebtoken/issues/472)
 - docs: Update README.md (#461) ([f0e0954505f274da95a8d9603598e455b4d2c894](https://github.com/auth0/node-jsonwebtoken/commit/f0e0954505f274da95a8d9603598e455b4d2c894)), closes [#461](https://github.com/auth0/node-jsonwebtoken/issues/461)
```

**Passage `b284103c6513`** — from `CHANGELOG.md`

```
### Security
token`.

 > Important: versions >= 4.2.2 this library are safe to use but we decided to deprecate everything `< 5.0.0` to prevent security warnings from library `node-jws` when doing `npm install`.

  https://github.com/auth0/node-jsonwebtoken/commit/634b8ed0ff5267dc25da5c808634208af109824e
  https://github.com/auth0/node-jsonwebtoken/commit/9f24ffd5791febb449d4d03ff58d7807da9b9b7e
  https://github.com/auth0/node-jsonwebtoken/commit/19e6cc6a1f2fd90356f89b074223b9665f2aa8a2
  https://github.com/auth0/node-jsonwebtoken/commit/1e4623420159c6410616f02a44ed240f176287a9
  https://github.com/auth0/node-jsonwebtoken/commit/954bd7a312934f03036b6bb6f00edd41f29e54d9
  https://github.com/auth0/node-jsonwebtoken/commit/24a370080e0b75f11d4717cd2b11b2949d95fc2e
  https://github.com/auth0/node-jsonwebtoken/commit/a77df6d49d4ec688dfd0a1cc723586bffe753516
```

**Passage `1e00eb1b8f83`** — from `CHANGELOG.md`

```
## 7.2.1 - 2016-12-07
- add nsp check to find vulnerabilities on npm test ([4219c34b5346811c07f520f10516cc495bcc70dd](https://github.com/auth0/node-jsonwebtoken/commit/4219c34b5346811c07f520f10516cc495bcc70dd))
 - revert to joi@^6 to keep ES5 compatibility ([51d4796c07344bf817687f7ccfeef78f00bf5b4f](https://github.com/auth0/node-jsonwebtoken/commit/51d4796c07344bf817687f7ccfeef78f00bf5b4f))
```

**Passage `50f30132186d`** — from `CHANGELOG.md`

```
### Bug Fixes
- Updating Node version in Engines spec in package.json (#528) ([cfd1079305170a897dee6a5f55039783e6ee2711](https://github.com/auth0/node-jsonwebtoken/commit/cfd1079305170a897dee6a5f55039783e6ee2711)), closes [#528](https://github.com/auth0/node-jsonwebtoken/issues/528) [#509](https://github.com/auth0/node-jsonwebtoken/issues/509)
 - Fixed error message when empty string passed as expiresIn or notBefore option (#531) ([7f9604ac98d4d0ff8d873c3d2b2ea64bd285cb76](https://github.com/auth0/node-jsonwebtoken/commit/7f9604ac98d4d0ff8d873c3d2b2ea64bd285cb76)), closes [#531](https://github.com/auth0/node-jsonwebtoken/issues/531)
```


---

## ITEM-014

**Dependency:** `sqlparse` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 0.4.1
- Declared specifier: ==0.4.1
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 0.6.0
- Versions behind the latest release: major 0, minor 2, patch 3
- Days since the package's latest release: 55
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 17
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2024-4340 / GHSA-2m57-hf25-phgg: severity high, CVSS 7.5, fixed in 0.5.0
  - CVE-2021-32839 / GHSA-p5w8-wqhj-9hhf: severity high, CVSS 7.5, fixed in 0.4.2
  - CVE-2026-59893 / GHSA-prg7-hcfm-mfcr: severity high, CVSS 7.5, fixed in 0.6.0
  - CVE-2024-4340 / PYSEC-2026-1940: severity high, CVSS 7.5, fixed in 0.5.0
  - CVE-2026-59893 / PYSEC-2026-3698: severity high, CVSS 7.5, fixed in 0.6.0

### Remediation to label

The project is using sqlparse 0.4.1, which is vulnerable to CVE‑2024‑4340. Upgrading to **sqlparse 0.5.0** resolves this denial‑of‑service issue – the release notes state it *"Fixes a potential denial of service attack (DOS) due to recursion error for deeply nested statements"*【3ecd17565546】. The upgrade also drops support for Python 3.5‑3.7 and adds support for Python 3.12, so the environment must run a newer Python version (≥3.8). No breaking API changes are mentioned besides added `encoding` keyword support, so the upgrade should be straightforward after confirming Python compatibility.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| sqlparse | upgrade | 0.5.0 |  |

### Source passages the author was shown

**Passage `cb6e80cba6b1`** — from `CHANGELOG`

```
* Improve Python 2/3 compatibility when using parsestream (issue190,
  by phdru).
* Improve splitting of PostgreSQL functions (issue277).


Release 0.2.0 (Jul 20, 2016)
----------------------------

IMPORTANT: The supported Python versions have changed with this release.
sqlparse 0.2.x supports Python 2.7 and Python >= 3.3.

Thanks to the many contributors for writing bug reports and working
on pull requests who made this version possible!

Internal Changes

* sqlparse.SQLParseError was removed from top-level module and moved to
  sqlparse.exceptions.
* sqlparse.sql.Token.to_unicode was removed.
* The signature of a filter's process method has changed from
  process(stack, stream) -> to process(stream). Stack was never used at
  all.
* Lots of code cleanups and modernization (thanks esp. to vmuriart!).
* Improved grouping performance. (sjoerdjob)

Enhancements
```

**Passage `c20877864301`** — from `CHANGELOG`

```
ssified as an identifier
  when it is followed by a float literal written without a leading zero, so
  that `x BETWEEN .03 AND .06` parses its bounds as numbers (issue601, pr868
  by deepakganesh78).
* Fix a late-binding closure bug in `TokenList.token_not_matching`.

Other

* Migrate project dependencies and environment management from `pixi` to `uv`.
* Replace `flake8` with `ruff` for code checking and linting.
* The README is now written in Markdown and the documentation uses an
  updated theme.


Release 0.5.5 (Dec 19, 2025)
----------------------------

Bug Fixes

* Fix DoS protection to raise SQLParseError instead of silently returning None
  when grouping limits are exceeded (issue827).
* Fix splitting of BEGIN TRANSACTION statements (issue826).


Release 0.5.4 (Nov 28, 2025)
----------------------------

Enhancements
```

**Passage `3ecd17565546`** — from `CHANGELOG`

```
expressions (issue782).
* Fix parsing and formatting of ORDER clauses containing NULLS FIRST or
  NULLS LAST (issue532).


Release 0.5.0 (Apr 13, 2024)
----------------------------

Notable Changes

* Drop support for Python 3.5, 3.6, and 3.7.
* Python 3.12 is now supported (pr725, by hugovk).
* IMPORTANT: Fixes a potential denial of service attack (DOS) due to recursion
  error for deeply nested statements. Instead of recursion error a generic
  SQLParseError is raised. See the security advisory for details:
  https://github.com/andialbrecht/sqlparse/security/advisories/GHSA-2m57-hf25-phgg
  The vulnerability was discovered by @uriyay-jfrog. Thanks for reporting!

Enhancements
```

**Passage `1ebf01c01973`** — from `CHANGELOG`

```
yshev).
* Fix a bug where keywords were identified as aliased identifiers in
  invalid SQL statements.
* Fix parsing of identifier lists where identifiers are keywords too
  (issue10).

Enhancements

* Top-level API functions now accept encoding keyword to parse
  statements in certain encodings more reliable (issue20).
* Improve parsing speed when SQL contains CLOBs or BLOBs (issue86).
* Improve formatting of ORDER BY clauses (issue89).
* Formatter now tries to detect runaway indentations caused by
  parsing errors or invalid SQL statements. When re-indenting such
  statements the formatter flips back to column 0 before going crazy.

Other

* Documentation updates.


Release 0.1.6 (Jan 01, 2013)
----------------------------

sqlparse is now compatible with Python 3 without any patches. The
Python 3 version is generated during install by 2to3. You'll need
distribute to install sqlparse for Python 3.

Bug Fixes

* Fix parsing error with dollar-quoted procedure bodies (issue83).

Other

* Documentation updates.
* Test suite now uses tox and pytest.
* py3k fixes (by vthriller).
* py3k fixes in setup.py (by Florian Bauer).
* setup.py now requires distribute (by Florian Bauer).
```

**Passage `ae92fa921d43`** — from `CHANGELOG`

```
t).
* IMPORTANT: Fixes a potential denial of service attack (DOS) in
  `format(sql, reindent=True)`, which consumed CPU quadratically on long
  lists of tuples. See the security advisory for details:
  https://github.com/andialbrecht/sqlparse/security/advisories/GHSA-cfqr-cjx5-5jcm
* IMPORTANT: Fixes a potential denial of service attack (DOS) on statements
  that consist only of comments (CVE-2026-71491). See the security advisory
  for details:
  https://github.com/andialbrecht/sqlparse/security/advisories/GHSA-f2ff-p2ww-7p4p
  The vulnerability was discovered by @sanktjodel. Thanks for reporting!
* IMPORTANT: Backslashes are now escaped in the `python` and `php` output
  formats. Without escaping, SQL containing a backslash could break out of
  the generated string literal (CVE-2026-59894). See the security advisory
  for details:
  https://github.com/andialbrecht/sqlparse/security/advisories/GHSA-3496-9g83-7v6x
  The vulnerability was discovered by @7thParkk. Thanks for reporting!

Enhancements

* Modernize type annotations in top-level API functions using PEP 585 and
  PEP 604 syntax.
* `END FOR` and `END CASE` are now recognized as keywords.

Bug Fixes
```


---

## ITEM-015

**Dependency:** `pandas` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 0.23.0
- Declared specifier: >=0.19.0
- Where that version came from: lockfile
- Manifest: Pipfile
- Dependency group: runtime
- Latest release on the registry: 3.0.6
- Versions behind the latest release: major 3, minor 2, patch 4
- Days since the package's latest release: 20
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: unknown
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2020-13091 / PYSEC-2020-73: severity unknown, CVSS not recorded, fixed in 1.0.4

### Remediation to label

The scan flagged pandas 0.23.0 as vulnerable (CVE‑2020‑13091). The advisory data indicates the issue is fixed starting with version 1.0.4, and a newer release 3.0.6 is available. Upgrade pandas in the Pipfile to at least 1.0.4, preferably the latest 3.0.6, to resolve the vulnerability. No documentation was retrieved to describe any migration steps or breaking changes, so review the pandas release notes after upgrading.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| pandas | upgrade | 3.0.6 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-016

**Dependency:** `pillow` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 5.0.0
- Declared specifier: ==5.0.0
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 12.3.0
- Versions behind the latest release: major 7, minor 4, patch 0
- Days since the package's latest release: 98
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 101
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2021-25289 / GHSA-57h3-9rgr-c24m: severity critical, CVSS 9.8, fixed in 8.1.1
  - CVE-2021-34552 / GHSA-7534-mm45-c74v: severity critical, CVSS 9.8, fixed in 8.3.0
  - CVE-2022-22817 / GHSA-8vj2-vxx3-667w: severity critical, CVSS 9.8, fixed in 9.0.1
  - CVE-2020-5312 / GHSA-p49h-hjvm-jg3h: severity critical, CVSS 9.8, fixed in 6.2.2
  - CVE-2020-5311 / GHSA-r7rm-8j6h-r933: severity critical, CVSS 9.8, fixed in 6.2.2

### Remediation to label

The project pins Pillow at version 5.0.0, which is affected by several critical CVEs (e.g., CVE‑2021‑25289 fixed in 8.1.1, CVE‑2021‑34552 fixed in 8.3.0, CVE‑2022‑22817 fixed in 9.0.1, and CVE‑2020‑5311/5312 fixed in 6.2.2). All of these fixes are included in newer releases, and the latest available version on PyPI is 12.3.0. Upgrading Pillow in *requirements.txt* to at least the latest version will eliminate the known vulnerabilities. The README links to the official release notes and changelog where the security fixes are documented【6388558f1cc9】. After updating, run your test suite to verify compatibility with the newer Pillow API.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| pillow | upgrade | 12.3.0 |  |

### Source passages the author was shown

**Passage `6388558f1cc9`** — from `README.md`

```
## More information
- [Documentation](https://pillow.readthedocs.io/)
  - [Installation](https://pillow.readthedocs.io/en/latest/installation/basic-installation.html)
  - [Handbook](https://pillow.readthedocs.io/en/latest/handbook/index.html)
- [Contribute](https://github.com/python-pillow/Pillow/blob/main/.github/CONTRIBUTING.md)
  - [Issues](https://github.com/python-pillow/Pillow/issues)
  - [Pull requests](https://github.com/python-pillow/Pillow/pulls)
- [Release notes](https://pillow.readthedocs.io/en/stable/releasenotes/index.html)
- [Changelog](https://github.com/python-pillow/Pillow/releases)
  - [Pre-fork](https://github.com/python-pillow/Pillow/blob/main/CHANGES.rst#pre-fork)
```

**Passage `8aa9bfef944a`** — from `README.md`

```
## Python Imaging Library (Fork)
Pillow is the friendly PIL fork by [Jeffrey 'Alex' Clark and
contributors](https://github.com/python-pillow/Pillow/graphs/contributors).
PIL is the Python Imaging Library by Fredrik Lundh and contributors.
Development is supported by:
- [Tidelift](https://tidelift.com/lifter/search/pypi/pillow) (since 2018)
- [Thanks.dev](https://thanks.dev) (since 2023)
- [GitHub Sponsors](https://github.com/sponsors/python-pillow) (since 2026)

<table>
    <tr>
        <th>docs</th>
        <td>
            <a href="https://pillow.readthedocs.io/?badge=latest"><img
                alt="Documentation Status"
                src="https://readthedocs.org/projects/pillow/badge/?version=latest"></a>
        </td>
    </tr>
    <tr>
        <th>tests</th>
        <td>
            <a href="https://github.com/python-pillow/Pillow/actions/workflows/lint.yml"><img
                alt="GitHub Actions build status (Lint)"
                src="https://github.com/python-pillow/Pillow/workflows/Lint/badge.svg"></a>
            <a href="https://github.com/python-pillow/Pillow/actions/workflows/test.yml"><img
                alt="GitHub Actions build status (Test Linux and macOS)"
```

**Passage `8742e04922d3`** — from `README.md`

```
## Report a vulnerability
To report sensitive vulnerability information, report it [privately on GitHub](https://github.com/python-pillow/Pillow/security/advisories/new).

If you cannot use GitHub, use the [Tidelift security contact](https://tidelift.com/security). Tidelift will coordinate the fix and disclosure.

DO NOT report sensitive vulnerability information in public.
```

**Passage `c9d74b523fbd`** — from `README.md`

```
## Python Imaging Library (Fork)
lt="Zenodo"
                src="https://zenodo.org/badge/17549/python-pillow/Pillow.svg"></a>
            <a href="https://tidelift.com/lifter/search/pypi/pillow"><img
                alt="Tidelift"
                src="https://tidelift.com/badges/package/pypi/pillow?style=flat"></a>
            <a href="https://pypi.org/project/pillow/"><img
                alt="Newest PyPI version"
                src="https://img.shields.io/pypi/v/pillow.svg"></a>
            <a href="https://pypi.org/project/pillow/"><img
                alt="Number of PyPI downloads"
                src="https://img.shields.io/pypi/dm/pillow.svg"></a>
            <a href="https://www.bestpractices.dev/projects/6331"><img
                alt="OpenSSF Best Practices"
                src="https://www.bestpractices.dev/projects/6331/badge"></a>
        </td>
    </tr>
    <tr>
        <th>social</th>
        <td>
            <a href="https://gitter.im/python-pillow/Pillow?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge"><img
                alt="Join the chat at https://gitter.im/python-pillow/Pillow"
                src="https://badges.gitter.im/python-pillow/Pillow.svg"></a>
```

**Passage `3e0967fa79b9`** — from `README.md`

```
<p align="center">
    <img width="248" height="250" src="https://raw.githubusercontent.com/python-pillow/pillow-logo/main/pillow-logo-248x250.png" alt="Pillow logo">
</p>
```


---

## ITEM-017

**Dependency:** `black` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 18.6b4
- Declared specifier: ==18.6b4
- Where that version came from: pinned
- Manifest: Pipfile
- Dependency group: development
- Latest release on the registry: 26.10.0
- Versions behind the latest release: major 5, minor 0, patch 0
- Days since the package's latest release: 3
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 4
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 4
  - CVE-2026-31900 / PYSEC-2026-2120: severity critical, CVSS 9.8, fixed in 26.3.0
  - CVE-2026-32274 / PYSEC-2026-2121: severity high, CVSS 7.5, fixed in 26.3.1
  - CVE-2024-21503 / GHSA-fj7x-q9j7-g6q6: severity medium, CVSS 5.3, fixed in 24.3.0
  - CVE-2024-21503 / PYSEC-2024-48: severity unknown, CVSS not recorded, fixed in 24.3.0

### Remediation to label

Black 18.6b4 is vulnerable to several CVEs, including CVE‑2024‑21503. The project's changelog states that a milestone release fixes this CVE and strongly encourages upgrading [5989badaffec]. Updating the Black dependency in your Pipfile to a newer, non‑vulnerable version will eliminate the issue. Preferably upgrade to the latest available version.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| black | upgrade |  |  |

### Source passages the author was shown

**Passage `12f276e8eb54`** — from `CHANGES.md`

```
### Packaging
<!-- Changes to how Black is packaged, such as dependency requirements -->
```

**Passage `5989badaffec`** — from `CHANGES.md`

```
### Highlights
This release is a milestone: it fixes Black's first CVE security vulnerability. If you
run Black on untrusted input, or if you habitually put thousands of leading tab
characters in your docstrings, you are strongly encouraged to upgrade immediately to fix
[CVE-2024-21503](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-21503).

This release also fixes a bug in Black's AST safety check that allowed Black to make
incorrect changes to certain f-strings that are valid in Python 3.12 and higher.
```

**Passage `2d48d6b9d642`** — from `CHANGES.md`

```
### _Blackd_
- Fix blackd (and all extras installs) for docker container (#4357)
```

**Passage `44e2daea5161`** — from `CHANGES.md`

```
### Highlights
It's almost 2024, which means it's time for a new edition of _Black_'s stable style!
Together with this release, we'll put out an alpha release 24.1a1 showcasing the draft
2024 stable style, which we'll finalize in the January release. Please try it out and
[share your feedback](https://github.com/psf/black/issues/4042).

This release (23.12.0) will still produce the 2023 style. Most but not all of the
changes in `--preview` mode will be in the 2024 stable style.
```

**Passage `6284e8cfda04`** — from `CHANGES.md`

```
### Stable style
- Don't move comments along with delimiters, which could cause crashes (#4248)
- Strengthen AST safety check to catch more unsafe changes to strings. Previous versions
  of Black would incorrectly format the contents of certain unusual f-strings containing
  nested strings with the same quote type. Now, Black will crash on such strings until
  support for the new f-string syntax is implemented. (#4270)
- Fix a bug where line-ranges exceeding the last code line would not work as expected
  (#4273)
```


---

## ITEM-018

**Dependency:** `markdown` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 2.6.11
- Declared specifier: ==2.6.11
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 3.11
- Versions behind the latest release: major 1, minor 0, patch 0
- Days since the package's latest release: 12
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2025-69534 / GHSA-5wmx-573v-2qwq: severity medium, CVSS 7.5, fixed in 3.8.1
  - CVE-2025-69534 / PYSEC-2026-89: severity high, CVSS 7.5, fixed in unknown

### Remediation to label

The scan flags **markdown 2.6.11** as vulnerable (high severity). Advisory data shows a fixed version of **3.8.1**, and the package’s latest release is 3.11. No documentation was retrieved, so migration details are unavailable. Upgrade the pinned requirement to at least 3.8.1 (or the newest 3.11) to resolve the issue.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| markdown | upgrade | 3.8.1 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-019

**Dependency:** `typed-ast` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.1.0
- Declared specifier: ==1.1.0
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 1.5.5
- Versions behind the latest release: major 0, minor 4, patch 2
- Days since the package's latest release: 1191
- Deprecated on the registry: yes
- Registry deprecation message: Development Status :: 7 - Inactive
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: unknown
- Why it was flagged: deprecated, vulnerable, stale
- Advisories in detail (highest CVSS first): 2
  - CVE-2019-19274 / PYSEC-2019-130: severity unknown, CVSS not recorded, fixed in 1.3.2
  - CVE-2019-19275 / PYSEC-2019-131: severity unknown, CVSS not recorded, fixed in 1.3.2

### Remediation to label

typed-ast 1.1.0 is deprecated and has two known CVEs. The advisories list version 1.3.2 as the first release that fixes the issues, and a newer 1.5.5 release is available. Because the package’s own changelog was not retrieved, we cannot confirm the exact changes, but upgrading to at least 1.3.2 (or the latest 1.5.5) will resolve the vulnerabilities. Update the pinned requirement in requirements.txt accordingly.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| typed-ast | upgrade | 1.3.2 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-020

**Dependency:** `sqlparse` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 0.4.1
- Declared specifier: ==0.4.1
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 0.6.0
- Versions behind the latest release: major 0, minor 2, patch 3
- Days since the package's latest release: 55
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 17
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2024-4340 / GHSA-2m57-hf25-phgg: severity high, CVSS 7.5, fixed in 0.5.0
  - CVE-2021-32839 / GHSA-p5w8-wqhj-9hhf: severity high, CVSS 7.5, fixed in 0.4.2
  - CVE-2026-59893 / GHSA-prg7-hcfm-mfcr: severity high, CVSS 7.5, fixed in 0.6.0
  - CVE-2024-4340 / PYSEC-2026-1940: severity high, CVSS 7.5, fixed in 0.5.0
  - CVE-2026-59893 / PYSEC-2026-3698: severity high, CVSS 7.5, fixed in 0.6.0

### Remediation to label

The project pins **sqlparse==0.4.1**, which is vulnerable to several high‑severity CVEs (CVE‑2024‑4340, CVE‑2021‑32839, CVE‑2026‑59893). The 0.5.0 release introduced a fix for the denial‑of‑service issue (recursion error) that addresses CVE‑2024‑4340 【3ecd17565546】, and later releases (0.6.0) contain the remaining security patches. Upgrading sqlparse to the latest version 0.6.0 (or at least 0.5.0) removes all known vulnerabilities. Update the version constraint in **requirements.txt** accordingly.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| sqlparse | upgrade | 0.6.0 |  |

### Source passages the author was shown

**Passage `cb6e80cba6b1`** — from `CHANGELOG`

```
* Improve Python 2/3 compatibility when using parsestream (issue190,
  by phdru).
* Improve splitting of PostgreSQL functions (issue277).


Release 0.2.0 (Jul 20, 2016)
----------------------------

IMPORTANT: The supported Python versions have changed with this release.
sqlparse 0.2.x supports Python 2.7 and Python >= 3.3.

Thanks to the many contributors for writing bug reports and working
on pull requests who made this version possible!

Internal Changes

* sqlparse.SQLParseError was removed from top-level module and moved to
  sqlparse.exceptions.
* sqlparse.sql.Token.to_unicode was removed.
* The signature of a filter's process method has changed from
  process(stack, stream) -> to process(stream). Stack was never used at
  all.
* Lots of code cleanups and modernization (thanks esp. to vmuriart!).
* Improved grouping performance. (sjoerdjob)

Enhancements
```

**Passage `c20877864301`** — from `CHANGELOG`

```
ssified as an identifier
  when it is followed by a float literal written without a leading zero, so
  that `x BETWEEN .03 AND .06` parses its bounds as numbers (issue601, pr868
  by deepakganesh78).
* Fix a late-binding closure bug in `TokenList.token_not_matching`.

Other

* Migrate project dependencies and environment management from `pixi` to `uv`.
* Replace `flake8` with `ruff` for code checking and linting.
* The README is now written in Markdown and the documentation uses an
  updated theme.


Release 0.5.5 (Dec 19, 2025)
----------------------------

Bug Fixes

* Fix DoS protection to raise SQLParseError instead of silently returning None
  when grouping limits are exceeded (issue827).
* Fix splitting of BEGIN TRANSACTION statements (issue826).


Release 0.5.4 (Nov 28, 2025)
----------------------------

Enhancements
```

**Passage `b7b75d38d399`** — from `CHANGELOG`

```
SE ... WHEN (issue580).
* Improve formatting of type casts in parentheses.
* Stabilize formatting of invalid SQL statements.


Release 0.3.1 (Feb 29, 2020)
----------------------------

Enhancements

* Add HQL keywords (pr475, by matwalk).
* Add support for time zone casts (issue489).
* Enhance formatting of AS keyword (issue507, by john-bodley).
* Stabilize grouping engine when parsing invalid SQL statements.

Bug Fixes

* Fix splitting of SQL with multiple statements inside
  parentheses (issue485, pr486 by win39).
* Correctly identify NULLS FIRST / NULLS LAST as keywords (issue487).
* Fix splitting of SQL statements that contain dollar signs in
  identifiers (issue491).
* Remove support for parsing double slash comments introduced in
  0.3.0 (issue456) as it had some side-effects with other dialects and
  doesn't seem to be widely used (issue476).
* Restrict detection of alias names to objects that actually could
  have an alias (issue455, adopted some parts of pr509 by john-bodley).
* Fix parsing of date/time literals (issue438, by vashek).
* Fix initialization of TokenList (issue499, pr505 by john-bodley).
* Fix parsing of LIKE (issue493, pr525 by dbczumar).
```

**Passage `1ebf01c01973`** — from `CHANGELOG`

```
yshev).
* Fix a bug where keywords were identified as aliased identifiers in
  invalid SQL statements.
* Fix parsing of identifier lists where identifiers are keywords too
  (issue10).

Enhancements

* Top-level API functions now accept encoding keyword to parse
  statements in certain encodings more reliable (issue20).
* Improve parsing speed when SQL contains CLOBs or BLOBs (issue86).
* Improve formatting of ORDER BY clauses (issue89).
* Formatter now tries to detect runaway indentations caused by
  parsing errors or invalid SQL statements. When re-indenting such
  statements the formatter flips back to column 0 before going crazy.

Other

* Documentation updates.


Release 0.1.6 (Jan 01, 2013)
----------------------------

sqlparse is now compatible with Python 3 without any patches. The
Python 3 version is generated during install by 2to3. You'll need
distribute to install sqlparse for Python 3.

Bug Fixes

* Fix parsing error with dollar-quoted procedure bodies (issue83).

Other

* Documentation updates.
* Test suite now uses tox and pytest.
* py3k fixes (by vthriller).
* py3k fixes in setup.py (by Florian Bauer).
* setup.py now requires distribute (by Florian Bauer).
```

**Passage `3ecd17565546`** — from `CHANGELOG`

```
expressions (issue782).
* Fix parsing and formatting of ORDER clauses containing NULLS FIRST or
  NULLS LAST (issue532).


Release 0.5.0 (Apr 13, 2024)
----------------------------

Notable Changes

* Drop support for Python 3.5, 3.6, and 3.7.
* Python 3.12 is now supported (pr725, by hugovk).
* IMPORTANT: Fixes a potential denial of service attack (DOS) due to recursion
  error for deeply nested statements. Instead of recursion error a generic
  SQLParseError is raised. See the security advisory for details:
  https://github.com/andialbrecht/sqlparse/security/advisories/GHSA-2m57-hf25-phgg
  The vulnerability was discovered by @uriyay-jfrog. Thanks for reporting!

Enhancements
```


---

## ITEM-021

**Dependency:** `@opentelemetry/tracing` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 0.21.0
- Declared specifier: ^0.21.0
- Where that version came from: lockfile
- Manifest: web-app-teams/package.json
- Dependency group: runtime
- Latest release on the registry: 0.24.0
- Versions behind the latest release: major 0, minor 3, patch 0
- Days since the package's latest release: 1897
- Deprecated on the registry: yes
- Registry deprecation message: Package renamed to @opentelemetry/sdk-trace-base
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `@opentelemetry/tracing` package is deprecated and has been renamed to `@opentelemetry/sdk-trace-base` (see the deprecation reason). All tracing APIs, including samplers like `AlwaysOnSampler`, have moved to the new package ["eef3c282ae27"]. Additionally, the `sdk-trace-base` package (and its siblings) are being consolidated into the unified `@opentelemetry/sdk-trace` package, with a full migration guide in the 3.x docs ["075af08b2a8e","5b42f1588c8d"]. To keep your project up‑to‑date, replace imports of `@opentelemetry/tracing` with either `@opentelemetry/sdk-trace-base` now, or consider moving directly to `@opentelemetry/sdk-trace` for the longer‑term path.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @opentelemetry/tracing | replace |  | @opentelemetry/sdk-trace-base |

### Source passages the author was shown

**Passage `075af08b2a8e`** — from `CHANGELOG.md`

```
### :boom: Breaking Changes
* chore(sdk-trace-base, sdk-trace-web)!: remove the `@opentelemetry/sdk-trace-base` and `@opentelemetry/sdk-trace-web` packages [#7117](https://github.com/open-telemetry/opentelemetry-js/issues/7117)
  * The sdk-trace-base, sdk-trace-web, and sdk-trace-node packages have been replaced by the `@opentelemetry/sdk-trace` package.
    See the [3.x migration guide](doc/3.x/migration-guide.md) for full migration instructions.
```

**Passage `c4be2e1f1cb2`** — from `CHANGELOG.md`

```
### :boom: Breaking Changes
* chore(sdk-trace-node)!: remove the `@opentelemetry/sdk-trace-node` package [#7054](https://github.com/open-telemetry/opentelemetry-js/issues/7054)
  * The sdk-trace-node package has been replaced by the `@opentelemetry/sdk-trace` package.
    See the [3.x migration guide](doc/3.x/migration-guide.md) for full migration instructions.
* chore(shim-opentracing)!: remove the `@opentelemetry/shim-opentracing` package
  * In the [OpenTelemetry Specification v1.58.0](https://github.com/open-telemetry/opentelemetry-specification/releases/tag/v1.56.0) the [OpenTracing compatibility requirements were deprecated](https://github.com/open-telemetry/opentelemetry-specification/pull/4938). The JavaScript OpenTracing shim package will not receive any more releases after the current [2.11.0 release](https://www.npmjs.com/package/@opentelemetry/shim-opentracing/v/2.11.0) ([source code for last release](https://github.com/open-telemetry/opentelemetry-js/tree/v2.11.0/packages/opentelemetry-shim-opentracing/)).
* chore(context-async-hooks)!: remove the unused class `AsyncHooksContextManager` [#7078](https://github.com/open-telemetry/opentelemetry-js/pull/7078)
```

**Passage `eef3c282ae27`** — from `CHANGELOG.md`

```
### :boom: Breaking Change
ove deprecated samplers [#5316](https://github.com/open-telemetry/opentelemetry-js/pull/5316) @pichlermarc
  * (user-facing): deprecated `AlwaysOnSampler` has moved to `@opentelemetry/sdk-trace-base`
  * (user-facing): deprecated `AlwaysOffSampler` has moved to `@opentelemetry/sdk-trace-base`
  * (user-facing): deprecated `ParentBasedSampler` has moved to `@opentelemetry/sdk-trace-base`
  * (user-facing): deprecated `TraceIdRatioSampler` has moved to  `@opentelemetry/sdk-trace-base`
* feat(resource): Merge sync and async resource interfaces into a single interface [#5350](https://github.com/open-telemetry/opentelemetry-js/pull/5350) @dyladan
  * Resource constructor now takes a single argument which contains an optional `attributes` object
  * Detected resource attribute values may be a promise or a synchronous value
  * Resources are now merged by the order in which their detectors are configured instead of async attributes being last
  * Resource detectors now return `DetectedResource` plain objects instead of `new Resource()`
```

**Passage `5b42f1588c8d`** — from `CHANGELOG.md`

```
### :rocket: Features
belongs elsewhere [#6775](https://github.com/open-telemetry/opentelemetry-js/pull/6775) @trentm
  * "sdk-trace" will eventually replace all of "sdk-trace-base", "sdk-trace-node", and "sdk-trace-web".
  * The `BatchSpanProcessor` constructor call signature has changed in "sdk-trace".  For example, before `new BatchSpanProcessor(exporter, { maxQueueSize: 1000 })`, after `new BatchSpanProcessor({ exporter, maxQueueSize: 1000 })`. [#6817](https://github.com/open-telemetry/opentelemetry-js/pull/6817)
  * The `SimpleSpanProcessor` constructor call signature has changed in "sdk-trace".  For example, before `new SimpleSpanProcessor(exporter)`, after `new SimpleSpanProcessor({ exporter, selfObsMeterProvider: ... })`. [#6504](https://github.com/open-telemetry/opentelemetry-js/pull/6504)
* feat(sdk-trace): add AlwaysRecordSampler [#6188](https://github.com/open-telemetry/opentelemetry-js/pull/6188) @majanjua-amzn
```

**Passage `5741cf56d296`** — from `CHANGELOG.md`

```
### :house: Internal
* chore: remove `@opentelemetry/sdk-trace-web` package from examples and bundler tests [#7095](https://github.com/open-telemetry/opentelemetry-js/pull/7095)
* chore(sdk-trace): add `StackContextManager` in `@opentelemetry/sdk-trace` package [#7086](https://github.com/open-telemetry/opentelemetry-js/pull/7086)
* feat(ci): support releasing from maintenance branches [#6767](https://github.com/open-telemetry/opentelemetry-js/issues/6767) @pichlermarc
  * The API documentation site is only redeployed for releases whose commit is reachable from `main`, so a maintenance release no longer overwrites it.
* chore: don't close stale issues [#x](https://github.com/open-telemetry/opentelemetry-js/issues/x) @maryliag
* chore: mark the workspace root package as private [#7097](https://github.com/open-telemetry/opentelemetry-js/pull/7097) @overbalance
```


---

## ITEM-022

**Dependency:** `flask` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.0
- Declared specifier: ==1.0
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 3.1.3
- Versions behind the latest release: major 2, minor 1, patch 4
- Days since the package's latest release: 230
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 4
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 4
  - CVE-2023-30861 / GHSA-m2qf-hxjv-5gpq: severity high, CVSS 7.5, fixed in 2.3.2
  - CVE-2026-27205 / PYSEC-2026-2151: severity medium, CVSS 4.3, fixed in 3.1.3
  - CVE-2026-27205 / GHSA-68rp-wp8r-4726: severity low, CVSS not recorded, fixed in 3.1.3
  - CVE-2023-30861 / PYSEC-2023-62: severity unknown, CVSS not recorded, fixed in 2.3.2

### Remediation to label

The current Flask version 1.0 is vulnerable to CVE‑2023‑30861, which is fixed in Flask 2.3.2 according to the advisory data. Upgrading to 2.3.2 (or newer) will eliminate the high‑severity issue. The README excerpts do not describe the security changes or any breaking‑API impacts introduced in 2.3.2, so you should review the Flask changelog and run your test suite after upgrading. Because the fix addresses a high‑severity vulnerability, prioritize the upgrade promptly.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| flask | upgrade | 2.3.2 |  |

### Source passages the author was shown

**Passage `480204f7dfa8`** — from `README.md`

```
# Flask
Flask is a lightweight [WSGI] web application framework. It is designed
to make getting started quick and easy, with the ability to scale up to
complex applications. It began as a simple wrapper around [Werkzeug]
and [Jinja], and has become one of the most popular Python web
application frameworks.

Flask offers suggestions, but doesn't enforce any dependencies or
project layout. It is up to the developer to choose the tools and
libraries they want to use. There are many extensions provided by the
community that make adding new functionality easy.

[WSGI]: https://wsgi.readthedocs.io/
[Werkzeug]: https://werkzeug.palletsprojects.com/
[Jinja]: https://jinja.palletsprojects.com/
```

**Passage `2434079f1365`** — from `README.md`

```
<div align="center"><img src="https://raw.githubusercontent.com/pallets/flask/refs/heads/stable/docs/_static/flask-name.svg" alt="" height="150"></div>
```

**Passage `01276c07996e`** — from `README.md`

```
## Donate
The Pallets organization develops and supports Flask and the libraries
it uses. In order to grow the community of contributors and users, and
allow the maintainers to devote more time to the projects, [please
donate today].

[please donate today]: https://palletsprojects.com/donate
```

**Passage `5cbac76bb21c`** — from `README.md`

```
## A Simple Example
```python
# save this as app.py
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, World!"
```

```
$ flask run
  * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```
```

**Passage `be8a08d595d3`** — from `README.md`

```
## Contributing
See our [detailed contributing documentation][contrib] for many ways to
contribute, including reporting issues, requesting features, asking or answering
questions, and making PRs.

[contrib]: https://palletsprojects.com/contributing/
```


---

## ITEM-023

**Dependency:** `@azure/identity` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 1.5.1
- Declared specifier: ^1.3.0
- Where that version came from: lockfile
- Manifest: web-app-external/package.json
- Dependency group: runtime
- Latest release on the registry: 4.13.3
- Versions behind the latest release: major 3, minor 0, patch 1
- Days since the package's latest release: 23
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2024-35255 / GHSA-m5vv-6r4h-3vj9: severity medium, CVSS 5.5, fixed in 4.2.1

### Remediation to label

The scan reports a medium‑severity vulnerability (CVE‑2024‑35255) in @azure/identity v1.5.1. Upgrading to the latest 4.x release (currently 4.13.3) will move you past the vulnerable range. When upgrading, follow the Azure SDK migration guide for authentication code changes [0a84ee448aa2].

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @azure/identity | upgrade | 4.13.3 |  |

### Source passages the author was shown

**Passage `0a84ee448aa2`** — from `README.md`

```
### Management
DKs, including the intuitive Azure Identity library, an HTTP Pipeline with custom policies, error-handling, distributed tracing, and much more. A few helpful resources to get started with these are:

- [List of management libraries that follow the new guidelines](https://azure.github.io/azure-sdk/releases/latest/mgmt/js.html)
- [Documentation and code samples](https://aka.ms/azsdk/js/mgmt).
- [Migration guide](https://github.com/Azure/azure-sdk-for-js/blob/main/documentation/MIGRATION-guide-for-next-generation-management-libraries.md) that shows how to transition from older versions of libraries.

> NOTE: If you are experiencing authentication issues with the management libraries after upgrading certain packages, it's possible that you upgraded to the new versions of SDK without changing the authentication code, please refer to the migration guide mentioned above for proper instructions.
```

**Passage `947a726819f9`** — from `README.md`

```
### Management
Management libraries enable you to provision and manage Azure resources via the [Azure Resource Manager i.e. ARM](https://learn.microsoft.com/azure/azure-resource-manager/management/overview). You can recognize these libraries by `@azure/arm-` in their package names. These are purely auto-generated based on the swagger files that represent the APIs for resource management.

Newer versions of these libraries follow the [Azure SDK Design Guidelines for TypeScript](https://azure.github.io/azure-sdk/typescript_introduction.html). These new versions provide a number of core capabilities that are shared amongst all Azure SDKs, including the intuitive Azure Identity library, an HTTP Pipeline with custom policies, error-handling, distributed tracing, and much more. A few helpful resources to get started with these are:
```

**Passage `92e04009e7c7`** — from `README.md`

```
### Community
Try our [community resources](https://github.com/Azure/azure-sdk-for-js/blob/main/SUPPORT.md#community-resources).
```

**Passage `9c72fa6bcdf0`** — from `README.md`

```
## Need help?
- For detailed documentation, visit our [Azure SDK for JavaScript documentation](https://aka.ms/js-docs)
- File an issue via [GitHub Issues](https://github.com/Azure/azure-sdk-for-js/issues)
- Check [previous questions](https://stackoverflow.com/questions/tagged/azure-sdk-js) or ask new ones on StackOverflow using `azure-sdk-js` tag.
- Read our [Support documentation](https://github.com/Azure/azure-sdk-for-js/blob/main/SUPPORT.md).
```

**Passage `9ae8126a91b8`** — from `README.md`

```
### Telemetry Configuration
unction removeUserAgentPolicy() {
  return {
    name: "removeUserAgentPolicy",
    sendRequest(request, next) {
      request.headers.delete("User-Agent");
      return next(request);
    },
  };
}

/**
 * Creates a SecretClient with managed identity authentication and empty user agent
 * @param keyvaultUri - The URI of the Azure Key Vault
 * @returns configured SecretClient instance
 */
function createSecretClientWithManagedIdentity(
  keyvaultUri: string
): SecretClient {
  // Create ManagedIdentityCredential for managed identity authentication
  const credential = new ManagedIdentityCredential();

  // Create secret client with managed identity and empty user agent
  const secretClient = new SecretClient(keyvaultUri, credential, {
    additionalPolicies: [
      {
        position: "perCall",
        policy: removeUserAgentPolicy(),
      },
    ],
  });

  return secretClient;
}

// Usage example
const keyvaultUri = "https://your-keyvault-name.vault.azure.net";
const secretClient = createSecretClientWithManagedIdentity(keyvaultUri);
```


---

## ITEM-024

**Dependency:** `fastify` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 4.10.2
- Declared specifier: 4.10.2
- Where that version came from: pinned
- Manifest: apps/server/package.json
- Dependency group: runtime
- Latest release on the registry: 5.12.5
- Versions behind the latest release: major 1, minor 19, patch 0
- Days since the package's latest release: 21
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 9
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-84504 / GHSA-667r-xxjv-c9mm: severity high, CVSS 8.1, fixed in 5.12.2
  - CVE-2026-84428 / GHSA-9q9j-q6p8-xq58: severity high, CVSS 7.5, fixed in 5.12.2
  - CVE-2026-84469 / GHSA-hwr6-493r-vm6h: severity high, CVSS 7.5, fixed in 5.12.2
  - CVE-2026-25223 / GHSA-jx2c-rxcm-jvmq: severity high, CVSS 7.5, fixed in 5.7.2
  - CVE-2026-76169 / GHSA-p68q-wchp-6fh7: severity high, CVSS 7.5, fixed in 5.12.2

### Remediation to label

The project is using **fastify 4.10.2**, which is vulnerable to several high‑severity CVEs. All listed advisories are fixed in fastify 5.12.2 (one CVE is fixed in 5.7.2), so upgrading to the latest 5.12.5 will resolve the known issues. Because this is a major version bump, you should run your test suite after the upgrade to catch any breaking changes. No upstream migration notes were retrieved, so verify compatibility manually.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| fastify | upgrade | 5.12.5 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-025

**Dependency:** `flag-icon-css` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 3.5.0
- Declared specifier: 3.5.0
- Where that version came from: pinned
- Manifest: package.json
- Dependency group: runtime
- Latest release on the registry: 4.1.7
- Versions behind the latest release: major 1, minor 0, patch 0
- Days since the package's latest release: 1757
- Deprecated on the registry: yes
- Registry deprecation message: The project has been renamed to flag-icons
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The scan reports that **flag-icon-css** is deprecated. The registry data shows a newer version 4.1.7 is available, which may include fixes and the continuation of the project. Upgrading to this version is the primary remediation step. Because no documentation was retrieved, details about a rename or migration path are not available, so you should review the upstream repository for any additional guidance.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| flag-icon-css | upgrade | 4.1.7 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-026

**Dependency:** `stylelint-config-factorial` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 7.1.1
- Declared specifier: ^7.0.2
- Where that version came from: range_latest_approx
- Manifest: package.json
- Dependency group: development
- Latest release on the registry: 7.1.1
- Versions behind the latest release: major 0, minor 0, patch 0
- Days since the package's latest release: 3522
- Deprecated on the registry: yes
- Registry deprecation message: DEPRECATED: Please use stylelint-config-suitcss instead.
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The scan flags **stylelint-config-factorial** as deprecated and stale, and no documentation was retrieved to describe a migration path or replacement. Because there is no source information confirming a safe upgrade or successor, you should investigate the necessity of this package and consider removing it or switching to an alternative after further research.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| stylelint-config-factorial | investigate |  |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-027

**Dependency:** `passport` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 0.4.1
- Declared specifier: ^0.4.1
- Where that version came from: lockfile
- Manifest: api/package.json
- Dependency group: runtime
- Latest release on the registry: 0.7.0
- Versions behind the latest release: major 0, minor 3, patch 0
- Days since the package's latest release: 1045
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: medium
- Why it was flagged: vulnerable, stale
- Advisories in detail (highest CVSS first): 1
  - CVE-2022-25896 / GHSA-v923-w3x8-wh69: severity medium, CVSS 4.8, fixed in 0.6.0

### Remediation to label

The scan found a medium‑severity vulnerability (CVE‑2022‑25896) in **passport** 0.4.1 that is fixed in version 0.6.0 or later. Your project is still on 0.4.1 and the latest available release is 0.7.0. Because no upstream documentation was retrieved, the exact changes in the fix are not described here. Upgrade the dependency to the latest version (≥ 0.6.0) to resolve the issue and also reduce staleness.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| passport | upgrade | 0.7.0 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-028

**Dependency:** `certifi` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 2023.7.22
- Declared specifier: ==2023.7.22
- Where that version came from: pinned
- Manifest: test_requirements.txt
- Dependency group: development
- Latest release on the registry: 2026.7.22
- Versions behind the latest release: major 3, minor 1, patch 0
- Days since the package's latest release: 77
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2024-39689 / PYSEC-2024-230: severity high, CVSS 7.5, fixed in 2024.7.4
  - CVE-2024-39689 / GHSA-248v-346w-9cwc: severity low, CVSS not recorded, fixed in 2024.7.4

### Remediation to label

The pinned version `2023.7.22` of **certifi** is flagged as vulnerable (CVE‑2024‑39689). The advisory data lists version `2024.7.4` as the first release that fixes the issue. Upgrading the requirement in `test_requirements.txt` to at least `2024.7.4` will resolve the high‑severity vulnerability. No replacement package is indicated, but you may investigate a temporary mitigation if an upgrade is not immediately possible.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| certifi | upgrade | 2024.7.4 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-029

**Dependency:** `scipy` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.9.3
- Declared specifier: ==1.9.3
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 1.18.1
- Versions behind the latest release: major 0, minor 9, patch 0
- Days since the package's latest release: 47
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 1
- Highest advisory severity: unknown
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 1
  - CVE-2023-25399 / PYSEC-2023-102: severity unknown, CVSS not recorded, fixed in 1.10.0

### Remediation to label

The scan flagged SciPy 1.9.3 as vulnerable (CVE‑2023‑25399). The advisory data shows the issue is fixed starting with SciPy 1.10.0, and a newer 1.18.1 release is available. Upgrade the pinned version in requirements.txt to at least 1.10.0 (or the latest 1.18.1) to resolve the vulnerability. The project’s README does not provide specific migration notes or replacement guidance, so a straightforward version bump is the recommended action.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| scipy | upgrade | 1.10.0 |  |

### Source passages the author was shown

**Passage `5000442d4577`** — from `README.rst`

```
uter and display or publish the results, give
SciPy a try!

For the installation instructions, see `our install
guide <https://scipy.org/install/>`__.


Call for Contributions
----------------------

We appreciate and welcome contributions. Small improvements or fixes are always appreciated; issues labeled as "good
first issue" may be a good starting point. Have a look at `our contributing
guide <https://scipy.github.io/devdocs/dev/index.html>`__ and familiarize yourself
with `our AI policy <https://scipy.github.io/devdocs/dev/conduct/ai_policy.html>`__.

Writing code isn’t the only way to contribute to SciPy. You can also:

- review pull requests
- triage issues
- develop tutorials, presentations, and other educational materials
- maintain and improve `our website <https://github.com/scipy/scipy.org>`__
- develop graphic design for our brand assets and promotional materials
- help with outreach and onboard new contributors
- write grant proposals and help with other fundraising efforts
```

**Passage `c9e5c04a7750`** — from `README.rst`

```
org/doc/scipy/dev/conduct/code_of_conduct.html
- **Report a security vulnerability:** via Tidelift, as explained in
  `our docs on Security <https://scipy.github.io/devdocs/tutorial/security.html>`__
- **Citing in your work:** https://www.scipy.org/citing-scipy/

SciPy is built to work with
NumPy arrays, and provides many user-friendly and efficient numerical routines,
such as routines for numerical integration and optimization. Together, they
run on all popular operating systems, are quick to install, and are free of
charge. NumPy and SciPy are easy to use, but powerful enough to be depended
upon by some of the world's leading scientists and engineers. If you need to
manipulate numbers on a computer and display or publish the results, give
SciPy a try!

For the installation instructions, see `our install
guide <https://scipy.org/install/>`__.


Call for Contributions
----------------------
```

**Passage `ad970dd734f1`** — from `README.rst`

```
https://www.nature.com/articles/s41592-019-0686-2

.. image:: https://insights.linuxfoundation.org/api/badge/health-score?project=scipy
  :target: https://insights.linuxfoundation.org/project/scipy

SciPy (pronounced "Sigh Pie") is an open-source software for mathematics,
science, and engineering. It includes modules for statistics, optimization,
integration, linear algebra, Fourier transforms, signal and image processing,
ODE solvers, and more.

- **Website:** https://scipy.org
- **Documentation:** https://docs.scipy.org/doc/scipy/
- **Development version of the documentation:** https://scipy.github.io/devdocs
- **SciPy development forum:** https://discuss.scientific-python.org/c/contributor/scipy
- **Stack Overflow:** https://stackoverflow.com/questions/tagged/scipy
- **Source code:** https://github.com/scipy/scipy
- **Contributing:** https://scipy.github.io/devdocs/dev/index.html
- **Bug reports:** https://github.com/scipy/scipy/issues
- **Code of Conduct:** https://docs.scipy.org/doc/scipy/dev/conduct/code_of_conduct.html
- **Report a security vulnerability:** via Tidelift, as explained in
  `our docs on Security <https://scipy.github.io/devdocs/tutorial/security.html>`__
```

**Passage `87fed58478cc`** — from `README.rst`

```
cipy.org>`__
- develop graphic design for our brand assets and promotional materials
- help with outreach and onboard new contributors
- write grant proposals and help with other fundraising efforts

If you’re unsure where to start or how your skills fit in, reach out! You can
ask on the `forum <https://discuss.scientific-python.org/c/contributor/scipy>`__
or here, on GitHub, by leaving a comment on a relevant issue that is already
open.

If you are new to contributing to open source, `this
guide <https://opensource.guide/how-to-contribute/>`__ helps explain why, what,
and how to get involved.
```

**Passage `355f2e607626`** — from `README.rst`

```
.. image:: https://raw.githubusercontent.com/scipy/scipy/main/doc/source/_static/logo.svg
  :target: https://scipy.org
  :width: 110
  :height: 110
  :align: left

.. image:: https://img.shields.io/badge/powered%20by-NumFOCUS-orange.svg?style=flat&colorA=E1523D&colorB=007D8A
  :target: https://numfocus.org

.. image:: https://img.shields.io/pypi/dm/scipy.svg?label=Pypi%20downloads
  :target: https://pypi.org/project/scipy/

.. image:: https://img.shields.io/conda/dn/conda-forge/scipy.svg?label=Conda%20downloads
  :target: https://anaconda.org/conda-forge/scipy

.. image:: https://img.shields.io/badge/stackoverflow-Ask%20questions-blue.svg?
  :target: https://stackoverflow.com/questions/tagged/scipy

.. image:: https://img.shields.io/badge/DOI-10.1038%2Fs41592--019--0686--2-blue.svg?
  :target: https://www.nature.com/articles/s41592-019-0686-2

.. image:: https://insights.linuxfoundation.org/api/badge/health-score?project=scipy
  :target: https://insights.linuxfoundation.org/project/scipy
```


---

## ITEM-030

**Dependency:** `tornado` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 5.1.1
- Declared specifier: ==5.1.1
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 6.5.10
- Versions behind the latest release: major 1, minor 0, patch 0
- Days since the package's latest release: 22
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 33
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-49853 / GHSA-3x9g-8vmp-wqvf: severity high, CVSS 7.7, fixed in 6.5.6
  - CVE-2026-49853 / PYSEC-2026-3387: severity high, CVSS 7.7, fixed in 6.5.6
  - CVE-2025-47287 / GHSA-7cx3-6m66-7c5m: severity high, CVSS 7.5, fixed in 6.5
  - CVE-2024-52804 / GHSA-8w49-h785-mj3c: severity high, CVSS 7.5, fixed in 6.4.2
  - CVE-2025-67725 / GHSA-c98p-7wgm-6p64: severity high, CVSS 7.5, fixed in 6.5.3

### Remediation to label

Tornado 5.1.1 is flagged as vulnerable; five high‑severity CVEs are listed with fixes in versions 6.4.2, 6.5, 6.5.3 and 6.5.6. The latest release is 6.5.10, which includes all those fixes. Upgrade the dependency to at least 6.5.6 – preferably the newest 6.5.10 – and run your test suite to verify compatibility. The project’s README describes Tornado as a web framework but does not provide migration notes, so no special steps are documented.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| tornado | upgrade | 6.5.10 |  |

### Source passages the author was shown

**Passage `f42209177e51`** — from `README.rst`

```
.. image:: docs/tornado.png?raw=true
   :alt: Tornado Web
   :align: center

Tornado Web Server
==================

`Tornado <http://www.tornadoweb.org>`_ is a Python web framework and
asynchronous networking library, originally developed at `FriendFeed
<http://friendfeed.com>`_.  By using non-blocking network I/O, Tornado
can scale to tens of thousands of open connections, making it ideal for
`long polling <http://en.wikipedia.org/wiki/Push_technology#Long_Polling>`_,
`WebSockets <http://en.wikipedia.org/wiki/WebSocket>`_, and other
applications that require a long-lived connection to each user.

Hello, world
------------

Here is a simple "Hello, world" example web app for Tornado:

.. code-block:: python

    import asyncio
    import tornado

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    def make_app():
        return tornado.web.Application([
            (r"/", MainHandler),
        ])

    async def main():
        app = make_app()
        app.listen(8888)
        await asyncio.Event().wait()

    if __name__ == "__main__":
        asyncio.run(main())
```

**Passage `77842e8a8958`** — from `README.rst`

```
/", MainHandler),
        ])

    async def main():
        app = make_app()
        app.listen(8888)
        await asyncio.Event().wait()

    if __name__ == "__main__":
        asyncio.run(main())

This example does not use any of Tornado's asynchronous features; for
that see this `simple chat room
<https://github.com/tornadoweb/tornado/tree/stable/demos/chat>`_.

Documentation
-------------

Documentation and links to additional resources are available at
https://www.tornadoweb.org
```


---

## ITEM-031

**Dependency:** `@react-native-community/bob` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 0.17.1
- Declared specifier: ^0.11.2
- Where that version came from: range_latest_approx
- Manifest: package.json
- Dependency group: development
- Latest release on the registry: 0.17.1
- Versions behind the latest release: major 0, minor 0, patch 0
- Days since the package's latest release: 2120
- Deprecated on the registry: yes
- Registry deprecation message: This package has been renamed to 'react-native-builder-bob'. Please use it instead.
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `@react-native-community/bob` package is deprecated and has been renamed to **react-native-builder-bob**. Replace the old dependency with the new package and install it from npm. Update any CLI commands to use the new tool, which provides “a set of CLIs to scaffold and build React Native libraries for different targets” 【b09200d81929】. Refer to the documentation at https://oss.callstack.com/react-native-builder-bob/ for migration guidance 【83dbb2a99853】.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @react-native-community/bob | replace |  | react-native-builder-bob |

### Source passages the author was shown

**Passage `83dbb2a99853`** — from `README.md`

```
## Documentation
Documentation is available at [https://oss.callstack.com/react-native-builder-bob/](https://oss.callstack.com/react-native-builder-bob/).
```

**Passage `b09200d81929`** — from `README.md`

```
<a href="https://www.callstack.com/open-source?utm_campaign=generic&utm_source=github&utm_medium=referral&utm_content=react-native-builder-bob" align="center">
  <picture>
    <img alt="React Native Builder Bob" src="docs/assets/banner.png">
  </picture>
</a>

[![create-react-native-library][create-react-native-library-version-badge]][create-react-native-library]
[![react-native-builder-bob][react-native-builder-bob-version-badge]][react-native-builder-bob]
[![MIT License][license-badge]][license]

👷‍♂️ Set of CLIs to scaffold and build React Native libraries for different targets.
```

**Passage `95a55ff7ca5b`** — from `README.md`

```
## LICENSE
MIT

<!-- badges -->

[create-react-native-library-version-badge]: https://img.shields.io/npm/v/create-react-native-library?label=create-react-native-library&style=flat-square
[react-native-builder-bob-version-badge]: https://img.shields.io/npm/v/react-native-builder-bob?label=react-native-builder-bob&style=flat-square
[create-react-native-library]: https://www.npmjs.com/package/create-react-native-library
[react-native-builder-bob]: https://www.npmjs.com/package/react-native-builder-bob
[license-badge]: https://img.shields.io/npm/l/react-native-builder-bob.svg?style=flat-square
[license]: https://opensource.org/licenses/MIT
```

**Passage `dec792457626`** — from `README.md`

```
## Acknowledgments
Thanks to the authors of these libraries for inspiration:

- [create-react-native-module](https://github.com/brodybits/create-react-native-module)
- [react-native-webview](https://github.com/react-native-community/react-native-webview)
- [RNNewArchitectureLibraries](https://github.com/react-native-community/RNNewArchitectureLibraries)
```

**Passage `eb4f5502e656`** — from `README.md`

```
## Alternatives
Some other tools for building React Native libraries that you may want to check out:

- [create-expo-module](https://docs.expo.dev/modules/get-started/)
- [create-nitro-module](https://github.com/patrickkabwe/create-nitro-module)
- [react-native-module-init](https://github.com/brodybits/react-native-module-init) (Unmaintained)
```


---

## ITEM-032

**Dependency:** `node-uuid` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 1.4.8
- Declared specifier: 1.4.8
- Where that version came from: lockfile
- Manifest: package.json
- Dependency group: runtime
- Latest release on the registry: 1.4.8
- Versions behind the latest release: major 0, minor 0, patch 0
- Days since the package's latest release: 3486
- Deprecated on the registry: yes
- Registry deprecation message: Use uuid module instead
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The npm package **node-uuid** is marked deprecated and its registry notes suggest using the **uuid** module instead. Since the provided documentation does not detail the migration, you should replace node-uuid with uuid in your package.json and code. Update any `require('node-uuid')` or import statements to `require('uuid')` (or the ES‑module equivalent) and adjust calls to use the uuid API (e.g., `uuid.v4()`). Test your application to ensure the new module works as expected.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| node-uuid | replace |  | uuid |

### Source passages the author was shown

**Passage `1e4a3a76f4cd`** — from `HISTORY.md`

```
# 1.3.0
* Support for version 1 ids, thanks to [@ctavan](https://github.com/ctavan)!
  * Support for node.js crypto API
  * De-emphasizing performance in favor of a) cryptographic quality PRNGs where available and b) more manageable code
```

**Passage `6013bd57e5b2`** — from `HISTORY.md`

```
# 1.4.0
* Improved module context detection
  * Removed public RNG functions
```

**Passage `085b26e6553a`** — from `HISTORY.md`

```
# 1.3.2
* Improve tests and handling of v1() options (Issue #24)
  * Expose RNG option to allow for perf testing with different generators
```

**Passage `561ac011f8d3`** — from `HISTORY.md`

```
# 3.0.0 (2016-11-17)
* remove .parse and .unparse
```


---

## ITEM-033

**Dependency:** `h11` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 0.12.0
- Declared specifier: ==0.12.0
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 0.16.0
- Versions behind the latest release: major 0, minor 4, patch 0
- Days since the package's latest release: 531
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2025-43859 / GHSA-vqfr-h8mv-ghfj: severity critical, CVSS 9.1, fixed in 0.16.0
  - CVE-2025-43859 / PYSEC-2026-348: severity critical, CVSS 9.1, fixed in 0.16.0

### Remediation to label

The advisory data shows that the critical vulnerability (CVE‑2025‑43859) is fixed in h11 0.16.0, and your project is currently pinned to 0.12.0. Upgrading the requirement to **0.16.0** will resolve the issue. The README excerpts do not describe what changed in the 0.16.0 release or any breaking‑change considerations, so you should review the project’s changelog or release notes for migration details. After updating the version, run your test suite to ensure compatibility with the newer library.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| h11 | upgrade | 0.16.0 |  |

### Source passages the author was shown

**Passage `b1a30cd2b9c3`** — from `README.rst`

```
he
benefits of this approach
<https://lukasa.co.uk/2015/10/The_New_Hyper/>`_, or if you like video
then here's his `PyCon 2016 talk on the same theme
<https://www.youtube.com/watch?v=7cC3_jGwl_U>`_.

This also means that h11 is not immediately useful out of the box:
it's a toolkit for building programs that speak HTTP, not something
that could directly replace ``requests`` or ``twisted.web`` or
whatever. But h11 makes it much easier to implement something like
``requests`` or ``twisted.web``.

At a high level, working with h11 goes like this:

1) First, create an ``h11.Connection`` object to track the state of a
   single HTTP/1.1 connection.

2) When you read data off the network, pass it to
   ``conn.receive_data(...)``; you'll get back a list of objects
   representing high-level HTTP "events".

3) When you want to send a high-level HTTP event, create the
   corresponding "event" object and pass it to ``conn.send(...)``;
   this will give you back some bytes that you can then push out
   through the network.
```

**Passage `da53d06b58e5`** — from `README.rst`

```
hedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

This is a little HTTP/1.1 library written from scratch in Python,
heavily inspired by `hyper-h2 <https://hyper-h2.readthedocs.io/>`_.

It's a "bring-your-own-I/O" library; h11 contains no IO code
whatsoever. This means you can hook h11 up to your favorite network
API, and that could be anything you want: synchronous, threaded,
asynchronous, or your own implementation of `RFC 6214
<https://tools.ietf.org/html/rfc6214>`_ -- h11 won't judge you.
(Compare this to the current state of the art, where every time a `new
network API <https://trio.readthedocs.io/>`_ comes along then someone
gets to start over reimplementing the entire HTTP protocol from
scratch.) Cory Benfield made an `excellent blog post describing the
benefits of this approach
<https://lukasa.co.uk/2015/10/The_New_Hyper/>`_, or if you like video
then here's his `PyCon 2016 talk on the same theme
<https://www.youtube.com/watch?v=7cC3_jGwl_U>`_.
```

**Passage `25f74e8a5b04`** — from `README.rst`

```
ry it?*

.. code-block:: sh

  $ pip install h11
  $ git clone git@github.com:python-hyper/h11
  $ cd h11/examples
  $ python basic-client.py

and go from there.

*License?*

MIT

*Code of conduct?*

Contributors are requested to follow our `code of conduct
<https://github.com/python-hyper/h11/blob/master/CODE_OF_CONDUCT.md>`_ in
all project spaces.
```

**Passage `5244f7e80256`** — from `README.rst`

```
h11
===

.. image:: https://travis-ci.org/python-hyper/h11.svg?branch=master
   :target: https://travis-ci.org/python-hyper/h11
   :alt: Automated test status

.. image:: https://codecov.io/gh/python-hyper/h11/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/python-hyper/h11
   :alt: Test coverage

.. image:: https://readthedocs.org/projects/h11/badge/?version=latest
   :target: http://h11.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

This is a little HTTP/1.1 library written from scratch in Python,
heavily inspired by `hyper-h2 <https://hyper-h2.readthedocs.io/>`_.
```

**Passage `349ed7b3eff7`** — from `README.rst`

```
to support the
full specification in the sense that any useful HTTP/1.1 conformant
application should be able to use h11.

It's pure Python, and has no dependencies outside of the standard
library.

It has a test suite with 100.0% coverage for both statements and
branches.

Currently it supports Python 3 (testing on 3.8-3.12) and PyPy 3.
The last Python 2-compatible version was h11 0.11.x.
(Originally it had a Cython wrapper for `http-parser
<https://github.com/nodejs/http-parser>`_ and a beautiful nested state
machine implemented with ``yield from`` to postprocess the output. But
I had to take these out -- the new *parser* needs fewer lines-of-code
than the old *parser wrapper*, is written in pure Python, uses no
exotic language syntax, and has more features. It's sad, really; that
old state machine was really slick. I just need a few sentences here
to mourn that.)
```


---

## ITEM-034

**Dependency:** `@babel/plugin-proposal-private-methods` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 7.18.6
- Declared specifier: ^7.18.6
- Where that version came from: range_latest_approx
- Manifest: book/10-end/app/package.json
- Dependency group: development
- Latest release on the registry: 7.18.6
- Versions behind the latest release: major 0, minor 0, patch 0
- Days since the package's latest release: 1563
- Deprecated on the registry: yes
- Registry deprecation message: This proposal has been merged to the ECMAScript standard and thus this plugin is no longer maintained. Please use @babel/plugin-transform-private-methods instead.
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `@babel/plugin-proposal-private-methods` package is deprecated because its proposal has been merged into the ECMAScript standard. You should replace it with `@babel/plugin-transform-private-methods` in your Babel configuration. The migration mainly consists of swapping the plugin name; no additional options or breaking changes are documented. The replacement plugin is listed among Babel’s plugins in the changelog [0d203f0dd0ca].

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @babel/plugin-proposal-private-methods | replace |  | @babel/plugin-transform-private-methods |

### Source passages the author was shown

**Passage `0d203f0dd0ca`** — from `CHANGELOG.md`

```
#### :loudspeaker: Deprecation
* `babel-plugin-transform-arrow-functions`, `babel-plugin-transform-classes`, `babel-plugin-transform-computed-properties`, `babel-plugin-transform-destructuring`, `babel-plugin-transform-for-of`, `babel-plugin-transform-modules-amd`, `babel-plugin-transform-modules-commonjs`, `babel-plugin-transform-modules-umd`, `babel-plugin-transform-nullish-coalescing-operator`, `babel-plugin-transform-object-rest-spread`, `babel-plugin-transform-optional-chaining`, `babel-plugin-transform-parameters`, `babel-plugin-transform-private-methods`, `babel-plugin-transform-private-property-in-object`, `babel-plugin-transform-spread`, `babel-plugin-transform-template-literals`
  * [#17972](https://github.com/babel/babel/pull/17972) Deprecate `spec` and `loose` plugin options ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
```

**Passage `f67d31928dc0`** — from `CHANGELOG.md`

```
#### :bug: Bug Fix
* `babel-generator`
  * [#18046](https://github.com/babel/babel/pull/18046) fix(generator): improve new callee parens check ([@JLHwung](https://github.com/JLHwung))
* `babel-plugin-transform-modules-systemjs`
  * [#18032](https://github.com/babel/babel/pull/18032) fix(systemjs): support __proto__ as an export name ([@JLHwung](https://github.com/JLHwung))
```

**Passage `f35f030bedec`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
* `babel-cli`, `babel-node`, `babel-plugin-proposal-decorators`, `babel-plugin-transform-classes`, `babel-plugin-transform-function-name`, `babel-plugin-transform-modules-commonjs`, `babel-plugin-transform-object-rest-spread`, `babel-plugin-transform-parameters`, `babel-plugin-transform-react-constant-elements`, `babel-plugin-transform-regenerator`, `babel-preset-env`, `babel-register`
  * [#18069](https://github.com/babel/babel/pull/18069) Fallback to assuming ESM support with `modules: auto` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
* `babel-plugin-transform-runtime`, `babel-runtime-corejs3`, `babel-runtime`
  * [#18036](https://github.com/babel/babel/pull/18036) Remove corejs exports for `@babe/runtime-corejs3` ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
* `babel-parser`
  * [#18034](https://github.com/babel/babel/pull/18034) Remove `locations: "packed"` ([@liuxingbaoyu](https://github.com/liuxingbaoyu))
```

**Passage `158ea42f785c`** — from `CHANGELOG.md`

```
#### :house: Internal
* `babel-plugin-transform-runtime`
  * [#17511](https://github.com/babel/babel/pull/17511) [babel 8] Remove `semver` dependency from transform-runtime ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```

**Passage `fdc085acc09a`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
* `babel-core`, `babel-plugin-transform-object-rest-spread`, `babel-plugin-transform-runtime`, `babel-preset-env`, `babel-standalone`
  * [#18079](https://github.com/babel/babel/pull/18079) Actually remove `preset-env`'s `useBuiltIns` ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```


---

## ITEM-035

**Dependency:** `nodemailer` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 6.4.16
- Declared specifier: ^6.3.1
- Where that version came from: lockfile
- Manifest: tutorials/backend/hasura/event-trigger/package.json
- Dependency group: runtime
- Latest release on the registry: 10.0.16
- Versions behind the latest release: major 4, minor 6, patch 2
- Days since the package's latest release: 0
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 16
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-92596 / GHSA-2x7j-588g-ccc2: severity high, CVSS 7.5, fixed in 9.1.0
  - CVE-2025-14874 / GHSA-rcmh-qjqh-p98v: severity high, CVSS 7.5, fixed in 7.0.11
  - CVE-2026-100700 / GHSA-v53p-9fqp-m79j: severity high, CVSS 7.5, fixed in 10.0.6
  - CVE-2026-82659 / GHSA-p6gq-j5cr-w38f: severity high, CVSS 7.1, fixed in 9.0.1
  - CVE-2026-82662 / GHSA-r7g4-qg5f-qqm2: severity high, CVSS 6.5, fixed in 8.0.8

### Remediation to label

The project is using **nodemailer 6.4.16**, which is flagged as vulnerable by several high‑severity CVEs. Each advisory lists a fixed version (e.g., 7.0.11, 8.0.8, 9.0.1, 9.1.0, 10.0.6). Upgrading to the latest available release **10.0.16** satisfies all of those fixed versions and eliminates the reported issues. Update the version constraint in *package.json* and run the install command to apply the new version. This single upgrade addresses the entire advisory set without needing to replace the package.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| nodemailer | upgrade | 10.0.16 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-036

**Dependency:** `werkzeug` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 2.3.8
- Declared specifier: ==2.3.8
- Where that version came from: pinned
- Manifest: pyproject.toml
- Dependency group: runtime
- Latest release on the registry: 3.1.9
- Versions behind the latest release: major 1, minor 0, patch 0
- Days since the package's latest release: 10
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 13
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2024-34069 / GHSA-2g68-c3qc-8985: severity high, CVSS 7.5, fixed in 3.0.3
  - CVE-2024-49767 / GHSA-q34m-jh98-gwm2: severity medium, CVSS 7.5, fixed in 3.0.6
  - CVE-2024-34069 / PYSEC-2026-2043: severity high, CVSS 7.5, fixed in 3.0.3
  - CVE-2024-49767 / PYSEC-2026-3417: severity high, CVSS 7.5, fixed in 3.0.6
  - CVE-2026-21860 / GHSA-87hc-h4r5-73f7: severity medium, CVSS 5.3, fixed in 3.1.5

### Remediation to label

The scan shows that the pinned version **2.3.8** of *werkzeug* is vulnerable to several high‑severity CVEs. The advisory data lists fixed versions 3.0.3, 3.0.6, and 3.1.5, and the latest available release is 3.1.9. Upgrading to the latest version will address all known fixes. No additional documentation was retrieved for this package, so the upgrade path is based solely on the advisory information.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| werkzeug | upgrade | 3.1.9 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-037

**Dependency:** `flag-icon-css` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 3.5.0
- Declared specifier: 3.5.0
- Where that version came from: pinned
- Manifest: package.json
- Dependency group: runtime
- Latest release on the registry: 4.1.7
- Versions behind the latest release: major 1, minor 0, patch 0
- Days since the package's latest release: 1757
- Deprecated on the registry: yes
- Registry deprecation message: The project has been renamed to flag-icons
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `flag-icon-css` package at version 3.5.0 is deprecated and has been renamed to **flag-icons**. The changelog notes that the package name changed from `flag-icon-css` to `flag-icons` and the CSS class prefixes were updated from `flag-icon`/`flag-icon-[xx]` to `fi`/`fi-[xx]` [184943b1248b]. Because the rename occurs starting with version 5.0.0, continuing to use `flag-icon-css` (even at its latest 4.1.7 release) will keep the project on a stale, deprecated name. Replace the dependency with the new `flag-icons` package and update any class names accordingly to stay current and avoid future breakage.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| flag-icon-css | replace |  | flag-icons |

### Source passages the author was shown

**Passage `184943b1248b`** — from `CHANGELOG.md`

```
# 5.0.0
- The package name changed from `flag-icon-css` to `flag-icons`
- The class names changed from `flag-icon` `flag-icon-[xx]` to `fi` `fi-[xx]`
```

**Passage `6f97fb1db8fd`** — from `CHANGELOG.md`

```
# 6.7.0
- Fix blurry US flag in Safari (#1096)
- Correcting Tunisia flag to match post 1999 shape updates (#1090)
- Correct green color in Saudi Arabia flag (#1080)
- Remove mix-blend-mode from Georgia flag (#1079)
- Fix flag of Malaysia (#1058)
- Fix Antigua and Barbuda flags (#1066)
- Add cefta flag to stylesheets (#1065)
- Fix flag of Kazakhstan (#1056)
- Fix flag of Dominican Republic (#1052)
- Add flag for Basque Country (#1050)
- Fix colors of Cuban flag (#1044)
- Fix Nepali flag should be transparent (#1034)
- Added CDN (#1032)
```

**Passage `6064313b7e73`** — from `CHANGELOG.md`

```
# 7.4.0
- Migrate SASS imports to @use-based code (#1356)
- Modern and minimalist UI redesign with new features (#1358)
- Fix flag of Palestine (#1366)
```

**Passage `7361b8023007`** — from `CHANGELOG.md`

```
# 6.11.2
- Fix French flags color to use the official ones (#1163)
```

**Passage `38f5d1507133`** — from `CHANGELOG.md`

```
# 6.6.5
- Fix Albania flag colors (Issue #1028)
- Fix South Africa flag colors (Issue #1020)
```


---

## ITEM-038

**Dependency:** `@babel/plugin-proposal-logical-assignment-operators` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 7.20.7
- Declared specifier: 7.20.7
- Where that version came from: lockfile
- Manifest: package.json
- Dependency group: development
- Latest release on the registry: 7.20.7
- Versions behind the latest release: major 0, minor 0, patch 0
- Days since the package's latest release: 1385
- Deprecated on the registry: yes
- Registry deprecation message: This proposal has been merged to the ECMAScript standard and thus this plugin is no longer maintained. Please use @babel/plugin-transform-logical-assignment-operators instead.
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `@babel/plugin-proposal-logical-assignment-operators` package is deprecated because its proposal has been merged into the ECMAScript standard, and the plugin is no longer maintained. There is no newer version available (latest = 7.20.7), so the safest remediation is to replace it with the maintained transformer plugin. Switch to `@babel/plugin-transform-logical-assignment-operators`, which appears in Babel’s changelog as the successor for handling logical‑assignment operators. Update your Babel configuration and `package.json` accordingly to use the new plugin.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @babel/plugin-proposal-logical-assignment-operators | replace |  | @babel/plugin-transform-logical-assignment-operators |

### Source passages the author was shown

**Passage `a110106dd02d`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
-sent`, `babel-plugin-proposal-import-defer`, `babel-plugin-proposal-import-wasm-source`, `babel-plugin-proposal-optional-chaining-assign`, `babel-plugin-proposal-partial-application`, `babel-plugin-proposal-pipeline-operator`, `babel-plugin-proposal-throw-expressions`, `babel-plugin-syntax-async-do-expressions`, `babel-plugin-syntax-decorators`, `babel-plugin-syntax-destructuring-private`, `babel-plugin-syntax-do-expressions`, `babel-plugin-syntax-export-default-from`, `babel-plugin-syntax-flow`, `babel-plugin-syntax-function-bind`, `babel-plugin-syntax-function-sent`, `babel-plugin-syntax-import-defer`, `babel-plugin-syntax-import-source`, `babel-plugin-syntax-jsx`, `babel-plugin-syntax-module-blocks`, `babel-plugin-syntax-optional-chaining-assign`, `babel-plugin-syntax-partial-application`, `babel-plugin-syntax-pipeline-operator`, `babel-plugin-syntax-throw-expressions`, `babel-plugin-syntax-typescript`, `babel-plugin-transform-arrow-functions`, `babel-plugin-transform-async-generator-functions`, `babel-plugin-transform-async-to-generator`, `babel-plugin-transform-block-scoped-functions`, `babel-plugin-transform-block-scoping`, `babel-plugin-transform-class-properties`, `babel-p
```

**Passage `4b8548f86424`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
)
* `babel-generator`, `babel-plugin-proposal-pipeline-operator`, `babel-plugin-proposal-record-and-tuple`, `babel-plugin-syntax-record-and-tuple`, `babel-standalone`, `babel-traverse`, `babel-types`
  * [#17528](https://github.com/babel/babel/pull/17528) Fully remove Records and Tuples support ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```

**Passage `d46865a031f7`** — from `CHANGELOG.md`

```
#### :house: Internal
* `babel-parser`, `babel-plugin-proposal-pipeline-operator`, `babel-plugin-syntax-pipeline-operator`
  * [#17058](https://github.com/babel/babel/pull/17058) [babel 8] Remove remaining references to minimal/smart pipelines ([@nicolo-ribaudo](https://github.com/nicolo-ribaudo))
```

**Passage `24ffd7fc7485`** — from `CHANGELOG.md`

```
#### :boom: Breaking Change
`babel-plugin-transform-literals`, `babel-plugin-transform-logical-assignment-operators`, `babel-plugin-transform-member-expression-literals`, `babel-plugin-transform-modules-amd`, `babel-plugin-transform-modules-commonjs`, `babel-plugin-transform-modules-systemjs`, `babel-plugin-transform-modules-umd`, `babel-plugin-transform-named-capturing-groups-regex`, `babel-plugin-transform-new-target`, `babel-plugin-transform-nullish-coalescing-operator`, `babel-plugin-transform-numeric-separator`, `babel-plugin-transform-object-rest-spread`, `babel-plugin-transform-object-super`, `babel-plugin-transform-optional-catch-binding`, `babel-plugin-transform-optional-chaining`, `babel-plugin-transform-parameters`, `babel-plugin-transform-private-methods`, `babel-plugin-transform-private-property-in-object`, `babel-plugin-transform-property-literals`, `babel-plugin-transform-proto-to-assign`, `babel-plugin-transform-react-constant-elements`, `babel-plugin-transform-react-display-name`, `babel-plugin-transform-react-inline-elements`, `babel-plugin-transform-react-jsx-development`, `babel-plugin-transform-react-jsx`, `babel-plugin-transform-react-pure-annotations`, `babel-plugin-transform-regenerat
```

**Passage `dc3848b2898e`** — from `CHANGELOG.md`

```
#### :eyeglasses: Spec Compliance
* `babel-parser`, `babel-plugin-transform-typescript`
  * [#18120](https://github.com/babel/babel/pull/18120) fix(parser): disallow `declare module M {}` ([@JLHwung](https://github.com/JLHwung))
* `babel-generator`, `babel-parser`, `babel-plugin-transform-typescript`
  * [#18100](https://github.com/babel/babel/pull/18100) fix(parser): forbid let x! and let x! = ([@JLHwung](https://github.com/JLHwung))
```


---

## ITEM-039

**Dependency:** `daphne` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 2.1.2
- Declared specifier: ==2.1.2
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 4.2.3
- Versions behind the latest release: major 2, minor 4, patch 0
- Days since the package's latest release: 78
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 4
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 4
  - CVE-2026-44545 / PYSEC-2026-213: severity high, CVSS 7.5, fixed in 4.2.2
  - CVE-2026-44545 / GHSA-rrc9-mx66-ffcm: severity medium, CVSS 5.3, fixed in 4.2.2
  - CVE-2026-44546 / PYSEC-2026-214: severity medium, CVSS 5.3, fixed in 4.2.2
  - CVE-2026-44546 / GHSA-xh68-hfp5-5x5m: severity low, CVSS 3.7, fixed in 4.2.2

### Remediation to label

The current pinned version 2.1.2 of **daphne** is vulnerable; the security advisories are fixed starting in version **4.2.2** (the latest is 4.2.3). Upgrading the `requirements.txt` entry to at least `daphne==4.2.2` will resolve the CVE‑2026‑44545 and CVE‑2026‑44546 issues. Daphne now requires Python 3.10 or newer, so ensure your runtime meets that requirement [097c6edf9021]. If you use HTTP/2 you may also need the Twisted `tls` and `http2` extras as described in the README [2f12eda0a1c2].

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| daphne | upgrade | 4.2.2 |  |

### Source passages the author was shown

**Passage `46de45cda448`** — from `README.rst`

```
02,741 INFO     Starting server at ssl:port=8000:privateKey=privkey.pem:certKey=cert.pem, channel layer django_project.asgi:channel_layer.
    2017-03-18 19:14:02,742 INFO     HTTP/2 support enabled

Then, connect with a browser that supports HTTP/2, and everything should be
working. It's often hard to tell that HTTP/2 is working, as the log Daphne gives you
will be identical (it's HTTP, after all), and most browsers don't make it obvious
in their network inspector windows. There are browser extensions that will let
you know clearly if it's working or not.

Daphne only supports "normal" requests over HTTP/2 at this time; there is not
yet support for extended features like Server Push. It will, however, result in
much faster connections and lower overheads.

If you have a reverse proxy in front of your site to serve static files or
similar, HTTP/2 will only work if that proxy understands and passes through the
connection correctly.


Root Path (SCRIPT_NAME)
-----------------------

In order to set the root path for Daphne, which is the equivalent of the
WSGI ``SCRIPT_NAME`` setting, you have two options:
```

**Passage `2f12eda0a1c2`** — from `README.rst`

```
m Let's Encrypt, which you can read more about at http://txacme.readthedocs.io/en/stable/.

To see all available command line options run daphne with the ``-h`` flag.


HTTP/2 Support
--------------

Daphne supports terminating HTTP/2 connections natively. You'll
need to do a couple of things to get it working, though. First, you need to
make sure you install the Twisted ``http2`` and ``tls`` extras::

    pip install -U "Twisted[tls,http2]"

Next, because all current browsers only support HTTP/2 when using TLS, you will
need to start Daphne with TLS turned on, which can be done using the Twisted endpoint syntax::

    daphne -e ssl:443:privateKey=key.pem:certKey=crt.pem django_project.asgi:application

Alternatively, you can use the ``txacme`` endpoint syntax or anything else that
enables TLS under the hood.

You will also need to be on a system that has **OpenSSL 1.0.2 or greater**.

Now, when you start up Daphne, it should tell you this in the log::

    2017-03-18 19:14:02,741 INFO     Starting server at ssl:port=8000:privateKey=privkey.pem:certKey=cert.pem, channel layer django_project.asgi:channel_layer.
    2017-03-18 19:14:02,742 INFO     HTTP/2 support enabled
```

**Passage `097c6edf9021`** — from `README.rst`

```
connection correctly.


Root Path (SCRIPT_NAME)
-----------------------

In order to set the root path for Daphne, which is the equivalent of the
WSGI ``SCRIPT_NAME`` setting, you have two options:

* Pass a header value ``Daphne-Root-Path``, with the desired root path as a
  URLencoded ASCII value. This header will not be passed down to applications.

* Set the ``--root-path`` commandline option with the desired root path as a
  URLencoded ASCII value.

The header takes precedence if both are set. As with ``SCRIPT_ALIAS``, the value
should start with a slash, but not end with one; for example::

    daphne --root-path=/forum django_project.asgi:application


Python Support
--------------

Daphne requires Python 3.10 or later.


Contributing
------------

Please refer to the
`main Channels contributing docs <https://github.com/django/channels/blob/main/CONTRIBUTING.rst>`_.

To run tests, make sure you have installed the ``tests`` extra with the package::

    cd daphne/
    pip install -e '.[tests]'
    pytest


Maintenance and Security
------------------------
```

**Passage `ee6849719943`** — from `README.rst`

```
daphne
======

.. image:: https://img.shields.io/pypi/v/daphne.svg
    :target: https://pypi.python.org/pypi/daphne

Daphne is a HTTP, HTTP2 and WebSocket protocol server for
`ASGI <https://github.com/django/asgiref/blob/main/specs/asgi.rst>`_ and
`ASGI-HTTP <https://github.com/django/asgiref/blob/main/specs/www.rst>`_,
developed to power Django Channels.

It supports automatic negotiation of protocols; there's no need for URL
prefixing to determine WebSocket endpoints versus HTTP endpoints.


Running
-------

Simply point Daphne to your ASGI application, and optionally
set a bind address and port (defaults to localhost, port 8000)::

    daphne -b 0.0.0.0 -p 8001 django_project.asgi:application

If you intend to run daphne behind a proxy server you can use UNIX
sockets to communicate between the two::

    daphne -u /tmp/daphne.sock django_project.asgi:application

If daphne is being run inside a process manager, you might
want it to bind to a file descriptor passed down from a parent process.
To achieve this you can use the --fd flag::

    daphne --fd 5 django_project.asgi:application
```

**Passage `fdfc0edd3051`** — from `README.rst`

```
st>`_.

To run tests, make sure you have installed the ``tests`` extra with the package::

    cd daphne/
    pip install -e '.[tests]'
    pytest


Maintenance and Security
------------------------

To report security issues, please contact security@djangoproject.com. For GPG
signatures and more security process information, see
https://docs.djangoproject.com/en/dev/internals/security/.

To report bugs or request new features, please open a new GitHub issue.

This repository is part of the Channels project. For the shepherd and maintenance team, please see the
`main Channels readme <https://github.com/django/channels/blob/main/README.rst>`_.
```


---

## ITEM-040

**Dependency:** `axios` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 0.24.0
- Declared specifier: ^0.24.0
- Where that version came from: lockfile
- Manifest: client/package.json
- Dependency group: runtime
- Latest release on the registry: 1.20.0
- Versions behind the latest release: major 1, minor 10, patch 0
- Days since the package's latest release: 42
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 23
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-44492 / GHSA-pjwm-pj3p-43mv: severity high, CVSS 8.6, fixed in 1.16.0
  - CVE-2026-25639 / GHSA-43fc-jf86-j433: severity high, CVSS 7.5, fixed in 1.13.5
  - CVE-2026-42039 / GHSA-62hf-57xw-28j9: severity medium, CVSS 7.5, fixed in 1.15.1
  - CVE-2026-44496 / GHSA-hfxv-24rg-xrqf: severity high, CVSS 7.5, fixed in 1.16.0
  - CVE-2026-44486 / GHSA-j5f8-grm9-p9fc: severity high, CVSS 7.5, fixed in 1.16.0

### Remediation to label

The project is using **axios 0.24.0**, which is flagged as vulnerable with several high‑severity CVEs. The advisory data lists fixed versions starting at 1.16.0, and the latest available release is 1.20.0. No documentation was retrieved to confirm migration details, so the safest remediation is to upgrade to the newest version. Upgrading to 1.20.0 will address all listed vulnerabilities and bring the package up‑to‑date.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| axios | upgrade | 1.20.0 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-041

**Dependency:** `axios` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 1.5.0
- Declared specifier: ^1.5.0
- Where that version came from: lockfile
- Manifest: package.json
- Dependency group: runtime
- Latest release on the registry: 1.20.0
- Versions behind the latest release: major 0, minor 15, patch 1
- Days since the package's latest release: 42
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 32
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-44494 / GHSA-35jp-ww65-95wh: severity high, CVSS 8.7, fixed in 1.16.0
  - CVE-2026-25639 / GHSA-43fc-jf86-j433: severity high, CVSS 7.5, fixed in 1.13.5
  - CVE-2025-58754 / GHSA-4hjh-wcwx-xvwj: severity high, CVSS 7.5, fixed in 1.12.0
  - CVE-2026-42039 / GHSA-62hf-57xw-28j9: severity medium, CVSS 7.5, fixed in 1.15.1
  - CVE-2026-44496 / GHSA-hfxv-24rg-xrqf: severity high, CVSS 7.5, fixed in 1.16.0

### Remediation to label

Your project is using axios 1.5.0, which is vulnerable. The advisories list fixed versions 1.12.0, 1.13.5, 1.15.1, and 1.16.0, so any version ≥ 1.16.0 resolves all listed CVEs. The changelog entries we have show that 1.13.5 introduced new contributors [a924aa7b2485] and 1.15.1 also added contributors [6e1a222aea01]; later releases 1.14.0 and 1.15.2 are documented [f166c50a1b22, 6806c88a4f1e]. No notes are available for the 1.16.0 release, so you should review the official changelog for potential breaking changes. Upgrading to the latest 1.20.0 (or at least 1.16.0) via your package.json will eliminate the vulnerabilities.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| axios | upgrade | 1.20.0 |  |

### Source passages the author was shown

**Passage `a924aa7b2485`** — from `CHANGELOG.md`

```
## 🌟 New Contributors
We are thrilled to welcome our new contributors. Thank you for helping improve axios:

- **@asmitha-16** (**#7326**)

[Full Changelog](https://github.com/axios/axios/compare/v1.13.4...v1.13.5)

---
```

**Passage `6e1a222aea01`** — from `CHANGELOG.md`

```
## 🌟 New Contributors
We are thrilled to welcome our new contributors. Thank you for helping improve axios:

- **@curiouscoder-cmd** (**#7252**)
- **@tryonelove** (**#7520**)
- **@darwin808** (**#7314**)
- **@zoontek** (**#10702**)
- **@AKIB473** (**#10725**)

[Full Changelog](https://github.com/axios/axios/compare/v1.15.0...v1.15.1)

---
```

**Passage `72567077937a`** — from `CHANGELOG.md`

```
### Bug Fixes
- **types:** fixed env config types; ([#7020](https://github.com/axios/axios/issues/7020)) ([b5f26b7](https://github.com/axios/axios/commit/b5f26b75bdd9afa95016fb67d0cab15fc74cbf05))
```

**Passage `f166c50a1b22`** — from `CHANGELOG.md`

```
## 🌟 New Contributors
We are thrilled to welcome our new contributors. Thank you for helping improve axios:

- **@penkzhou** (**#7515**)
- **@aviu16** (**#7456**)
- **@fedotov** (**#7457**)

[Full Changelog](https://github.com/axios/axios/compare/v1.13.6...v1.14.0)

---
```

**Passage `6806c88a4f1e`** — from `CHANGELOG.md`

```
## 🔧 Maintenance & Chores
- **Changelog:** Updated `CHANGELOG.md` with v1.15.1 release notes. (**#10781**)

[Full Changelog](https://github.com/axios/axios/compare/v1.15.1...v1.15.2)

---
```


---

## ITEM-042

**Dependency:** `requests` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 2.20.0
- Declared specifier: ==2.20.0
- Where that version came from: pinned
- Manifest: dev_requirements.txt
- Dependency group: development
- Latest release on the registry: 2.34.2
- Versions behind the latest release: major 0, minor 14, patch 1
- Days since the package's latest release: 146
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 8
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2023-32681 / GHSA-j8r2-6x86-q33q: severity medium, CVSS 6.1, fixed in 2.31.0
  - CVE-2024-35195 / GHSA-9wx4-h78v-vm56: severity medium, CVSS 5.6, fixed in 2.32.0
  - CVE-2024-35195 / PYSEC-2026-1873: severity medium, CVSS 5.6, fixed in 2.32.0
  - CVE-2026-25645 / PYSEC-2026-2275: severity medium, CVSS 5.5, fixed in 2.33.0
  - CVE-2024-47081 / GHSA-9hjg-9r4m-mvj7: severity medium, CVSS 5.3, fixed in 2.32.4

### Remediation to label

Version 2.31.0 of **requests** adds a security fix that stops forwarding the `Proxy-Authorization` header to destination servers on HTTPS redirects, addressing CVE‑2023‑32681 【cf70c1403035】. The change is described as a fix for proxy‑credential leakage and users are encouraged to upgrade to 2.31.0 or later 【ac038485e0f9】. No breaking API changes are reported for this release, so the upgrade is safe for most codebases. If you use proxy URLs with embedded credentials, you should rotate those credentials after upgrading to ensure any previously leaked tokens are invalidated.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| requests | upgrade | 2.31.0 |  |

### Source passages the author was shown

**Passage `43ae54dca851`** — from `HISTORY.md`

```
subclass of `Mapping` is now treated like a
    dictionary by the `data=` keyword argument.
-   Requests now tolerates empty passwords in proxy credentials, rather
    than stripping the credentials.
-   If a request is made with a file-like object as the body and that
    request is redirected with a 307 or 308 status code, Requests will
    now attempt to rewind the body object so it can be replayed.

**Bugfixes**

-   When calling `response.close`, the call to `close` will be
    propagated through to non-urllib3 backends.
-   Fixed issue where the `ALL_PROXY` environment variable would be
    preferred over scheme-specific variables like `HTTP_PROXY`.
-   Fixed issue where non-UTF8 reason phrases got severely mangled by
    falling back to decoding using ISO 8859-1 instead.
-   Fixed a bug where Requests would not correctly correlate cookies set
    when using custom Host headers if those Host headers did not use the
    native string type for the platform.

**Miscellaneous**

-   Updated bundled urllib3 to 1.19.
-   Updated bundled certifi certs to 2016.09.26.

2.11.1 (2016-08-17)
-------------------

**Bugfixes**
```

**Passage `09f5c5b89e76`** — from `HISTORY.md`

```
- Requests has officially dropped support for CPython 3.7 (#6642)
- Requests has officially dropped support for PyPy 3.7 and 3.8 (#6641)

**Documentation**
- Various typo fixes and doc improvements.

**Packaging**
- Requests has started adopting some modern packaging practices.
  The source files for the projects (formerly `requests`) is now located
  in `src/requests` in the Requests sdist. (#6506)
- Starting in Requests 2.33.0, Requests will migrate to a PEP 517 build system
  using `hatchling`. This should not impact the average user, but extremely old
  versions of packaging utilities may have issues with the new packaging format.


2.31.0 (2023-05-22)
-------------------

**Security**
- Versions of Requests between v2.3.0 and v2.30.0 are vulnerable to potential
  forwarding of `Proxy-Authorization` headers to destination servers when
  following HTTPS redirects.

  When proxies are defined with user info (`https://user:pass@proxy:8080`), Requests
  will construct a `Proxy-Authorization` header that is attached to the request to
  authenticate with the proxy.
```

**Passage `cf70c1403035`** — from `HISTORY.md`

```
nvalidHeader error in
  all invalid cases. (#6154)
- Added provisional 3.11 support with current beta build. (#6155)
- Requests got a makeover and we decided to paint it black. (#6095)

**Bugfixes**

- Fixed bug where setting `CURL_CA_BUNDLE` to an empty string would disable
  cert verification. All Requests 2.x versions before 2.28.0 are affected. (#6074)
- Fixed urllib3 exception leak, wrapping `urllib3.exceptions.SSLError` with
  `requests.exceptions.SSLError` for `content` and `iter_content`. (#6057)
- Fixed issue where invalid Windows registry entries caused proxy resolution
  to raise an exception rather than ignoring the entry. (#6149)
- Fixed issue where entire payload could be included in the error message for
  JSONDecodeError. (#6036)

2.27.1 (2022-01-05)
-------------------

**Bugfixes**

- Fixed parsing issue that resulted in the `auth` component being
  dropped from proxy URLs. (#6028)

2.27.0 (2022-01-03)
-------------------

**Improvements**

- Officially added support for Python 3.10. (#5928)
```

**Passage `ac038485e0f9`** — from `HISTORY.md`

```
When proxies are defined with user info (`https://user:pass@proxy:8080`), Requests
  will construct a `Proxy-Authorization` header that is attached to the request to
  authenticate with the proxy.

  In cases where Requests receives a redirect response, it previously reattached
  the `Proxy-Authorization` header incorrectly, resulting in the value being
  sent through the tunneled connection to the destination server. Users who rely on
  defining their proxy credentials in the URL are *strongly* encouraged to upgrade
  to Requests 2.31.0+ to prevent unintentional leakage and rotate their proxy
  credentials once the change has been fully deployed.

  Users who do not use a proxy or do not supply their proxy credentials through
  the user information portion of their proxy URL are not subject to this
  vulnerability.

  Full details can be read in our [Github Security Advisory](https://github.com/psf/requests/security/advisories/GHSA-j8r2-6x86-q33q)
  and [CVE-2023-32681](https://nvd.nist.gov/vuln/detail/CVE-2023-32681).


2.30.0 (2023-05-03)
-------------------

**Dependencies**
- ⚠️ Added support for urllib3 2.0. ⚠️
```

**Passage `492cec244c46`** — from `HISTORY.md`

```
in sub-classes of
  HTTPAdapter. (#6716)
- Fixed issue where Requests started failing to run on Python versions compiled
  without the `ssl` module. (#6724)

2.32.2 (2024-05-21)
-------------------

**Deprecations**
- To provide a more stable migration for custom HTTPAdapters impacted
  by the CVE changes in 2.32.0, we've renamed `_get_connection` to
  a new public API, `get_connection_with_tls_context`. Existing custom
  HTTPAdapters will need to migrate their code to use this new API.
  `get_connection` is considered deprecated in all versions of Requests>=2.32.0.

  A minimal (2-line) example has been provided in the linked PR to ease
  migration, but we strongly urge users to evaluate if their custom adapter
  is subject to the same issue described in CVE-2024-35195. (#6710)

2.32.1 (2024-05-20)
-------------------

**Bugfixes**
- Add missing test certs to the sdist distributed on PyPI.


2.32.0 (2024-05-20)
-------------------
```


---

## ITEM-043

**Dependency:** `@nestjs/core` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 8.0.5
- Declared specifier: ^8.0.5
- Where that version came from: lockfile
- Manifest: api/package.json
- Dependency group: runtime
- Latest release on the registry: 12.1.2
- Versions behind the latest release: major 4, minor 4, patch 6
- Days since the package's latest release: 7
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2026-35515 / GHSA-36xv-jgw5-4q75: severity medium, CVSS 6.1, fixed in 11.1.18
  - CVE-2023-26108 / GHSA-4jpv-8r57-pv7j: severity medium, CVSS 5.3, fixed in 9.0.5

### Remediation to label

The project is using @nestjs/core 8.0.5, which is flagged as vulnerable (CVE‑2023‑26108 and CVE‑2026‑35515). The advisory data indicates the issues are fixed in versions 9.0.5 and 11.1.18 respectively, and the newest release is 12.1.2. Upgrading the dependency to at least 9.0.5 – preferably the latest 12.1.2 – will resolve the known vulnerabilities. The package’s README does not contain specific migration notes or breaking‑change guidance, so you should consult the official Nest changelog for any required code adjustments.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @nestjs/core | upgrade | 12.1.2 |  |

### Source passages the author was shown

**Passage `cdf2a7975896`** — from `Readme.md`

```
## Consulting
With official support, you can get expert help straight from the Nest core team. We provide dedicated technical support, migration strategies, advice on best practices (and design decisions), PR reviews, and team augmentation. Read more about [support here](https://enterprise.nestjs.com).
```

**Passage `d16ba275076a`** — from `Readme.md`

```
## Issues
Please make sure to read the [Issue Reporting Checklist](https://github.com/nestjs/nest/blob/master/CONTRIBUTING.md#-submitting-an-issue) before opening an issue. Issues not conforming to the guidelines may be closed immediately.
```

**Passage `9e079cffb1b8`** — from `Readme.md`

```
## Support
Nest is an MIT-licensed open source project. It can grow thanks to the sponsors and support from the amazing backers. If you'd like to join them, please [read more here](https://docs.nestjs.com/support).
```

**Passage `e4e5326dfc0e`** — from `Readme.md`

```
## Philosophy
<p>In recent years, thanks to Node.js, JavaScript has become the “lingua franca” of the web for both front-end and back-end applications, giving rise to awesome projects like <a href="https://angular.dev/" target="_blank">Angular</a>, <a href="https://react.dev/" target="_blank">React</a>, and <a href="https://vuejs.org/" target="_blank">Vue</a>, which improve developer productivity and enable the construction of fast, testable, and extensible frontend applications. However, on the server-side, while there are a lot of superb libraries, helpers, and tools for Node, none of them effectively solve the main problem - the architecture.</p>
<p>Nest aims to provide an application architecture out of the box which allows for effortless creation of highly testable, scalable, and loosely coupled and easily maintainable applications. The architecture is heavily inspired by Angular.</p>
```

**Passage `f39977a0f1bb`** — from `Readme.md`

```
## Description
Nest is a framework for building efficient, scalable <a href="https://nodejs.org" target="_blank">Node.js</a> server-side applications. It uses modern JavaScript, is built with <a href="https://www.typescriptlang.org" target="_blank">TypeScript</a> (preserves compatibility with pure JavaScript) and combines elements of OOP (Object Oriented Programming), FP (Functional Programming), and FRP (Functional Reactive Programming).

<p>Under the hood, Nest makes use of <a href="https://expressjs.com/" target="_blank">Express</a>, but also provides compatibility with a wide range of other libraries, like <a href="https://github.com/fastify/fastify" target="_blank">Fastify</a>, allowing for easy use of the myriad of third-party plugins which are available.</p>
```


---

## ITEM-044

**Dependency:** `@nextui-org/react` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 2.2.10
- Declared specifier: ^2.2.10
- Where that version came from: lockfile
- Manifest: frontend/package.json
- Dependency group: runtime
- Latest release on the registry: 2.6.11
- Versions behind the latest release: major 0, minor 4, patch 0
- Days since the package's latest release: 640
- Deprecated on the registry: yes
- Registry deprecation message: This package has been deprecated. Please use @heroui/react instead.
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `@nextui-org/react` package is deprecated and the maintainers recommend switching to the new `@heroui/react` library. HeroUI is the rebranded successor of NextUI, and the README lists `@heroui/react` as the full component bundle [21eaae5c289c][9baf941894c4]. Replace the dependency in `frontend/package.json` and install the new package (`npm install @heroui/react`). This migration updates imports to the new namespace and avoids using a deprecated library.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| @nextui-org/react | replace |  | @heroui/react |

### Source passages the author was shown

**Passage `21eaae5c289c`** — from `README.md`

```
## Why HeroUI?
HeroUI (previously NextUI) is a production-ready React component library that combines the accessibility rigor of [React Aria](https://react-spectrum.adobe.com/react-aria/) with the utility-first styling of [Tailwind CSS v4](https://tailwindcss.com/). It ships a clean compound component API (`Card.Header`, `Card.Content`, `Select.Item`, …), requires no `<Provider>` wrapper, and works out of the box with React 19 and Next.js.

- **Accessible by default** — Built on React Aria for WCAG-compliant keyboard, focus, and screen-reader behavior
- **Tailwind CSS v4** — Modern engine, no CSS-in-JS runtime, smaller output, faster builds
- **Compound components** — Composable API (`Card.Header`, `Card.Content`) instead of deeply nested props
- **Zero boilerplate** — No Provider wrapper needed (unlike Chakra, MUI)
- **AI-native** — MCP server, `llms.txt`, and agent skills so AI assistants understand your components
- **Battle-tested** — Previously known as NextUI, trusted by thousands of production apps
```

**Passage `d0ff68f739c8`** — from `README.md`

```
## Who Is This For?
HeroUI is a good fit if you are building:

- **SaaS applications** — forms, tables, overlays, and notifications out of the box
- **Dashboards & admin panels** — data-dense layouts with consistent design tokens
- **E-commerce storefronts** — performant, accessible, SEO-friendly components
- **Marketing sites & landing pages** — polished UI without a heavyweight runtime
- **Any React / Next.js project** that values design quality and accessibility
```

**Passage `9baf941894c4`** — from `README.md`

```
## Packages
| Package | Description |
|---|---|
| [`@heroui/react`](https://www.npmjs.com/package/@heroui/react) | Full component bundle |
| [`@heroui/styles`](https://www.npmjs.com/package/@heroui/styles) | Styles / theme only |
| Individual packages | e.g. `@heroui/button`, `@heroui/modal` — tree-shakeable per-component imports |
```

**Passage `8c98d7f8a412`** — from `README.md`

```
## Getting Started
Visit [heroui.com/docs/react/getting-started/quick-start](https://heroui.com/docs/react/getting-started/quick-start) to get started with HeroUI.

```bash
npm install @heroui/react
```
```

**Passage `bd5879276db5`** — from `README.md`

```
## Documentation
- **Latest (v3)**: [heroui.com](https://heroui.com)
- **v2**: [v2.heroui.com](https://v2.heroui.com)
```


---

## ITEM-045

**Dependency:** `pyyaml` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 3.12
- Declared specifier: ==3.12
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 6.0.3
- Versions behind the latest release: major 2, minor 1, patch 0
- Days since the package's latest release: 373
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 4
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 4
  - CVE-2020-14343 / GHSA-8q59-q68h-6hv4: severity critical, CVSS 9.8, fixed in 5.4
  - CVE-2017-18342 / GHSA-rprw-h62v-c2w7: severity critical, CVSS 9.8, fixed in 5.1
  - CVE-2017-18342 / PYSEC-2018-49: severity unknown, CVSS not recorded, fixed in 5.1
  - CVE-2020-14343 / PYSEC-2021-142: severity unknown, CVSS not recorded, fixed in 5.4

### Remediation to label

The scan flags **pyyaml==3.12** as vulnerable (critical CVEs). The README does not mention which release fixes the issues or any migration guidance【01f4a09182a3】. Advisory data indicates that versions 5.1 and 5.4 address the reported CVEs and the latest available version is 6.0.3. Upgrade the entry in requirements.txt to at least 5.4 (preferably the newest 6.0.3) to remediate the vulnerabilities.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| pyyaml | upgrade | 6.0.3 |  |

### Source passages the author was shown

**Passage `833adc5f9df1`** — from `README.md`

```
## Further Information
* For more information, check the
  [PyYAML homepage](https://github.com/yaml/pyyaml).

* [PyYAML tutorial and reference](http://pyyaml.org/wiki/PyYAMLDocumentation).

* Discuss PyYAML with the maintainers on
  Matrix at https://matrix.to/#/#pyyaml:yaml.io or
  IRC #pyyaml irc.libera.chat

* Submit bug reports and feature requests to the
  [PyYAML bug tracker](https://github.com/yaml/pyyaml/issues).
```

**Passage `186d787c0b01`** — from `README.md`

```
## License
The PyYAML module was written by Kirill Simonov <xi@resolvent.net>.
It is currently maintained by the YAML and Python communities.

PyYAML is released under the MIT license.

See the file LICENSE for more details.
```

**Passage `01f4a09182a3`** — from `README.md`

```
PyYAML
======

A full-featured YAML processing framework for Python
```

**Passage `5dd9bf807225`** — from `README.md`

```
## Testing
PyYAML includes a comprehensive test suite.

To run the complete local test suite, type:

    make test

This creates a local Python environment, runs the pure Python tests, builds a
local copy of LibYAML, and then runs the LibYAML extension tests. The local
LibYAML build is pinned by `LIBYAML-REF`, which defaults to `0.2.5`.

To run only one test mode:

    make test-python
    make test-libyaml

To test with a specific Python version:

    make test PYTHON-VERSION=3.13.5
```

**Passage `86b6e2c81004`** — from `README.md`

```
## Installation
To install, type `python setup.py install`.

By default, the `setup.py` script checks whether LibYAML is installed and if
so, builds and installs LibYAML bindings.
To skip the check and force installation of LibYAML bindings, use the option
`--with-libyaml`: `python setup.py --with-libyaml install`.
To disable the check and skip building and installing LibYAML bindings, use
`--without-libyaml`: `python setup.py --without-libyaml install`.

When LibYAML bindings are installed, you may use fast LibYAML-based parser and
emitter as follows:

    >>> yaml.load(stream, Loader=yaml.CLoader)
    >>> yaml.dump(data, Dumper=yaml.CDumper)

If you don't trust the input YAML stream, you should use:

    >>> yaml.safe_load(stream)
```


---

## ITEM-046

**Dependency:** `scikit-learn` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.1.1
- Declared specifier: ==1.1.1
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 1.9.1
- Versions behind the latest release: major 0, minor 8, patch 2
- Days since the package's latest release: 27
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: medium
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2024-5206 / GHSA-jw8x-6495-233v: severity medium, CVSS 5.3, fixed in 1.5.0
  - CVE-2024-5206 / PYSEC-2024-110: severity medium, CVSS 4.7, fixed in 1.5.0

### Remediation to label

The current pinned version 1.1.1 of **scikit-learn** is vulnerable (CVE‑2024‑5206). Advisory data indicates the issue is fixed starting with version 1.5.0, and a newer 1.9.1 release is available. Upgrade the requirement in `requirements.txt` to at least 1.5.0 (preferably the latest 1.9.1) to resolve the vulnerability. No documentation was retrieved to describe additional migration steps.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| scikit-learn | upgrade | 1.5.0 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-047

**Dependency:** `gdown` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 3.13.0
- Declared specifier: ==3.13.0
- Where that version came from: pinned
- Manifest: requirements_demo.txt
- Dependency group: runtime
- Latest release on the registry: 6.4.1
- Versions behind the latest release: major 3, minor 2, patch 1
- Days since the package's latest release: 8
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2026-40491 / PYSEC-2026-2158: severity high, CVSS 7.8, fixed in 5.2.2
  - CVE-2026-40491 / GHSA-76hw-p97h-883f: severity medium, CVSS 6.5, fixed in 5.2.2

### Remediation to label

The project pins **gdown==3.13.0**, which is reported as vulnerable (CVE‑2026‑40491) with a high severity rating. The scan data indicates the vulnerability is fixed starting in version **5.2.2** and the newest release is **6.4.1**. Upgrade the requirement to at least 5.2.2 (or the latest 6.4.1) to eliminate the issue. No documentation passages were retrieved, so the recommendation is based solely on the scan metadata.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| gdown | upgrade | 5.2.2 |  |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-048

**Dependency:** `pyjwt` (pypi)

**Measured data** (all of it counts as evidence):

- Version in use: 1.6.0
- Declared specifier: ==1.6.0
- Where that version came from: pinned
- Manifest: requirements.txt
- Dependency group: runtime
- Latest release on the registry: 2.15.1
- Versions behind the latest release: major 1, minor 1, patch 3
- Days since the package's latest release: 9
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 19
- Highest advisory severity: critical
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 5
  - CVE-2026-102268 / GHSA-ffc3-869f-jxw9: severity critical, CVSS 9.1, fixed in 2.14.0
  - CVE-2026-102268 / PYSEC-2026-4145: severity critical, CVSS 9.1, fixed in 2.14.0
  - CVE-2026-32597 / GHSA-752w-5fwx-jx9f: severity high, CVSS 7.5, fixed in 2.12.0
  - CVE-2026-32597 / PYSEC-2026-120: severity high, CVSS 7.5, fixed in 2.12.0
  - CVE-2026-102267 / GHSA-9v7f-9g4p-ffgj: severity high, CVSS 7.4, fixed in 2.14.0

### Remediation to label

pyjwt 1.6.0 is affected by several critical and high‑severity vulnerabilities. The advisory data shows that version 2.14.0 (and later) contains fixes for CVE‑2026‑102268 and CVE‑2026‑32597, and the current latest release is 2.15.1. Upgrade the dependency in requirements.txt to at least 2.14.0 (e.g., `pyjwt==2.15.1`). This change does not require code modifications for basic encode/decode usage, but review the release notes for any breaking changes when moving from 1.x to 2.x. After upgrading, re‑run tests to confirm compatibility.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| pyjwt | upgrade | 2.14.0 |  |

### Source passages the author was shown

**Passage `439371e9b7ba`** — from `README.rst`

```
----------------------------------------------------------------+

Installing
----------

Install with **pip**:

.. code-block:: console

    $ pip install PyJWT


Usage
-----

.. code-block:: pycon

    >>> import jwt
    >>> encoded = jwt.encode({"some": "payload"}, "secret", algorithm="HS256")
    >>> print(encoded)
    eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzb21lIjoicGF5bG9hZCJ9.4twFt5NiznN84AWoo1d7KO1T_yoc0Z6XOpOVswacPZg
    >>> jwt.decode(encoded, "secret", algorithms=["HS256"])
    {'some': 'payload'}

Documentation
-------------

View the full docs online at https://pyjwt.readthedocs.io/en/stable/


Tests
-----

You can run tests from the project root after cloning with:

.. code-block:: console

    $ tox
```

**Passage `a550643918f7`** — from `README.rst`

```
PyJWT
=====

.. image:: https://github.com/jpadilla/pyjwt/workflows/CI/badge.svg
   :target: https://github.com/jpadilla/pyjwt/actions?query=workflow%3ACI

.. image:: https://img.shields.io/pypi/v/pyjwt.svg
   :target: https://pypi.python.org/pypi/pyjwt

.. image:: https://codecov.io/gh/jpadilla/pyjwt/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/jpadilla/pyjwt

.. image:: https://readthedocs.org/projects/pyjwt/badge/?version=stable
   :target: https://pyjwt.readthedocs.io/en/stable/

A Python implementation of `RFC 7519 <https://tools.ietf.org/html/rfc7519>`_. Original implementation was written by `@progrium <https://github.com/progrium>`_.

Sponsor
-------

.. |auth0-logo| image:: https://github.com/user-attachments/assets/ee98379e-ee76-4bcb-943a-e25c4ea6d174
   :width: 160px
```

**Passage `35424d1a2e25`** — from `README.rst`

```
was written by `@progrium <https://github.com/progrium>`_.

Sponsor
-------

.. |auth0-logo| image:: https://github.com/user-attachments/assets/ee98379e-ee76-4bcb-943a-e25c4ea6d174
   :width: 160px

+--------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
| |auth0-logo| | If you want to quickly add secure token-based authentication to Python projects, feel free to check Auth0's Python SDK and free plan at `auth0.com/signup <https://auth0.com/signup?utm_source=external_sites&utm_medium=pyjwt&utm_campaign=devn_signup>`_. |
+--------------+-----------------------------------------------------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Installing
----------

Install with **pip**:

.. code-block:: console

    $ pip install PyJWT


Usage
-----

.. code-block:: pycon
```


---

## ITEM-049

**Dependency:** `react-navigation-tabs` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 2.5.6
- Declared specifier: 2.5.6
- Where that version came from: pinned
- Manifest: tutorials/mobile/react-native-apollo/app-boilerplate/package.json
- Dependency group: runtime
- Latest release on the registry: 2.11.2
- Versions behind the latest release: major 0, minor 6, patch 0
- Days since the package's latest release: 1708
- Deprecated on the registry: yes
- Registry deprecation message: This package is no longer supported. Please use @react-navigation/bottom-tabs instead. See https://reactnavigation.org/docs/bottom-tab-navigator/ for usage guide
- Advisories affecting this version (scanner's count): 0
- Highest advisory severity: not recorded
- Why it was flagged: deprecated, stale
- Advisories in detail (highest CVSS first): none

### Remediation to label

The `react-navigation-tabs` package (v2.5.6) is marked as deprecated and no longer supported. Its deprecation notice advises switching to `@react-navigation/bottom-tabs`. While a newer 2.11.2 release exists, the package remains deprecated, so the safest remediation is to replace it with the recommended bottom‑tabs library. Update your `package.json` to remove `react-navigation-tabs` and add `@react-navigation/bottom-tabs` according to the migration guide linked in the deprecation message.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| react-navigation-tabs | replace |  | @react-navigation/bottom-tabs |

### Source passages the author was shown

_None. The author was shown no passages for this item._

---

## ITEM-050

**Dependency:** `webpack-dev-middleware` (npm)

**Measured data** (all of it counts as evidence):

- Version in use: 3.1.3
- Declared specifier: ^3.1.3
- Where that version came from: lockfile
- Manifest: package.json
- Dependency group: development
- Latest release on the registry: 8.3.0
- Versions behind the latest release: major 5, minor 6, patch 0
- Days since the package's latest release: 34
- Deprecated on the registry: no
- Advisories affecting this version (scanner's count): 2
- Highest advisory severity: high
- Why it was flagged: vulnerable
- Advisories in detail (highest CVSS first): 2
  - CVE-2026-76844 / GHSA-g84c-rxfj-3j2c: severity high, CVSS 7.4, fixed in 8.3.0
  - CVE-2024-29180 / GHSA-wr3j-pwj9-hqq6: severity high, CVSS 7.4, fixed in 7.1.0

### Remediation to label

The project is using **webpack-dev-middleware 3.1.3**, which is flagged as vulnerable (CVE‑2026‑76844, CVE‑2024‑29180). Both advisories are fixed in version **8.3.0** according to the advisory data, so upgrading to at least that version will resolve the issues. The changelog notes that a release addressed “18 security vulnerabilities”【9937e3929a15】, confirming that security fixes are part of newer releases. Upgrading may involve a major version jump, and the changelog does not provide detailed migration guidance, so review the release notes for potential breaking changes. Apply the upgrade in your package.json to eliminate the high‑severity vulnerabilities.

| Package | Fix | Target version | Replacement |
|---|---|---|---|
| webpack-dev-middleware | upgrade | 8.3.0 |  |

### Source passages the author was shown

**Passage `ebcd931ef71a`** — from `CHANGELOG.md`

```
### [5.2.1](https://github.com/webpack/webpack-dev-middleware/compare/v5.2.0...v5.2.1) (2021-09-25)
- internal release, no visible changes and features
```

**Passage `44208a984fa8`** — from `CHANGELOG.md`

```
## [4.0.0-rc.3](https://github.com/webpack/webpack-dev-middleware/compare/v4.0.0-rc.2...v4.0.0-rc.3) (2020-07-14)
- internal improvements
```

**Passage `65959f157a91`** — from `CHANGELOG.md`

```
### Features
- **middleware:** expose the memory filesystem (`response.locals.fs`) ([#337](https://github.com/webpack/webpack-dev-middleware/issues/337)) ([f9a138e](https://github.com/webpack/webpack-dev-middleware/commit/f9a138e))

<a name="3.2.0"></a>
```

**Passage `9937e3929a15`** — from `CHANGELOG.md`

```
### Bug Fixes
- **package:** 18 security vulnerabilities ([#329](https://github.com/webpack/webpack-dev-middleware/issues/329)) ([5951de9](https://github.com/webpack/webpack-dev-middleware/commit/5951de9))
```

**Passage `2e14a6da5e6f`** — from `CHANGELOG.md`

```
### Patch Changes
- Fixed compatibility with rspack. (by [@alexander-akait](https://github.com/alexander-akait) in [#2295](https://github.com/webpack/webpack-dev-middleware/pull/2295))
```


---

# S3 qualitative slice

One example per kind of outcome (File C §3.4.9). Each is the first item, by id, that meets its kind's definition, so the selection is a rule rather than a choice. Faithfulness labels are the human's (WP-9); the judge is not validated (kappa 0.134).

## 1. Grounded and correct

*Rule: B or C, grounding sufficient, at least one passage cited, correct, and labelled faithful by the human.*

- **Item:** `S3-3dc2ebde9f`, condition **C**, pypi, `cve_fix`, WP-9 `ITEM-039`
- **Dependency:** `daphne@2.1.2`; latest 4.2.3; deprecated no
- **Advisories (fixed in):** CVE-2026-44545 (4.2.2), CVE-2026-44546 (4.2.2)
- **Ground truth:** upgrade to 4.2.2 or later
- **Outcome:** correct True (escapes_every_advisory); grounding sufficient; branch no_reason; TARGET shows the answer: yes
- **Passages shown:** `README.rst` (readme, sim 0.38), `README.rst` (readme, sim 0.34), `README.rst` (readme, sim 0.33), `README.rst` (readme, sim 0.29), `README.rst` (readme, sim 0.26)
- **Human label:** faithful

**The plan's summary:**

> The current pinned version 2.1.2 of **daphne** is vulnerable; the security advisories are fixed starting in version **4.2.2** (the latest is 4.2.3). Upgrading the `requirements.txt` entry to at least `daphne==4.2.2` will resolve the CVE‑2026‑44545 and CVE‑2026‑44546 issues. Daphne now requires Python 3.10 or newer, so ensure your runtime meets that requirement [097c6edf9021]. If you use HTTP/2 you may also need the Twisted `tls` and `http2` extras as described in the README [2f12eda0a1c2].

| Fix | Target version | Replacement |
|---|---|---|
| upgrade | 4.2.2 |  |

## 2. Grounded but wrong

*Rule: B or C, grounding sufficient, at least one passage shown, not correct, and TARGET did show a correct answer.*

- **Item:** `S3-07e91951e7`, condition **B**, npm, `deprecation_replacement`
- **Dependency:** `@babel/plugin-proposal-class-properties@7.8.3`; latest 7.18.6; deprecated yes ("This proposal has been merged to the ECMAScript standard and thus this plugin is no longer maintained. Please use @babel/plugin-transform-class-properties instead.")
- **Advisories (fixed in):** none
- **Ground truth:** replace with `@babel/plugin-transform-class-properties`
- **Outcome:** correct False (no_replacement); grounding sufficient; branch fixed; TARGET shows the answer: yes
- **Passages shown:** `CHANGELOG.md` (changelog, sim 0.62), `CHANGELOG.md` (changelog, sim 0.62), `CHANGELOG.md` (changelog, sim 0.61), `CHANGELOG.md` (changelog, sim 0.61), `CHANGELOG.md` (changelog, sim 0.61)

**The plan's summary:**

> The `@babel/plugin-proposal-class-properties` plugin is deprecated. The provided changelog excerpts do not mention any newer version or a replacement for this plugin. You should investigate how to address this, such as upgrading to a maintained alternative or removing it if unnecessary.

| Fix | Target version | Replacement |
|---|---|---|
| investigate |  |  |

## 3. Honest abstention

*Rule: C, grounding low, and the plan declares insufficient information.*

- **Item:** `S3-211276731e`, condition **C**, npm, `deprecation_replacement`
- **Dependency:** `@clerk/clerk-react@4.30.3`; latest 5.61.3; deprecated yes ("This package is no longer supported. Please use @clerk/react instead. See the upgrade guide for more info: https://clerk.com/docs/guides/development/upgrading/upgrade-guides/core-3")
- **Advisories (fixed in):** none
- **Ground truth:** replace with `@clerk/react`
- **Outcome:** correct True (successor_named); grounding low; branch reason_available; TARGET shows the answer: yes
- **Passages shown:** none

**The plan's summary:**

> RepoVitals could not retrieve enough of this package's documentation to support a detailed plan, so what follows rests on the scan's own measurements alone. The package **@clerk/clerk-react** is marked deprecated in the registry, with the deprecation reason indicating it is no longer supported and recommending the use of **@clerk/react** instead. It is currently behind by one major, two minor, and seven patch versions. To address the deprecation, consider replacing the dependency with the suggested package. No further migration details are available from the scan.

| Fix | Target version | Replacement |
|---|---|---|
| replace |  | @clerk/react |

## 4. Unsupported core claim

*Rule: labelled major_unsupported by the human.*

- **Item:** `S3-04ab73079a`, condition **B**, pypi, `cve_fix`, WP-9 `ITEM-003`
- **Dependency:** `h11@0.14.0`; latest 0.16.0; deprecated no
- **Advisories (fixed in):** CVE-2025-43859 (0.16.0)
- **Ground truth:** upgrade to 0.16.0 or later
- **Outcome:** correct True (escapes_every_advisory); grounding sufficient; branch fixed; TARGET shows the answer: yes
- **Passages shown:** `README.rst` (readme, sim 0.46), `README.rst` (readme, sim 0.44), `README.rst` (readme, sim 0.35), `README.rst` (readme, sim 0.34), `README.rst` (readme, sim 0.33)
- **Human label:** major_unsupported — 'The upgrade does not change its API surface' is not in the measured data or passages (they only say h11 is a toolkit); treated as core because it asserts the upgrade is non-breaking. Target 0.16.0 is supported.

**The plan's summary:**

> Your project pins h11 at version 0.14.0, which is flagged as **critical** (CVE‑2025‑43859) and has a fix in version 0.16.0. Upgrading the `requirements-lock.txt` entry to `h11==0.16.0` will resolve the vulnerability. h11 is a low‑level HTTP/1.1 toolkit rather than a full client library, so the upgrade does not change its API surface [ b1a30cd2b9c3 ].

| Fix | Target version | Replacement |
|---|---|---|
| upgrade | 0.16.0 |  |

## 5. Overclaim on coverage

*Rule: labelled unsupported by the human with a note that the plan claims to fix all known vulnerabilities.*

- **Item:** `S3-45c2ef2c7b`, condition **B**, pypi, `cve_fix`, WP-9 `ITEM-020`
- **Dependency:** `sqlparse@0.4.1`; latest 0.6.0; deprecated no
- **Advisories (fixed in):** CVE-2024-4340 (0.5.0), CVE-2021-32839 (0.4.2), CVE-2026-59893 (0.6.0)
- **Ground truth:** upgrade to 0.6.0 or later
- **Outcome:** correct True (escapes_every_advisory); grounding sufficient; branch fixed; TARGET shows the answer: yes
- **Passages shown:** `CHANGELOG` (changelog, sim 0.63), `CHANGELOG` (changelog, sim 0.58), `CHANGELOG` (changelog, sim 0.55), `CHANGELOG` (changelog, sim 0.54), `CHANGELOG` (changelog, sim 0.54)
- **Human label:** major_unsupported — '(Or at least 0.5.0) removes all known vulnerabilities' contradicts the measured data (CVE-2026-59893 is fixed only in 0.6.0); target 0.6.0, the latest release, is supported.

**The plan's summary:**

> The project pins **sqlparse==0.4.1**, which is vulnerable to several high‑severity CVEs (CVE‑2024‑4340, CVE‑2021‑32839, CVE‑2026‑59893). The 0.5.0 release introduced a fix for the denial‑of‑service issue (recursion error) that addresses CVE‑2024‑4340 【3ecd17565546】, and later releases (0.6.0) contain the remaining security patches. Upgrading sqlparse to the latest version 0.6.0 (or at least 0.5.0) removes all known vulnerabilities. Update the version constraint in **requirements.txt** accordingly.

| Fix | Target version | Replacement |
|---|---|---|
| upgrade | 0.6.0 |  |

## 6. Missed successor

*Rule: labelled unsupported by the human with a note that the plan says no successor or replacement is known.*

- **Item:** `S3-30835ec6e2`, condition **A**, npm, `deprecation_replacement`, WP-9 `ITEM-026`
- **Dependency:** `stylelint-config-factorial@7.1.1`; latest 7.1.1; deprecated yes ("DEPRECATED: Please use stylelint-config-suitcss instead.")
- **Advisories (fixed in):** none
- **Ground truth:** replace with `stylelint-config-suitcss`
- **Outcome:** correct False (no_replacement); grounding n/a (condition A retrieves nothing); TARGET shows the answer: yes
- **Passages shown:** none
- **Human label:** major_unsupported — 'No source information confirming a ... successor' is contradicted by the deprecation message, which names stylelint-config-suitcss as the replacement; the core recommendation (investigate/remove, no replacement) is not what the measured data supports.

**The plan's summary:**

> The scan flags **stylelint-config-factorial** as deprecated and stale, and no documentation was retrieved to describe a migration path or replacement. Because there is no source information confirming a safe upgrade or successor, you should investigate the necessity of this package and consider removing it or switching to an alternative after further research.

| Fix | Target version | Replacement |
|---|---|---|
| investigate |  |  |

## 7. Retrieval made it worse

*Rule: TARGET did not show a correct answer; A was correct and C was not.*

- **Item:** `S3-03551af2a3`, condition **C**, pypi, `cve_fix`
- **Dependency:** `torch@2.0.0`; latest 2.14.1; deprecated no
- **Advisories (fixed in):** CVE-2024-48063 (2.5.0), CVE-2025-32434 (2.6.0), CVE-2026-24747 (2.10.0), CVE-2024-31583 (2.2.0), CVE-2026-4538 (no fix recorded)
- **Ground truth:** upgrade to 2.13.0 or later
- **Outcome:** correct False (still_affected_or_not_an_upgrade); grounding sufficient; branch no_reason; TARGET shows the answer: no
- **Passages shown:** `README.md` (readme, sim 0.45), `README.md` (readme, sim 0.39), `README.md` (readme, sim 0.39), `README.md` (readme, sim 0.38), `README.md` (readme, sim 0.29)

**The plan's summary:**

> The critical CVEs listed are fixed starting with PyTorch 2.5.0, and the high‑severity CVE‑2026‑24747 is only fixed in 2.10.0, so upgrading to at least version 2.10.0 (or the newest 2.14.1) will resolve all known issues. Updating requires changing the pinned specifier in *pre-requirements.txt* from `==2.0.0` to the desired version and reinstalling the package. The README points developers to the release notes for details (see RELEASE.md) but does not describe specific breaking changes for these versions, so consult the official release documentation before upgrading.

| Fix | Target version | Replacement |
|---|---|---|
| upgrade | 2.10.0 |  |

## 8. README-only retrieval

*Rule: B on PyPI, every passage shown is from a README, and precision@k is 0.*

- **Item:** `S3-025ccd1209`, condition **B**, pypi, `cve_fix`
- **Dependency:** `pytest@3.5.1`; latest 9.1.1; deprecated no
- **Advisories (fixed in):** CVE-2025-71176 (9.0.3)
- **Ground truth:** upgrade to 9.0.3 or later
- **Outcome:** correct True (escapes_every_advisory); grounding sufficient; branch fixed; TARGET shows the answer: yes
- **Passages shown:** `README.rst` (readme, sim 0.67), `README.rst` (readme, sim 0.62), `README.rst` (readme, sim 0.52), `README.rst` (readme, sim 0.50), `README.rst` (readme, sim 0.45)

**The plan's summary:**

> Your project is using pytest 3.5.1, which is flagged as vulnerable (CVE‑2025‑71176). The advisory data lists version 9.0.3 as the first release that fixes the issue, and the latest available release is 9.1.1. The pytest README advises consulting the Changelog page for fixes and enhancements [2], so upgrading to the latest version will apply the security patches. Updating the `Pipfile` to `pytest >=9.1.1` resolves the vulnerability without needing to replace the package.

| Fix | Target version | Replacement |
|---|---|---|
| upgrade | 9.1.1 |  |

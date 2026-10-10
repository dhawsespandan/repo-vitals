# WP-9: judge validation

- Items: 50
- Cohen's kappa (human vs judge): **-0.023**
- Linearly weighted kappa (ordinal): -0.010
- Raw agreement: 22.0%
- **Decision:** kappa < 0.50: tighten the rubric, re-judge and re-validate before any S3 claim

## Confusion (rows: human, columns: judge)

| | faithful | minor_unsupported | major_unsupported |
|---|---|---|---|
| faithful | 10 | 1 | 0 |
| minor_unsupported | 18 | 1 | 1 |
| major_unsupported | 17 | 2 | 0 |

## Disagreements

| Item | Human | Judge | Condition | Ecosystem | Human note | Judge note |
|---|---|---|---|---|---|---|
| ITEM-001 | major_unsupported | faithful | A | pypi | Target version 5.19.0 ('the newest release') is not in the facts and no passages were shown; the facts give 4.48.0 for the high CVEs and no fix for CVE-2026-5241, so 'updating to the latest version will address all known vulnerabilities' is also unsupported. |  |
| ITEM-003 | major_unsupported | minor_unsupported | B | pypi | 'The upgrade does not change its API surface' is not in the facts or passages (they only say h11 is a toolkit); treated as core because it asserts the upgrade is non-breaking. Target 0.16.0 is supported. | The report asserts that the upgrade does not change its API surface, which is not stated in the source. |
| ITEM-005 | minor_unsupported | faithful | A | npm | 'A newer release 10.4.3 is available' is not in the facts (no passages were shown); the upgrade to the fixed version 9.5.6 is supported. |  |
| ITEM-006 | major_unsupported | faithful | A | pypi | Target version 1.9.1 ('latest version on PyPI') is not in the facts (no passages were shown); the facts give fixes in 1.0.1 and 1.5.0, which the text wrongly says cannot be identified. |  |
| ITEM-007 | minor_unsupported | faithful | B | npm | 'The current latest 8.0.7' is not in the facts or passages; target 8.0.0-rc.6 and the cited Babel 8 breaking changes (#18079, #17633) are supported. |  |
| ITEM-008 | minor_unsupported | faithful | C | pypi | 'The latest 1.18.1' is not in the facts or passages; the upgrade to 1.10.0 is supported by the measured fix. |  |
| ITEM-009 | minor_unsupported | faithful | C | npm | 'A direct upgrade to 7.23.2 should be safe' is not in the evidence (the passages say nothing about 7.x upgrades); target 7.23.2 and the cited Babel 8 breaking change are supported. |  |
| ITEM-011 | minor_unsupported | faithful | C | npm | 'The latest 12.1.2' is not in the facts or passages; the upgrade to 11.0.16 is supported by the measured fix. |  |
| ITEM-012 | minor_unsupported | faithful | A | npm | 'A newer 5.61.3 release exists' is not in the facts (no passages were shown); the replacement @clerk/react is named in the deprecation message. |  |
| ITEM-013 | minor_unsupported | faithful | B | npm | 'The latest 9.0.3' is not in the facts or passages; target 9.0.0, its breaking changes and the v8-to-v9 migration guide are supported. |  |
| ITEM-014 | minor_unsupported | major_unsupported | C | pypi | Several peripheral claims unsupported: 'added encoding keyword support' is presented as part of this upgrade but the passage puts it in a pre-0.1.6 release, not 0.5.0, and 'the upgrade should be straightforward' is not stated in the evidence; target 0.5.0, the DoS fix and the Python 3.5-3.7 drop are supported. | The report lists CVE-2021-32839 and CVE-2026-59893 under target version 0.5.0, but measured data shows 0.4.2 fixes CVE-2021-32839 and 0.6.0 fixes CVE-2026-59893. |
| ITEM-015 | major_unsupported | faithful | A | pypi | Target version 3.0.6 ('preferably the latest') is not in the facts (no passages were shown); only the fix in 1.0.4 is supported. |  |
| ITEM-016 | major_unsupported | faithful | B | pypi | Target version 12.3.0 ('latest available version on PyPI') is not in the facts or passages; the facts only support upgrading to at least 9.0.1. |  |
| ITEM-018 | minor_unsupported | faithful | A | pypi | 'The latest release is 3.11' is not in the facts (no passages were shown); the upgrade to 3.8.1 is supported by the measured fix. |  |
| ITEM-019 | minor_unsupported | faithful | A | pypi | 'A newer 1.5.5 release is available' is not in the facts (no passages were shown); the upgrade to 1.3.2 is supported by the measured fixes. |  |
| ITEM-020 | major_unsupported | faithful | B | pypi | '(Or at least 0.5.0) removes all known vulnerabilities' contradicts the facts (CVE-2026-59893 is fixed only in 0.6.0); calling 0.6.0 'the latest version' is also not in the evidence. Target 0.6.0 itself is supported. |  |
| ITEM-022 | faithful | minor_unsupported | C | pypi |  | CVE-2026-27205 is fixed in 3.1.3 according to measured data, not 2.3.2. |
| ITEM-023 | major_unsupported | faithful | B | npm | Target version 4.13.3 ('latest 4.x release') is not in the facts or passages; the facts give the fix as 4.2.1. |  |
| ITEM-024 | major_unsupported | faithful | A | npm | Target version 5.12.5 ('the latest') is not in the facts (no passages were shown); the facts support 5.12.2. |  |
| ITEM-025 | major_unsupported | faithful | A | npm | Target version 4.1.7 ('registry shows a newer version') is not in the facts (no passages were shown); it also contradicts the deprecation message, which names the rename to flag-icons, by saying no rename details are available. |  |
| ITEM-026 | major_unsupported | faithful | A | npm | 'No source information confirming a ... successor' is contradicted by the deprecation message, which names stylelint-config-suitcss as the replacement, so the core recommendation (investigate/remove, no replacement) is unsupported; 'stale' is also not in the facts. |  |
| ITEM-027 | major_unsupported | faithful | A | npm | Target version 0.7.0 ('latest available release') is not in the facts (no passages were shown); the facts support 0.6.0. |  |
| ITEM-029 | minor_unsupported | faithful | B | pypi | 'A newer 1.18.1 release is available' is not in the facts or passages; the upgrade to 1.10.0 is supported by the measured fix. |  |
| ITEM-030 | major_unsupported | faithful | B | pypi | Target version 6.5.10 ('the latest release') is not in the facts or passages; the facts support at least 6.5.6. |  |
| ITEM-034 | minor_unsupported | faithful | C | npm | 'No additional options ... are documented' is contradicted by passage 0d203f0dd0ca, which deprecates the spec and loose options of transform-private-methods; the replacement itself is named in the deprecation message. |  |
| ITEM-035 | major_unsupported | faithful | A | npm | Target version 10.0.16 ('latest available release') is not in the facts (no passages were shown); the highest measured fix is 10.0.6. |  |
| ITEM-036 | major_unsupported | faithful | A | pypi | Target version 3.1.9 ('latest available release') is not in the facts (no passages were shown); the facts support at least 3.1.5. |  |
| ITEM-037 | minor_unsupported | faithful | B | npm | 'Its latest 4.1.7 release' (of flag-icon-css) is not in the facts or passages; the replacement flag-icons, the rename at 5.0.0 and the class-name change are supported. |  |
| ITEM-038 | minor_unsupported | faithful | B | npm | Several peripheral claims unsupported: 'no newer version available (latest = 7.20.7)' is not in the facts or passages, and the changelog does not present the transform plugin 'as the successor' (only the deprecation message does); the replacement itself is supported. |  |
| ITEM-039 | minor_unsupported | faithful | C | pypi | 'The latest is 4.2.3' is not in the facts or passages; target 4.2.2, the Python 3.10 requirement and the Twisted tls/http2 extras are supported. |  |
| ITEM-040 | major_unsupported | faithful | A | npm | Target version 1.20.0 ('latest available release') is not in the facts (no passages were shown); the facts support 1.16.0, and 'fixed versions starting at 1.16.0' misstates them (they range from 1.13.5 to 1.16.0). |  |
| ITEM-041 | major_unsupported | faithful | C | npm | Target version 1.20.0 ('the latest') is not in the facts or passages; the facts support at least 1.16.0. |  |
| ITEM-042 | minor_unsupported | faithful | C | pypi | 'The upgrade is safe for most codebases' is not in the evidence (no passage says the 2.20.0-to-2.31.0 upgrade is safe); target 2.31.0, the Proxy-Authorization fix and the credential-rotation advice are supported. |  |
| ITEM-043 | major_unsupported | faithful | B | npm | Target version 12.1.2 ('the latest') is not in the facts or passages; 'at least 9.0.5 will resolve the known vulnerabilities' also contradicts the facts (CVE-2026-35515 is fixed only in 11.1.18). |  |
| ITEM-045 | major_unsupported | faithful | B | pypi | Target version 6.0.3 ('the latest available version') is not in the facts or passages; the facts support at least 5.4. |  |
| ITEM-046 | minor_unsupported | faithful | A | pypi | 'A newer 1.9.1 release' / 'preferably the latest 1.9.1' is not in the facts (no passages were shown); treated as peripheral because the recommended target in the table (and the text's minimum) is 1.5.0, which matches the measured fix. |  |
| ITEM-047 | minor_unsupported | faithful | A | pypi | 'The newest release is 6.4.1' is not in the facts (no passages were shown); the upgrade to 5.2.2 is supported by the measured fix. |  |
| ITEM-048 | major_unsupported | minor_unsupported | B | pypi | 'This change does not require code modifications for basic encode/decode usage' (a 1.x-to-2.x non-breaking claim) is not in the facts or passages; 'current latest release 2.15.1' is also unsupported. Target 2.14.0 is supported. | The report asserts that the upgrade does not require code modifications for basic encode/decode usage, which is not stated or entailed in the measured data or sources. |
| ITEM-049 | minor_unsupported | faithful | A | npm | 'A newer 2.11.2 release exists' is not in the facts (no passages were shown); the replacement @react-navigation/bottom-tabs is named in the deprecation message. |  |

# WP-9: judge validation

- Items: 50
- Cohen's kappa (human vs judge): **0.134**
- Linearly weighted kappa (ordinal): 0.186
- Raw agreement: 68.0%
- **Decision:** kappa < 0.50: tighten the rubric, re-judge and re-validate before any S3 claim

## Confusion (rows: human, columns: judge)

| | faithful | minor_unsupported | major_unsupported |
|---|---|---|---|
| faithful | 33 | 1 | 0 |
| minor_unsupported | 8 | 1 | 1 |
| major_unsupported | 4 | 2 | 0 |

## Disagreements

| Item | Human | Judge | Condition | Ecosystem | Human note | Judge note |
|---|---|---|---|---|---|---|
| ITEM-001 | minor_unsupported | faithful | A | pypi | 'Updating the dependency to the latest version will address all known vulnerabilities' is not supported: CVE-2026-5241 has no recorded fixed version and only 5 of 44 advisory records are detailed; target 5.19.0 is the latest release in the measured data. |  |
| ITEM-003 | major_unsupported | minor_unsupported | B | pypi | 'The upgrade does not change its API surface' is not in the measured data or passages (they only say h11 is a toolkit); treated as core because it asserts the upgrade is non-breaking. Target 0.16.0 is supported. |  |
| ITEM-006 | minor_unsupported | faithful | A | pypi | 'We cannot point to a specific release that addresses these issues' contradicts the measured data (fixed in 1.0.1 and 1.5.0); target 1.9.1 is the latest release and above both fixes. |  |
| ITEM-009 | minor_unsupported | faithful | C | npm | 'A direct upgrade to 7.23.2 should be safe' is not in the evidence (nothing shown covers 7.x upgrades); target 7.23.2 and the cited Babel 8 breaking change are supported. |  |
| ITEM-014 | minor_unsupported | major_unsupported | C | pypi | Several peripheral claims unsupported: 'added encoding keyword support' is presented as part of this upgrade but the passage puts it in a pre-0.1.6 release, not 0.5.0, and 'the upgrade should be straightforward' is not stated in the evidence; target 0.5.0, the DoS fix and the Python 3.5-3.7 drop are supported. |  |
| ITEM-016 | minor_unsupported | faithful | B | pypi | Several peripheral claims unsupported: 'will eliminate the known vulnerabilities' goes beyond the evidence (101 advisory records, only 5 detailed), and the README passage only links the release notes and changelog without saying the security fixes are documented there; target 12.3.0 is the latest release and above every detailed fix. |  |
| ITEM-020 | major_unsupported | faithful | B | pypi | '(Or at least 0.5.0) removes all known vulnerabilities' contradicts the measured data (CVE-2026-59893 is fixed only in 0.6.0); target 0.6.0, the latest release, is supported. |  |
| ITEM-022 | faithful | minor_unsupported | C | pypi |  |  |
| ITEM-025 | major_unsupported | faithful | A | npm | Says 'details about a rename or migration path are not available' and recommends staying on flag-icon-css 4.1.7, but the deprecation message names the rename to flag-icons; the core recommendation (no replacement) contradicts the measured data. |  |
| ITEM-026 | major_unsupported | faithful | A | npm | 'No source information confirming a ... successor' is contradicted by the deprecation message, which names stylelint-config-suitcss as the replacement; the core recommendation (investigate/remove, no replacement) is not what the measured data supports. |  |
| ITEM-034 | minor_unsupported | faithful | C | npm | 'No additional options ... are documented' is contradicted by passage 0d203f0dd0ca, which deprecates the spec and loose options of transform-private-methods; the replacement itself is named in the deprecation message. |  |
| ITEM-038 | minor_unsupported | faithful | B | npm | 'Appears in Babel's changelog as the successor' misdescribes passage 24ffd7fc7485, which only lists the plugin under a Breaking Change heading; the replacement is named in the deprecation message and 'latest = 7.20.7' is in the measured data. |  |
| ITEM-040 | minor_unsupported | faithful | A | npm | 'The advisory data lists fixed versions starting at 1.16.0' misstates the measured data (fixes range from 1.13.5 to 1.16.0); target 1.20.0 is the latest release and above every detailed fix. |  |
| ITEM-042 | minor_unsupported | faithful | C | pypi | 'The upgrade is safe for most codebases' is not in the evidence (no passage says the 2.20.0-to-2.31.0 upgrade is safe); target 2.31.0, the Proxy-Authorization fix and the credential-rotation advice are supported. |  |
| ITEM-043 | major_unsupported | faithful | B | npm | 'At least 9.0.5 ... will resolve the known vulnerabilities' contradicts the measured data (CVE-2026-35515 is fixed only in 11.1.18); target 12.1.2 itself is the latest release. |  |
| ITEM-048 | major_unsupported | minor_unsupported | B | pypi | 'This change does not require code modifications for basic encode/decode usage' (a 1.x-to-2.x non-breaking claim) is not in the measured data or passages; target 2.14.0 and the latest release 2.15.1 are supported. |  |

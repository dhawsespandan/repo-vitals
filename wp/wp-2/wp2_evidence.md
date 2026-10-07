# WP-2 evidence: what was read for each row

Every value in `wp2_anchor_set.csv` was read on 2026-10-08 from the commit linked in its row below. Repository facts come from the GitHub API (`archived`, `pushed_at`, and the head commit of the default branch). The manifests were planned and parsed by RepoVitals' own code: `plan_manifests`, `adopt_workspace_lockfiles` and the npm/PyPI adapters, with the scanner's 50-manifest and size limits. Nothing was scored, and no registry or OSV data was fetched, except for the one named package@version of each known anchor.

## atom/atom (risky, KNOWN ANCHOR postcss@8.2.10)

- Commit read: [1c3bd35ce2](https://github.com/atom/atom/tree/1c3bd35ce238dc0491def9e1780d04748d8e18af), dated 2022-11-22; GitHub `pushed_at` 2023-01-03; archived: true
- Rule applied: R1 known anchor
- Manifests read: 49 of 84 in the tree; 262 dependencies; readable lockfiles: apm/package-lock.json, package-lock.json, packages/about/package-lock.json, packages/dalek/package-lock.json, packages/welcome/package-lock.json, script/package-lock.json, script/update-server/package-lock.json, script/vsts/package-lock.json
  - [package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/package.json): 157 (lockfile package-lock.json)
  - [apm/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/apm/package.json): 1 (lockfile apm/package-lock.json)
  - [script/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/package.json): 51 (lockfile script/package-lock.json)
  - [packages/about/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/about/package.json): 3 (lockfile packages/about/package-lock.json)
  - [packages/atom-dark-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-dark-syntax/package.json): 0
  - [packages/atom-dark-ui/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-dark-ui/package.json): 0
  - [packages/atom-light-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-light-syntax/package.json): 0
  - [packages/atom-light-ui/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-light-ui/package.json): 0
  - [packages/autoflow/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/autoflow/package.json): 2
  - [packages/base16-tomorrow-dark-theme/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/base16-tomorrow-dark-theme/package.json): 0
  - [packages/base16-tomorrow-light-theme/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/base16-tomorrow-light-theme/package.json): 0
  - [packages/dalek/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/dalek/package.json): 4 (lockfile packages/dalek/package-lock.json)
  - ... 37 more manifests, 44 dependencies
- Anchor as read: `package.json` declares `8.2.10` -> 8.2.10 (lockfile, from package-lock.json; runtime)
- OSV advisories for this exact version: GHSA-566m-qj78-rww5 (CVE-2021-23382), GHSA-6g55-p6wh-862q (CVE-2026-45623), GHSA-7fh5-64p2-3v2j (CVE-2023-44270), GHSA-fxqj-rqcc-2cmp (CVE-2026-69153), GHSA-qx2v-qp2m-jg93 (CVE-2026-41305), GHSA-r28c-9q8g-f849 (CVE-2026-73646)

## atom/apm (risky, KNOWN ANCHOR request@2.88.2)

- Commit read: [d4f986aa53](https://github.com/atom/apm/tree/d4f986aa53c7a4f83e90ac4ef169c0cc53276187), dated 2022-09-28; GitHub `pushed_at` 2022-09-28; archived: true
- Rule applied: R1 known anchor
- Manifests read: 13 of 13 in the tree; 35 dependencies; readable lockfiles: package-lock.json, spec/fixtures/test-module-with-lockfile/package-lock.json
  - [package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/package.json): 32 (lockfile package-lock.json)
  - [native-module/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/native-module/package.json): 0
  - [templates/bundle/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/bundle/package.json): 0
  - [templates/language/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/language/package.json): 0
  - [templates/package-coffeescript/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/package-coffeescript/package.json): 0
  - [templates/package-javascript/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/package-javascript/package.json): 0
  - [templates/theme/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/theme/package.json): 0
  - [spec/fixtures/package-with-native-deps/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/package-with-native-deps/package.json): 1
  - [spec/fixtures/test-module-three/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-three/package.json): 0
  - [spec/fixtures/test-module-two/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-two/package.json): 0
  - [spec/fixtures/test-module-with-dependencies/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-with-dependencies/package.json): 1
  - [spec/fixtures/test-module-with-lockfile/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-with-lockfile/package.json): 1 (lockfile spec/fixtures/test-module-with-lockfile/package-lock.json)
  - ... 1 more manifests, 0 dependencies
- Anchor as read: `package.json` declares `^2.88.2` -> 2.88.2 (lockfile, from package-lock.json; runtime)
- OSV advisories for this exact version: GHSA-p8p7-x288-28g6 (CVE-2023-28155)
- npm deprecation message for this version: "request has been deprecated, see https://github.com/request/request/issues/3142"

## angular/angular.js (risky, KNOWN ANCHOR karma@4.4.1)

- Commit read: [d8f77817eb](https://github.com/angular/angular.js/tree/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe), dated 2024-04-12; GitHub `pushed_at` 2024-04-12; archived: true
- Rule applied: R1 known anchor
- Manifests read: 3 of 3 in the tree; 87 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: scripts/code.angularjs.org-firebase/functions/yarn.lock, scripts/docs.angularjs.org-firebase/functions/yarn.lock, yarn.lock
  - [package.json](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/package.json): 80
  - [scripts/code.angularjs.org-firebase/functions/package.json](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/scripts/code.angularjs.org-firebase/functions/package.json): 3
  - [scripts/docs.angularjs.org-firebase/functions/package.json](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/scripts/docs.angularjs.org-firebase/functions/package.json): 4
- Anchor as read: `package.json` declares `4.4.1` -> 4.4.1 (pinned; development)
- OSV advisories for this exact version: GHSA-7x7c-qm48-pq9c (CVE-2022-0437), GHSA-rc3x-jf5g-xvc5 (CVE-2021-23495)

## angular/protractor (risky, KNOWN ANCHOR lodash@4.17.11)

- Commit read: [4bc80d1a45](https://github.com/angular/protractor/tree/4bc80d1a459542d883ea9200e4e1f48d265d0fda), dated 2020-04-21; GitHub `pushed_at` 2023-05-24; archived: true
- Rule applied: R1 known anchor
- Manifests read: 6 of 6 in the tree; 90 dependencies; readable lockfiles: example/package-lock.json, package-lock.json, testapp/package-lock.json, website/package-lock.json
  - [package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/package.json): 36 (lockfile package-lock.json)
  - [example/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/example/package.json): 2 (lockfile example/package-lock.json)
  - [exampleTypescript/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/exampleTypescript/package.json): 6
  - [testapp/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/testapp/package.json): 21 (lockfile testapp/package-lock.json)
  - [website/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/website/package.json): 19 (lockfile website/package-lock.json)
  - [spec/install/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/spec/install/package.json): 6
- Anchor as read: `package.json` declares `^4.17.11` -> 4.17.11 (lockfile, from package-lock.json; development)
- OSV advisories for this exact version: GHSA-29mw-wpgm-hmr9 (CVE-2020-28500), GHSA-35jh-r3h4-6jhm (CVE-2021-23337,CVE-2026-4800), GHSA-f23m-r3pf-42rh (CVE-2025-13465,CVE-2026-2950), GHSA-jf85-cpcp-j695 (CVE-2019-10744), GHSA-p6mc-m468-83gw (CVE-2020-8203), GHSA-r5fr-rjxr-66jc (CVE-2021-23337,CVE-2026-4800) and 1 more

## microsoft/vscode-go (risky, KNOWN ANCHOR tslint@6.1.1)

- Commit read: [9ee1f173b0](https://github.com/microsoft/vscode-go/tree/9ee1f173b05bb74ee64e4906f832603cd7380687), dated 2020-06-10; GitHub `pushed_at` 2020-06-10; archived: true
- Rule applied: R1 known anchor
- Manifests read: 1 of 1 in the tree; 27 dependencies; readable lockfiles: package-lock.json
  - [package.json](https://github.com/microsoft/vscode-go/blob/9ee1f173b05bb74ee64e4906f832603cd7380687/package.json): 27 (lockfile package-lock.json)
- Anchor as read: `package.json` declares `^6.1.1` -> 6.1.1 (lockfile, from package-lock.json; development)
- npm deprecation message for this version: "TSLint has been deprecated in favor of ESLint. Please see https://github.com/palantir/tslint/issues/4534 for more information."

## facebookarchive/react-native-fbsdk (risky, KNOWN ANCHOR eslint@7.14.0)

- Commit read: [b8ed568b05](https://github.com/facebookarchive/react-native-fbsdk/tree/b8ed568b05f3e41e6d6b937ae3125492f95e60bf), dated 2021-03-26; GitHub `pushed_at` 2021-03-26; archived: true
- Rule applied: R1 known anchor
- Manifests read: 2 of 2 in the tree; 16 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: yarn.lock
  - [package.json](https://github.com/facebookarchive/react-native-fbsdk/blob/b8ed568b05f3e41e6d6b937ae3125492f95e60bf/package.json): 14
  - [example/package.json](https://github.com/facebookarchive/react-native-fbsdk/blob/b8ed568b05f3e41e6d6b937ae3125492f95e60bf/example/package.json): 2
- Anchor as read: `package.json` declares `7.14.0` -> 7.14.0 (pinned; development)
- npm deprecation message for this version: "This version is no longer supported. Please see https://eslint.org/version-support for other options."

## bower/bower (risky, KNOWN ANCHOR request@2.67.0)

- Commit read: [4e0c3c1181](https://github.com/bower/bower/tree/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a), dated 2024-10-13; GitHub `pushed_at` 2024-10-13; archived: false
- Rule applied: R1 known anchor
- Manifests read: 6 of 6 in the tree; 99 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: yarn.lock
  - [package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/package.json): 60
  - [packages/bower-config/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-config/package.json): 13
  - [packages/bower-endpoint-parser/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-endpoint-parser/package.json): 3
  - [packages/bower-json/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-json/package.json): 10
  - [packages/bower-logger/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-logger/package.json): 2
  - [packages/bower-registry-client/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-registry-client/package.json): 11
- Anchor as read: `package.json` declares `2.67.0` -> 2.67.0 (pinned; runtime)
- OSV advisories for this exact version: GHSA-7xfp-9c55-5vqj (CVE-2017-16026), GHSA-p8p7-x288-28g6 (CVE-2023-28155)
- npm deprecation message for this version: "request has been deprecated, see https://github.com/request/request/issues/3142"

## facebookarchive/flux (risky)

- Commit read: [4ee8c50865](https://github.com/facebookarchive/flux/tree/4ee8c50865c357e005cb40ea03cdd403533aad26), dated 2023-03-21; GitHub `pushed_at` 2023-03-21; archived: true
- Rule applied: R2 archived
- Manifests read: 9 of 9 in the tree; 166 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: website/yarn.lock, yarn.lock
  - [package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/package.json): 22
  - [website/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/website/package.json): 5
  - [examples/flux-async/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-async/package.json): 24
  - [examples/flux-flow/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-flow/package.json): 19
  - [examples/flux-jest-container/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-jest-container/package.json): 20
  - [examples/flux-jest/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-jest/package.json): 19
  - [examples/flux-logging/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-logging/package.json): 19
  - [examples/flux-shell/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-shell/package.json): 19
  - [examples/flux-todomvc/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-todomvc/package.json): 19

## react/create-react-app (risky)

- Commit read: [6254386531](https://github.com/react/create-react-app/tree/6254386531d263688ccfa542d0e628fbc0de0b28), dated 2025-02-15; GitHub `pushed_at` 2025-02-15; archived: false
- Rule applied: R4 maintainers declare deprecated/EOL/unmaintained
- Manifests read: 26 of 26 in the tree; 218 dependencies; readable lockfiles: package-lock.json
  - [package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package.json): 23 (lockfile package-lock.json)
  - [docusaurus/website/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/docusaurus/website/package.json): 5 (lockfile package-lock.json)
  - [packages/babel-plugin-named-asset-import/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/babel-plugin-named-asset-import/package.json): 3 (lockfile package-lock.json)
  - [packages/babel-preset-react-app/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/babel-preset-react-app/package.json): 17 (lockfile package-lock.json)
  - [packages/confusing-browser-globals/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/confusing-browser-globals/package.json): 1 (lockfile package-lock.json)
  - [packages/cra-template-typescript/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/cra-template-typescript/package.json): 0 (lockfile package-lock.json)
  - [packages/cra-template/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/cra-template/package.json): 0 (lockfile package-lock.json)
  - [packages/create-react-app/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/create-react-app/package.json): 13 (lockfile package-lock.json)
  - [packages/eslint-config-react-app/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/eslint-config-react-app/package.json): 15 (lockfile package-lock.json)
  - [packages/react-app-polyfill/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-app-polyfill/package.json): 6 (lockfile package-lock.json)
  - [packages/react-dev-utils/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-dev-utils/package.json): 26 (lockfile package-lock.json)
  - [packages/react-error-overlay/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-error-overlay/package.json): 23 (lockfile package-lock.json)
  - ... 14 more manifests, 86 dependencies
- README status line: "Deprecated ... it is now in long-term stasis"

## request/request (risky)

- Commit read: [3c0cddc7c8](https://github.com/request/request/tree/3c0cddc7c8eb60b470e9519da85896ed7ee0081e), dated 2020-02-11; GitHub `pushed_at` 2024-08-14; archived: false
- Rule applied: R4 maintainers declare deprecated/EOL/unmaintained
- Manifests read: 1 of 1 in the tree; 40 dependencies; readable lockfiles: none
  - [package.json](https://github.com/request/request/blob/3c0cddc7c8eb60b470e9519da85896ed7ee0081e/package.json): 40
- README status line: "As of Feb 11th 2020, request is fully deprecated."

## strongloop/loopback (risky)

- Commit read: [13371fd2a1](https://github.com/strongloop/loopback/tree/13371fd2a138a6f39db77e5a455b3170e5d4a0f5), dated 2021-03-06; GitHub `pushed_at` 2023-10-09; archived: false
- Rule applied: R4 maintainers declare deprecated/EOL/unmaintained
- Manifests read: 1 of 1 in the tree; 60 dependencies; readable lockfiles: none
  - [package.json](https://github.com/strongloop/loopback/blob/13371fd2a138a6f39db77e5a455b3170e5d4a0f5/package.json): 60
- README status line: "LoopBack 3.x has reached End-of-Life."

## openai/gpt-2 (risky, KNOWN ANCHOR requests@2.21.0)

- Commit read: [9b63575ef4](https://github.com/openai/gpt-2/tree/9b63575ef42771a015060c964af2c3da4cf7c8ab), dated 2024-01-26; GitHub `pushed_at` 2024-08-14; archived: true
- Rule applied: R1 known anchor
- Manifests read: 1 of 1 in the tree; 4 dependencies; readable lockfiles: none
  - [requirements.txt](https://github.com/openai/gpt-2/blob/9b63575ef42771a015060c964af2c3da4cf7c8ab/requirements.txt): 4
- Anchor as read: `requirements.txt` declares `==2.21.0` -> 2.21.0 (pinned; runtime)
- OSV advisories for this exact version: GHSA-9hjg-9r4m-mvj7 (CVE-2024-47081), GHSA-9wx4-h78v-vm56 (CVE-2024-35195), GHSA-gc5v-m9x4-r6x2 (CVE-2026-25645), GHSA-j8r2-6x86-q33q (CVE-2023-32681), PYSEC-2023-74 (CVE-2023-32681), PYSEC-2026-1872 (CVE-2024-47081) and 2 more

## Netflix/security_monkey (risky, KNOWN ANCHOR PyYAML@5.3)

- Commit read: [c28592ffd5](https://github.com/Netflix/security_monkey/tree/c28592ffd518fa399527d26262683fc860c30eef), dated 2021-02-11; GitHub `pushed_at` 2021-02-11; archived: true
- Rule applied: R1 known anchor
- Manifests read: 2 of 2 in the tree; 58 dependencies; readable lockfiles: none
  - [requirements.txt](https://github.com/Netflix/security_monkey/blob/c28592ffd518fa399527d26262683fc860c30eef/requirements.txt): 46
  - [setup.py](https://github.com/Netflix/security_monkey/blob/c28592ffd518fa399527d26262683fc860c30eef/setup.py): 12
- Anchor as read: `requirements.txt` declares `==5.3` -> 5.3 (pinned; runtime)
- OSV advisories for this exact version: GHSA-6757-jp84-gxfx (CVE-2020-1747), GHSA-8q59-q68h-6hv4 (CVE-2020-14343), PYSEC-2020-96 (CVE-2020-1747), PYSEC-2021-142 (CVE-2020-14343)

## mdn/kuma (risky, KNOWN ANCHOR django@3.2.12)

- Commit read: [ae0860087c](https://github.com/mdn/kuma/tree/ae0860087cfb7ce19c9296f5dfbae10260dca759), dated 2022-08-26; GitHub `pushed_at` 2022-08-26; archived: true
- Rule applied: R1 known anchor
- Manifests read: 2 of 2 in the tree; 51 dependencies; readable lockfiles: poetry.lock
  - [pyproject.toml](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/pyproject.toml): 44 (lockfile poetry.lock)
  - [docs/requirements.txt](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/docs/requirements.txt): 7
- Anchor as read: `pyproject.toml` declares `^3` -> 3.2.12 (lockfile, from poetry.lock; runtime)
- OSV advisories for this exact version: GHSA-2gwj-7jmv-h26r (CVE-2022-28346), GHSA-2hrw-hx67-34x6 (CVE-2023-24580), GHSA-3h9f-r86x-qvjx (CVE-2026-48588), GHSA-6w2r-r2m5-xq5w (CVE-2025-57833), GHSA-7h4p-27mh-hmrw (CVE-2023-41164), GHSA-7xr5-9hcq-chf9 (CVE-2025-48432) and 38 more

## openai/jukebox (risky, KNOWN ANCHOR tqdm@4.45.0)

- Commit read: [08efbbc1d4](https://github.com/openai/jukebox/tree/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3), dated 2020-11-14; GitHub `pushed_at` 2024-06-19; archived: true
- Rule applied: R1 known anchor
- Manifests read: 4 of 4 in the tree; 14 dependencies; readable lockfiles: none
  - [requirements.txt](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/requirements.txt): 7
  - [setup.py](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/setup.py): 1
  - [apex/setup.py](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/apex/setup.py): 0
  - [tensorboardX/setup.py](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/tensorboardX/setup.py): 6
- Anchor as read: `requirements.txt` declares `==4.45.0` -> 4.45.0 (pinned; runtime)
- OSV advisories for this exact version: GHSA-g7vv-2v7x-gj9p (CVE-2024-34062), PYSEC-2026-1976 (CVE-2024-34062)

## googleapis/oauth2client (risky, KNOWN ANCHOR Django@1.10.0)

- Commit read: [50d20532a7](https://github.com/googleapis/oauth2client/tree/50d20532a748f18e53f7d24ccbe6647132c979a9), dated 2018-09-07; GitHub `pushed_at` 2019-11-01; archived: true
- Rule applied: R1 known anchor
- Manifests read: 4 of 4 in the tree; 21 dependencies; readable lockfiles: none
  - [setup.py](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/setup.py): 5
  - [docs/requirements.txt](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/docs/requirements.txt): 10
  - [samples/django/django_user/requirements.txt](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/samples/django/django_user/requirements.txt): 3
  - [samples/django/google_user/requirements.txt](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/samples/django/google_user/requirements.txt): 3
- Anchor as read: `samples/django/django_user/requirements.txt` declares `==1.10.0` -> 1.10.0 (pinned; runtime)
- Anchor as read: `samples/django/google_user/requirements.txt` declares `==1.10.0` -> 1.10.0 (pinned; runtime)
- OSV advisories for this exact version: GHSA-37hp-765x-j95x (CVE-2017-7233), GHSA-3f2c-jm6v-cr35 (CVE-2016-9014), GHSA-3h9f-r86x-qvjx (CVE-2026-48588), GHSA-68w8-qjq3-2gfm (CVE-2021-33203), GHSA-6w2r-r2m5-xq5w (CVE-2025-57833), GHSA-7xr5-9hcq-chf9 (CVE-2025-48432) and 26 more

## tensorflow/tensor2tensor (risky)

- Commit read: [bafdc1b677](https://github.com/tensorflow/tensor2tensor/tree/bafdc1b67730430d38d6ab802cbd51f9d053ba2e), dated 2023-04-01; GitHub `pushed_at` 2023-06-02; archived: true
- Rule applied: R2 archived
- Manifests read: 3 of 3 in the tree; 38 dependencies; readable lockfiles: none
  - [floyd_requirements.txt](https://github.com/tensorflow/tensor2tensor/blob/bafdc1b67730430d38d6ab802cbd51f9d053ba2e/floyd_requirements.txt): 1
  - [setup.py](https://github.com/tensorflow/tensor2tensor/blob/bafdc1b67730430d38d6ab802cbd51f9d053ba2e/setup.py): 36
  - [tensor2tensor/test_data/example_usr_dir/requirements.txt](https://github.com/tensorflow/tensor2tensor/blob/bafdc1b67730430d38d6ab802cbd51f9d053ba2e/tensor2tensor/test_data/example_usr_dir/requirements.txt): 1
- README status line: "It is now deprecated"

## YelpArchive/elastalert (risky)

- Commit read: [e0bbcb5b71](https://github.com/YelpArchive/elastalert/tree/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16), dated 2022-11-12; GitHub `pushed_at` 2024-08-07; archived: false
- Rule applied: R4 maintainers declare deprecated/EOL/unmaintained
- Manifests read: 3 of 3 in the tree; 52 dependencies; readable lockfiles: none
  - [requirements-dev.txt](https://github.com/YelpArchive/elastalert/blob/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16/requirements-dev.txt): 8
  - [requirements.txt](https://github.com/YelpArchive/elastalert/blob/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16/requirements.txt): 22
  - [setup.py](https://github.com/YelpArchive/elastalert/blob/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16/setup.py): 22
- README status line: "ElastAlert is no longer maintained."

## openai/spinningup (risky)

- Commit read: [038665d62d](https://github.com/openai/spinningup/tree/038665d62d569055401d91856abb287263096178), dated 2020-02-07; GitHub `pushed_at` 2024-08-05; archived: false
- Rule applied: R3 no default-branch commit in 3+ years
- Manifests read: 2 of 2 in the tree; 31 dependencies; readable lockfiles: none
  - [setup.py](https://github.com/openai/spinningup/blob/038665d62d569055401d91856abb287263096178/setup.py): 15
  - [docs/docs_requirements.txt](https://github.com/openai/spinningup/blob/038665d62d569055401d91856abb287263096178/docs/docs_requirements.txt): 16

## boto/boto (risky)

- Commit read: [70c65b4f67](https://github.com/boto/boto/tree/70c65b4f67af41ccfd40d21e49880be568997ba6), dated 2022-05-13; GitHub `pushed_at` 2024-01-12; archived: true
- Rule applied: R2 archived
- Manifests read: 5 of 5 in the tree; 24 dependencies; readable lockfiles: none
  - [requirements-docs.txt](https://github.com/boto/boto/blob/70c65b4f67af41ccfd40d21e49880be568997ba6/requirements-docs.txt): 7
  - [requirements-py26.txt](https://github.com/boto/boto/blob/70c65b4f67af41ccfd40d21e49880be568997ba6/requirements-py26.txt): 5
  - [requirements-py33.txt](https://github.com/boto/boto/blob/70c65b4f67af41ccfd40d21e49880be568997ba6/requirements-py33.txt): 2
  - [requirements.txt](https://github.com/boto/boto/blob/70c65b4f67af41ccfd40d21e49880be568997ba6/requirements.txt): 10
  - [setup.py](https://github.com/boto/boto/blob/70c65b4f67af41ccfd40d21e49880be568997ba6/setup.py): 0
- README status line: "This package is no longer maintained and has been replaced by Boto3"

## eslint/eslint (healthy)

- Commit read: [87bd2cef7b](https://github.com/eslint/eslint/tree/87bd2cef7b2309739c29598fb2be335f4bed71a3), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 28 of 31 in the tree; 134 dependencies; readable lockfiles: none
  - [package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/package.json): 88
  - [docs/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/docs/package.json): 32
  - [packages/eslint-config-eslint/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/packages/eslint-config-eslint/package.json): 9
  - [packages/js/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/packages/js/package.json): 1
  - [tests/pnpm/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/tests/pnpm/package.json): 2
  - [docs/_examples/custom-rule-tutorial-code/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/docs/_examples/custom-rule-tutorial-code/package.json): 1
  - [docs/_examples/integration-tutorial-code/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/docs/_examples/integration-tutorial-code/package.json): 1
  - [tests/fixtures/ignored-paths/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/tests/fixtures/ignored-paths/package.json): 0
  - [tests/fixtures/packagejson/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/tests/fixtures/packagejson/package.json): 0
  - [tests/fixtures/config-file/package-json/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/tests/fixtures/config-file/package-json/package.json): 0
  - [tests/fixtures/config-hierarchy/broken/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/tests/fixtures/config-hierarchy/broken/package.json): 0
  - [tests/fixtures/config-hierarchy/packagejson/package.json](https://github.com/eslint/eslint/blob/87bd2cef7b2309739c29598fb2be335f4bed71a3/tests/fixtures/config-hierarchy/packagejson/package.json): 0
  - ... 16 more manifests, 0 dependencies

## prettier/prettier (healthy)

- Commit read: [5927216227](https://github.com/prettier/prettier/tree/5927216227411bc2cdaf30d50559e0a475ab4832), dated 2026-10-04; GitHub `pushed_at` 2026-10-06; archived: false
- Rule applied: H1
- Manifests read: 44 of 44 in the tree; 192 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: scripts/release/yarn.lock, scripts/tools/bundle-test/yarn.lock, scripts/tools/eslint-plugin-prettier-internal-rules/yarn.lock, tests/integration/cli/patterns-dirs/yarn.lock and more
  - [package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/package.json): 149
  - [website/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/website/package.json): 36
  - [packages/plugin-hermes/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/packages/plugin-hermes/package.json): 0
  - [packages/plugin-oxc/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/packages/plugin-oxc/package.json): 0
  - [packages/plugin-yuku/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/packages/plugin-yuku/package.json): 0
  - [scripts/release/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/release/package.json): 6
  - [scripts/tools/bundle-test/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/tools/bundle-test/package.json): 1
  - [scripts/tools/eslint-plugin-prettier-internal-rules/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/tools/eslint-plugin-prettier-internal-rules/package.json): 0
  - [tests/config/prettier-plugins/prettier-plugin-async-printer/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-async-printer/package.json): 0
  - [tests/config/prettier-plugins/prettier-plugin-dummy-toml/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-dummy-toml/package.json): 0
  - [tests/config/prettier-plugins/prettier-plugin-missing-comments/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-missing-comments/package.json): 0
  - [tests/config/prettier-plugins/prettier-plugin-uppercase-rocks/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-uppercase-rocks/package.json): 0
  - ... 32 more manifests, 0 dependencies

## vercel/next.js (healthy)

- Commit read: [1aec1b2fbd](https://github.com/vercel/next.js/tree/1aec1b2fbddfd789cc355db0a260ddc63592d16b), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 50 of 670 in the tree; 725 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: .github/pnpm-lock.yaml, examples/with-docker-export-output/pnpm-lock.yaml, examples/with-docker/pnpm-lock.yaml, pnpm-lock.yaml and more
  - [package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/package.json): 192
  - [.github/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/.github/package.json): 0
  - [rspack/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/rspack/package.json): 2
  - [apps/bundle-analyzer/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/apps/bundle-analyzer/package.json): 31
  - [bench/app-router-server/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/app-router-server/package.json): 4
  - [bench/fuzzponent/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/fuzzponent/package.json): 4
  - [bench/heavy-npm-deps/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/heavy-npm-deps/package.json): 6
  - [bench/module-cost/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/module-cost/package.json): 3
  - [bench/nested-deps-app-router-many-pages/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/nested-deps-app-router-many-pages/package.json): 5
  - [bench/nested-deps-app-router/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/nested-deps-app-router/package.json): 5
  - [bench/nested-deps/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/nested-deps/package.json): 5
  - [bench/next-minimal-server/package.json](https://github.com/vercel/next.js/blob/1aec1b2fbddfd789cc355db0a260ddc63592d16b/bench/next-minimal-server/package.json): 1
  - ... 38 more manifests, 467 dependencies

## microsoft/vscode (healthy)

- Commit read: [e8f54c79d5](https://github.com/microsoft/vscode/tree/e8f54c79d5c46126f427cccd37cceb531b0dcdf6), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 50 of 153 in the tree; 492 dependencies; readable lockfiles: build/package-lock.json, build/rspack/package-lock.json, build/vite/package-lock.json, extensions/configuration-editing/package-lock.json, extensions/copilot/package-lock.json, extensions/css-language-features/package-lock.json, extensions/debug-auto-launch/package-lock.json, extensions/debug-server-ready/package-lock.json, extensions/emmet/package-lock.json, extensions/extension-editing/package-lock.json, extensions/git-base/package-lock.json, extensions/git/package-lock.json, extensions/github-authentication/package-lock.json, extensions/github/package-lock.json, extensions/grunt/package-lock.json, extensions/gulp/package-lock.json, extensions/html-language-features/package-lock.json, extensions/ipynb/package-lock.json, extensions/jake/package-lock.json, extensions/json-language-features/package-lock.json, extensions/package-lock.json, package-lock.json, remote/package-lock.json
  - [package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/package.json): 174 (lockfile package-lock.json)
  - [.eslint-plugin-local/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/.eslint-plugin-local/package.json): 0
  - [build/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/build/package.json): 60 (lockfile build/package-lock.json)
  - [extensions/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/extensions/package.json): 4 (lockfile extensions/package-lock.json)
  - [remote/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/remote/package.json): 52 (lockfile remote/package-lock.json)
  - [scripts/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/scripts/package.json): 0
  - [test/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/test/package.json): 0
  - [build/builtin/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/build/builtin/package.json): 0
  - [build/monaco/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/build/monaco/package.json): 0
  - [build/rspack/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/build/rspack/package.json): 7 (lockfile build/rspack/package-lock.json)
  - [build/vite/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/build/vite/package.json): 5 (lockfile build/vite/package-lock.json)
  - [extensions/bat/package.json](https://github.com/microsoft/vscode/blob/e8f54c79d5c46126f427cccd37cceb531b0dcdf6/extensions/bat/package.json): 0
  - ... 38 more manifests, 190 dependencies

## microsoft/TypeScript (healthy)

- Commit read: [54f05ae22a](https://github.com/microsoft/TypeScript/tree/54f05ae22afd5f0ec5ec3ae0333b03efa1156fe6), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 5 of 5 in the tree; 24 dependencies; readable lockfiles: package-lock.json
  - [package.json](https://github.com/microsoft/TypeScript/blob/54f05ae22afd5f0ec5ec3ae0333b03efa1156fe6/package.json): 13 (lockfile package-lock.json)
  - [packages/typescript/package.json](https://github.com/microsoft/TypeScript/blob/54f05ae22afd5f0ec5ec3ae0333b03efa1156fe6/packages/typescript/package.json): 3 (lockfile package-lock.json)
  - [packages/vscode-typescript-nightly/package.json](https://github.com/microsoft/TypeScript/blob/54f05ae22afd5f0ec5ec3ae0333b03efa1156fe6/packages/vscode-typescript-nightly/package.json): 0 (lockfile package-lock.json)
  - [packages/vscode-typescript/package.json](https://github.com/microsoft/TypeScript/blob/54f05ae22afd5f0ec5ec3ae0333b03efa1156fe6/packages/vscode-typescript/package.json): 8 (lockfile package-lock.json)
  - [tools/scripts/tsc/package.json](https://github.com/microsoft/TypeScript/blob/54f05ae22afd5f0ec5ec3ae0333b03efa1156fe6/tools/scripts/tsc/package.json): 0

## mochajs/mocha (healthy)

- Commit read: [a9fc529683](https://github.com/mochajs/mocha/tree/a9fc5296831641fbbcc8862e561e498549d840dc), dated 2026-10-03; GitHub `pushed_at` 2026-10-05; archived: false
- Rule applied: H1
- Manifests read: 11 of 11 in the tree; 65 dependencies; readable lockfiles: docs/package-lock.json, package-lock.json, repro/package-lock.json
  - [package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/package.json): 54 (lockfile package-lock.json)
  - [docs/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/docs/package.json): 8 (lockfile docs/package-lock.json)
  - [repro/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/repro/package.json): 2 (lockfile repro/package-lock.json)
  - [test/compiler-esm/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/compiler-esm/package.json): 0
  - [test/compiler-fixtures/esm-only-loader/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/compiler-fixtures/esm-only-loader/package.json): 0
  - [test/node-unit/fixtures/commonjs/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/node-unit/fixtures/commonjs/package.json): 0
  - [test/integration/fixtures/config/mocha-config/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/integration/fixtures/config/mocha-config/package.json): 1
  - [test/integration/fixtures/esm/js-folder/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/integration/fixtures/esm/js-folder/package.json): 0
  - [test/integration/fixtures/esm/type-module/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/integration/fixtures/esm/type-module/package.json): 0
  - [test/integration/fixtures/plugins/root-hooks/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/integration/fixtures/plugins/root-hooks/package.json): 0
  - [test/integration/fixtures/plugins/root-hooks/esm/package.json](https://github.com/mochajs/mocha/blob/a9fc5296831641fbbcc8862e561e498549d840dc/test/integration/fixtures/plugins/root-hooks/esm/package.json): 0

## expressjs/express (healthy)

- Commit read: [9efc29e280](https://github.com/expressjs/express/tree/9efc29e280018dafc1f0617f3a3d28f4e463b7be), dated 2026-10-06; GitHub `pushed_at` 2026-10-06; archived: false
- Rule applied: H1
- Manifests read: 1 of 1 in the tree; 44 dependencies; readable lockfiles: none
  - [package.json](https://github.com/expressjs/express/blob/9efc29e280018dafc1f0617f3a3d28f4e463b7be/package.json): 44

## axios/axios (healthy)

- Commit read: [a0ed1a2841](https://github.com/axios/axios/tree/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 7 of 7 in the tree; 59 dependencies; readable lockfiles: docs/package-lock.json, package-lock.json, tests/module/cjs/package-lock.json, tests/module/esm/package-lock.json, tests/smoke/cjs/package-lock.json, tests/smoke/esm/package-lock.json; lockfiles present that RepoVitals does not read: tests/smoke/bun/bun.lock
  - [package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/package.json): 42 (lockfile package-lock.json)
  - [docs/package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/docs/package.json): 6 (lockfile docs/package-lock.json)
  - [tests/module/cjs/package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/tests/module/cjs/package.json): 3 (lockfile tests/module/cjs/package-lock.json)
  - [tests/module/esm/package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/tests/module/esm/package.json): 3 (lockfile tests/module/esm/package-lock.json)
  - [tests/smoke/bun/package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/tests/smoke/bun/package.json): 2
  - [tests/smoke/cjs/package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/tests/smoke/cjs/package.json): 2 (lockfile tests/smoke/cjs/package-lock.json)
  - [tests/smoke/esm/package.json](https://github.com/axios/axios/blob/a0ed1a2841d3b16101d4645bcdaab3bcda6b1cd5/tests/smoke/esm/package.json): 1 (lockfile tests/smoke/esm/package-lock.json)

## mozilla/pdf.js (healthy)

- Commit read: [89b500f5e1](https://github.com/mozilla/pdf.js/tree/89b500f5e1d98ed89bb90211e45b28730b2d99ac), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 5 of 5 in the tree; 60 dependencies; readable lockfiles: package-lock.json
  - [package.json](https://github.com/mozilla/pdf.js/blob/89b500f5e1d98ed89bb90211e45b28730b2d99ac/package.json): 50 (lockfile package-lock.json)
  - [.github/fluent_linter_requirements.txt](https://github.com/mozilla/pdf.js/blob/89b500f5e1d98ed89bb90211e45b28730b2d99ac/.github/fluent_linter_requirements.txt): 5
  - [.github/font_tests_requirements.txt](https://github.com/mozilla/pdf.js/blob/89b500f5e1d98ed89bb90211e45b28730b2d99ac/.github/font_tests_requirements.txt): 1
  - [examples/webpack/package.json](https://github.com/mozilla/pdf.js/blob/89b500f5e1d98ed89bb90211e45b28730b2d99ac/examples/webpack/package.json): 3
  - [test/types/package.json](https://github.com/mozilla/pdf.js/blob/89b500f5e1d98ed89bb90211e45b28730b2d99ac/test/types/package.json): 1

## django/django (healthy)

- Commit read: [7f48e266a8](https://github.com/django/django/tree/7f48e266a83110d62ffb4663d72c9e347db75a9b), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 10 of 10 in the tree; 58 dependencies; readable lockfiles: none
  - [package.json](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/package.json): 5
  - [pyproject.toml](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/pyproject.toml): 5
  - [docs/requirements.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/docs/requirements.txt): 5
  - [tests/requirements/mysql.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/requirements/mysql.txt): 1
  - [tests/requirements/oracle.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/requirements/oracle.txt): 1
  - [tests/requirements/postgres-free-threading.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/requirements/postgres-free-threading.txt): 2
  - [tests/requirements/postgres.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/requirements/postgres.txt): 2
  - [tests/requirements/py3-free-threading.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/requirements/py3-free-threading.txt): 17
  - [tests/requirements/py3.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/requirements/py3.txt): 20
  - [tests/admin_scripts/custom_templates/project_template/additional_dir/requirements.txt](https://github.com/django/django/blob/7f48e266a83110d62ffb4663d72c9e347db75a9b/tests/admin_scripts/custom_templates/project_template/additional_dir/requirements.txt): 0

## pallets/flask (healthy)

- Commit read: [d086db856b](https://github.com/pallets/flask/tree/d086db856be187255b8ec61ef409357393020f32), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 5 of 5 in the tree; 35 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: uv.lock
  - [pyproject.toml](https://github.com/pallets/flask/blob/d086db856be187255b8ec61ef409357393020f32/pyproject.toml): 8
  - [examples/celery/pyproject.toml](https://github.com/pallets/flask/blob/d086db856be187255b8ec61ef409357393020f32/examples/celery/pyproject.toml): 2
  - [examples/celery/requirements.txt](https://github.com/pallets/flask/blob/d086db856be187255b8ec61ef409357393020f32/examples/celery/requirements.txt): 21
  - [examples/javascript/pyproject.toml](https://github.com/pallets/flask/blob/d086db856be187255b8ec61ef409357393020f32/examples/javascript/pyproject.toml): 2
  - [examples/tutorial/pyproject.toml](https://github.com/pallets/flask/blob/d086db856be187255b8ec61ef409357393020f32/examples/tutorial/pyproject.toml): 2

## celery/celery (healthy)

- Commit read: [71d1b8f89d](https://github.com/celery/celery/tree/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 15 of 15 in the tree; 51 dependencies; readable lockfiles: none
  - [pyproject.toml](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/pyproject.toml): 0
  - [setup.py](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/setup.py): 3
  - [requirements/constraints.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/constraints.txt): 1
  - [requirements/default.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/default.txt): 10
  - [requirements/dev.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/dev.txt): 2
  - [requirements/docs.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/docs.txt): 4
  - [requirements/pkgutils.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/pkgutils.txt): 9
  - [requirements/security.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/security.txt): 0
  - [requirements/test-ci-base.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/test-ci-base.txt): 2
  - [requirements/test-ci-default.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/test-ci-default.txt): 3
  - [requirements/test-integration.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/test-integration.txt): 2
  - [requirements/test-pypy3.txt](https://github.com/celery/celery/blob/71d1b8f89d50694ad2774ee2dcf3204dd2ae5272/requirements/test-pypy3.txt): 0
  - ... 3 more manifests, 15 dependencies

## pytest-dev/pytest (healthy)

- Commit read: [59200df778](https://github.com/pytest-dev/pytest/tree/59200df778adf8079df6125d60662908ac0a0646), dated 2026-10-06; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 3 of 3 in the tree; 45 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: uv.lock
  - [pyproject.toml](https://github.com/pytest-dev/pytest/blob/59200df778adf8079df6125d60662908ac0a0646/pyproject.toml): 20
  - [doc/en/requirements.txt](https://github.com/pytest-dev/pytest/blob/59200df778adf8079df6125d60662908ac0a0646/doc/en/requirements.txt): 10
  - [testing/plugins_integration/requirements.txt](https://github.com/pytest-dev/pytest/blob/59200df778adf8079df6125d60662908ac0a0646/testing/plugins_integration/requirements.txt): 15

## psf/requests (healthy)

- Commit read: [611c6162cb](https://github.com/psf/requests/tree/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60), dated 2026-09-21; GitHub `pushed_at` 2026-09-28; archived: false
- Rule applied: H1
- Manifests read: 4 of 4 in the tree; 13 dependencies; readable lockfiles: none
  - [pyproject.toml](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/pyproject.toml): 6
  - [requirements-dev.txt](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/requirements-dev.txt): 6
  - [setup.py](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/setup.py): 0
  - [docs/requirements.txt](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/docs/requirements.txt): 1

## scrapy/scrapy (healthy)

- Commit read: [aef037d6fd](https://github.com/scrapy/scrapy/tree/aef037d6fd57cdf4ecec415cc7456be22bf990ca), dated 2026-10-07; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 2 of 2 in the tree; 113 dependencies; readable lockfiles: none
  - [pyproject.toml](https://github.com/scrapy/scrapy/blob/aef037d6fd57cdf4ecec415cc7456be22bf990ca/pyproject.toml): 38
  - [docs/requirements.txt](https://github.com/scrapy/scrapy/blob/aef037d6fd57cdf4ecec415cc7456be22bf990ca/docs/requirements.txt): 75

## python-poetry/poetry (healthy)

- Commit read: [63bba274f8](https://github.com/python-poetry/poetry/tree/63bba274f8ea6bc9a064f5328fa6c67bce617cc1), dated 2026-10-06; GitHub `pushed_at` 2026-10-06; archived: false
- Rule applied: H1
- Manifests read: 50 of 108 in the tree; 80 dependencies; readable lockfiles: poetry.lock, tests/fixtures/deleted_directory_dependency/poetry.lock, tests/fixtures/deleted_file_dependency/poetry.lock, tests/fixtures/incompatible_lock/poetry.lock, tests/fixtures/invalid_lock/poetry.lock, tests/fixtures/missing_directory_dependency/poetry.lock, tests/fixtures/missing_extra_directory_dependency/poetry.lock, tests/fixtures/missing_file_dependency/poetry.lock, tests/fixtures/old_lock/poetry.lock, tests/fixtures/old_lock_path_dependency/poetry.lock, tests/fixtures/outdated_lock/poetry.lock, tests/fixtures/up_to_date_lock/poetry.lock, tests/fixtures/up_to_date_lock_non_package/poetry.lock
  - [pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/pyproject.toml): 34 (lockfile poetry.lock)
  - [tests/fixtures/build_constraints/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/build_constraints/pyproject.toml): 0
  - [tests/fixtures/build_constraints_empty/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/build_constraints_empty/pyproject.toml): 0
  - [tests/fixtures/build_system_requires_not_available/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/build_system_requires_not_available/pyproject.toml): 0
  - [tests/fixtures/deleted_directory_dependency/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/deleted_directory_dependency/pyproject.toml): 0 (lockfile tests/fixtures/deleted_directory_dependency/poetry.lock)
  - [tests/fixtures/deleted_file_dependency/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/deleted_file_dependency/pyproject.toml): 0 (lockfile tests/fixtures/deleted_file_dependency/poetry.lock)
  - [tests/fixtures/excluded_subpackage/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/excluded_subpackage/pyproject.toml): 1
  - [tests/fixtures/extended_project/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/extended_project/pyproject.toml): 0
  - [tests/fixtures/extended_project_without_setup/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/extended_project_without_setup/pyproject.toml): 0
  - [tests/fixtures/extended_with_no_setup/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/extended_with_no_setup/pyproject.toml): 0
  - [tests/fixtures/file_scripts_dir_ref_project/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/file_scripts_dir_ref_project/pyproject.toml): 0
  - [tests/fixtures/file_scripts_missing_ref_project/pyproject.toml](https://github.com/python-poetry/poetry/blob/63bba274f8ea6bc9a064f5328fa6c67bce617cc1/tests/fixtures/file_scripts_missing_ref_project/pyproject.toml): 0
  - ... 38 more manifests, 45 dependencies

## pypa/pipenv (healthy)

- Commit read: [226bc13420](https://github.com/pypa/pipenv/tree/226bc1342043f387eec027fb07a8254768b3f718), dated 2026-09-25; GitHub `pushed_at` 2026-10-07; archived: false
- Rule applied: H1
- Manifests read: 13 of 13 in the tree; 74 dependencies; readable lockfiles: Pipfile.lock, examples/Pipfile.lock
  - [Pipfile](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/Pipfile): 27 (lockfile Pipfile.lock)
  - [pyproject.toml](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/pyproject.toml): 18
  - [benchmarks/Pipfile](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/benchmarks/Pipfile): 0
  - [docs/requirements.txt](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/docs/requirements.txt): 15
  - [examples/Pipfile](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/examples/Pipfile): 6 (lockfile examples/Pipfile.lock)
  - [tests/fixtures/cython-import-package/pyproject.toml](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/cython-import-package/pyproject.toml): 0
  - [tests/fixtures/cython-import-package/setup.py](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/cython-import-package/setup.py): 2
  - [tests/fixtures/fake-package/Pipfile](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/fake-package/Pipfile): 4
  - [tests/fixtures/fake-package/pyproject.toml](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/fake-package/pyproject.toml): 0
  - [tests/fixtures/fake-package/setup.py](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/fake-package/setup.py): 0
  - [tests/fixtures/legacy-backend-package/pyproject.toml](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/legacy-backend-package/pyproject.toml): 0
  - [tests/fixtures/legacy-backend-package/setup.py](https://github.com/pypa/pipenv/blob/226bc1342043f387eec027fb07a8254768b3f718/tests/fixtures/legacy-backend-package/setup.py): 0
  - ... 1 more manifests, 2 dependencies

## gulpjs/gulp (in_between)

- Commit read: [61f22dc11b](https://github.com/gulpjs/gulp/tree/61f22dc11bb14234b555253095fa1d224ce0eab1), dated 2026-02-09; GitHub `pushed_at` 2026-02-09; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 1 of 1 in the tree; 12 dependencies; readable lockfiles: none
  - [package.json](https://github.com/gulpjs/gulp/blob/61f22dc11bb14234b555253095fa1d224ce0eab1/package.json): 12

## jaredhanson/passport (in_between)

- Commit read: [217018dbc4](https://github.com/jaredhanson/passport/tree/217018dbc46dcd4118dd6f2c60c8d97010c587f8), dated 2024-08-16; GitHub `pushed_at` 2024-08-16; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 1 of 1 in the tree; 9 dependencies; readable lockfiles: none
  - [package.json](https://github.com/jaredhanson/passport/blob/217018dbc46dcd4118dd6f2c60c8d97010c587f8/package.json): 9

## moment/moment (in_between)

- Commit read: [15b45d48a1](https://github.com/moment/moment/tree/15b45d48a176312e8f34143c5a800090abf4787f), dated 2026-09-15; GitHub `pushed_at` 2026-09-15; archived: false
- Rule applied: I1 maintenance mode
- Manifests read: 1 of 1 in the tree; 20 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: pnpm-lock.yaml
  - [package.json](https://github.com/moment/moment/blob/15b45d48a176312e8f34143c5a800090abf4787f/package.json): 20
- README status line: "Moment.js is a legacy project, now in maintenance mode."

## pugjs/pug (in_between)

- Commit read: [c323ed3e63](https://github.com/pugjs/pug/tree/c323ed3e630b931bc04790efb509d34ac5927040), dated 2026-03-13; GitHub `pushed_at` 2026-03-13; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 13 of 13 in the tree; 69 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: yarn.lock
  - [package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/package.json): 5
  - [packages/pug-attrs/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-attrs/package.json): 3
  - [packages/pug-code-gen/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-code-gen/package.json): 8
  - [packages/pug-error/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-error/package.json): 0
  - [packages/pug-filters/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-filters/package.json): 14
  - [packages/pug-lexer/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-lexer/package.json): 5
  - [packages/pug-linker/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-linker/package.json): 5
  - [packages/pug-load/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-load/package.json): 4
  - [packages/pug-parser/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-parser/package.json): 2
  - [packages/pug-runtime/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-runtime/package.json): 1
  - [packages/pug-strip-comments/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-strip-comments/package.json): 2
  - [packages/pug-walk/package.json](https://github.com/pugjs/pug/blob/c323ed3e630b931bc04790efb509d34ac5927040/packages/pug-walk/package.json): 2
  - ... 1 more manifests, 18 dependencies

## jquery/jquery-ui (in_between)

- Commit read: [dcf10556bb](https://github.com/jquery/jquery-ui/tree/dcf10556bbcfdf3e10e3ea30966482e201191411), dated 2026-08-16; GitHub `pushed_at` 2026-09-13; archived: false
- Rule applied: I1 maintenance mode
- Manifests read: 1 of 1 in the tree; 17 dependencies; readable lockfiles: package-lock.json
  - [package.json](https://github.com/jquery/jquery-ui/blob/dcf10556bbcfdf3e10e3ea30966482e201191411/package.json): 17 (lockfile package-lock.json)

## bevacqua/dragula (in_between)

- Commit read: [09ab978dd5](https://github.com/bevacqua/dragula/tree/09ab978dd550490f1f8e456551a1a39ed0d7f984), dated 2024-03-16; GitHub `pushed_at` 2024-06-07; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 1 of 1 in the tree; 15 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: yarn.lock
  - [package.json](https://github.com/bevacqua/dragula/blob/09ab978dd550490f1f8e456551a1a39ed0d7f984/package.json): 15

## rstacruz/nprogress (in_between)

- Commit read: [e1a8b7fb6e](https://github.com/rstacruz/nprogress/tree/e1a8b7fb6e059085df5f83c45d3c2308a147ca18), dated 2020-04-19; GitHub `pushed_at` 2022-06-04; archived: false
- Rule applied: I2 stale but small/clean
- Manifests read: 1 of 1 in the tree; 5 dependencies; readable lockfiles: none
  - [package.json](https://github.com/rstacruz/nprogress/blob/e1a8b7fb6e059085df5f83c45d3c2308a147ca18/package.json): 5

## dropbox/pyannotate (in_between)

- Commit read: [a7a46f394f](https://github.com/dropbox/pyannotate/tree/a7a46f394f0ba91a1b5fbf657e2393af542969ae), dated 2021-10-12; GitHub `pushed_at` 2026-07-06; archived: false
- Rule applied: I2 stale but small/clean
- Manifests read: 2 of 2 in the tree; 8 dependencies; readable lockfiles: none
  - [requirements.txt](https://github.com/dropbox/pyannotate/blob/a7a46f394f0ba91a1b5fbf657e2393af542969ae/requirements.txt): 5
  - [setup.py](https://github.com/dropbox/pyannotate/blob/a7a46f394f0ba91a1b5fbf657e2393af542969ae/setup.py): 3

## kennethreitz/records (in_between)

- Commit read: [ea4273695c](https://github.com/kennethreitz/records/tree/ea4273695cee6da42edf1cb294d1f2a4505470fc), dated 2026-02-09; GitHub `pushed_at` 2026-02-09; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 2 of 2 in the tree; 8 dependencies; readable lockfiles: none
  - [requirements.txt](https://github.com/kennethreitz/records/blob/ea4273695cee6da42edf1cb294d1f2a4505470fc/requirements.txt): 1
  - [setup.py](https://github.com/kennethreitz/records/blob/ea4273695cee6da42edf1cb294d1f2a4505470fc/setup.py): 7

## nvbn/thefuck (in_between)

- Commit read: [c7e7e1d884](https://github.com/nvbn/thefuck/tree/c7e7e1d884d3bb241ea6448f72a989434c2a35ec), dated 2024-01-25; GitHub `pushed_at` 2024-07-19; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 2 of 2 in the tree; 19 dependencies; readable lockfiles: none
  - [requirements.txt](https://github.com/nvbn/thefuck/blob/c7e7e1d884d3bb241ea6448f72a989434c2a35ec/requirements.txt): 11
  - [setup.py](https://github.com/nvbn/thefuck/blob/c7e7e1d884d3bb241ea6448f72a989434c2a35ec/setup.py): 8

## pyeve/eve (in_between)

- Commit read: [fe7d9c919b](https://github.com/pyeve/eve/tree/fe7d9c919bf35fe149feb42e51ba9c5c337e3119), dated 2026-03-24; GitHub `pushed_at` 2026-03-24; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 3 of 3 in the tree; 16 dependencies; readable lockfiles: none
  - [pyproject.toml](https://github.com/pyeve/eve/blob/fe7d9c919bf35fe149feb42e51ba9c5c337e3119/pyproject.toml): 0
  - [setup.py](https://github.com/pyeve/eve/blob/fe7d9c919bf35fe149feb42e51ba9c5c337e3119/setup.py): 12
  - [docs/requirements.txt](https://github.com/pyeve/eve/blob/fe7d9c919bf35fe149feb42e51ba9c5c337e3119/docs/requirements.txt): 4

## cookiecutter/cookiecutter (in_between)

- Commit read: [c88fbe921c](https://github.com/cookiecutter/cookiecutter/tree/c88fbe921c97c58b65f1883ba90a0ab53cc91b34), dated 2026-03-04; GitHub `pushed_at` 2026-04-01; archived: false
- Rule applied: I1 last commit 6 months-3 years ago
- Manifests read: 6 of 6 in the tree; 20 dependencies; readable lockfiles: none; lockfiles present that RepoVitals does not read: uv.lock
  - [pyproject.toml](https://github.com/cookiecutter/cookiecutter/blob/c88fbe921c97c58b65f1883ba90a0ab53cc91b34/pyproject.toml): 8
  - [docs/requirements.txt](https://github.com/cookiecutter/cookiecutter/blob/c88fbe921c97c58b65f1883ba90a0ab53cc91b34/docs/requirements.txt): 8
  - [tests/test-templates/extends/{{cookiecutter.project_slug}}/requirements.txt](https://github.com/cookiecutter/cookiecutter/blob/c88fbe921c97c58b65f1883ba90a0ab53cc91b34/tests/test-templates/extends/{{cookiecutter.project_slug}}/requirements.txt): 0
  - [tests/test-templates/include/{{cookiecutter.project_slug}}/requirements.txt](https://github.com/cookiecutter/cookiecutter/blob/c88fbe921c97c58b65f1883ba90a0ab53cc91b34/tests/test-templates/include/{{cookiecutter.project_slug}}/requirements.txt): 1
  - [tests/test-templates/no-templates/{{cookiecutter.project_slug}}/requirements.txt](https://github.com/cookiecutter/cookiecutter/blob/c88fbe921c97c58b65f1883ba90a0ab53cc91b34/tests/test-templates/no-templates/{{cookiecutter.project_slug}}/requirements.txt): 3
  - [tests/test-templates/super/{{cookiecutter.project_slug}}/requirements.txt](https://github.com/cookiecutter/cookiecutter/blob/c88fbe921c97c58b65f1883ba90a0ab53cc91b34/tests/test-templates/super/{{cookiecutter.project_slug}}/requirements.txt): 0

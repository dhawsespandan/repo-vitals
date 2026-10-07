# WP-2 verification worksheet (for Astha to check by hand)

Prepared 2026-10-05 from a draft built with an AI tool. **This is not a deliverable and must not be submitted as is.** The reviewer's rule is that every row has to come from opening the repo's actual manifest files on GitHub. Use this sheet to do that. Open every link yourself and confirm or correct each value. Then write the final `wp2_anchor_set.csv` from what you saw, and record how you checked.

Links point at the exact commit that was read on 2026-10-05, so they won't move. Also check the live repo, because things may have changed since.

**For every row, confirm:**

- [ ] The repo opens (not 404), and it is archived only if the row says so (look for the yellow "archived by the owner on …" banner).
- [ ] The last-activity date. The draft uses the *default-branch last commit*; the reviewer judges by the *pushed* date. With your token you can read `pushed_at` from `https://api.github.com/repos/OWNER/REPO`.
- [ ] `ecosystem`: which manifest types the repo has.
- [ ] `has_lockfile`: true only for package-lock.json, npm-shrinkwrap.json, poetry.lock or Pipfile.lock beside a manifest. yarn.lock, pnpm-lock.yaml and uv.lock count as false.
- [ ] `approx_dep_count`: add up the dependency entries in the manifests listed. For package.json that is dependencies + devDependencies + optionalDependencies + peerDependencies. For Python it is the requirement lines or entries. This includes examples/ and fixtures; node_modules, vendor, bower_components, site-packages and venv folders are skipped; at most 50 manifests, shallowest first.
- [ ] `why_this_bucket` contains only facts you just confirmed.

**For known anchors, also confirm:**

- [ ] The anchor line is in the manifest as a DIRECT dependency.
- [ ] The version is an exact pin, or is recorded in the readable lockfile next to that manifest.
- [ ] The evidence page shows that exact version as deprecated (npm), yanked (PyPI) or affected (osv.dev).


## psf/requests  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`13`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-09-21; 13 deps across 4 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/psf/requests · commit read: [611c6162cb](https://github.com/psf/requests/tree/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60) · [commits on default branch](https://github.com/psf/requests/commits/main)
- Manifests read (4 of 4 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/pyproject.toml): 6
  - [ ] [requirements-dev.txt](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/requirements-dev.txt): 6
  - [ ] [setup.py](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/setup.py): 0
  - [ ] [docs/requirements.txt](https://github.com/psf/requests/blob/611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60/docs/requirements.txt): 1

## fastapi/fastapi  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`19`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 19 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads; uv.lock present but not read by RepoVitals.

- Repo: https://github.com/fastapi/fastapi · commit read: [52159d7e70](https://github.com/fastapi/fastapi/tree/52159d7e7018df55b57a0b8fdd6c1193e48b2b57) · [commits on default branch](https://github.com/fastapi/fastapi/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/fastapi/fastapi/blob/52159d7e7018df55b57a0b8fdd6c1193e48b2b57/pyproject.toml): 19
- Lockfiles present that RepoVitals does NOT read: [uv.lock](https://github.com/fastapi/fastapi/blob/52159d7e7018df55b57a0b8fdd6c1193e48b2b57/uv.lock)

## pydantic/pydantic  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`7`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 7 deps across 4 manifests RepoVitals reads; no lockfile RepoVitals reads; uv.lock present but not read by RepoVitals.

- Repo: https://github.com/pydantic/pydantic · commit read: [1e6cc758a0](https://github.com/pydantic/pydantic/tree/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a) · [commits on default branch](https://github.com/pydantic/pydantic/commits/main)
- Manifests read (4 of 4 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/pyproject.toml): 6
  - [ ] [pydantic-core/pyproject.toml](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/pydantic-core/pyproject.toml): 1
  - [ ] [tests/plugin/pyproject.toml](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/tests/plugin/pyproject.toml): 0
  - [ ] [tests/typechecking/pyproject.toml](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/tests/typechecking/pyproject.toml): 0
- Lockfiles present that RepoVitals does NOT read: [pydantic-core/uv.lock](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/pydantic-core/uv.lock), [tests/typechecking/uv.lock](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/tests/typechecking/uv.lock), [uv.lock](https://github.com/pydantic/pydantic/blob/1e6cc758a04b3b1b50d12907b6c463a9ea575b4a/uv.lock)

## chalk/chalk  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`11`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-09-27; 11 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/chalk/chalk · commit read: [47fc05abd4](https://github.com/chalk/chalk/tree/47fc05abd46171b235e24174cd2dba83d25bf037) · [commits on default branch](https://github.com/chalk/chalk/commits/main)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/chalk/chalk/blob/47fc05abd46171b235e24174cd2dba83d25bf037/package.json): 11

## pallets/click  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`11`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-04; 11 deps across 11 manifests RepoVitals reads; no lockfile RepoVitals reads; uv.lock present but not read by RepoVitals.

- Repo: https://github.com/pallets/click · commit read: [2247b35ea1](https://github.com/pallets/click/tree/2247b35ea1c47c727d7a06e51fa280e12a863ff6) · [commits on default branch](https://github.com/pallets/click/commits/main)
- Manifests read (11 of 11 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/pyproject.toml): 0
  - [ ] [examples/aliases/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/aliases/pyproject.toml): 1
  - [ ] [examples/colors/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/colors/pyproject.toml): 1
  - [ ] [examples/completion/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/completion/pyproject.toml): 1
  - [ ] [examples/complex/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/complex/pyproject.toml): 1
  - [ ] [examples/imagepipe/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/imagepipe/pyproject.toml): 2
  - [ ] [examples/inout/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/inout/pyproject.toml): 1
  - [ ] [examples/naval/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/naval/pyproject.toml): 1
  - [ ] [examples/repo/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/repo/pyproject.toml): 1
  - [ ] [examples/termui/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/termui/pyproject.toml): 1
  - [ ] [examples/validation/pyproject.toml](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/examples/validation/pyproject.toml): 1
- Lockfiles present that RepoVitals does NOT read: [uv.lock](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/uv.lock)

## psf/black  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`14`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-04; 14 deps across 7 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/psf/black · commit read: [1ed66a8b33](https://github.com/psf/black/tree/1ed66a8b3385a000508a03158ac3dc2a8a75a209) · [commits on default branch](https://github.com/psf/black/commits/main)
- Manifests read (7 of 7 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/pyproject.toml): 14
  - [ ] [docs/compatible_configs/isort/pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/docs/compatible_configs/isort/pyproject.toml): 0
  - [ ] [docs/compatible_configs/pylint/pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/docs/compatible_configs/pylint/pyproject.toml): 0
  - [ ] [tests/data/include_exclude_tests/pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/tests/data/include_exclude_tests/pyproject.toml): 0
  - [ ] [tests/data/invalid_gitignore_tests/pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/tests/data/invalid_gitignore_tests/pyproject.toml): 0
  - [ ] [tests/data/invalid_nested_gitignore_tests/pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/tests/data/invalid_nested_gitignore_tests/pyproject.toml): 0
  - [ ] [tests/data/nested_gitignore_tests/pyproject.toml](https://github.com/psf/black/blob/1ed66a8b3385a000508a03158ac3dc2a8a75a209/tests/data/nested_gitignore_tests/pyproject.toml): 0

## pytest-dev/pytest  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`45`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 45 deps across 3 manifests RepoVitals reads; no lockfile RepoVitals reads; uv.lock present but not read by RepoVitals.

- Repo: https://github.com/pytest-dev/pytest · commit read: [fd17fdfea2](https://github.com/pytest-dev/pytest/tree/fd17fdfea252260bb7db5c9144f04b881e11d5d7) · [commits on default branch](https://github.com/pytest-dev/pytest/commits/main)
- Manifests read (3 of 3 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/pytest-dev/pytest/blob/fd17fdfea252260bb7db5c9144f04b881e11d5d7/pyproject.toml): 20
  - [ ] [doc/en/requirements.txt](https://github.com/pytest-dev/pytest/blob/fd17fdfea252260bb7db5c9144f04b881e11d5d7/doc/en/requirements.txt): 10
  - [ ] [testing/plugins_integration/requirements.txt](https://github.com/pytest-dev/pytest/blob/fd17fdfea252260bb7db5c9144f04b881e11d5d7/testing/plugins_integration/requirements.txt): 15
- Lockfiles present that RepoVitals does NOT read: [uv.lock](https://github.com/pytest-dev/pytest/blob/fd17fdfea252260bb7db5c9144f04b881e11d5d7/uv.lock)

## eslint/eslint  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`134`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 134 deps across 31 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/eslint/eslint · commit read: [e5aea414cc](https://github.com/eslint/eslint/tree/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6) · [commits on default branch](https://github.com/eslint/eslint/commits/main)
- Manifests read (28 of 31 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/package.json): 88
  - [ ] [docs/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/docs/package.json): 32
  - [ ] [packages/eslint-config-eslint/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/packages/eslint-config-eslint/package.json): 9
  - [ ] [packages/js/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/packages/js/package.json): 1
  - [ ] [tests/pnpm/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/pnpm/package.json): 2
  - [ ] [docs/_examples/custom-rule-tutorial-code/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/docs/_examples/custom-rule-tutorial-code/package.json): 1
  - [ ] [docs/_examples/integration-tutorial-code/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/docs/_examples/integration-tutorial-code/package.json): 1
  - [ ] [tests/fixtures/ignored-paths/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ignored-paths/package.json): 0
  - [ ] [tests/fixtures/packagejson/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/packagejson/package.json): 0
  - [ ] [tests/fixtures/config-file/package-json/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-file/package-json/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/broken/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/broken/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/packagejson/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/packagejson/package.json): 0
  - [ ] [tests/fixtures/ignored-paths/bad-package-json-ignore/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ignored-paths/bad-package-json-ignore/package.json): 0
  - [ ] [tests/fixtures/ignored-paths/package-json-ignore/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ignored-paths/package-json-ignore/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/packagejson/subdir/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/packagejson/subdir/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/personal-config/home-folder-with-packagejson/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/personal-config/home-folder-with-packagejson/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/personal-config/project-with-config/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/personal-config/project-with-config/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/personal-config/project-without-config/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/personal-config/project-without-config/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/cts/with-type-commonjs/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/cts/with-type-commonjs/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/cts/with-type-module/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/cts/with-type-module/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/mts/with-type-commonjs/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/mts/with-type-commonjs/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/mts/with-type-module/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/mts/with-type-module/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/ts/with-type-commonjs/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/ts/with-type-commonjs/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/ts/with-type-module/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/ts/with-type-module/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/packagejson/subdir/subsubdir/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/packagejson/subdir/subsubdir/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/personal-config/home-folder/project/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/personal-config/home-folder/project/package.json): 0
  - [ ] [tests/fixtures/ts-config-files/ts/jiti-interopDefault/plugin/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/ts-config-files/ts/jiti-interopDefault/plugin/package.json): 0
  - [ ] [tests/fixtures/config-hierarchy/packagejson/subdir/subsubdir/subsubsubdir/package.json](https://github.com/eslint/eslint/blob/e5aea414cc00555ecd43f6e608bf80e0f9a6d4d6/tests/fixtures/config-hierarchy/packagejson/subdir/subsubdir/subsubsubdir/package.json): 0

## prettier/prettier  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`192`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-04; 192 deps across 44 manifests RepoVitals reads; no lockfile RepoVitals reads; yarn.lock present but not read by RepoVitals.

- Repo: https://github.com/prettier/prettier · commit read: [5927216227](https://github.com/prettier/prettier/tree/5927216227411bc2cdaf30d50559e0a475ab4832) · [commits on default branch](https://github.com/prettier/prettier/commits/main)
- Manifests read (44 of 44 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/package.json): 149
  - [ ] [website/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/website/package.json): 36
  - [ ] [packages/plugin-hermes/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/packages/plugin-hermes/package.json): 0
  - [ ] [packages/plugin-oxc/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/packages/plugin-oxc/package.json): 0
  - [ ] [packages/plugin-yuku/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/packages/plugin-yuku/package.json): 0
  - [ ] [scripts/release/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/release/package.json): 6
  - [ ] [scripts/tools/bundle-test/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/tools/bundle-test/package.json): 1
  - [ ] [scripts/tools/eslint-plugin-prettier-internal-rules/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/tools/eslint-plugin-prettier-internal-rules/package.json): 0
  - [ ] [tests/config/prettier-plugins/prettier-plugin-async-printer/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-async-printer/package.json): 0
  - [ ] [tests/config/prettier-plugins/prettier-plugin-dummy-toml/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-dummy-toml/package.json): 0
  - [ ] [tests/config/prettier-plugins/prettier-plugin-missing-comments/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-missing-comments/package.json): 0
  - [ ] [tests/config/prettier-plugins/prettier-plugin-uppercase-rocks/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/config/prettier-plugins/prettier-plugin-uppercase-rocks/package.json): 0
  - [ ] [tests/integration/cli/cache/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/cache/package.json): 0
  - [ ] [tests/integration/cli/config-external-config-syntax-error/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config-external-config-syntax-error/package.json): 0
  - [ ] [tests/integration/cli/config/package/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/package/package.json): 0
  - [ ] [tests/integration/cli/config/external-config/cjs-package/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/external-config/cjs-package/package.json): 0
  - [ ] [tests/integration/cli/config/external-config/esm-file/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/external-config/esm-file/package.json): 0
  - [ ] [tests/integration/cli/config/external-config/esm-package-forbids-require/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/external-config/esm-package-forbids-require/package.json): 0
  - [ ] [tests/integration/cli/config/external-config/esm-package-with-tla/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/external-config/esm-package-with-tla/package.json): 0
  - [ ] [tests/integration/cli/config/external-config/esm-package/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/external-config/esm-package/package.json): 0
  - [ ] [tests/integration/cli/config/rc-cjs/prettier-config-cjs-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-cjs/prettier-config-cjs-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-cjs/prettier-config-cjs-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-cjs/prettier-config-cjs-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-cjs/prettier-config-cjs-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-cjs/prettier-config-cjs-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-cjs/prettierrc-cjs-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-cjs/prettierrc-cjs-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-cjs/prettierrc-cjs-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-cjs/prettierrc-cjs-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-cjs/prettierrc-cjs-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-cjs/prettierrc-cjs-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/cjs-prettier-config-js-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/cjs-prettier-config-js-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/cjs-prettier-config-js-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/cjs-prettier-config-js-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/cjs-prettier-config-js-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/cjs-prettier-config-js-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/cjs-prettierrc-js-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/cjs-prettierrc-js-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/cjs-prettierrc-js-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/cjs-prettierrc-js-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/cjs-prettierrc-js-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/cjs-prettierrc-js-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/mjs-prettier-config-js-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/mjs-prettier-config-js-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/mjs-prettier-config-js-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/mjs-prettier-config-js-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/mjs-prettier-config-js-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/mjs-prettier-config-js-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/mjs-prettierrc-js-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/mjs-prettierrc-js-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/mjs-prettierrc-js-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/mjs-prettierrc-js-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-js/mjs-prettierrc-js-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-js/mjs-prettierrc-js-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-mjs/prettier-config-mjs-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-mjs/prettier-config-mjs-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-mjs/prettier-config-mjs-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-mjs/prettier-config-mjs-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-mjs/prettier-config-mjs-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-mjs/prettier-config-mjs-in-type-none/package.json): 0
  - [ ] [tests/integration/cli/config/rc-mjs/prettierrc-mjs-in-type-commonjs/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-mjs/prettierrc-mjs-in-type-commonjs/package.json): 0
  - [ ] [tests/integration/cli/config/rc-mjs/prettierrc-mjs-in-type-module/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-mjs/prettierrc-mjs-in-type-module/package.json): 0
  - [ ] [tests/integration/cli/config/rc-mjs/prettierrc-mjs-in-type-none/package.json](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/config/rc-mjs/prettierrc-mjs-in-type-none/package.json): 0
- Lockfiles present that RepoVitals does NOT read: [scripts/release/yarn.lock](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/release/yarn.lock), [scripts/tools/bundle-test/yarn.lock](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/tools/bundle-test/yarn.lock), [scripts/tools/eslint-plugin-prettier-internal-rules/yarn.lock](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/scripts/tools/eslint-plugin-prettier-internal-rules/yarn.lock), [tests/integration/cli/patterns-dirs/yarn.lock](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/tests/integration/cli/patterns-dirs/yarn.lock), [website/yarn.lock](https://github.com/prettier/prettier/blob/5927216227411bc2cdaf30d50559e0a475ab4832/website/yarn.lock)

## django/django  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`58`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 58 deps across 10 manifests RepoVitals reads; no lockfile RepoVitals reads; also contains npm manifests (5 deps).

- Repo: https://github.com/django/django · commit read: [fd91518f17](https://github.com/django/django/tree/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a) · [commits on default branch](https://github.com/django/django/commits/main)
- Manifests read (10 of 10 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/package.json): 5
  - [ ] [pyproject.toml](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/pyproject.toml): 5
  - [ ] [docs/requirements.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/docs/requirements.txt): 5
  - [ ] [tests/requirements/mysql.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/requirements/mysql.txt): 1
  - [ ] [tests/requirements/oracle.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/requirements/oracle.txt): 1
  - [ ] [tests/requirements/postgres-free-threading.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/requirements/postgres-free-threading.txt): 2
  - [ ] [tests/requirements/postgres.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/requirements/postgres.txt): 2
  - [ ] [tests/requirements/py3-free-threading.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/requirements/py3-free-threading.txt): 17
  - [ ] [tests/requirements/py3.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/requirements/py3.txt): 20
  - [ ] [tests/admin_scripts/custom_templates/project_template/additional_dir/requirements.txt](https://github.com/django/django/blob/fd91518f17c8a84fa47fe0e5534ef46afa7a0f7a/tests/admin_scripts/custom_templates/project_template/additional_dir/requirements.txt): 0

## sqlalchemy/sqlalchemy  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`32`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 32 deps across 3 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/sqlalchemy/sqlalchemy · commit read: [ae11d43079](https://github.com/sqlalchemy/sqlalchemy/tree/ae11d43079207e159f3ba00f3c0e5188e2ccfe45) · [commits on default branch](https://github.com/sqlalchemy/sqlalchemy/commits/main)
- Manifests read (3 of 3 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/sqlalchemy/sqlalchemy/blob/ae11d43079207e159f3ba00f3c0e5188e2ccfe45/pyproject.toml): 25
  - [ ] [setup.py](https://github.com/sqlalchemy/sqlalchemy/blob/ae11d43079207e159f3ba00f3c0e5188e2ccfe45/setup.py): 0
  - [ ] [doc/build/requirements.txt](https://github.com/sqlalchemy/sqlalchemy/blob/ae11d43079207e159f3ba00f3c0e5188e2ccfe45/doc/build/requirements.txt): 7

## celery/celery  (healthy)

Draft values: ecosystem=`pypi`, approx_dep_count=`51`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 51 deps across 15 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/celery/celery · commit read: [1490f6d1c4](https://github.com/celery/celery/tree/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d) · [commits on default branch](https://github.com/celery/celery/commits/main)
- Manifests read (15 of 15 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/pyproject.toml): 0
  - [ ] [setup.py](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/setup.py): 3
  - [ ] [requirements/constraints.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/constraints.txt): 1
  - [ ] [requirements/default.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/default.txt): 10
  - [ ] [requirements/dev.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/dev.txt): 2
  - [ ] [requirements/docs.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/docs.txt): 4
  - [ ] [requirements/pkgutils.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/pkgutils.txt): 9
  - [ ] [requirements/security.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/security.txt): 0
  - [ ] [requirements/test-ci-base.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/test-ci-base.txt): 2
  - [ ] [requirements/test-ci-default.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/test-ci-default.txt): 3
  - [ ] [requirements/test-integration.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/test-integration.txt): 2
  - [ ] [requirements/test-pypy3.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/test-pypy3.txt): 0
  - [ ] [requirements/test.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/requirements/test.txt): 11
  - [ ] [examples/django/requirements.txt](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/examples/django/requirements.txt): 3
  - [ ] [examples/next-steps/setup.py](https://github.com/celery/celery/blob/1490f6d1c4d07649c7e428b0a20ea57b8dfc0a0d/examples/next-steps/setup.py): 1

## expressjs/express  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`44`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-09-28; 44 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/expressjs/express · commit read: [7ef98448f8](https://github.com/expressjs/express/tree/7ef98448f8b38099ab1ded55e458538ad47a51e7) · [commits on default branch](https://github.com/expressjs/express/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/expressjs/express/blob/7ef98448f8b38099ab1ded55e458538ad47a51e7/package.json): 44

## sindresorhus/got  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`50`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-09-20; 50 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/sindresorhus/got · commit read: [e1d87d2ced](https://github.com/sindresorhus/got/tree/e1d87d2ced01d5b7d855a7dc8b091bf7b014a1e4) · [commits on default branch](https://github.com/sindresorhus/got/commits/main)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/sindresorhus/got/blob/e1d87d2ced01d5b7d855a7dc8b091bf7b014a1e4/package.json): 50

## axios/axios  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`59`, has_lockfile=`true`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 59 deps across 7 manifests RepoVitals reads; readable lockfile docs/package-lock.json, package-lock.json, tests/module/cjs/package-lock.json and others.

- Repo: https://github.com/axios/axios · commit read: [6576f5753e](https://github.com/axios/axios/tree/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0) · [commits on default branch](https://github.com/axios/axios/commits/v1.x)
- Manifests read (7 of 7 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/package.json): 42 · lockfile [package-lock.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/package-lock.json)
  - [ ] [docs/package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/docs/package.json): 6 · lockfile [docs/package-lock.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/docs/package-lock.json)
  - [ ] [tests/module/cjs/package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/module/cjs/package.json): 3 · lockfile [tests/module/cjs/package-lock.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/module/cjs/package-lock.json)
  - [ ] [tests/module/esm/package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/module/esm/package.json): 3 · lockfile [tests/module/esm/package-lock.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/module/esm/package-lock.json)
  - [ ] [tests/smoke/bun/package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/smoke/bun/package.json): 2
  - [ ] [tests/smoke/cjs/package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/smoke/cjs/package.json): 2 · lockfile [tests/smoke/cjs/package-lock.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/smoke/cjs/package-lock.json)
  - [ ] [tests/smoke/esm/package.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/smoke/esm/package.json): 1 · lockfile [tests/smoke/esm/package-lock.json](https://github.com/axios/axios/blob/6576f5753e26444d8d04b0a7c0b4d9d0a83bdaa0/tests/smoke/esm/package-lock.json)

## getsentry/sentry  (healthy)

Draft values: ecosystem=`npm`, approx_dep_count=`373`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 373 deps across 7 manifests RepoVitals reads; no lockfile RepoVitals reads; pnpm-lock.yaml and uv.lock present but not read by RepoVitals; also contains pypi manifests (113 deps).

- Repo: https://github.com/getsentry/sentry · commit read: [96cf934dcb](https://github.com/getsentry/sentry/tree/96cf934dcb652999ed02754012b2173f60e285c9) · [commits on default branch](https://github.com/getsentry/sentry/commits/master)
- Manifests read (7 of 7 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/package.json): 227
  - [ ] [pyproject.toml](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/pyproject.toml): 113
  - [ ] [api-docs/package.json](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/api-docs/package.json): 6
  - [ ] [build-utils/package.json](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/build-utils/package.json): 0
  - [ ] [static/oxlint/eslintPluginScraps/package.json](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/static/oxlint/eslintPluginScraps/package.json): 3
  - [ ] [static/oxlint/eslintPluginSentry/package.json](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/static/oxlint/eslintPluginSentry/package.json): 3
  - [ ] [static/packages/scraps/package.json](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/static/packages/scraps/package.json): 21
- Lockfiles present that RepoVitals does NOT read: [pnpm-lock.yaml](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/pnpm-lock.yaml), [uv.lock](https://github.com/getsentry/sentry/blob/96cf934dcb652999ed02754012b2173f60e285c9/uv.lock)

## atom/atom  (risky, KNOWN ANCHOR postcss@8.2.10)

Draft values: ecosystem=`npm`, approx_dep_count=`262`, has_lockfile=`true`  
Draft sentence: Archived on GitHub 2023-03-03; package.json: "postcss": "8.2.10" (package-lock.json also records 8.2.10); osv.dev lists GHSA-566m-qj78-rww5 (CVE-2021-23382) for postcss 8.2.10.

- Repo: https://github.com/atom/atom · commit read: [1c3bd35ce2](https://github.com/atom/atom/tree/1c3bd35ce238dc0491def9e1780d04748d8e18af) · [commits on default branch](https://github.com/atom/atom/commits/master)
- Manifests read (49 of 84 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/package.json): 157 · lockfile [package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/package-lock.json)
  - [ ] [apm/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/apm/package.json): 1 · lockfile [apm/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/apm/package-lock.json)
  - [ ] [script/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/package.json): 51 · lockfile [script/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/package-lock.json)
  - [ ] [packages/about/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/about/package.json): 3 · lockfile [packages/about/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/about/package-lock.json)
  - [ ] [packages/atom-dark-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-dark-syntax/package.json): 0
  - [ ] [packages/atom-dark-ui/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-dark-ui/package.json): 0
  - [ ] [packages/atom-light-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-light-syntax/package.json): 0
  - [ ] [packages/atom-light-ui/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/atom-light-ui/package.json): 0
  - [ ] [packages/autoflow/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/autoflow/package.json): 2
  - [ ] [packages/base16-tomorrow-dark-theme/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/base16-tomorrow-dark-theme/package.json): 0
  - [ ] [packages/base16-tomorrow-light-theme/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/base16-tomorrow-light-theme/package.json): 0
  - [ ] [packages/dalek/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/dalek/package.json): 4 · lockfile [packages/dalek/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/dalek/package-lock.json)
  - [ ] [packages/deprecation-cop/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/deprecation-cop/package.json): 6
  - [ ] [packages/dev-live-reload/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/dev-live-reload/package.json): 2
  - [ ] [packages/exception-reporting/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/exception-reporting/package.json): 5
  - [ ] [packages/git-diff/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/git-diff/package.json): 3
  - [ ] [packages/go-to-line/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/go-to-line/package.json): 1
  - [ ] [packages/grammar-selector/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/grammar-selector/package.json): 2
  - [ ] [packages/incompatible-packages/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/incompatible-packages/package.json): 1
  - [ ] [packages/language-rust-bundled/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/language-rust-bundled/package.json): 1
  - [ ] [packages/line-ending-selector/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/line-ending-selector/package.json): 3
  - [ ] [packages/link/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/link/package.json): 2
  - [ ] [packages/one-dark-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/one-dark-syntax/package.json): 0
  - [ ] [packages/one-dark-ui/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/one-dark-ui/package.json): 1
  - [ ] [packages/one-light-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/one-light-syntax/package.json): 0
  - [ ] [packages/one-light-ui/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/one-light-ui/package.json): 1
  - [ ] [packages/solarized-dark-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/solarized-dark-syntax/package.json): 0
  - [ ] [packages/solarized-light-syntax/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/solarized-light-syntax/package.json): 0
  - [ ] [packages/update-package-dependencies/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/update-package-dependencies/package.json): 1
  - [ ] [packages/welcome/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/welcome/package.json): 3 · lockfile [packages/welcome/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/packages/welcome/package-lock.json)
  - [ ] [script/update-server/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/update-server/package.json): 2 · lockfile [script/update-server/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/update-server/package-lock.json)
  - [ ] [script/vsts/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/vsts/package.json): 10 · lockfile [script/vsts/package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/script/vsts/package-lock.json)
  - [ ] [spec/fixtures/packages/package-with-activation-commands-and-deserializers/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-activation-commands-and-deserializers/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-cached-incompatible-native-module/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-cached-incompatible-native-module/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-consumed-services/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-consumed-services/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-deserializers/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-deserializers/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-different-directory-name/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-different-directory-name/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-directory-provider/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-directory-provider/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-empty-activation-commands/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-empty-activation-commands/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-empty-activation-hooks/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-empty-activation-hooks/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-empty-keymap/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-empty-keymap/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-empty-menu/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-empty-menu/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-empty-workspace-openers/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-empty-workspace-openers/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-eval-time-api-calls/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-eval-time-api-calls/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-ignored-incompatible-native-module/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-ignored-incompatible-native-module/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-incompatible-native-module-loaded-conditionally/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-incompatible-native-module-loaded-conditionally/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-incompatible-native-module/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-incompatible-native-module/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-invalid-activation-commands/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-invalid-activation-commands/package.json): 0
  - [ ] [spec/fixtures/packages/package-with-invalid-context-menu/package.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/spec/fixtures/packages/package-with-invalid-context-menu/package.json): 0
- Anchor line: [package.json#L139](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/package.json#L139) → `"postcss": "8.2.10",`
- Locked in [package-lock.json](https://github.com/atom/atom/blob/1c3bd35ce238dc0491def9e1780d04748d8e18af/package-lock.json): search the file for `postcss` and check the version is 8.2.10
- npm page for this version: https://www.npmjs.com/package/postcss/v/8.2.10
- osv.dev: https://osv.dev/vulnerability/GHSA-566m-qj78-rww5 (CVE-2021-23382)
- osv.dev: https://osv.dev/vulnerability/GHSA-6g55-p6wh-862q (CVE-2026-45623)

## atom/apm  (risky, KNOWN ANCHOR request@2.88.2)

Draft values: ecosystem=`npm`, approx_dep_count=`35`, has_lockfile=`true`  
Draft sentence: Archived on GitHub 2022-12-15; package.json: "request": "^2.88.2", locked to 2.88.2 by package-lock.json; npm marks request@2.88.2 deprecated and osv.dev lists GHSA-p8p7-x288-28g6 for it.

- Repo: https://github.com/atom/apm · commit read: [d4f986aa53](https://github.com/atom/apm/tree/d4f986aa53c7a4f83e90ac4ef169c0cc53276187) · [commits on default branch](https://github.com/atom/apm/commits/master)
- Manifests read (13 of 13 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/package.json): 32 · lockfile [package-lock.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/package-lock.json)
  - [ ] [native-module/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/native-module/package.json): 0
  - [ ] [templates/bundle/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/bundle/package.json): 0
  - [ ] [templates/language/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/language/package.json): 0
  - [ ] [templates/package-coffeescript/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/package-coffeescript/package.json): 0
  - [ ] [templates/package-javascript/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/package-javascript/package.json): 0
  - [ ] [templates/theme/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/templates/theme/package.json): 0
  - [ ] [spec/fixtures/package-with-native-deps/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/package-with-native-deps/package.json): 1
  - [ ] [spec/fixtures/test-module-three/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-three/package.json): 0
  - [ ] [spec/fixtures/test-module-two/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-two/package.json): 0
  - [ ] [spec/fixtures/test-module-with-dependencies/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-with-dependencies/package.json): 1
  - [ ] [spec/fixtures/test-module-with-lockfile/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-with-lockfile/package.json): 1 · lockfile [spec/fixtures/test-module-with-lockfile/package-lock.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module-with-lockfile/package-lock.json)
  - [ ] [spec/fixtures/test-module/package.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/spec/fixtures/test-module/package.json): 0
- Anchor line: [package.json#L46](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/package.json#L46) → `"request": "^2.88.2",`
- Locked in [package-lock.json](https://github.com/atom/apm/blob/d4f986aa53c7a4f83e90ac4ef169c0cc53276187/package-lock.json): search the file for `request` and check the version is 2.88.2
- npm page for this version: https://www.npmjs.com/package/request/v/2.88.2
- osv.dev: https://osv.dev/vulnerability/GHSA-p8p7-x288-28g6 (CVE-2023-28155)
- npm deprecation text seen on 2026-10-05: "request has been deprecated, see https://github.com/request/request/issues/3142"

## angular/angular.js  (risky, KNOWN ANCHOR karma@4.4.1)

Draft values: ecosystem=`npm`, approx_dep_count=`87`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2024-04-12; package.json: "karma": "4.4.1" (exact pin; the repo's yarn.lock is not read by RepoVitals); osv.dev lists GHSA-7x7c-qm48-pq9c (CVE-2022-0437) for karma 4.4.1.

- Repo: https://github.com/angular/angular.js · commit read: [d8f77817eb](https://github.com/angular/angular.js/tree/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe) · [commits on default branch](https://github.com/angular/angular.js/commits/master)
- Manifests read (3 of 3 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/package.json): 80
  - [ ] [scripts/code.angularjs.org-firebase/functions/package.json](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/scripts/code.angularjs.org-firebase/functions/package.json): 3
  - [ ] [scripts/docs.angularjs.org-firebase/functions/package.json](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/scripts/docs.angularjs.org-firebase/functions/package.json): 4
- Lockfiles present that RepoVitals does NOT read: [scripts/code.angularjs.org-firebase/functions/yarn.lock](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/scripts/code.angularjs.org-firebase/functions/yarn.lock), [scripts/docs.angularjs.org-firebase/functions/yarn.lock](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/scripts/docs.angularjs.org-firebase/functions/yarn.lock), [yarn.lock](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/yarn.lock)
- Anchor line: [package.json#L66](https://github.com/angular/angular.js/blob/d8f77817eb5c98dec5317bc3756d1ea1812bcfbe/package.json#L66) → `"karma": "4.4.1",`
- npm page for this version: https://www.npmjs.com/package/karma/v/4.4.1
- osv.dev: https://osv.dev/vulnerability/GHSA-7x7c-qm48-pq9c (CVE-2022-0437)
- osv.dev: https://osv.dev/vulnerability/GHSA-rc3x-jf5g-xvc5 (CVE-2021-23495)

## angular/protractor  (risky, KNOWN ANCHOR lodash@4.17.11)

Draft values: ecosystem=`npm`, approx_dep_count=`90`, has_lockfile=`true`  
Draft sentence: Archived on GitHub 2024-07-29; package.json: "lodash": "^4.17.11", locked to 4.17.11 by package-lock.json; osv.dev lists GHSA-29mw-wpgm-hmr9 (CVE-2020-28500) for lodash 4.17.11.

- Repo: https://github.com/angular/protractor · commit read: [4bc80d1a45](https://github.com/angular/protractor/tree/4bc80d1a459542d883ea9200e4e1f48d265d0fda) · [commits on default branch](https://github.com/angular/protractor/commits/master)
- Manifests read (6 of 6 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/package.json): 36 · lockfile [package-lock.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/package-lock.json)
  - [ ] [example/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/example/package.json): 2 · lockfile [example/package-lock.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/example/package-lock.json)
  - [ ] [exampleTypescript/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/exampleTypescript/package.json): 6
  - [ ] [testapp/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/testapp/package.json): 21 · lockfile [testapp/package-lock.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/testapp/package-lock.json)
  - [ ] [website/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/website/package.json): 19 · lockfile [website/package-lock.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/website/package-lock.json)
  - [ ] [spec/install/package.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/spec/install/package.json): 6
- Anchor line: [package.json#L44](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/package.json#L44) → `"lodash": "^4.17.11",`
- Locked in [package-lock.json](https://github.com/angular/protractor/blob/4bc80d1a459542d883ea9200e4e1f48d265d0fda/package-lock.json): search the file for `lodash` and check the version is 4.17.11
- npm page for this version: https://www.npmjs.com/package/lodash/v/4.17.11
- osv.dev: https://osv.dev/vulnerability/GHSA-29mw-wpgm-hmr9 (CVE-2020-28500)
- osv.dev: https://osv.dev/vulnerability/GHSA-35jh-r3h4-6jhm (CVE-2021-23337, CVE-2026-4800)

## microsoft/vscode-go  (risky, KNOWN ANCHOR tslint@6.1.1)

Draft values: ecosystem=`npm`, approx_dep_count=`27`, has_lockfile=`true`  
Draft sentence: Archived on GitHub 2023-07-15; package.json: "tslint": "^6.1.1", locked to 6.1.1 by package-lock.json; npm marks tslint@6.1.1 deprecated ("TSLint has been deprecated in favor of ESLint").

- Repo: https://github.com/microsoft/vscode-go · commit read: [9ee1f173b0](https://github.com/microsoft/vscode-go/tree/9ee1f173b05bb74ee64e4906f832603cd7380687) · [commits on default branch](https://github.com/microsoft/vscode-go/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/microsoft/vscode-go/blob/9ee1f173b05bb74ee64e4906f832603cd7380687/package.json): 27 · lockfile [package-lock.json](https://github.com/microsoft/vscode-go/blob/9ee1f173b05bb74ee64e4906f832603cd7380687/package-lock.json)
- Anchor line: [package.json#L68](https://github.com/microsoft/vscode-go/blob/9ee1f173b05bb74ee64e4906f832603cd7380687/package.json#L68) → `"tslint": "^6.1.1",`
- Locked in [package-lock.json](https://github.com/microsoft/vscode-go/blob/9ee1f173b05bb74ee64e4906f832603cd7380687/package-lock.json): search the file for `tslint` and check the version is 6.1.1
- npm page for this version: https://www.npmjs.com/package/tslint/v/6.1.1
- npm deprecation text seen on 2026-10-05: "TSLint has been deprecated in favor of ESLint. Please see https://github.com/palantir/tsli"

## facebookarchive/react-native-fbsdk  (risky, KNOWN ANCHOR eslint@7.14.0)

Draft values: ecosystem=`npm`, approx_dep_count=`16`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2021-04-02; package.json: "eslint": "7.14.0" (exact pin; the repo's yarn.lock is not read by RepoVitals); npm marks eslint@7.14.0 deprecated ("This version is no longer supported").

- Repo: https://github.com/facebookarchive/react-native-fbsdk · commit read: [b8ed568b05](https://github.com/facebookarchive/react-native-fbsdk/tree/b8ed568b05f3e41e6d6b937ae3125492f95e60bf) · [commits on default branch](https://github.com/facebookarchive/react-native-fbsdk/commits/master)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/facebookarchive/react-native-fbsdk/blob/b8ed568b05f3e41e6d6b937ae3125492f95e60bf/package.json): 14
  - [ ] [example/package.json](https://github.com/facebookarchive/react-native-fbsdk/blob/b8ed568b05f3e41e6d6b937ae3125492f95e60bf/example/package.json): 2
- Lockfiles present that RepoVitals does NOT read: [yarn.lock](https://github.com/facebookarchive/react-native-fbsdk/blob/b8ed568b05f3e41e6d6b937ae3125492f95e60bf/yarn.lock)
- Anchor line: [package.json#L75](https://github.com/facebookarchive/react-native-fbsdk/blob/b8ed568b05f3e41e6d6b937ae3125492f95e60bf/package.json#L75) → `"eslint": "7.14.0",`
- npm page for this version: https://www.npmjs.com/package/eslint/v/7.14.0
- npm deprecation text seen on 2026-10-05: "This version is no longer supported. Please see https://eslint.org/version-support for oth"

## openai/gpt-2  (risky, KNOWN ANCHOR requests@2.21.0)

Draft values: ecosystem=`pypi`, approx_dep_count=`4`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2026-04-08; requirements.txt: requests==2.21.0; osv.dev lists GHSA-9hjg-9r4m-mvj7 (CVE-2024-47081) among 8 advisories for requests 2.21.0.

- Repo: https://github.com/openai/gpt-2 · commit read: [9b63575ef4](https://github.com/openai/gpt-2/tree/9b63575ef42771a015060c964af2c3da4cf7c8ab) · [commits on default branch](https://github.com/openai/gpt-2/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [requirements.txt](https://github.com/openai/gpt-2/blob/9b63575ef42771a015060c964af2c3da4cf7c8ab/requirements.txt): 4
- Anchor line: [requirements.txt#L3](https://github.com/openai/gpt-2/blob/9b63575ef42771a015060c964af2c3da4cf7c8ab/requirements.txt#L3) → `requests==2.21.0`
- PyPI page for this version: https://pypi.org/project/requests/2.21.0/
- osv.dev: https://osv.dev/vulnerability/GHSA-9hjg-9r4m-mvj7 (CVE-2024-47081)
- osv.dev: https://osv.dev/vulnerability/GHSA-9wx4-h78v-vm56 (CVE-2024-35195)

## Netflix/security_monkey  (risky, KNOWN ANCHOR PyYAML@5.3)

Draft values: ecosystem=`pypi`, approx_dep_count=`58`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2021-09-17; requirements.txt: PyYAML==5.3; osv.dev lists GHSA-6757-jp84-gxfx (CVE-2020-1747) for PyYAML 5.3.

- Repo: https://github.com/Netflix/security_monkey · commit read: [c28592ffd5](https://github.com/Netflix/security_monkey/tree/c28592ffd518fa399527d26262683fc860c30eef) · [commits on default branch](https://github.com/Netflix/security_monkey/commits/develop)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [requirements.txt](https://github.com/Netflix/security_monkey/blob/c28592ffd518fa399527d26262683fc860c30eef/requirements.txt): 46
  - [ ] [setup.py](https://github.com/Netflix/security_monkey/blob/c28592ffd518fa399527d26262683fc860c30eef/setup.py): 12
- Anchor line: [requirements.txt#L15](https://github.com/Netflix/security_monkey/blob/c28592ffd518fa399527d26262683fc860c30eef/requirements.txt#L15) → `PyYAML==5.3`
- PyPI page for this version: https://pypi.org/project/PyYAML/5.3/
- osv.dev: https://osv.dev/vulnerability/GHSA-6757-jp84-gxfx (CVE-2020-1747)
- osv.dev: https://osv.dev/vulnerability/GHSA-8q59-q68h-6hv4 (CVE-2020-14343)

## mdn/kuma  (risky, KNOWN ANCHOR django@3.2.12)

Draft values: ecosystem=`pypi`, approx_dep_count=`51`, has_lockfile=`true`  
Draft sentence: Archived on GitHub 2022-08-26; pyproject.toml: django = "^3", locked to 3.2.12 by poetry.lock; osv.dev lists GHSA-2gwj-7jmv-h26r (CVE-2022-28346) for Django 3.2.12.

- Repo: https://github.com/mdn/kuma · commit read: [ae0860087c](https://github.com/mdn/kuma/tree/ae0860087cfb7ce19c9296f5dfbae10260dca759) · [commits on default branch](https://github.com/mdn/kuma/commits/main)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [pyproject.toml](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/pyproject.toml): 44 · lockfile [poetry.lock](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/poetry.lock)
  - [ ] [docs/requirements.txt](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/docs/requirements.txt): 7
- Anchor line: [pyproject.toml#L17](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/pyproject.toml#L17) → `django = "^3"`
- Locked in [poetry.lock](https://github.com/mdn/kuma/blob/ae0860087cfb7ce19c9296f5dfbae10260dca759/poetry.lock): search the file for `django` and check the version is 3.2.12
- PyPI page for this version: https://pypi.org/project/django/3.2.12/
- osv.dev: https://osv.dev/vulnerability/GHSA-2gwj-7jmv-h26r (CVE-2022-28346)
- osv.dev: https://osv.dev/vulnerability/GHSA-2hrw-hx67-34x6 (CVE-2023-24580)

## openai/jukebox  (risky, KNOWN ANCHOR tqdm@4.45.0)

Draft values: ecosystem=`pypi`, approx_dep_count=`14`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2026-04-08; requirements.txt: tqdm==4.45.0; osv.dev lists GHSA-g7vv-2v7x-gj9p (CVE-2024-34062) for tqdm 4.45.0.

- Repo: https://github.com/openai/jukebox · commit read: [08efbbc1d4](https://github.com/openai/jukebox/tree/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3) · [commits on default branch](https://github.com/openai/jukebox/commits/master)
- Manifests read (4 of 4 in tree), dependency count per file:
  - [ ] [requirements.txt](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/requirements.txt): 7
  - [ ] [setup.py](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/setup.py): 1
  - [ ] [apex/setup.py](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/apex/setup.py): 0
  - [ ] [tensorboardX/setup.py](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/tensorboardX/setup.py): 6
- Anchor line: [requirements.txt#L2](https://github.com/openai/jukebox/blob/08efbbc1d4ed1a3cef96e08a931944c8b4d63bb3/requirements.txt#L2) → `tqdm==4.45.0`
- PyPI page for this version: https://pypi.org/project/tqdm/4.45.0/
- osv.dev: https://osv.dev/vulnerability/GHSA-g7vv-2v7x-gj9p (CVE-2024-34062)
- osv.dev: https://osv.dev/vulnerability/PYSEC-2026-1976 (CVE-2024-34062)

## googleapis/oauth2client  (risky, KNOWN ANCHOR Django@1.10.0)

Draft values: ecosystem=`pypi`, approx_dep_count=`21`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2025-01-18; samples/django/django_user/requirements.txt: Django==1.10.0; osv.dev lists GHSA-37hp-765x-j95x (CVE-2017-7233) for Django 1.10.0.

- Repo: https://github.com/googleapis/oauth2client · commit read: [50d20532a7](https://github.com/googleapis/oauth2client/tree/50d20532a748f18e53f7d24ccbe6647132c979a9) · [commits on default branch](https://github.com/googleapis/oauth2client/commits/master)
- Manifests read (4 of 4 in tree), dependency count per file:
  - [ ] [setup.py](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/setup.py): 5
  - [ ] [docs/requirements.txt](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/docs/requirements.txt): 10
  - [ ] [samples/django/django_user/requirements.txt](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/samples/django/django_user/requirements.txt): 3
  - [ ] [samples/django/google_user/requirements.txt](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/samples/django/google_user/requirements.txt): 3
- Anchor line: [samples/django/django_user/requirements.txt#L1](https://github.com/googleapis/oauth2client/blob/50d20532a748f18e53f7d24ccbe6647132c979a9/samples/django/django_user/requirements.txt#L1) → `Django==1.10.0`
- PyPI page for this version: https://pypi.org/project/Django/1.10.0/
- osv.dev: https://osv.dev/vulnerability/GHSA-37hp-765x-j95x (CVE-2017-7233)
- osv.dev: https://osv.dev/vulnerability/GHSA-3f2c-jm6v-cr35 (CVE-2016-9014)

## tensorflow/tensor2tensor  (risky)

Draft values: ecosystem=`pypi`, approx_dep_count=`38`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2023-07-07; default-branch last commit 2023-04-01; 38 deps across 3 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/tensorflow/tensor2tensor · commit read: [bafdc1b677](https://github.com/tensorflow/tensor2tensor/tree/bafdc1b67730430d38d6ab802cbd51f9d053ba2e) · [commits on default branch](https://github.com/tensorflow/tensor2tensor/commits/master)
- Manifests read (3 of 3 in tree), dependency count per file:
  - [ ] [floyd_requirements.txt](https://github.com/tensorflow/tensor2tensor/blob/bafdc1b67730430d38d6ab802cbd51f9d053ba2e/floyd_requirements.txt): 1
  - [ ] [setup.py](https://github.com/tensorflow/tensor2tensor/blob/bafdc1b67730430d38d6ab802cbd51f9d053ba2e/setup.py): 36
  - [ ] [tensor2tensor/test_data/example_usr_dir/requirements.txt](https://github.com/tensorflow/tensor2tensor/blob/bafdc1b67730430d38d6ab802cbd51f9d053ba2e/tensor2tensor/test_data/example_usr_dir/requirements.txt): 1

## facebookarchive/draft-js  (risky)

Draft values: ecosystem=`npm`, approx_dep_count=`87`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2023-02-06; default-branch last commit 2022-12-14; 87 deps across 5 manifests RepoVitals reads; no lockfile RepoVitals reads; yarn.lock present but not read by RepoVitals.

- Repo: https://github.com/facebookarchive/draft-js · commit read: [afdb5c3177](https://github.com/facebookarchive/draft-js/tree/afdb5c3177c13fd26cb0abbdc439488f3e21b73b) · [commits on default branch](https://github.com/facebookarchive/draft-js/commits/main)
- Manifests read (5 of 5 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/package.json): 43
  - [ ] [website/package.json](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/website/package.json): 8
  - [ ] [examples/draft-0-10-0/playground/package.json](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/examples/draft-0-10-0/playground/package.json): 11
  - [ ] [examples/draft-0-10-0/tex/package.json](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/examples/draft-0-10-0/tex/package.json): 14
  - [ ] [examples/draft-0-10-0/universal/package.json](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/examples/draft-0-10-0/universal/package.json): 11
- Lockfiles present that RepoVitals does NOT read: [examples/draft-0-10-0/playground/yarn.lock](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/examples/draft-0-10-0/playground/yarn.lock), [examples/draft-0-10-0/tex/yarn.lock](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/examples/draft-0-10-0/tex/yarn.lock), [examples/draft-0-10-0/universal/yarn.lock](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/examples/draft-0-10-0/universal/yarn.lock), [website/yarn.lock](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/website/yarn.lock), [yarn.lock](https://github.com/facebookarchive/draft-js/blob/afdb5c3177c13fd26cb0abbdc439488f3e21b73b/yarn.lock)

## palantir/tslint  (risky)

Draft values: ecosystem=`npm`, approx_dep_count=`52`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2021-03-25; default-branch last commit 2021-03-25; 52 deps across 10 manifests RepoVitals reads; no lockfile RepoVitals reads; yarn.lock present but not read by RepoVitals.

- Repo: https://github.com/palantir/tslint · commit read: [285fc1db18](https://github.com/palantir/tslint/tree/285fc1db18d1fd24680d6a2282c6445abf1566ee) · [commits on default branch](https://github.com/palantir/tslint/commits/master)
- Manifests read (8 of 10 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/package.json): 41
  - [ ] [test/config/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/config/package.json): 3
  - [ ] [test/external/tslint-test-config-non-relative/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/external/tslint-test-config-non-relative/package.json): 0
  - [ ] [test/external/tslint-test-config/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/external/tslint-test-config/package.json): 0
  - [ ] [test/external/tslint-test-custom-formatter/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/external/tslint-test-custom-formatter/package.json): 0
  - [ ] [test/external/tslint-test-custom-rules/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/external/tslint-test-custom-rules/package.json): 0
  - [ ] [test/rules/no-implicit-dependencies/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/rules/no-implicit-dependencies/package.json): 7
  - [ ] [test/rules/no-implicit-dependencies/default/nested-package/package.json](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/test/rules/no-implicit-dependencies/default/nested-package/package.json): 1
- Lockfiles present that RepoVitals does NOT read: [yarn.lock](https://github.com/palantir/tslint/blob/285fc1db18d1fd24680d6a2282c6445abf1566ee/yarn.lock)

## babel/babel-eslint  (risky)

Draft values: ecosystem=`npm`, approx_dep_count=`29`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2021-08-18; default-branch last commit 2020-10-09; 29 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads; yarn.lock present but not read by RepoVitals.

- Repo: https://github.com/babel/babel-eslint · commit read: [b5b9a09edb](https://github.com/babel/babel-eslint/tree/b5b9a09edbac4350e4e51033a4608dd95dad1f67) · [commits on default branch](https://github.com/babel/babel-eslint/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/babel/babel-eslint/blob/b5b9a09edbac4350e4e51033a4608dd95dad1f67/package.json): 29
- Lockfiles present that RepoVitals does NOT read: [yarn.lock](https://github.com/babel/babel-eslint/blob/b5b9a09edbac4350e4e51033a4608dd95dad1f67/yarn.lock)

## facebookarchive/flux  (risky)

Draft values: ecosystem=`npm`, approx_dep_count=`166`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2023-03-23; default-branch last commit 2023-03-22; 166 deps across 9 manifests RepoVitals reads; no lockfile RepoVitals reads; yarn.lock present but not read by RepoVitals.

- Repo: https://github.com/facebookarchive/flux · commit read: [4ee8c50865](https://github.com/facebookarchive/flux/tree/4ee8c50865c357e005cb40ea03cdd403533aad26) · [commits on default branch](https://github.com/facebookarchive/flux/commits/main)
- Manifests read (9 of 9 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/package.json): 22
  - [ ] [website/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/website/package.json): 5
  - [ ] [examples/flux-async/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-async/package.json): 24
  - [ ] [examples/flux-flow/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-flow/package.json): 19
  - [ ] [examples/flux-jest-container/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-jest-container/package.json): 20
  - [ ] [examples/flux-jest/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-jest/package.json): 19
  - [ ] [examples/flux-logging/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-logging/package.json): 19
  - [ ] [examples/flux-shell/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-shell/package.json): 19
  - [ ] [examples/flux-todomvc/package.json](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/examples/flux-todomvc/package.json): 19
- Lockfiles present that RepoVitals does NOT read: [website/yarn.lock](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/website/yarn.lock), [yarn.lock](https://github.com/facebookarchive/flux/blob/4ee8c50865c357e005cb40ea03cdd403533aad26/yarn.lock)

## GoogleChromeLabs/sw-precache  (risky)

Draft values: ecosystem=`npm`, approx_dep_count=`63`, has_lockfile=`false`  
Draft sentence: Archived on GitHub 2021-01-23; default-branch last commit 2019-04-02; 63 deps across 2 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/GoogleChromeLabs/sw-precache · commit read: [b202ca04fe](https://github.com/GoogleChromeLabs/sw-precache/tree/b202ca04fe87555d7fe9ca338f87fbcf76812c39) · [commits on default branch](https://github.com/GoogleChromeLabs/sw-precache/commits/master)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/GoogleChromeLabs/sw-precache/blob/b202ca04fe87555d7fe9ca338f87fbcf76812c39/package.json): 27
  - [ ] [app-shell-demo/package.json](https://github.com/GoogleChromeLabs/sw-precache/blob/b202ca04fe87555d7fe9ca338f87fbcf76812c39/app-shell-demo/package.json): 36

## request/request  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`40`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2020-02-11; 40 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads; npm marks request@2.88.2, the latest release, deprecated.

- Repo: https://github.com/request/request · commit read: [3c0cddc7c8](https://github.com/request/request/tree/3c0cddc7c8eb60b470e9519da85896ed7ee0081e) · [commits on default branch](https://github.com/request/request/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/request/request/blob/3c0cddc7c8eb60b470e9519da85896ed7ee0081e/package.json): 40

## strongloop/loopback  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`60`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2021-03-05; 60 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/strongloop/loopback · commit read: [13371fd2a1](https://github.com/strongloop/loopback/tree/13371fd2a138a6f39db77e5a455b3170e5d4a0f5) · [commits on default branch](https://github.com/strongloop/loopback/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/strongloop/loopback/blob/13371fd2a138a6f39db77e5a455b3170e5d4a0f5/package.json): 60

## jaredhanson/passport-local  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`5`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2022-12-15; 5 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/jaredhanson/passport-local · commit read: [6045c1cd62](https://github.com/jaredhanson/passport-local/tree/6045c1cd62a1e6e56afe851eb7304549a597ac23) · [commits on default branch](https://github.com/jaredhanson/passport-local/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/jaredhanson/passport-local/blob/6045c1cd62a1e6e56afe851eb7304549a597ac23/package.json): 5

## krakenjs/kraken-js  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`30`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2025-08-11; 30 deps across 3 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/krakenjs/kraken-js · commit read: [01656bf883](https://github.com/krakenjs/kraken-js/tree/01656bf883acf05ecf81a91aa5ccd4ba13c73a95) · [commits on default branch](https://github.com/krakenjs/kraken-js/commits/v2.x)
- Manifests read (3 of 3 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/krakenjs/kraken-js/blob/01656bf883acf05ecf81a91aa5ccd4ba13c73a95/package.json): 29
  - [ ] [test/fixtures/views/package.json](https://github.com/krakenjs/kraken-js/blob/01656bf883acf05ecf81a91aa5ccd4ba13c73a95/test/fixtures/views/package.json): 1
  - [ ] [test/fixtures/views/view-engine/text/package.json](https://github.com/krakenjs/kraken-js/blob/01656bf883acf05ecf81a91aa5ccd4ba13c73a95/test/fixtures/views/view-engine/text/package.json): 0

## omab/django-social-auth  (in_between)

Draft values: ecosystem=`pypi`, approx_dep_count=`4`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2015-03-30; 4 deps across 2 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/omab/django-social-auth · commit read: [699571a3b6](https://github.com/omab/django-social-auth/tree/699571a3b6d84aa2c25ffce59daa4c7f3559a0e4) · [commits on default branch](https://github.com/omab/django-social-auth/commits/master)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [requirements.txt](https://github.com/omab/django-social-auth/blob/699571a3b6d84aa2c25ffce59daa4c7f3559a0e4/requirements.txt): 2
  - [ ] [setup.py](https://github.com/omab/django-social-auth/blob/699571a3b6d84aa2c25ffce59daa4c7f3559a0e4/setup.py): 2

## bower/bower  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`99`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2024-10-13; 99 deps across 6 manifests RepoVitals reads; no lockfile RepoVitals reads; yarn.lock present but not read by RepoVitals.

- Repo: https://github.com/bower/bower · commit read: [4e0c3c1181](https://github.com/bower/bower/tree/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a) · [commits on default branch](https://github.com/bower/bower/commits/master)
- Manifests read (6 of 6 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/package.json): 60
  - [ ] [packages/bower-config/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-config/package.json): 13
  - [ ] [packages/bower-endpoint-parser/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-endpoint-parser/package.json): 3
  - [ ] [packages/bower-json/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-json/package.json): 10
  - [ ] [packages/bower-logger/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-logger/package.json): 2
  - [ ] [packages/bower-registry-client/package.json](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/packages/bower-registry-client/package.json): 11
- Lockfiles present that RepoVitals does NOT read: [yarn.lock](https://github.com/bower/bower/blob/4e0c3c1181c21624c5b3ab5bdf5d3becdb172b5a/yarn.lock)

## YelpArchive/elastalert  (in_between)

Draft values: ecosystem=`pypi`, approx_dep_count=`52`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2022-11-11; 52 deps across 3 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/YelpArchive/elastalert · commit read: [e0bbcb5b71](https://github.com/YelpArchive/elastalert/tree/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16) · [commits on default branch](https://github.com/YelpArchive/elastalert/commits/master)
- Manifests read (3 of 3 in tree), dependency count per file:
  - [ ] [requirements-dev.txt](https://github.com/YelpArchive/elastalert/blob/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16/requirements-dev.txt): 8
  - [ ] [requirements.txt](https://github.com/YelpArchive/elastalert/blob/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16/requirements.txt): 22
  - [ ] [setup.py](https://github.com/YelpArchive/elastalert/blob/e0bbcb5b71e9fdb4a750c3871d365a882ff17b16/setup.py): 22

## openai/spinningup  (in_between)

Draft values: ecosystem=`pypi`, approx_dep_count=`31`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2020-02-07; 31 deps across 2 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/openai/spinningup · commit read: [038665d62d](https://github.com/openai/spinningup/tree/038665d62d569055401d91856abb287263096178) · [commits on default branch](https://github.com/openai/spinningup/commits/master)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [setup.py](https://github.com/openai/spinningup/blob/038665d62d569055401d91856abb287263096178/setup.py): 15
  - [ ] [docs/docs_requirements.txt](https://github.com/openai/spinningup/blob/038665d62d569055401d91856abb287263096178/docs/docs_requirements.txt): 16

## openai/baselines  (in_between)

Draft values: ecosystem=`pypi`, approx_dep_count=`14`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2020-01-31; 14 deps across 1 manifest RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/openai/baselines · commit read: [ea25b9e8b2](https://github.com/openai/baselines/tree/ea25b9e8b234e6ee1bca43083f8f3cf974143998) · [commits on default branch](https://github.com/openai/baselines/commits/master)
- Manifests read (1 of 1 in tree), dependency count per file:
  - [ ] [setup.py](https://github.com/openai/baselines/blob/ea25b9e8b234e6ee1bca43083f8f3cf974143998/setup.py): 14

## airbnb/react-sketchapp  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`162`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2021-03-30; 162 deps across 19 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/airbnb/react-sketchapp · commit read: [b238e69c6f](https://github.com/airbnb/react-sketchapp/tree/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7) · [commits on default branch](https://github.com/airbnb/react-sketchapp/commits/master)
- Manifests read (19 of 19 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/package.json): 41
  - [ ] [template/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/template/package.json): 5
  - [ ] [examples/basic-setup-typescript/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/basic-setup-typescript/package.json): 8
  - [ ] [examples/basic-setup/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/basic-setup/package.json): 6
  - [ ] [examples/basic-svg/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/basic-svg/package.json): 5
  - [ ] [examples/colors/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/colors/package.json): 8
  - [ ] [examples/emotion/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/emotion/package.json): 6
  - [ ] [examples/form-validation/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/form-validation/package.json): 10
  - [ ] [examples/foursquare-maps/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/foursquare-maps/package.json): 11
  - [ ] [examples/glamorous/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/glamorous/package.json): 6
  - [ ] [examples/profile-cards-graphql/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/profile-cards-graphql/package.json): 10
  - [ ] [examples/profile-cards-primitives/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/profile-cards-primitives/package.json): 8
  - [ ] [examples/profile-cards-react-with-styles/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/profile-cards-react-with-styles/package.json): 5
  - [ ] [examples/profile-cards/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/profile-cards/package.json): 4
  - [ ] [examples/react-router-prototyping/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/react-router-prototyping/package.json): 7
  - [ ] [examples/styled-components/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/styled-components/package.json): 8
  - [ ] [examples/styleguide/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/styleguide/package.json): 5
  - [ ] [examples/symbols/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/symbols/package.json): 4
  - [ ] [examples/timeline-airtable/package.json](https://github.com/airbnb/react-sketchapp/blob/b238e69c6f1e65ec6b1d8a908a91fbd9a8cc43a7/examples/timeline-airtable/package.json): 5

## react/create-react-app  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`218`, has_lockfile=`true`  
Draft sentence: Not archived; default-branch last commit 2025-02-14; 218 deps across 26 manifests RepoVitals reads; readable lockfile package-lock.json.

- Repo: https://github.com/react/create-react-app · commit read: [6254386531](https://github.com/react/create-react-app/tree/6254386531d263688ccfa542d0e628fbc0de0b28) · [commits on default branch](https://github.com/react/create-react-app/commits/main)
- Manifests read (26 of 26 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package.json): 23 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [docusaurus/website/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/docusaurus/website/package.json): 5 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/babel-plugin-named-asset-import/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/babel-plugin-named-asset-import/package.json): 3 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/babel-preset-react-app/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/babel-preset-react-app/package.json): 17 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/confusing-browser-globals/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/confusing-browser-globals/package.json): 1 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/cra-template-typescript/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/cra-template-typescript/package.json): 0 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/cra-template/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/cra-template/package.json): 0 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/create-react-app/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/create-react-app/package.json): 13 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/eslint-config-react-app/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/eslint-config-react-app/package.json): 15 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/react-app-polyfill/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-app-polyfill/package.json): 6 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/react-dev-utils/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-dev-utils/package.json): 26 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/react-error-overlay/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-error-overlay/package.json): 23 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [packages/react-scripts/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-scripts/package.json): 51 · lockfile [package-lock.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/package-lock.json)
  - [ ] [test/fixtures/boostrap-sass/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/boostrap-sass/package.json): 4
  - [ ] [test/fixtures/builds-with-multiple-runtimes/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/builds-with-multiple-runtimes/package.json): 5
  - [ ] [test/fixtures/global-scss-asset-resolution/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/global-scss-asset-resolution/package.json): 3
  - [ ] [test/fixtures/issue-5176-flow-class-properties/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/issue-5176-flow-class-properties/package.json): 0
  - [ ] [test/fixtures/issue-5947-not-typescript/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/issue-5947-not-typescript/package.json): 0
  - [ ] [test/fixtures/jsconfig/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/jsconfig/package.json): 3
  - [ ] [test/fixtures/mjs-support/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/mjs-support/package.json): 4
  - [ ] [test/fixtures/relative-paths/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/relative-paths/package.json): 2
  - [ ] [test/fixtures/typescript-advanced/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/typescript-advanced/package.json): 6
  - [ ] [test/fixtures/typescript-typecheck/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/typescript-typecheck/package.json): 5
  - [ ] [test/fixtures/typescript/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/typescript/package.json): 1
  - [ ] [test/fixtures/webpack-message-formatting/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/test/fixtures/webpack-message-formatting/package.json): 2
  - [ ] [packages/react-scripts/fixtures/kitchensink/package.json](https://github.com/react/create-react-app/blob/6254386531d263688ccfa542d0e628fbc0de0b28/packages/react-scripts/fixtures/kitchensink/package.json): 0

## vercel/next.js  (in_between)

Draft values: ecosystem=`npm`, approx_dep_count=`725`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2026-10-05; 725 deps across 50 manifests RepoVitals reads; no lockfile RepoVitals reads; pnpm-lock.yaml present but not read by RepoVitals; 35 of the 50 manifests RepoVitals reads (of 669 in the tree) are under examples/.

- Repo: https://github.com/vercel/next.js · commit read: [41215d7776](https://github.com/vercel/next.js/tree/41215d77762375b4b5154b12cfbb4372a835f8a0) · [commits on default branch](https://github.com/vercel/next.js/commits/canary)
- Manifests read (50 of 669 in tree), dependency count per file:
  - [ ] [package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/package.json): 192
  - [ ] [.github/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/.github/package.json): 0
  - [ ] [rspack/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/rspack/package.json): 2
  - [ ] [apps/bundle-analyzer/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/apps/bundle-analyzer/package.json): 31
  - [ ] [bench/app-router-server/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/app-router-server/package.json): 4
  - [ ] [bench/fuzzponent/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/fuzzponent/package.json): 4
  - [ ] [bench/heavy-npm-deps/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/heavy-npm-deps/package.json): 6
  - [ ] [bench/module-cost/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/module-cost/package.json): 3
  - [ ] [bench/nested-deps-app-router-many-pages/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/nested-deps-app-router-many-pages/package.json): 5
  - [ ] [bench/nested-deps-app-router/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/nested-deps-app-router/package.json): 5
  - [ ] [bench/nested-deps/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/nested-deps/package.json): 5
  - [ ] [bench/next-minimal-server/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/next-minimal-server/package.json): 1
  - [ ] [bench/recursive-delete/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/recursive-delete/package.json): 3
  - [ ] [bench/rendering/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/rendering/package.json): 2
  - [ ] [bench/vercel/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/bench/vercel/package.json): 10
  - [ ] [examples/active-class-name/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/active-class-name/package.json): 7
  - [ ] [examples/api-routes-apollo-server-and-client-auth/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-apollo-server-and-client-auth/package.json): 16
  - [ ] [examples/api-routes-apollo-server-and-client/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-apollo-server-and-client/package.json): 13
  - [ ] [examples/api-routes-apollo-server/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-apollo-server/package.json): 12
  - [ ] [examples/api-routes-cors/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-cors/package.json): 9
  - [ ] [examples/api-routes-graphql/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-graphql/package.json): 10
  - [ ] [examples/api-routes-middleware/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-middleware/package.json): 10
  - [ ] [examples/api-routes-rest/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/api-routes-rest/package.json): 8
  - [ ] [examples/auth/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/auth/package.json): 8
  - [ ] [examples/auth0/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/auth0/package.json): 8
  - [ ] [examples/basic-css/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/basic-css/package.json): 7
  - [ ] [examples/blog-starter/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/blog-starter/package.json): 15
  - [ ] [examples/blog-with-comment/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/blog-with-comment/package.json): 19
  - [ ] [examples/blog/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/blog/package.json): 11
  - [ ] [examples/cache-handler-redis/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cache-handler-redis/package.json): 8
  - [ ] [examples/cloudflare-turnstile/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cloudflare-turnstile/package.json): 7
  - [ ] [examples/cms-agilitycms/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-agilitycms/package.json): 16
  - [ ] [examples/cms-builder-io/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-builder-io/package.json): 10
  - [ ] [examples/cms-buttercms/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-buttercms/package.json): 14
  - [ ] [examples/cms-contentful/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-contentful/package.json): 16
  - [ ] [examples/cms-cosmic/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-cosmic/package.json): 16
  - [ ] [examples/cms-datocms/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-datocms/package.json): 11
  - [ ] [examples/cms-dotcms/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-dotcms/package.json): 13
  - [ ] [examples/cms-drupal/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-drupal/package.json): 9
  - [ ] [examples/cms-enterspeed/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-enterspeed/package.json): 11
  - [ ] [examples/cms-ghost/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-ghost/package.json): 10
  - [ ] [examples/cms-graphcms/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-graphcms/package.json): 8
  - [ ] [examples/cms-kontent-ai/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-kontent-ai/package.json): 17
  - [ ] [examples/cms-makeswift/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-makeswift/package.json): 7
  - [ ] [examples/cms-payload/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-payload/package.json): 28
  - [ ] [examples/cms-plasmic/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-plasmic/package.json): 7
  - [ ] [examples/cms-prepr/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-prepr/package.json): 8
  - [ ] [examples/cms-prismic/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-prismic/package.json): 16
  - [ ] [examples/cms-sanity/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-sanity/package.json): 25
  - [ ] [examples/cms-sitecore-xmcloud/package.json](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/cms-sitecore-xmcloud/package.json): 42
- Lockfiles present that RepoVitals does NOT read: [.github/pnpm-lock.yaml](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/.github/pnpm-lock.yaml), [examples/with-docker-export-output/pnpm-lock.yaml](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/with-docker-export-output/pnpm-lock.yaml), [examples/with-docker/pnpm-lock.yaml](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/examples/with-docker/pnpm-lock.yaml), [pnpm-lock.yaml](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/pnpm-lock.yaml), [rspack/crates/binding/pnpm-lock.yaml](https://github.com/vercel/next.js/blob/41215d77762375b4b5154b12cfbb4372a835f8a0/rspack/crates/binding/pnpm-lock.yaml)

## dropbox/pyannotate  (in_between)

Draft values: ecosystem=`pypi`, approx_dep_count=`8`, has_lockfile=`false`  
Draft sentence: Not archived; default-branch last commit 2021-10-12; 8 deps across 2 manifests RepoVitals reads; no lockfile RepoVitals reads.

- Repo: https://github.com/dropbox/pyannotate · commit read: [a7a46f394f](https://github.com/dropbox/pyannotate/tree/a7a46f394f0ba91a1b5fbf657e2393af542969ae) · [commits on default branch](https://github.com/dropbox/pyannotate/commits/master)
- Manifests read (2 of 2 in tree), dependency count per file:
  - [ ] [requirements.txt](https://github.com/dropbox/pyannotate/blob/a7a46f394f0ba91a1b5fbf657e2393af542969ae/requirements.txt): 5
  - [ ] [setup.py](https://github.com/dropbox/pyannotate/blob/a7a46f394f0ba91a1b5fbf657e2393af542969ae/setup.py): 3

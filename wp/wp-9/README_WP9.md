# WP-9: check the AI judge by labelling 50 items

> **Version 2 (10 Oct 2026).** Version 1 of the packet left out part of each item's measured data. If you labelled version 1, **start again from a blank workbook**, and don't copy or look at your old labels.

**Start here.** Everything you need is in this folder. You don't need the codebase, the internet or anyone's help, and you mustn't use them.

| | |
|---|---|
| **Who** | One team member, working alone. |
| **Time** | One sitting of about 3–4 hours, so roughly 4–5 minutes an item. |
| **What you produce** | 50 labels, one per item, with a one-line note on every label that isn't `faithful`. |
| **What you return** | The filled workbook (`wp9_labelling_workbook.xlsx`), or the filled CSV. Send it to Spandan privately. **Do not upload it to GitHub.** |

## Files in this folder

| File | What it is | What you do with it |
|---|---|---|
| `README_WP9.md` | This guide: rules, the rubric and worked examples. | Read it fully before you start. |
| `wp9_labelling_workbook.xlsx` | The workbook. `Labels` is where you record answers, with a dropdown and automatic checks. `Items` holds all 50 items. `Progress` tells you when you're done. | **Fill in the `Labels` sheet** (the yellow cells only). |
| `judge_validation_packet.md` | The same 50 items as the `Items` sheet, formatted for easier reading. | Read the items here or in `Items`, whichever you prefer. |
| `wp9_judge_labels_template.csv` | The same answer sheet as a plain CSV (`item_id,label,note`). | Use it **only if you can't use Excel**. Otherwise ignore it. |

## Why this task exists (2 minutes)

RepoVitals asked an AI model to write 450 dependency-fix recommendations. A second AI model, "the judge", then checked each one for **faithfulness**: is every claim actually backed by the evidence the writer was shown?

Nobody trusts an AI judge on its word. Your blind labels on 50 of those recommendations are compared with the judge's labels, and the agreement score (Cohen's kappa) is what lets the research paper rely on the judge's other 400 verdicts. **Your independent judgement is the whole point.** That's why the rules below matter.

## The rules (non-negotiable)

1. **Label blind.** You must not see the judge's answers. They are not in these files.
   - Do not open `judge_validation_key.json` or `judge_cache.jsonl`, wherever you come across them.
   - Do not ask anyone what the judge said.
2. **Work alone, and don't discuss items** with anyone until you've returned all 50.
3. **Use only what the item shows.** That means its measured data and its source passages.
   - Not your own knowledge.
   - Not the internet, the package's website or GitHub.
   - **No ChatGPT, Gemini, Claude or any other AI tool.** You are checking an AI, so an AI can't help.
4. **Label every item.** No skipping, no "not sure". Pick the best-fitting label and explain in the note.
5. **One sitting if you can.** If you must stop, stop between items, never mid-item.

## What each item shows you

Every item, in the `Items` sheet or the packet, has four parts:

| Part | What it is | Is it evidence? |
|---|---|---|
| **Dependency** | Package name, ecosystem (npm or pypi) and the version the project uses. | Yes. |
| **Measured data** | Everything a scanner recorded about the dependency, as a list. Every line counts as evidence. | **Yes.** |
| **Remediation to label** | The AI's recommendation: a short text plus a table (Package / Fix / Target version / Replacement). | No. **This is what you are checking.** |
| **Source passages** | The text snippets (changelogs, READMEs) the AI was shown before writing. Some items show **none**: the AI was given only the measured data. | **Yes.** |

**What the measured data lists:**

| Line | Meaning |
|---|---|
| Version in use / Declared specifier / Where that version came from | The version the project uses, how its manifest declares it (`==4.39.2`, `^3.0.0`), and whether it was pinned, read from a lockfile, or approximated from a range |
| Manifest / Dependency group | The file that declares it, and whether it's a runtime or development dependency |
| Latest release on the registry / Versions behind the latest release | The newest version the package registry lists, and how far behind it the version in use is |
| Days since the package's latest release | How long ago the package last published anything (its staleness) |
| Deprecated on the registry / Registry deprecation message | Whether the registry marks the package deprecated, and its message (which sometimes names a replacement) |
| Advisories affecting this version (scanner's count) | How many advisory records affect the version in use. The same CVE can appear under two ids, so this is often larger than the list below |
| Highest advisory severity / Why it was flagged | The worst severity, and the reasons RepoVitals flagged it (vulnerable, deprecated, stale) |
| Advisories in detail (highest CVSS first) | Up to five advisories, each with its ids (CVE / GHSA / PYSEC), severity, CVSS score and "fixed in" version. "fixed in unknown" means no fixed version was recorded |

A claim is supported if **any** line of the measured data, or a passage, states it or directly entails it. Read the whole list before deciding a claim is unsupported.

**Evidence = the measured data + the source passages, and nothing else.**
- An item with no passages can still be fully `faithful`, if every claim is backed by the measured data.
- A passage that's irrelevant (say, a README full of badges) simply supports nothing. It doesn't count against the remediation, and it doesn't count for it.

## The three labels

| Label | Use it when | Note required? |
|---|---|---|
| `faithful` | **Every** material claim is stated by, or directly follows from, the measured data or passages shown. Saying "there isn't enough information to recommend X" is faithful when the evidence really is thin. | No |
| `minor_unsupported` | **At most one** peripheral claim is unsupported, and the core recommendation is supported. | **Yes:** name the unsupported claim. |
| `major_unsupported` | A **core** claim is not in what was shown: the recommended version, the replacement package, or an assertion that something breaks. | **Yes:** name the unsupported core claim. |

Spell the labels exactly as above, all lowercase with underscores. The workbook's dropdown does this for you.

### Core or peripheral?

| Core: if unsupported, the label is `major_unsupported` | Peripheral: one unsupported means `minor_unsupported` at most |
|---|---|
| The recommended **target version** (also in the table's "Target version" column) | Background remarks ("this is a widely used library") |
| The **replacement package** (the table's "Replacement" column) | Extra benefits ("also faster", "improves typing") |
| Any claim that something **breaks**, or is a breaking change | Restating a measured fact (that's supported if it matches the measured data) |
| | Side advice ("run your tests afterwards") |

Version numbers, package names and migration steps all count as claims, wherever they appear: in the text or in the table.

## How to label one item, step by step

1. **Read the whole measured data list and the passages first,** so you know what evidence exists.
2. **Read the remediation, text and table, and list its claims** in your head or on paper: each version, each package name, each "X fixes Y", each "X breaks Y", each migration step.
3. **For each claim, ask: is it stated in, or directly entailed by, the measured data or passages?**
   - Being *true* isn't enough. It has to be *in what was shown*.
4. **Decide whether each unsupported claim is core or peripheral** (table above).
5. **Pick the label:**
   - nothing unsupported → `faithful`;
   - one unsupported peripheral claim, and the core is fine → `minor_unsupported`;
   - any unsupported core claim → `major_unsupported`.
6. **Write the note** for anything that isn't `faithful`. Quote or name the offending claim in one line, for example: `Target version 3.2.0 is not in the measured data or passages`.

## Worked examples

These are invented, and none is one of your 50 items. They show how the rules apply.

**Example 1: `faithful` (no passages, measured data only)**
- **Measured data:** "CVE-2023-1111 (high, fixed in 2.4.1)". **Passages:** none.
- **Remediation:** "Version 2.0.0 is affected by CVE-2023-1111. Upgrade to 2.4.1, which fixes it." Table: upgrade → 2.4.1.
- **Label:** `faithful`. Every claim (the CVE, that it's fixed in 2.4.1, the target 2.4.1) is in the measured data.

**Example 2: `major_unsupported` (replacement package not shown)**
- **Measured data:** deprecation message "This package is no longer maintained." **Passages:** nothing mentions axios.
- **Remediation:** "Migrate to axios." Table: Replacement = axios.
- **Label:** `major_unsupported`. **Note:** `Replacement package axios is not in the measured data or passages.`
- This holds even if you personally know axios would be a good choice.

**Example 3: `minor_unsupported` (one peripheral extra)**
- **Measured data:** "fixed in 4.17.21". **Passage:** "4.17.21: fixes prototype pollution".
- **Remediation:** "Upgrade to 4.17.21, which fixes the prototype-pollution issue; this release also improves performance."
- **Label:** `minor_unsupported`. **Note:** `'Improves performance' is not in the evidence; the upgrade to 4.17.21 is supported.`

**Example 4: `faithful` (honest about thin evidence)**
- **Measured data:** deprecation message "Deprecated." **Passages:** a README with badges only.
- **Remediation:** "The package is deprecated, but the information shown does not name a successor, so no specific replacement can be recommended."
- **Label:** `faithful`. Saying "not enough information" when that's true is the intended behaviour.

**Example 5: `faithful` (replacement named in the deprecation message)**
- **Measured data:** deprecation message "This project has been renamed to new-pkg."
- **Remediation:** "Replace old-pkg with new-pkg." Table: Replacement = new-pkg.
- **Label:** `faithful`. The facts name the replacement.

**Example 6: `major_unsupported` (a breaking-change claim nothing supports)**
- **Measured data:** "fixed in 3.0.0". **Passages:** a changelog entry listing bug fixes, with no mention of breaking changes.
- **Remediation:** "Upgrade to 3.0.0. Note: 3.0.0 removes the legacy config API, so your config will break."
- **Label:** `major_unsupported`. **Note:** `Breaking-change claim (legacy config API removed) is not in the evidence.`

## Hard cases

**"I know the claim is true, but it's not in the evidence."**
Then it's unsupported. Only what was shown counts.

**"Two or more peripheral claims are unsupported, but the core is fine."**
The rubric doesn't spell this case out. Choose the label you think fits best, and start your note with `Several peripheral claims unsupported:`, then list them.

**"I can't tell whether a claim is core or peripheral."**
Use the table above. If you're still unsure, decide, and say why in the note.

**"The passages are about something unrelated."**
Ignore them. Judge the remediation against the measured data alone.

**"The text and the table disagree"** (for example the text says 1.22 and the table says 1.23).
Both are claims. Check each one.

**"Formatting looks broken"** (markdown symbols, odd characters).
Ignore the formatting. Judge the content.

## Recording your answers

**Preferred: the workbook.**
1. Open `wp9_labelling_workbook.xlsx` and go to the **`Labels`** sheet.
2. For each item, choose the label from the dropdown in column **C** (yellow).
3. Type the note in column **D** (yellow). It's required unless the label is `faithful`.
4. Column **E** checks each row: `to do`, then `note needed` (shown in red) until it's complete, then `ok` (green).
5. The **`Progress`** sheet counts everything and shows **READY TO RETURN** when all 50 are labelled and every non-faithful label has its note.
6. Edit nothing except columns C and D on `Labels`.

**Only if you can't use Excel: the CSV.** Fill `wp9_judge_labels_template.csv` in any text editor.
- One line per item: `ITEM-001,faithful,`.
- If a note contains a comma, wrap the note in double quotes: `ITEM-002,minor_unsupported,"Claim X, Y not shown"`.
- Keep the header line `item_id,label,note`, and don't add or remove rows.

## Before you return it

- [ ] All 50 items are labelled, and `Progress` says **READY TO RETURN**.
- [ ] Only `faithful`, `minor_unsupported` and `major_unsupported` are used.
- [ ] Every non-faithful label has a one-line note naming the claim.
- [ ] You used no outside knowledge, no internet and no AI tools.
- [ ] You haven't seen any of the judge's verdicts.

Then send the file to **Spandan, privately** (not to GitHub, and not to a group chat). Say the date you labelled and how long it took.

## What happens next (not your job)

Spandan compares your labels with the judge's hidden labels and computes Cohen's kappa.
- If agreement is good, the judge's other verdicts are trusted in the paper.
- If it's poor, that's a finding about the **rubric**, not about you. The rubric gets tightened, and in the worst case a fresh 50 are labelled.

---

### For Spandan, when the file comes back

From `backend/`, with `DATABASE_URL` set as in `../wp-8/README.md`:

1. **If the workbook came back,** convert its `Labels` sheet to the CSV the kappa step reads. Use any Python that has `openpyxl`:
   ```
   python -c "import csv,openpyxl; ws=openpyxl.load_workbook('../wp/wp-9/wp9_labelling_workbook.xlsx',data_only=True)['Labels']; w=csv.writer(open('../wp/wp-9/wp9_judge_labels.csv','w',newline='',encoding='utf-8')); w.writerow(['item_id','label','note']); [w.writerow([r[0], (r[2] or '').strip().lower(), (r[3] or '').strip()]) for r in ws.iter_rows(min_row=2,values_only=True) if r[0]]"
   ```
2. **Compute kappa:**
   ```
   python manage.py judge_validation_kappa --labels ../wp/wp-9/wp9_judge_labels.csv --key ../research_data/runs/judge_validation/judge_validation_key.json
   ```
   It refuses a sheet with a blank or misspelt label and names the row. It writes `judge_validation_kappa.md` beside the key.
3. **Commit three things:**
   - the labels;
   - the kappa report, copied into `wp/wp-9/`;
   - `research_data/runs/judge_cache.jsonl`, copied into `wp/wp-8/runs/`.

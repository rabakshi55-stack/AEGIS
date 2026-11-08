# Latest patch — Uploaded-data access in natural Copilot

Fixed evidence-source selection after uploading data, grounded field-mapping suggestions from actual column names, source-scoped Qwen follow-ups, and fallback when Qwen falsely denies file access. The automated suite is now 183/183. Direct Windows Qwen inference remains to be tested by the user. See `COPILOT_UPLOADED_DATA_FIX.md`.

---

# AEGIS — Copilot conversation upgrade (7 November 2026)

This version adds an optional *general* local-Qwen conversation context, per-source trusted in-memory session continuity, visible opt-in natural-mode control, and a New chat reset control. An honest general fallback is used when no local model is installed. Company-specific answers remain checked against AEGIS evidence and never become operational directives.

**New verification:** 163/163 Python automated tests passed, including 8 new session, safety and general-chat tests. Integrated localhost HTTP smoke test passed; static Chromium UI interaction check passed with zero script errors. Protected source archive remained 418/418 unchanged. Live Ollama Qwen inference is UNVERIFIED because Ollama was not available in the build environment. See `DECISION_COPILOT_FINALIZATION.md`.

---

# AEGIS — Consolidated research release (7 November 2026)

## What was actually changed

1. Consolidated the latest supplied **Copilot evidence-routing** code and its source-derived synthetic monthly optimizer with the previously built, simplified **Data → Visualizations → Decision Copilot** manager interface. The earlier manager build did **not** include the newer `joint_copilot.py`; the updated release does.
2. Preserved the original research bundle and model evidence, plus all available original Olist and synthetic experiment inputs and notebooks. Source-data bytes in this release were copied without modification; `VERIFY_PACKAGE.py` independently checks them against its generated SHA-256 manifest.
3. Kept CSV and Excel upload workflows, descriptive completeness, category/distribution, timeline and mapped-date charts, plus recorded-source review priorities.
4. Added the prior reviewed explicit read-only **single selected SQLite table** import, connected to those visualizations and grounded data-review suggestions. It does *not* connect to a production ERP.
5. Kept the analyst-only bounded exact daily multi-resource feasibility research prototype. It enforces constraints on declared JSON input, but it does *not* automatically interpret arbitrary uploads or certify real capacity.
6. Corrected the Decision Copilot's previously repeated synthetic answer. It now answers supplier-switch questions with a **specific verification checklist**, grounded in the monthly solver's checked result, while still withholding actual business execution. Added regression coverage for follow-up questions and source isolation.
7. Removed only clearly unnecessary distribution clutter: pre-patch application backup, redundant patch-installer folder, repeated intermediary consolidated-validation 001/002, `.pyc` caches, and Windows desktop.ini. Retained consolidated 003, step 200/204/205 audit artifacts, step 191 paired stress, notebooks, original source inputs and the frozen bundle.
8. Placed the application directly under `AEGIS/AEGIS_App`, the archived synthetic source data under `AEGIS/Research/Integrated_v02`, and one-click scripts at `AEGIS/` to avoid deeply nested installation paths. Existing historical version strings in research filenames are retained for provenance; the application is named **AEGIS**.

## Checks performed on this package

| Check | Result |
|---|---|
| Application Python automated unit tests | **128/128 pass** |
| Archived validation foundation | **34/34 software checks pass**, research-only |
| Node parsing `web/app.js` | Pass |
| Local HTTP GET status / model evidence / joint synthetic solver | Pass |
| Local HTTP upload + mapping + charts + data review suggestions | Pass (6-row synthetic example) |
| Local HTTP Copilot topic routing + distinct supplier-switch follow-up | Pass |
| Cross-source business action request | Blocked |
| Foreign origin HTTP submission | HTTP 403 |
| Synthetic Step 191 paired stress reproducibility | 500 shared shocks, 40,000 paired exposure rows; baseline pair summary and paired exposures byte-identical with archived experiment when seed 191 used |
| Static headless Chromium rendering with stubbed local API | Three navigation sections, chart counts, Copilot source selector, zero page script exceptions |
| Live headless Chromium navigation to local HTTP | **Blocked by sandbox administrator**; full Windows click-through still required |
| Local Ollama Qwen inference | Not exercised on this machine |

**Not a claim of real-world validation.** Passing software tests and synthetic experiments does not certify prediction accuracy, supplier feasibility in a live business, supplier-switch effects, security or actual savings.

## Synthetic reference results

For the archived **fictional** July 2025 CMP-007 monthly experiment: 16 whole orders, 13,900 units, baseline modeled landed cost $1,928,061.00; exact monthly modeled minimum $1,698,024.00; hypothetical difference $230,037.00. The experiment verifies only its declared synthetic monthly constraints. No real company should act on this amount.

## Important research model limitation

The historical Olist validation cohort ROC-AUC was approximately **0.558705**, with observed late rate 12.83% and mean frozen score 5.62%, indicating weak and miscalibrated performance in that period. The historical test set has been inspected repeatedly and is **not a pristine prospective holdout**. This release did not retrain or re-certify that model.

## Advanced software-check update (7 November 2026)

See `ADVANCED_RESEARCH_FIXES.md` for the five newly implemented software safeguards, 500 fictional paired daily shock outcomes, and the unchanged external evidence limitations. The archived Step 191 test and original Olist records remain unmodified. The previous 103-test suite has been extended to **128/128**. The optional local Qwen model still requires on-device acceptance testing.

## Broader algorithm comparison (7 November 2026)

- 38 relevant classification configurations benchmarked on the same 2017 train / January 2018 selection population, **including four exact full-data kernel SVM configurations and three linear SVM configurations**; see `MODEL_BENCHMARK_OUTCOME.md`.
- The existing frozen L2 Logistic Regression research challenger remains highest by the predeclared January Average Precision rule, but close alternatives have overlapping descriptive uncertainty intervals. No operational model was replaced.
- Added read-only research model ranking and separately acknowledged frozen shadow-scoring endpoints, grounded Copilot model-comparison answers, and a collapsed Visualization model-evidence section. No added enterprise actions.
- Model selection remains retrospective, source feature as-of availability unproven, scores uncalibrated for live operations. Not a certified improvement over the archived 0.5587 study.

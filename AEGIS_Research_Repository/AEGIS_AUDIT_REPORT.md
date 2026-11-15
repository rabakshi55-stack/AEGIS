# AEGIS — comprehensive reliability audit

This is a cumulative release, based on the Streamlit AI Edition and prior verified analytics update. It retains the archived research, predictive-model limitations and recommend-only policy. Neither real-world predictive reliability nor actual financial savings are certified.

## Changes
- Consistent, bounded numeric conversion and ISO calendar-date validation across query and chart engines; malformed numbers are not silently treated as zero, and invalid date pairs remain excluded only from relevant delivery calculations.
- Independent verification of unambiguous scalar counts/aggregates; inconsistent model SQL/prose cannot replace the independently computed result. Grouped calculations preserve missing groups and distinguish missing measures from zero. Ranked outer queries expand ties; unsupported nested limits and row-number shortcuts are rejected, and duplicate result aliases are rejected.
- Focused questions are separated from broad dataset overviews. Checked supplier/region/item cohorts retain all valid financial records independently of delivery eligibility, do not infer currencies, and avoid overconfident recommendations. Scoped questions that do not fit verified tools remain model-planned or require clarification.
- Provider failures preserve a clearly labeled standard-analytics response or checked evidence where available. Prior structured-plan retry/recovery remains. Hosted model output and generated SQL are untrusted; read-only constraints remain in force.
- Mapping changes advance dataset revision. Online chart edits advance chart revision; stale chart selections, in-flight hosted results and previous-dataset recommendations are rejected. Session state is invalidated on the new deployment.
- Online chat retains safe Markdown and collapsible calculation evidence. Portable chat uses safe text nodes for basic bold formatting and collapsible calculated evidence. Portable standard/local model paths share the checked cohort/focused calculation engine and hosted outage recovery.
- Research evidence > AEGIS reliability self-check uses a separate fictional dataset, tests core calculations without provider calls, and optionally checks one live AI ranking with explicit hosted consent. It does not inspect or alter the user's active dataset.

## Verification performed in build environment
- Online shared application: 296 automated tests passed.
- Online cloud adapter: 76 automated tests passed.
- Portable application: 299 automated tests passed.
- New regression coverage: 10 shared audit tests + 4 cloud tests, included above.
- Portable original source: 418/418 hash checks unchanged. Online original Research files are hash-compared with the original Streamlit AI Edition archive.
- Node syntax validation for portable web/app.js passed. Python source syntax is checked by compilation.
- Windows CHECK_AEGIS.bat keeps offline test mode, UTF-8, private Python runtime and integrity checks.

## Remaining limits / acceptance checks
No live Groq credential was available for independent provider tests; tests use simulated provider replies. Streamlit was not available in the build environment, so the deployed UI needs acceptance checking. Windows bootstrap and live Ollama/Qwen need on-device acceptance. No finite suite establishes correctness for every novel question, arbitrary AI-generated SQL or dataset; complex semantic analysis, units, causal inference, forecasting, real supplier decisions and data provenance still require verification. Public service quotas and outages remain external constraints. Offline self-check is not a certification of AI reasoning.

## Deployment
Online: extract and copy the CONTENTS of AEGIS_Research_Repository into the existing repository folder of that name. Review changes, commit and push once; reboot Streamlit to clear old runtime objects. Keep existing GROQ_API_KEY secret; never commit it. Run Research evidence > AEGIS reliability self-check. Optional live check requires hosted consent and only sends fictional evidence.
Portable: extract into a fresh folder, run CHECK_AEGIS.bat, then START_AEGIS.bat. The first launch may download the private Python runtime. Hosted AI uses your own key via the existing secure local launcher; local Qwen remains optional. Never bundle credentials. Use non-sensitive data for hosted inference.

# AEGIS — Analytical semantics and conversation reliability

This cumulative online-edition patch supersedes the earlier Combined AI Reliability,
Focused Analysis, and Hosted Plan Recovery patches. Apply it to the existing
`AEGIS_Research_Repository` directory (not the parent `.git` directory). It does
not replace research data or change the underlying predictive research models.

## What changed

- A reusable checked cohort-analysis tool, available for suppliers, regions and
  items, maintains separate eligibility for recorded order/row totals, numeric
  quantities, valid quantity × unit-cost products and comparable delivery dates.
  Unique order counts require complete, unique order identifiers; otherwise the
  output explicitly says source rows. Blanks/invalid dates are not classified
  as on-time. Incomplete financial metrics show valid-row coverage. Mixed or
  ambiguous currencies are not summed. No currency is inferred from bare numbers.
- Explicit field mappings take priority; unambiguous header matches can support
  provisional profiles without changing the stored mapping. Ambiguity is not
  resolved by guessing. Filtered, time-scoped and advanced requests remain in
  the AI query planner rather than receiving an unrelated full-source comparison.
- GPT-OSS can select the new checked cohort tools dynamically. When a checked
  cohort is selected, AEGIS renders its independent results and conservative
  review guidance as the authoritative response instead of exposing speculative
  model prose. Other questions retain the existing model-driven SQL/chart loop.
- The latest user question is explicit in the model conversation; follow-ups
  requesting transaction precautions after a checked comparison use the current
  dataset and answer the action question directly. A dataset or mapping change
  clears the conversation's cohort context.
- The general SQL-answer path has an additional conservative screen for common
  unsupported currency labels and overconfident reliability/sourcing claims;
  if flagged, interpretation is withheld, with exact calculations retained.
  This is a limited safeguard, not universal semantic verification.
- Chat answers render Markdown (HTML disabled); raw calculated SQL evidence is
  separately available in an expander. External image syntax is suppressed.
  Session version changes prevent reuse of pre-update workspace instances.
- Previous tie-aware ranking, trend, focused analysis, plan recovery and
  read-only safety checks are retained.

## Expected fictional-example results

| Supplier | Total orders | Comparable dates | Late | Ordered quantity | Quantity × unit cost |
|---|---:|---:|---:|---:|---:|
| Alpha | 2 | 2 | 0 | 20 | 492 |
| Beta | 2 | 2 | 1 | 34 | 728 |
| Gamma | 2 | 1 | 1 | 19 | 473 |

Gamma has the highest observed late rate (one of one), but one of its two rows
lacks a comparable actual/promised date pair. Its purchase metrics include both
rows. There is no basis for claiming a systematic problem, a known currency,
measured delay loss, or a need to suspend Gamma. Beta has the largest recorded
purchase exposure; verify actual consequences before assigning priority.

## Install and test

1. Extract the update. Copy all items into the existing local
   `Documents/GitHub/AEGIS/AEGIS_Research_Repository` folder, replacing matching
   files. Keep `.git` and Streamlit Secrets untouched.
2. Commit: `AEGIS AI - Verified Analytics and Conversation Reliability`.
3. Push origin; reboot the existing Streamlit application to load the update.
4. Reload the fictional sample, enable hosted AI with consent, and ask the
   supplier comparison question. Follow with: `What should be avoided from the
   next transaction?` Verify the figures above and direct action guidance.
5. Repeat in Standard analytics. Test a filtered query, an unrelated general
   question, and a new dataset. Confirm fallback or checked-cohort labels are
   not misrepresented as an unrestricted hosted answer.

Offline checks use `AEGIS_OFFLINE_TEST_MODE=1`, `PYTHONUTF8=1` and:

```
python -m unittest discover -s AEGIS_App/tests -q
python -m unittest discover -s cloud_tests -q
```

The patch is for the Streamlit edition. It does not rebuild the Windows package.
No API key is included. Live Groq responses and actual deployed Markdown rendering
require acceptance testing on the live app. Arbitrary SQL can still have
semantic errors despite read-only validation; broader questions require human
review and further verification. No operational procurement is authorized.

# AEGIS — Additional final-release integrity audit

Baseline: AEGIS_Final_Online.zip and AEGIS_Final_Windows.zip, reopened and extracted. This release contains every prior correction. No changes to research models, datasets, archived notebook outputs or protected research files.

## Reproduced and corrected defects

- Nonblank and distinct-count custom charts previously omitted observed groups with no populated Y values. Such observed groups now correctly have a count of zero. Numeric sum/average with no valid values still do not become zero. The existing test expecting omitted groups was changed to check the corrected behavior.
- Pie/donut charts previously accepted averages, extrema, medians and distinct counts as shares. The shared builder now permits only additive counts/sums and the existing nonnegative/positive-total safeguards. This is conservative: it rejects even a distinct-count pie where groups might happen to be disjoint.
- Ordinary chart recommendations could silently replace an on-time rate, mean delay or lead time with an after-date ratio, or total purchase cost with a sum of unit costs. They now identify unsupported derived measures explicitly, and use an unambiguous recorded total field when available. Existing validated expenditure/quantity vs late-rate cohort scatter is retained.
- Time-scoped chart requests could be treated as whole-dataset requests. Common explicit month/year/range qualifiers now block an unfiltered chart; ordinary grouping by month remains available. The builder still does not implement arbitrary row filters.
- Distinct-count recommendations could turn into ordinary row counts, especially with a text field. Explicit distinct fields and group-by wording now produce a distinct-count configuration instead.
- Model-selected charts could swap the requested aggregation, grouping or measure while still passing structural checks. The shared Qwen recommendation validator and hosted planner now compare the proposed configuration with the deterministic plan when a specific objective is identifiable. Open-ended chart questions retain model flexibility. The first regression run exposed an over-strict guard on generic questions; this was refined and the original tests passed.
- Custom monetary aggregate charts and automatic recorded-amount trends could sum rows across different currencies. Monetary custom aggregations are now conservatively blocked when the recognized currency field is mixed/missing/ambiguous; automatic recorded-amount trends are suppressed in that case. No currency conversion is invented. This is not a general currency audit of arbitrary hosted SQL or unknown field semantics.
- The hosted SQL direct-text aggregation check could be bypassed by quoted column identifiers or DISTINCT in a function argument. Those direct cases now require the existing aegis_num conversion, which preserves invalid inputs as NULL. This does not constitute a full semantic validator for arbitrary SQL expressions.
- Streamlit workspace version advanced to invalidate old instances after deployment.

## Verification and scope

New regression module: AEGIS_App/tests/test_additional_integrity.py (10 tests). Full test suites were run in Linux with AEGIS_OFFLINE_TEST_MODE=1. The release includes the updated complete applications, not incremental patches. The original protected Windows source manifest is unchanged. Online and Windows shared fixes are byte-identical. The archive comparison found no removed baseline files and no unexpected source changes.

Offline tests verify calculations, source interfaces, simulated model responses and provider error paths. They do not prove live Groq availability, arbitrary AI reasoning correctness, full Streamlit rendering, Windows batch execution, clean-machine runtime setup or production certification. Streamlit is not installed in this environment; no Groq API credential was used. A limited set of chart intents is supported; unsupported objectives should be explained rather than substituted. The public demo remains subject to provider quota and hosting limits. Human approval remains required for decisions.

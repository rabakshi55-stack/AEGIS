# AEGIS — comprehensive relevant classifier benchmark (research-only)

**Study:** Olist retrospective late-delivery classification, 7 November 2026.  
**Scope:** Major suitable classical supervised classifier families + nonlinear/neural families; **not literally every ML algorithm**. Many algorithms solve different tasks (regression, clustering, reinforcement learning) and cannot be compared meaningfully on this binary classification target.

## Result

- **38 tested classifier configurations**: 17 previous broad candidates and 21 supplementary candidates; all were trained on 43,426 2017 orders with mature comparable outcomes and evaluated on the same 7,069 January 2018 orders.
- Feature set: 65 extended checkout **research candidates**, including some without independent as-of evidence. No post-delivery status, review score or actual delivered date was allowed as a model input. The outcome label is derived from retrospectively recorded delivery vs estimated date, not an independently certified contractual SLA.
- Primary selection: **Average Precision** in January 2018, with ROC-AUC as a tiebreak. This emphasizes ranking the rarer delayed deliveries. Random ranking corresponds approximately to the 5.7% January late rate, not a universal 0.5 AP benchmark.
- **Selected historical research model: L2 Logistic Regression** (average precision **0.145852**, ROC-AUC **0.690373**). L1 Logistic Regression: AP 0.145779 / AUC 0.692032; Elastic Net: AP 0.145723 / AUC 0.690256; balanced Linear SVM: AP 0.145340 / AUC 0.693405; MLP: AP 0.142801 / AUC 0.699121. Selection differences are small.
- Full-data nonlinear SVM trials: RBF C=0.5 AP **0.066886**, AUC **0.525253**; RBF C=2 AP **0.061788**, AUC **0.493961**; degree-2 polynomial AP 0.046959; sigmoid AP 0.064435. **SVM was evaluated, not omitted.**
- Additional algorithms included: L1/ElasticNet logistic, linear SVM, linear SGD hinge/modified Huber, ridge, KNN, Bernoulli/Complement/Gaussian Naive Bayes, linear/quadratic discriminant analysis, decision trees, random/extra/bagged forests, Gradient Boosting/Histogram GB, AdaBoost, LightGBM, XGBoost, CatBoost, MLP neural networks, approximate RBF Fourier and Nyström features. **All 38 numerical results are in the bundled JSON reports.**

## Historical stability and uncertainty

For the selected L2 Logistic Regression, **March 2018** (7,003 retrospectively comparable orders) had ROC-AUC **0.634753** and average precision **0.304187**; **April–July 2018** (25,799 comparable orders) had ROC-AUC **0.678720** and average precision **0.075016**. These are post-hoc descriptive diagnostics and cannot be used as fresh holdout evidence.

The February-fitted sigmoid model's April–July mean predicted late score was **0.219829** while observed late frequency was **0.039847**—a gap of **0.179982** (17.9982 percentage points). The candidate **does not meet operational calibration requirements**.

On January 2018, a descriptive stratified paired bootstrap (300 draws) estimated L2 AP minus balanced linear SVM AP at **0.000512** with a 95% interval of **[-0.005466, 0.005998]**, and L2 AP minus L1 AP at **0.000073**, interval **[-0.001004, 0.001172]**. Intervals cross zero and data have been repeatedly analyzed; differences are not proof of a superior generalizing algorithm.

## What was actually integrated

1. `AEGIS_App/benchmark_extended.py`: reproducible supplementary classical + support-vector comparison. `AEGIS_App/champion_diagnostics.py`: fixed-model temporal and descriptive paired uncertainty comparisons.
2. `AEGIS_App/model_registry.py`: reconciles source hashes and feature schema across both benchmark reports, ranks the configurations, verifies the already frozen L2 Logistic Regression JSON shadow artifact, and rejects unsupported automatic deployment.
3. `GET /api/model-selection`: local read-only report of top algorithms, 38 scores, and research-only status. A collapsed research-model explanation appears on the existing **Visualizations** page (no additional main navigation).
4. `POST /api/research-score`: an *explicitly acknowledged research-only* score for a complete and strictly timestamp-asserted 65-feature snapshot using the frozen JSON model. It rejects missing acknowledgement, invalid fields, outcome leakage, and unsupported actions. Its claimed timestamps are **not independent proof** of source availability. AEGIS does **not** auto-score uploaded company files or execute procurement.
5. Decision Copilot can answer questions about algorithm selection and SVM using the checked bundled results rather than making up a winner.

**No operational model has been replaced.** The previously frozen original Olist research scores and source files are unchanged. The winning L2 Logistic Regression model was already the frozen research challenger, so claiming a new algorithm improved accuracy would be false. Benchmarking is useful precisely because it prevents an unjustified replacement with a worse model.

## Reproduce (optional research dependencies)

Install the optional research libraries on a trusted local Python environment: `numpy`, `pandas`, `scikit-learn`, `xgboost`, `lightgbm`, `catboost`. The local AEGIS manager application itself does not require these libraries just to launch.

From `AEGIS/AEGIS_App`:

```shell
python benchmark_candidates.py --olist-dir ../Research/Public_Data/Olist_Raw/archive --output BENCHMARK_NEW.json
python benchmark_extended.py --olist-dir ../Research/Public_Data/Olist_Raw/archive --output BENCHMARK_SVM_NEW.json
python champion_diagnostics.py --olist-dir ../Research/Public_Data/Olist_Raw/archive --output DIAGNOSTICS_NEW.json
```

The stored release reports are `Research/Validation_Archive/Current_Validation_2026_11_07/BROAD_ALGORITHM_BENCHMARK.json`, `EXPANDED_BENCHMARK_REPORT.json`, and `CHAMPION_TEMPORAL_DIAGNOSTICS.json`. Do not overwrite the archived release reports when reproducing.

## Unresolved limitations

- Model-selection comparisons are post-hoc and later evaluation windows are not untouched. Repeated selection risks overfitting the selection period.
- Olist's current snapshot does not independently witness checkout inputs and estimated delivery commitments at decision time. Provenance and historical label semantics remain provisional.
- Historical ranking discrimination and February calibration do not certify future accuracy. **A genuinely new prospective, pre-registered scoring cohort with later independent outcome labels is required.**
- Supplier disruption, sourcing optimization, cost benefits and causal intervention effects remain separate research questions, not established by predicting deliveries.
- No real-world supplier, purchasing, or contract action is authorized. AEGIS remains a local research demonstration requiring human evaluation.

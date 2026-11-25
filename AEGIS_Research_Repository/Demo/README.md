# Fictional 120-order demonstration

Upload `AEGIS_Sample_Supply_Chain.csv`; map order ID, supplier, region, quantity, unit cost, order date, promised date and actual date. All rows use INR. `verify_sample.py` computes independent expected values with Python standard library; `EXPECTED_RESULTS.json` is its saved output.

| Supplier | Orders | Units | INR purchase value | Comparable | Late | Late rate | Mean signed days | Mean late-only days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Alpha | 30 | 1050 | 111458 | 30 | 6 | 20% | -0.4 | 1 |
| Beta | 30 | 1410 | 128396 | 30 | 18 | 60% | 1 | 2 |
| Gamma | 30 | 930 | 108062 | 24 | 18 | 75% | 2.25 | 3 |
| Delta | 30 | 1230 | 124352 | 30 | 12 | 40% | 0 | 1.5 |
| Overall | 120 | 4620 | 472268 | 114 | 54 | 47.368421% | 0.631579 | 2.111111 |

Suggested checks: compare all suppliers by volume, spend, late rate and both delay averages; create a supplier-level purchase-value versus late-rate scatter; ask whether Gamma should be removed immediately; ask what further information is needed for allocation. Gamma's six missing actual dates do not remove its orders from finance. Alpha has the lowest observed late rate, but the sample cannot establish future reliability, causal effects, comparable product mix or feasible allocation. Do not treat fictional values as business results.

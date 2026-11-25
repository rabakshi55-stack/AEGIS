# Actual offline sample test

Routing: OFFLINE_CHECKED_COHORT

Question: Compare all suppliers by total orders, ordered quantity, total purchase expenditure, late-delivery rate, average signed delivery delay and average delay among late deliveries. Rank the suppliers by delivery reliability.

**Supplier comparison — verified calculations**

Coverage: 120 source rows. Totals use all rows with the group recorded; delivery rates use only valid actual/promised calendar-date pairs. 0 rows with blank group values are excluded from the grouped table.

| Supplier | Orders | Comparable deliveries | Late rate | Mean signed delay (days) | Mean delay, late only (days) | Ordered units (valid rows) | Quantity × unit cost (valid rows) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Alpha | 30 | 30 | 6/30 (20.0%) | -0.40 | 1.00 | 1,050.00 (30) | 111,458.00 (30) |
| Beta | 30 | 30 | 18/30 (60.0%) | 1.00 | 2.00 | 1,410.00 (30) | 128,396.00 (30) |
| Delta | 30 | 30 | 12/30 (40.0%) | 0.00 | 1.50 | 1,230.00 (30) | 124,352.00 (30) |
| Gamma | 30 | 24 | 18/24 (75.0%) | 2.25 | 3.00 | 930.00 (30) | 108,062.00 (30) |
Mean signed delay = actual minus promised calendar days over comparable records (early values are negative). Late-only mean uses only late records; n/a means no late records.

Currency: recorded INR. Cost is the sum of valid quantity × unit-cost products, not observed financial loss from delay. Missing or invalid date pairs do not remove otherwise valid units or costs. Valid-row counts expose incomplete measures; partial sums are not complete totals.
**Highest observed late rate:** Gamma: 18/24 (75.0%) late, 6 of 30 orders without comparable dates.
The highest observed rate is based on limited or incomplete comparable deliveries; it is not evidence of a systematic reliability problem. Review the missing records and gather more observations before drawing a supplier-performance conclusion.
**Recorded purchase exposure:** Beta has the highest recorded quantity × unit-cost total (128,396.00, currency recorded INR). This is potential exposure, not measured delay loss.
**Management priority:** Review groups with recorded delays and high purchase exposure, reconcile incomplete delivery records, and verify delay causes and current commitments. Do not suspend or reallocate orders based on these descriptive figures alone.

Independent comparison: all four suppliers matched orders, comparable deliveries, late counts, quantity and cost; displayed mean signed and late-only delays agree with the reference. The reply identifies the highest late rate but does not explicitly sort every supplier by reliability; the answer key supplies the full order Alpha, Delta, Beta, Gamma. This is a source-level standard-engine check, not a live browser or GPT-OSS test.

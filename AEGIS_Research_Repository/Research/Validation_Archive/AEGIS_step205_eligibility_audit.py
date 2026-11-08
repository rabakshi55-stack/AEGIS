#!/usr/bin/env python3
"""AEGIS Step 205: read-only prediction-eligibility versus outcome-observability audit.

Reads the original Olist orders CSV; optionally reconciles with the frozen Step
204 report. Uses standard Python only. Does not train, predict, change original
files, access a network, or authorize business actions. Outputs aggregate
counts only. This is historical evidence, never prospective certification.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PHASES = {
    'TRAIN': (datetime(2017, 1, 1), datetime(2017, 10, 1), datetime(2018, 1, 1)),
    'VALIDATION': (datetime(2018, 1, 1), datetime(2018, 4, 1), datetime(2018, 6, 1)),
    'TEST': (datetime(2018, 6, 1), datetime(2018, 8, 1), None),
}
REQUIRED_FIELDS = {
    'order_id', 'customer_id', 'order_status', 'order_purchase_timestamp',
    'order_delivered_carrier_date', 'order_delivered_customer_date',
    'order_estimated_delivery_date',
}
OUTCOME_CATEGORIES = (
    'DELIVERED_COMPARABLE_STRICT',
    'DELIVERED_COMPARABLE_FLAGGED_CHRONOLOGY_OR_PROMISE',
    'DELIVERED_STATUS_MISSING_COMPARABLE_DATES',
    'CANCELED_WITHOUT_COMPARABLE_DELIVERY',
    'UNAVAILABLE_WITHOUT_COMPARABLE_DELIVERY',
    'OTHER_STATUS_WITHOUT_COMPARABLE_DELIVERY',
)


def parse_olist_datetime(value):
    if not value or not value.strip():
        return None
    try:
        result = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f'Unparseable timestamp: {value!r}') from exc
    if result.tzinfo is not None:
        raise ValueError('Timezone-aware timestamp detected: clock policy required')
    return result


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def phase_for(purchase):
    if purchase is None:
        return None
    for name, (start, end, _) in PHASES.items():
        if start <= purchase < end:
            return name
    return None


def counter_dict():
    return {
        'all_orders': 0,
        'purchase_calendar_eligible': 0,
        'recorded_promise_proxy_candidate': 0,
        'missing_or_invalid_recorded_promise': 0,
        'observed_comparable_outcome': 0,
        'unobserved_or_incomparable_outcome': 0,
        'strict_historical_label_candidate': 0,
        'historical_frozen_selected': 0,
        'recorded_delivery_at_or_after_phase_label_cutoff': 0,
        'observed_late_by_recorded_calendar_dates': 0,
        'strict_label_late_by_recorded_calendar_dates': 0,
        'final_status_delivery_timestamp_contradiction': 0,
        'category_counts': {k: 0 for k in OUTCOME_CATEGORIES},
    }


def analyze_rows(rows):
    totals = counter_dict()
    phases = {p: counter_dict() for p in PHASES}
    ids = set()
    anomalies = Counter()
    outside_windows = 0
    for rowno, r in enumerate(rows, start=1):
        order_id = r['order_id']
        if not order_id or order_id in ids:
            raise ValueError(f'Missing or duplicate order_id at data row {rowno}')
        ids.add(order_id)
        status = r['order_status'].strip().lower()
        purchase = parse_olist_datetime(r['order_purchase_timestamp'])
        estimate = parse_olist_datetime(r['order_estimated_delivery_date'])
        delivery = parse_olist_datetime(r['order_delivered_customer_date'])
        carrier = parse_olist_datetime(r['order_delivered_carrier_date'])
        phase = phase_for(purchase)
        if phase is None:
            outside_windows += 1

        # At-purchase eligibility may ONLY reference purchase-time data.
        # Here we can audit the purchase timestamp; the source does NOT prove
        # availability of promised dates or customer-state fields as-of purchase.
        calendar_eligible = purchase is not None
        recorded_promise_proxy = bool(purchase and estimate and estimate >= purchase)

        # Outcome and chronology checks MUST NOT flow into prediction eligibility.
        observed = status == 'delivered' and delivery is not None and estimate is not None
        carrier_before_purchase = bool(carrier and purchase and carrier < purchase)
        delivery_before_carrier = bool(delivery and carrier and delivery < carrier)
        delivery_before_purchase = bool(delivery and purchase and delivery < purchase)
        invalid_promise = bool(estimate and purchase and estimate < purchase)
        chronology_problem = carrier_before_purchase or delivery_before_carrier or delivery_before_purchase
        strict = observed and not chronology_problem and not invalid_promise
        cutoff = PHASES[phase][2] if phase else None
        beyond_cutoff = bool(strict and cutoff and delivery >= cutoff)
        frozen_selected = bool(phase and strict and not beyond_cutoff)
        late = bool(observed and delivery.date() > estimate.date())
        contradiction = status != 'delivered' and delivery is not None

        if carrier_before_purchase:
            anomalies['carrier_before_purchase'] += 1
        if delivery_before_carrier:
            anomalies['delivery_before_carrier'] += 1
        if delivery_before_purchase:
            anomalies['delivery_before_purchase'] += 1
        if invalid_promise:
            anomalies['estimated_before_purchase'] += 1
        if contradiction:
            anomalies['non_delivered_status_with_delivery_timestamp'] += 1

        if strict:
            category = 'DELIVERED_COMPARABLE_STRICT'
        elif observed:
            category = 'DELIVERED_COMPARABLE_FLAGGED_CHRONOLOGY_OR_PROMISE'
        elif status == 'delivered':
            category = 'DELIVERED_STATUS_MISSING_COMPARABLE_DATES'
        elif status == 'canceled':
            category = 'CANCELED_WITHOUT_COMPARABLE_DELIVERY'
        elif status == 'unavailable':
            category = 'UNAVAILABLE_WITHOUT_COMPARABLE_DELIVERY'
        else:
            category = 'OTHER_STATUS_WITHOUT_COMPARABLE_DELIVERY'

        for d in (totals, phases[phase] if phase else None):
            if d is None:
                continue
            d['all_orders'] += 1
            d['purchase_calendar_eligible'] += int(calendar_eligible)
            d['recorded_promise_proxy_candidate'] += int(recorded_promise_proxy)
            d['missing_or_invalid_recorded_promise'] += int(not recorded_promise_proxy)
            d['observed_comparable_outcome'] += int(observed)
            d['unobserved_or_incomparable_outcome'] += int(not observed)
            d['strict_historical_label_candidate'] += int(strict)
            d['historical_frozen_selected'] += int(frozen_selected)
            d['recorded_delivery_at_or_after_phase_label_cutoff'] += int(beyond_cutoff)
            d['observed_late_by_recorded_calendar_dates'] += int(late)
            d['strict_label_late_by_recorded_calendar_dates'] += int(late and strict)
            d['final_status_delivery_timestamp_contradiction'] += int(contradiction)
            d['category_counts'][category] += 1

    for name, d in [('ALL_SOURCE', totals), *phases.items()]:
        if sum(d['category_counts'].values()) != d['all_orders']:
            raise RuntimeError(f'Outcome categories fail population partition: {name}')
        if d['observed_comparable_outcome'] + d['unobserved_or_incomparable_outcome'] != d['all_orders']:
            raise RuntimeError(f'Comparable/uncomparable partition failed: {name}')
        if d['purchase_calendar_eligible'] + (d['all_orders'] - d['purchase_calendar_eligible']) != d['all_orders']:
            raise RuntimeError(f'Purchase eligibility population failed: {name}')
        if d['recorded_promise_proxy_candidate'] + d['missing_or_invalid_recorded_promise'] != d['all_orders']:
            raise RuntimeError(f'Recorded promise population failed: {name}')
        if d['observed_comparable_outcome'] != (d['category_counts']['DELIVERED_COMPARABLE_STRICT']
                    + d['category_counts']['DELIVERED_COMPARABLE_FLAGGED_CHRONOLOGY_OR_PROMISE']):
            raise RuntimeError(f'Comparable category partition failed: {name}')
        if d['historical_frozen_selected'] > d['strict_historical_label_candidate']:
            raise RuntimeError(f'Frozen cohort outside strict historical label cohort: {name}')
    if sum(d['all_orders'] for d in phases.values()) + outside_windows != totals['all_orders']:
        raise RuntimeError('Research date windows do not reconcile')
    if totals['historical_frozen_selected'] != sum(d['historical_frozen_selected'] for d in phases.values()):
        raise RuntimeError('Historical frozen selected count does not reconcile')
    return {
        'source_order_count': totals['all_orders'],
        'unique_order_count': len(ids),
        'outside_research_period_order_count': outside_windows,
        'full_original_population': totals,
        'research_phases': phases,
        'anomaly_evidence_counts': dict(sorted(anomalies.items())),
    }


def reconcile_step204(result, prior):
    source = result['full_original_population']
    prev = prior.get('all_source_orders', {})
    checks = {
        'source_registry': result['source_order_count'] == prior.get('source_order_count'),
        'purchase_timestamp_coverage': source['purchase_calendar_eligible'] == prev.get('calendar_purchase_candidates'),
        'recorded_promise_proxy': source['recorded_promise_proxy_candidate'] == prev.get('recorded_promise_candidates'),
        'observed_outcome_count': source['observed_comparable_outcome'] == prev.get('observed_delivery_outcome'),
        'strict_historical_candidate_count': source['strict_historical_label_candidate'] == prev.get('strict_historical_candidates'),
        'frozen_selected_count': source['historical_frozen_selected'] == prev.get('selected_frozen_rule'),
        'outside_research_windows': result['outside_research_period_order_count'] == prior.get('purchases_outside_three_research_windows'),
    }
    for name, fresh in result['research_phases'].items():
        old = prior.get('phases', {}).get(name, {})
        checks[f'{name.lower()}_purchase_population'] = fresh['all_orders'] == old.get('all_purchases')
        checks[f'{name.lower()}_observed_outcomes'] = fresh['observed_comparable_outcome'] == old.get('observed_delivery_outcome')
        checks[f'{name.lower()}_strict_candidate'] = fresh['strict_historical_label_candidate'] == old.get('strict_historical_candidates')
        checks[f'{name.lower()}_frozen_selected'] = fresh['historical_frozen_selected'] == old.get('selected_frozen_rule')
        checks[f'{name.lower()}_recorded_delivery_cutoff_proxy'] = fresh['recorded_delivery_at_or_after_phase_label_cutoff'] == old.get('labels_delivered_after_phase_cutoff')
    return {'checks': checks, 'passed': sum(checks.values()), 'total': len(checks), 'all_pass': all(checks.values())}


def fixture(oid, purchase, status='shipped', delivery='', estimate='2017-09-15 00:00:00', carrier=''):
    return {
        'order_id': oid, 'customer_id': 'c', 'order_status': status,
        'order_purchase_timestamp': purchase, 'order_delivered_carrier_date': carrier,
        'order_delivered_customer_date': delivery, 'order_estimated_delivery_date': estimate,
    }


def run_self_test():
    rows = [
        fixture('a', '2017-09-01 10:00:00', 'delivered', '2017-09-15 11:00:00'),
        fixture('b', '2017-09-02 10:00:00', 'delivered', '2017-09-16 10:00:00'),
        fixture('c', '2017-09-03 10:00:00', 'delivered', '2018-01-03 10:00:00'),
        fixture('d', '2017-09-04 10:00:00', 'canceled'),
        fixture('e', '2017-09-05 10:00:00', 'unavailable'),
        fixture('f', '2017-09-06 10:00:00', 'shipped'),
        fixture('g', '2017-09-07 10:00:00', 'delivered'),
        fixture('h', '2017-09-08 10:00:00', 'delivered', '2017-09-12 10:00:00', carrier='2017-09-01 00:00:00'),
        fixture('i', '2017-09-09 10:00:00', 'delivered', '2017-09-12 10:00:00', estimate='2017-09-01 00:00:00'),
        fixture('j', '2018-02-01 10:00:00', 'delivered', '2018-02-20 12:00:00', estimate='2018-02-18 00:00:00'),
        fixture('k', '2018-02-02 10:00:00', 'delivered', '2018-06-04 12:00:00', estimate='2018-06-10 00:00:00'),
        fixture('l', '2018-06-05 10:00:00', 'delivered', '2018-06-19 12:00:00', estimate='2018-06-20 00:00:00'),
        fixture('m', '2017-11-01 10:00:00', 'shipped'),
        fixture('n', '2018-06-06 10:00:00', 'processing', delivery='2018-06-20 12:00:00'),
    ]
    r = analyze_rows(rows)
    t = r['full_original_population']
    tr, va, te = [r['research_phases'][k] for k in ('TRAIN', 'VALIDATION', 'TEST')]
    changed = [dict(x) for x in rows]
    changed[3]['order_status'] = 'delivered'
    changed[3]['order_delivered_customer_date'] = '2017-09-18 10:00:00'
    after = analyze_rows(changed)
    checks = {
        'source_14_rows_reconciled': t['all_orders'] == 14 and r['unique_order_count'] == 14,
        'calendar_eligibility_does_not_require_delivery': t['purchase_calendar_eligible'] == 14,
        'outcome_mutation_does_not_change_prediction_eligibility': after['full_original_population']['purchase_calendar_eligible'] == t['purchase_calendar_eligible'],
        'outcome_mutation_does_change_label_availability': after['full_original_population']['observed_comparable_outcome'] == t['observed_comparable_outcome']+1,
        'three_terminal_and_pending_statuses_unlabeled': t['category_counts']['CANCELED_WITHOUT_COMPARABLE_DELIVERY'] == 1 and t['category_counts']['UNAVAILABLE_WITHOUT_COMPARABLE_DELIVERY'] == 1 and t['category_counts']['OTHER_STATUS_WITHOUT_COMPARABLE_DELIVERY'] == 3,
        'delivered_missing_timestamp_unlabeled': t['category_counts']['DELIVERED_STATUS_MISSING_COMPARABLE_DATES'] == 1,
        'strict_excludes_chronology_and_invalid_promise': t['category_counts']['DELIVERED_COMPARABLE_FLAGGED_CHRONOLOGY_OR_PROMISE'] == 2,
        'strict_delivered_count': t['category_counts']['DELIVERED_COMPARABLE_STRICT'] == 6,
        'train_count': tr['all_orders'] == 9,
        'validation_count': va['all_orders'] == 2,
        'test_count': te['all_orders'] == 2,
        'out_of_period_count': r['outside_research_period_order_count'] == 1,
        'train_cutoff_applied_to_labels_only': tr['recorded_delivery_at_or_after_phase_label_cutoff'] == 1 and tr['historical_frozen_selected'] == 2,
        'validation_cutoff_applied_to_labels_only': va['recorded_delivery_at_or_after_phase_label_cutoff'] == 1 and va['historical_frozen_selected'] == 1,
        'no_test_maturity_cutoff_certified': PHASES['TEST'][2] is None,
        'non_delivered_status_timestamp_contradiction_flagged': t['final_status_delivery_timestamp_contradiction'] == 1,
        'same_calendar_date_not_late': tr['observed_late_by_recorded_calendar_dates'] == 3,  # b,c,i (i invalid promise still counted under raw observed)
        'frozen_sample_selected_count': t['historical_frozen_selected'] == 4,
        'aggregate_category_partition': sum(t['category_counts'].values()) == 14,
    }
    print(json.dumps({'study': 'AEGIS_STEP_205_ELIGIBILITY_SELF_TEST', 'fixture': 'SOFTWARE_ONLY_NOT_OLIST',
                      'checks': checks, 'passed': sum(checks.values()), 'total': len(checks),
                      'all_pass': all(checks.values())}, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='Run fictional fixture checks; no Olist dataset needed')
    parser.add_argument('--orders', type=Path, help='Path to original Olist orders CSV')
    parser.add_argument('--baseline', type=Path, help='Step 204 selection report for strict-count and hash reconciliation')
    parser.add_argument('--report', type=Path, help='Output aggregate JSON report; refuses overwrite')
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return
    if not args.orders:
        parser.error('--orders is required except for --self-test')
    if not args.orders.is_file():
        parser.error(f'Original Olist file not found: {args.orders}')
    if not args.baseline:
        parser.error('--baseline is required for source and frozen-cohort reconciliation')
    if not args.baseline.is_file():
        parser.error(f'Baseline report not found: {args.baseline}')
    paths = [args.orders.resolve(), args.baseline.resolve()]
    if args.report:
        if args.report.resolve() in paths:
            raise ValueError('Report path cannot overwrite any input file')
        if args.report.exists():
            raise FileExistsError(f'Refusing to replace existing report: {args.report}')

    with args.baseline.open('r', encoding='utf-8') as f:
        prior = json.load(f)
    digest = sha256_file(args.orders)
    if prior.get('original_csv_sha256') != digest:
        raise RuntimeError('Step 204 source checksum mismatch; refusing to compare different source files')
    with args.orders.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f'Missing source columns: {sorted(missing)}')
        result = analyze_rows(reader)

    verification = reconcile_step204(result, prior)
    result.update({
        'study': 'AEGIS_STEP_205_PURCHASE_TIME_ELIGIBILITY_VS_OUTCOME_OBSERVABILITY',
        'status': 'RETROSPECTIVE_POPULATION_AUDITED_NOT_PROSPECTIVE',
        'original_csv_sha256': digest,
        'step204_reconciliation': verification,
        'prediction_eligibility_policy': {
            'calendar_only_eligible': 'Purchase timestamp valid; independent of final status, recorded delivery and outcome label',
            'recorded_promise_proxy': 'Historical estimated date is valid by the saved record; not independently verified as available and unchanged at purchase time',
            'customer_state': 'Not evaluated from orders CSV; as-of contract not independently verified',
            'full_step180_model_asof_certified': False,
            'full_model_eligible_order_count': None,
        },
        'evaluation_eligibility_policy': {
            'late_label': 'Recorded delivery calendar date later than recorded estimated delivery calendar date, only among delivered orders with comparable dates',
            'unobserved_canceled_unavailable': 'Separate outcomes; never automatically labeled on time or late',
            'chronology_anomalies': 'Separate flagged comparable records, excluded from strict historical label candidate',
            'train_validation_label_cutoff': 'Recorded delivery timestamp prior to cutoff is a historical proxy only, not evidence of event ingestion or label availability',
            'test_label_cutoff': 'NO_VERIFIED_AS_OF_CUTOFF',
            'prospective_outcome_availability_certified': False,
        },
        'known_limitations': [
            'Original Olist CSV is a retrospective snapshot, not a sequence of operational as-of snapshots',
            'Purchase-time availability and immutability of recorded promise and customer state unverified',
            'Delivery timestamp is not an independently verified source-system label-ingestion timestamp',
            'Final statuses do not establish the order status at purchase time or at a later operational cutoff',
            'Selection still has retrospective outcome-availability bias; scoring eligibility must not use delivery outcome',
            'Previous test cohort was inspected; it is not an independent pristine future holdout',
            'No model retraining, scoring, supplier causality, calibration, or business action performed',
        ],
        'operational_approval': 'NOT_GRANTED',
        'automatic_business_action': 'DISABLED',
        'original_data_modified': False,
    })
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')

    print('AEGIS STEP 205 — read-only eligibility and outcome-observability audit')
    print('Original orders:', result['source_order_count'])
    print('Purchase-calendar eligibility (status-independent):', result['full_original_population']['purchase_calendar_eligible'])
    print('Recorded-promise candidates (as-of UNVERIFIED):', result['full_original_population']['recorded_promise_proxy_candidate'])
    print('Historical strict-label candidates:', result['full_original_population']['strict_historical_label_candidate'])
    print('Final frozen cohort:', result['full_original_population']['historical_frozen_selected'])
    print('Outcome classes:')
    for key, count in result['full_original_population']['category_counts'].items():
        print(' ', key + ':', count)
    for phase, section in result['research_phases'].items():
        print(f' {phase}: purchases={section["all_orders"]}, clean_labels={section["strict_historical_label_candidate"]}, frozen_selected={section["historical_frozen_selected"]}, recorded_cutoff_proxy_excluded={section["recorded_delivery_at_or_after_phase_label_cutoff"]}')
    print(f'Step 204 reconciliation: {verification["passed"]}/{verification["total"]}, all_pass={str(verification["all_pass"]).lower()}')
    print('Full model purchase-time eligibility: NOT CERTIFIED')
    print('Prospective operational validity: NOT CERTIFIED')
    print('Business actions: DISABLED')
    print('STATUS:', result['status'] if verification['all_pass'] else 'RECONCILIATION_MISMATCH_STOP')
    if args.report:
        print('Aggregate report:', args.report)
    if not verification['all_pass']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()

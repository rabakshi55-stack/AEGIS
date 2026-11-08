# AEGIS: Evidence-Grounded Supply-Chain Decision Intelligence

Academic research project for Advanced Machine Learning for Business Transformation (GIM, Big Data Analytics). **Research-only**; not authorized for production procurement.

## What this repository contains

- Local Python/JavaScript manager-facing AEGIS application (source code and tests)
- Original research Jupyter notebooks and synthetic planning inputs
- Reproducible historical classification study and selected archived JSON reports
- Synthetic exact supplier assignment and shared-shock experiments
- Read-only data visualizations and a source-grounded Decision Copilot, optionally with local Ollama/Qwen

The repository deliberately **does not redistribute Olist raw CSV files**; obtain them from the official Kaggle source and observe CC BY-NC-SA 4.0 conditions. The full, independently verified Windows distribution is supplied separately to course reviewers where authorized.

## Academic paper

See `Paper/AEGIS_IEEE_Paper.pdf` in the submission materials. The paper reports the fixed 38-configuration historical benchmarking results, separately from fictional procurement experiments. Reported benefits are simulated, not realized.

## Data and reproduction

Read `REPRODUCE_AEGIS.md` before running anything. After downloading Olist, place the relevant original CSV files under `Research/Public_Data/Olist_Raw/archive/`.

The `AEGIS_App/data/aegis_bundle.json` is a preserved, frozen research artifact, not a live ERP connection. No real company system or private dataset is included. The source-only repository omits the original full-release package verification manifests; it must not be confused with an untouched verified installer.

## GitHub publication

This folder is a **local repository starter, not a published GitHub repository**. Before committing:

1. Review the entire source tree for credentials, secrets, sensitive data and external licenses.
2. Check license terms for **derived** research files and do not invent a blanket project license.
3. Keep the author's original notebooks and source data attribution intact.
4. Publish the approved repository using a GitHub account you control.
5. Paste the **actual** repository URL into the paper; do not leave a placeholder in a submitted reproducibility statement.
6. Document the actual Python and ML package versions used to rerun the benchmarks.

## Research boundaries

A test passing does not imply calibrated predictive accuracy, historical feature timestamp certification, real-world capacity feasibility, business value, or AI response faithfulness. Supplier actions are disabled.

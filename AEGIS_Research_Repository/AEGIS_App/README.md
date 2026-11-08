# AEGIS — Local Decision Intelligence App

A polished, standalone **local application** for your completed AEGIS research.

This is **not a hosted website or another Jupyter dashboard**. All application files and the Python server run on your own laptop at `127.0.0.1`. A browser-based window works without new dependencies; a native desktop window is also supported. There is no paid service or cloud deployment.

The design uses the supplied navy / cobalt / cyan interface references. Unlike a speculative supply-chain mockup, every research metric appears only after the original notebook exports its existing results. Nothing called *live*, *certified*, *supplier caused this delay*, or *approved recommendation* is invented.

AEGIS's brand mark and browser-tab icon use the exact `favicon.ico` supplied by the project owner, without alteration. The same icon is included for future desktop executable packaging.

## Run on Windows

### A. One-time research export

1. Extract the `AEGIS_App` folder **beside your latest saved AEGIS Jupyter notebook**. Do not replace the notebook.
2. Open that existing notebook. Its Step 189/190/short-ID variables must already be available in the running kernel.
3. Create one new code cell **at the end** and run:

   ```python
   %run -i "AEGIS_App/export_from_notebook.py"
   ```

4. Verify the output reports exactly:
   - 99,441 original Olist orders
   - 58,911 frozen historical research scores
   - 10 synthetic optimization scenarios
   - 6 synthetic sourcing policies
   - no model fitting and no business actions

   This creates `AEGIS_App/data/aegis_bundle.json` on **your own computer**. It does **not** download another dataset or retrain anything. It leaves the original notebook and Olist tables unchanged.

   If a required object is missing from memory after a kernel restart, AEGIS stops with a clear message. The uploaded `.ipynb` alone cannot reconstruct every model object from its saved output screenshots; you need the notebook's original working environment for this single export.

### B. Open AEGIS

1. Double-click **`launch_aegis.bat`** inside `AEGIS_App`.
2. A local browser tab should open at `http://127.0.0.1:8787`, or a native window if you've installed the optional desktop support below.
3. Leave the small Python console window open while using AEGIS. Close it with `Ctrl+C` when finished.

If the browser doesn't open automatically, enter `http://127.0.0.1:8787` manually.

**Want AEGIS in its own application window rather than a browser tab?** On Windows, optionally install the free [pywebview](https://pywebview.idepy.com/en/guide/installation) package once in the Python environment running AEGIS:

```bat
python -m pip install pywebview
```

Double-click `launch_aegis.bat` again. AEGIS will open in its own desktop window. This is optional, not a new dataset or AI model. Windows may also require the Microsoft Edge WebView2 Runtime.

**You do not need Jupyter open for future app sessions after this export.** The app reads the frozen file directly. If you intentionally update/export the underlying research, restart the AEGIS app to load the new snapshot.

## What you can do

| Section | Function | Evidence |
|---|---|---|
| Overview | Research counts, historical score distribution, evaluation splits | Real historical Olist research |
| Order Intelligence | Search, sort, inspect, copy original IDs | Real historical Olist research |
| Scenario Lab | Inspect optimization cost/reserve trade-offs | Synthetic 16-order experiment |
| Policy Research | Review original sourcing-policy evidence | Synthetic sourcing experiments |
| Decision Copilot | Contextual follow-up questions, local Qwen natural explanations when enabled, and independently attached original Olist delivery outcomes | Explicitly selected research source; source outcomes kept separate from predictions |
| Enterprise Connections | Read-only connector capability and schema-contract inspection | Connection metadata only; no company system is presumed |
| Data Workspace | Upload local CSV/XLSX files, inspect columns and blanks, choose field roles and ask limited descriptive questions | User-supplied session data; not independently validated |
| Data Readiness | Original audit of missing operational records | Existing data contract |
| Governance | Evidence boundaries, safety controls, limitations | Current research status |

### Conversational AEGIS and local Qwen

AEGIS now remembers recent questions **within each selected research context**, so follow-ups like *“Are you sure?”* and *“And how many were after?”* can refer to the previous topic. The Python evidence checks remain the factual source and do not trust any client-supplied previous answer. Without a local language model, replies are still limited to supported research questions, but conversational greetings and reactions no longer trigger blanket data-analysis refusals.

Casual conversational messages—such as *“bruh”*, *“hey”*, or *“why are you being so robotic?”*—now use a separate friendly-dialogue route. When local Qwen is enabled, that route talks naturally without sending research records or inventing business facts; when unavailable, a simple conversational fallback is used. Ordinary non-data chat is deliberately distinct from evidence-backed business analysis, which remains narrower than general-purpose ChatGPT.

For more natural explanations in plain English, run the free local [Ollama](https://ollama.com/) service with the `qwen3.5:4b` model installed on your own computer. In **Decision Copilot** choose the evidence area and explicitly enable **Natural conversation with local Qwen**. No account, API key, paid subscription, browser cloud service or Jupyter notebook is required. You can verify your local installation in a Windows Command Prompt:

```bat
ollama list
```

If the model is not listed, `ollama pull qwen3.5:4b` downloads it once; this requires an Internet connection and free local disk space. Start Ollama in the background before using the toggle. The computer needs sufficient RAM to run this model comfortably. When the model is stopped, slow, or proposes unsupported numbers, AEGIS falls back to its evidence-based response and shows a notice.

**Important privacy boundary:** Enabling the toggle sends the current checked answer, a small packet of local derived counts, the current question, and up to four previous **user questions** to Ollama running at `127.0.0.1`. It does **not** send whole uploaded source tables or prior assistant answers. A selected original research answer can contain an order reference/date; treat those, column names, and your typed questions as potentially sensitive too. Keep the toggle off for data that cannot be processed by a local LLM under your company's policy. The native model could still make a wording mistake: this is a research prototype and not a certified, general-purpose business intelligence engine.

For the *original historical and synthetic research* contexts, the same checkbox now enables conversational wording of grounded research answers. Original research predictions and scoring remain unchanged. Qwen never executes business actions and is not trusted to calculate new source findings.

## Historical delivery outcomes — separate from model research

**Why this is needed:** The frozen research export includes 99,441 original order references and 58,911 model research scores, but **not the customer-delivery timestamps**. AEGIS therefore cannot legitimately count deliveries before/after estimated dates from those scores alone.

You can now attach the actual original Olist order table **without going back to Jupyter**:

1. Open **Decision Copilot** and choose **Historical order research**.
2. In the right-hand panel, find **Historical Delivery Evidence** and select **Attach original Olist CSV**.
3. Select your existing Olist source file, usually named `olist_orders_dataset.csv`. It must have the original `order_id`, `order_status`, `order_purchase_timestamp`, `order_estimated_delivery_date` and `order_delivered_customer_date` columns.
4. AEGIS reconciles **every order ID** with the original frozen 99,441-order registry. It rejects incomplete, duplicate, or unrelated tables instead of silently comparing them.
5. Ask *“How many orders were delivered before their estimated delivery date?”* and follow up with *“And how many after?”* or *“Are you sure?”*

AEGIS will calculate a **day-level historical source comparison**: before, on, or after the **estimated delivery date**, counting only source-status-confirmed delivered orders with coherent dates. It reports missing, undelivered, contradictory-status and impossible-timestamp records separately instead of treating them as on time. The estimate is **not independently verified as a contractual customer promise**. These counts are not a prediction accuracy score or certified business KPI.

The attachment lives **in local session memory**, and you may detach it at any time. It never overwrites `data/aegis_bundle.json`, the original notebook, or your frozen model. The CSV remains your source file on your own computer; it is not bundled with the downloadable application. Maximum outcome-table upload size: 30 MB.

## Data Workspace — inspect your own business dataset

1. Open **Data Workspace** from the left sidebar.
2. Choose a **CSV** (`.csv`) or Excel **XLSX** (`.xlsx`) file. No Jupyter notebook is needed.
3. Review the detected column names, blank-cell counts, and first ten rows.
4. In **Tell AEGIS what each field means**, choose the source column for each available business role (order ID, dates, supplier, item, quantities, and so on). Leave unknown roles blank.
5. Click **Save field mapping**. You can inspect descriptive duplicate-order counts and date comparisons, but do not interpret them as independently validated business KPIs.
6. Use **Ask AEGIS about this dataset** for questions about the upload's size, columns, missingness, repeated IDs, or mapped recorded dates. Ask follow-up questions in the same conversation, and optionally enable local Qwen for more natural wording.
7. Click **Remove dataset from memory** when finished. Closing the AEGIS process also removes it.

**Limits:** 20 MB per file; up to 100,000 rows, 60 columns and 1,500,000 cells; UTF-8 or UTF-16 CSV; first visible Excel worksheet only. Rejected/oversized files are **not** silently sampled. Multi-sheet Excel files need separate imports. Formula cells without cached values are treated as blank; formulas are never executed. Excel cells explicitly formatted as dates are converted to ISO-style display values; unstyled numeric serials remain unconverted. For recorded-date comparisons, AEGIS understands unambiguous ISO-style `YYYY-MM-DD` timestamps only.

**Privacy/security:** This is a **single-user localhost research prototype**, not a hardened enterprise tenant or authenticated data lake. Uploaded records remain in Python process memory while AEGIS runs (the browser receives the first ten rows for preview) and are not written to disk by the intake module. Only on explicit opt-in are derived summaries and recent user questions sent to the localhost Ollama model; no cloud endpoint is contacted by the app. One new successful upload replaces the previous session upload. Load only data you have permission to use; do not load regulated/confidential company records until appropriate security review and organizational approval.

**What the upload does NOT do:** It does not train an AI model, connect to an ERP, compute an approved service-level KPI, prove decision-time information was available, identify responsible suppliers, optimize real allocations, or execute decisions. It does not modify `data/aegis_bundle.json` or any original notebook variables.

### Updating an existing Windows AEGIS install

If AEGIS is already running with your successful one-time notebook export, **do not delete or replace the `data` folder**. Close the AEGIS app first, then extract the updated download into a *separate* temporary location. Copy these changed files into your existing `AEGIS_Standalone_App\AEGIS_App` directory, choosing **Replace** when Windows asks:

For the **Steps 193–196 validation foundation update**, close AEGIS, unzip
`AEGIS_Validation_Foundation_Steps193_to196.zip` into a new temporary folder,
then open its `AEGIS_App` subfolder. Copy the files below into the identically
named places inside your **existing** `AEGIS_Standalone_App\AEGIS_App`
folder. If Windows asks about `README.md`, `VALIDATION_ROADMAP.md` or existing
Python files, choose **Replace the file in the destination**. Do not copy the
whole project over your current installation or delete the original app.

```text
AEGIS_App\historical_outcomes.py          (updated)
AEGIS_App\asof_validation.py             (updated)
AEGIS_App\prospective_validation.py      (new)
AEGIS_App\intervention_evidence.py       (new)
AEGIS_App\validation_suite.py            (new)
AEGIS_App\tests\test_app.py              (updated)
AEGIS_App\tests\test_historical_outcomes.py (updated)
AEGIS_App\tests\test_asof_validation.py  (updated)
AEGIS_App\tests\test_prospective_validation.py (new)
AEGIS_App\tests\test_intervention_evidence.py (new)
AEGIS_App\tests\test_validation_suite.py (new)
AEGIS_App\VALIDATION_ROADMAP.md
AEGIS_App\README.md
```

Keep your existing `AEGIS_App\data\aegis_bundle.json`, `export_from_notebook.py`,
`launch_aegis.bat`, original notebook, `paired_stress.py`, and
`web\favicon.ico` unchanged. There is **no re-export, retraining, or UI logo
change**. Restart with `launch_aegis.bat` afterwards; use `Ctrl+Shift+R` if a
browser tab has cached an old view.

## Mode 3 — Enterprise Connections (foundation)

The Enterprise Connections page is a working read-only integration foundation, **not an actual connection to SAP, Oracle or another company's system**.

- **Implemented:** Local SQLite connector that inspects the names of tables and columns without selecting business records. It compares them with the exact eight Step 182 canonical table contracts.
- **Not implemented:** ERP API authentication, SQL Server/PostgreSQL adapters, ERP-to-canonical data mapping, decision-time provenance verification, controlled live model inference, and operational authorization.
- **Always disabled:** Automated purchases, supplier switching, allocation execution and business system writes.

By default, no database is connected. The page correctly displays that state. A company must explicitly authorize a source before it can be configured.

For a *separately authorized* local SQLite database, an administrator can set this environment variable **in a Command Prompt opened in the application folder**:

```bat
set "AEGIS_ENTERPRISE_SQLITE=C:\approved\directory\company_readonly.sqlite3"
python desktop.py
```

The example above is a path *format*, not an actual company file. Do not create or download a dataset to make the page appear connected. The connector returns only contract names, missing column names, and readiness statuses. Even all eight column sets being present does **not** certify data quality, decision-time availability, causality, or future model performance.

Credentials and arbitrary file paths are not entered through the browser UI. The concrete ERP or database adapter will be selected and implemented only after a real company system and its authorized access requirements are known.

## What AEGIS does not claim

- The research score is **not** a calibrated probability of late delivery.
- This is **not** a live shipping feed or an independently validated production model.
- Synthetic capacity results are **not** proof that real suppliers can meet new allocations or that switching reduces disruptions.
- The application has **no procurement, supplier-switch, or business-execution API**.
- Human approval remains necessary. In fact, the current operational gate is **NOT GRANTED**.

## Validation work before a larger LLM upgrade

The detailed acceptance criteria and unresolved evidence gaps are maintained in
[`VALIDATION_ROADMAP.md`](VALIDATION_ROADMAP.md). Passing an application or
synthetic stress test is not evidence that a commercial model is calibrated or
that a supplier intervention works.

### Complete, paired, **synthetic** stress-test structure

The optional `paired_stress.py` script is separate from the live interface,
original notebook, and frozen models. It reads the **original integrated
dataset ZIP** in place, builds the July 2025 `CMP-007` source candidate menu,
and generates a new hypothetical shared-shock experiment without modifying any
existing evidence. The resulting stress index is **not** a probability,
delivery delay forecast, or real supplier-switching recommendation.

From a Windows Command Prompt in the existing `AEGIS_Standalone_App` folder,
enter this if the original `data` directory is still in the parent
`AEGIS_4_0_v0_2` folder, as in your existing layout:

```bat
python AEGIS_App\paired_stress.py --source ".." --output "AEGIS_step191_paired_stress"
```

Alternatively, use your original ZIP file (adjust the ZIP path):

```bat
python AEGIS_App\paired_stress.py --source "C:\path\to\AEGIS_4_0_Integrated_Dataset_v0_2.zip" --output "AEGIS_step191_paired_stress"
```

The output path must be a new or empty folder. The script creates
`audit_report.json`, `candidate_menu.csv`, `synthetic_shared_shocks.json`,
`paired_exposures.csv`, and `pair_summary.csv`, with all actions and real-world
claims blocked. It does **not** re-solve joint supplier capacity limits: this
tests shared-shock structure of candidate options, not the feasibility of
every alternative allocation. No extra Python packages are needed. The
original candidate experiment in the notebook remains unchanged.

### Step 192 — decision-time evidence validator

This new independent research module checks the **eight** Step 182 canonical
business tables for missing fields/duplicate keys and mechanical as-of
consistency. It rejects future-known order inputs, stale or future-dated
quotes/capacity, and source-described execution without human approval.

To run its **software-only self-test** from your usual `AEGIS_Standalone_App`
Command Prompt, paste:

```bat
python AEGIS_App\asof_validation.py --self-test
```

It runs nine tiny invented positive/negative scenarios, writes **no files**,
and prints `all_pass: true` if all controls behave as expected. You do not
need a new dataset, a notebook, an LLM, or a company connection.

Later, only for explicitly authorized eight-table canonical CSV data:

```bat
python AEGIS_App\asof_validation.py --source-dir "C:\approved\canonical_csv" --report "C:\approved\asof_audit.json"
```

**This is not company integration or operational certification.** The validator
uses the timestamps supplied within those files, but cannot independently
prove when the underlying system first knew a value, that currency and units
are compatible, or that **outside reservations** and changing real capacity
were captured. It now checks that source-listed allocations collectively fit
each shared capacity snapshot and sum to the recorded demand. No proposed
business action is certified safe. The report contains issue counts
and table status rather than source rows; it does not change business data.

### Steps 193–196 — combined validation foundation

This release adds historical delivery-status checks, a prospective shadow
evaluation gate, a shared source-capacity and demand-integrity gate, and a
strictly descriptive intervention-group comparison gate. They do **not** use
an LLM, retrain the original model, or automatically act on supplier records.

In your existing Windows Command Prompt opened in
`AEGIS_4_0_v0_2\AEGIS_Standalone_App`, run the following **after copying the
new files**. Your existing integrated dataset must still be in its parent
folder (the original `data` directory):

```bat
python AEGIS_App\validation_suite.py --synthetic-source ".." --report "AEGIS_validation_foundation_report.json"
```

You should see **34/34 software controls PASS**, the 40,000-row synthetic
paired experiment status and **Real-world validation: NOT CERTIFIED**. The
report is a new JSON file in `AEGIS_Standalone_App`; the command will refuse
to overwrite an existing report. For another run, choose a different report
filename. If you no longer have the original synthetic source directory, leave
out `--synthetic-source`; the 34 self-checks still work, but Step 191 is
marked NOT_RUN.

You can separately run these without company records:

```bat
python AEGIS_App\asof_validation.py --self-test
python AEGIS_App\prospective_validation.py --self-test
python AEGIS_App\intervention_evidence.py --self-test
```

For a future **approved** prospective evaluation, Step 194 requires a plan
registered before collecting a fresh scoring cohort, the exact scoring-time
model identity/digest and feature-availability timestamps, the subsequent
recorded outcomes, and an independent reviewer:

```bat
python AEGIS_App\prospective_validation.py --scores "C:\approved\shadow_scores.csv" --outcomes "C:\approved\recorded_outcomes.csv" --plan "C:\approved\study_plan.json" --report "C:\approved\shadow_results.json"
```

Step 196 has a separate **non-causal** comparison input contract:

```bat
python AEGIS_App\intervention_evidence.py --source-dir "C:\approved\eight_canonical_csv" --plan "C:\approved\comparison_plan.json" --report "C:\approved\comparison_results.json"
```

These paths are **examples only**, not included files or granted business
access. Don't load confidential or regulated company data into this prototype
without permission and a security review. The remaining acceptance criteria
are in `VALIDATION_ROADMAP.md`.

### Step 200 — original Olist historical outcome and score audit

This optional, **read-only** research check attaches the original Olist orders
CSV to the existing frozen AEGIS export to reconcile all 99,441 source IDs,
check purchase-time consistency for the 58,911 scored records, and summarize
recorded delivery timing relative to Olist's estimated dates. It reports
retrospective ranking statistics by original phase and purchase month only
where enough comparable observations exist. It never certifies future
prediction accuracy, a contractual promise, model provenance or causal effects.

From your `AEGIS_Standalone_App` Command Prompt, run this against the original
Olist CSV that you located on your Desktop:

```bat
python AEGIS_App\olist_temporal_audit.py --olist-orders "C:\Users\VISHAL\OneDrive\Desktop\AEGIS\AEGIS_Public_Data\Olist_Raw\archive\olist_orders_dataset.csv" --report "AEGIS_step200_olist_temporal_audit.json"
```

The source and existing `AEGIS_App\data\aegis_bundle.json` are never
overwritten. The report will be saved alongside `AEGIS_Standalone_App` (not
into the original Olist folder), and refuses to overwrite an earlier report.
If you want to test the validator without loading the real Olist file, run
`python AEGIS_App\olist_temporal_audit.py --self-test`. Seven fictional
software controls must pass. The full suite includes five additional
Step 200 unit tests; the expected total is **64 tests** for this release.

## Data safety and file structure

```text
AEGIS_App/
├── app.py                  Local Python research server
├── desktop.py              Optional native-window launcher
├── connectors.py            Read-only Mode 3 connector framework
├── intake.py                Memory-only local CSV/XLSX import and inspection
├── conversation.py          Opt-in localhost-only Qwen explanations
├── historical_outcomes.py  Exact-ID checked Olist source outcome attachment
├── paired_stress.py        Independent full-menu synthetic paired study
├── asof_validation.py      Independent, read-only decision-time data gate
├── prospective_validation.py  Read-only shadow prediction audit
├── intervention_evidence.py  Read-only, descriptive comparison gate
├── validation_suite.py     One-command research controls and limitations report
├── olist_temporal_audit.py Retrospective, read-only original Olist/source-score audit
├── VALIDATION_ROADMAP.md   Model/operational limitations and acceptance gates
├── web/
│   ├── index.html          Interface
│   ├── styles.css          Visual system
│   └── app.js              Interaction and charts
├── export_from_notebook.py One-time research data export
├── data/                   Frozen JSON export (created locally)
├── launch_aegis.bat        Windows launcher
└── README.md               This guide
```

No dependencies are required for the browser version beyond standard Python. Only the optional native window uses `pywebview`. The one-time export runs inside your existing Jupyter environment, using its existing `pandas` installation.

The server binds **only** to `127.0.0.1`. It does not offer user authentication or enterprise access management; do not expose it to a public network or place private company records in it without a security review.

### Troubleshooting

- **“Research data not connected”:** Run the one-time export cell in the original notebook, then restart the app.
- **“Required notebook results not in memory”:** Your notebook kernel was restarted or the relevant cells haven't been executed in the current kernel. Restore its original working environment before exporting.
- **“Port 8787 already in use”:** Close an earlier AEGIS console, or run `set AEGIS_PORT=8788` before `python app.py` in a command prompt.
- **Ollama isn't running:** The natural-conversation checkbox will be switched off and checked descriptive answers continue to work. Start Ollama and verify `ollama list` includes `qwen3.5:4b` to enable natural conversation.
- **Data Workspace import fails:** Use UTF-8 CSV or an unencrypted XLSX file. Check the size/row/column limits and make sure every header is unique. Rejected files do not remove the previous session upload.
- **Data Workspace seems empty after restart:** This is intended: user-uploaded records are held in memory only, not permanently saved. Upload again when needed.
- **Older browser:** Use an up-to-date local browser. No browser extension is required.

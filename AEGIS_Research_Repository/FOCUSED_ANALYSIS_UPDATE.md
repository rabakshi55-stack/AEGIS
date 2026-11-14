# AEGIS — focused dataset analysis update

## Install (existing Streamlit AI Edition)

Copy all five items in this patch into the existing GitHub repository subfolder `AEGIS_Research_Repository`, merging/replacing matching files and folders. Commit and push. The updated app uses a versioned session workspace, so old sessions reset their dataset/chat after deployment. Load the dataset again. The existing Groq secret, Streamlit URL and Python 3.12 remain unchanged. This patch includes the preceding tie-aware and provider JSON recovery fixes. The portable Windows package is not rebuilt by this web patch.

## What changed

- Shared focused analysis tool for exact source-column descriptions and unqualified mapped delivery performance / monthly trend questions. All accepted rows are examined. Other complex/qualified requests remain with the existing planner, not an unfiltered approximation.
- Reports early, same-day and late counts, comparable denominators, missing date counts and malformed date pairs. Distinguishes promised-date compliance (on or before) from exact-date or late counts. Order labels are used only when mapped order references are unique and nonblank; otherwise reports source rows. For trends, separately reports delivery performance by order month and recorded deliveries by actual date month. Shows at most 24 observed months and labels incomplete coverage; missing periods are not imputed. No causal, contractual or prospective claims.
- Generic exact field descriptions compute bounded categorical frequencies with ties, numeric summary measures or date ranges and observed-month frequencies; identifiers are not treated as numerical measures.
- Hosted model gets checked focused evidence instead of an irrelevant general overview. If no extra tool result is produced, the independently computed focused answer is displayed rather than an unvalidated paraphrase. If provider inference fails, the checked evidence remains explicitly available. More complex questions continue to use the model-driven analytical tools. Not all arbitrary questions or model-produced SQL are guaranteed correct.
- Standard mode prioritizes this focused tool ahead of generic chart/overview routing. Explicit chart requests and procurement blocks are preserved. Versioned session initialization prevents reuse of obsolete CloudWorkspace instances across deployments.

## Verification

49 online adapter tests and 286 application tests pass offline, including prior tie and JSON recovery checks plus 11 focused-analysis tests. Provider tests use simulated responses, not live Groq. Live Streamlit acceptance remains necessary after deployment. No original research data or models changed.

From the repository subfolder, in PowerShell:
```
$env:AEGIS_OFFLINE_TEST_MODE='1'
$env:PYTHONUTF8='1'
$env:PYTHONPATH='.;AEGIS_App'
python -m unittest discover -s cloud_tests -q
python -m unittest discover -s AEGIS_App/tests -q
```

## Live acceptance

Load the fictional example; check that eight mappings are present (apply the displayed mappings in Data if needed). In both modes, ask: `What is the trend in the delivery date?` Expected: Jan 1 early / 1 late, Feb 1 exact / 1 late, Mar 1 early / 1 missing; late rate 50%, 50%, 0% among comparable dates, with small and incomplete samples. Ask `What does the delivery column say?` Expected: 3 of 5 on/before the promised date, 2 late, 1 missing actual date. Ask `How many orders were delivered on the promised date?` Expected: 1 of 5 exactly on date. Ask `What is happening in the data?` Expected: general overview including flat order volume, not confused with delivery trend. Test other source fields and a second dataset before broad release. No need to share secrets.

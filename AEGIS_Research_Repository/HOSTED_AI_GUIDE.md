# AEGIS AI — GPT-OSS reasoning and dataset tools

AEGIS now has three distinct modes: hosted GPT-OSS AI (independent of Qwen), standard deterministic analytics, and private Ollama/Qwen on the local edition. The hosted mode is **not a model trained by AEGIS**, nor is it ChatGPT. It uses Groq's hosted `openai/gpt-oss-120b` model. Model capabilities and quotas are subject to the provider. Use a free-tier Groq organization if you do not want to incur charges. The free plan is quota-limited; a public app shares the owner's quota. Do not add a paid key unless you understand the charges. This release adds process-local request caps (12 calls/minute and 180 calls/rolling 24 hours); these are not a provider-side spending cap or durable limits across restarts/replicas. A question can require up to four calls.

## What changed
- The model proposes SQL calculations against a separate in-memory SQLite table built from the active dataset. A read-only authorizer, SQL function allowlist, table scope, statement length, time/step limits and bounded result sizes protect the calculation interface. It does not execute arbitrary Python, write a database, contact other systems, access files or execute procurement.
- The model can plan more than one calculation, interpret checked results, ask for clarification, hold a short conversational context, answer general questions, and suggest a chart using the existing chart builder. It is no longer confined to predefined question phrases. Exact computed values and SQL are displayed separately from AI interpretations. Chart selections are recalculated from source data.
- Existing standard and local Qwen modes remain available. Existing research archives are unchanged. The prior offline distinct-count fix is included too.
- Uploads remain isolated by session on Streamlit. The hosted service receives questions, schema/column names, recent dialogue and bounded query results or chart descriptions (which may contain source values). No whole file is sent by this interface. Do not upload or discuss confidential/personal data; accept the explicit notice only if authorized. Standard local analytics and local Qwen do not need Groq. No key is stored in this package.
- This is still a research prototype, not a certified procurement or predictive system. A valid SQL query does not guarantee correct business semantics; LLM interpretation can be wrong. The agent uses one table and existing source-field chart types; multi-table joins, arbitrary derived chart expressions, independent external research, and all possible forecasting/causal questions are not supported. Model training and business execution are not enabled.

## Online: update the existing deployed app
1. Back up the local GitHub repository. Extract the complete cloud package. Copy **contents** of the new `AEGIS_Research_Repository` into `Documents/GitHub/AEGIS/AEGIS_Research_Repository`, replacing matching files; preserve the root `.git`. Commit and push. The deployed app already uses `AEGIS_Research_Repository/streamlit_app.py`; no new Streamlit app is needed. Keep the app entrypoint and Python 3.12 unchanged.
2. Create a key in a free Groq account at https://console.groq.com/keys (check the organization limits and billing status). Do not post or commit the key.
3. Go to the existing app at https://aegis-decision-intelligence.streamlit.app. In the owner's Manage app settings (or the My apps menu), open Secrets. Add this TOML with your actual key, then save:

```toml
GROQ_API_KEY = "your_actual_key_here"
```

4. Refresh/reboot the app if needed. Select **AEGIS AI (GPT-OSS)** in the sidebar and accept the data-sharing notice. Standard analytics stays available if a key is absent or the quota is exhausted. If the service fails, the app shows the error or displays partial computed evidence rather than pretending to have a successful AI answer.
5. Load the fictional sample. Ask `How many suppliers are there?` (3), `List them and count the orders.` (Alpha 2, Beta 2, Gamma 2), `Which supplier has the highest total quantity times unit cost?` (Beta 728), `How many orders arrived after their promised date, excluding missing dates?` (2 out of 5 comparable orders), `What chart best compares quantity by supplier?` (validated chart), and a novel question of your choosing. Test general conversation with the dataset cleared. Verify the reported calculations, not just the prose. Test a different dataset, two separate browser sessions, and the mobile display. These are live acceptance checks, not claimed to have been executed by the build environment.

## Windows portable edition
Extract into a fresh writable folder. Run `CHECK_AEGIS.bat` first; it provisions the official private Python runtime if needed and forces offline tests. For standard mode or local Qwen, run `START_AEGIS.bat` as before. For hosted AI, run `START_AEGIS_AI.bat`, which prompts for your Groq key without displaying or saving it; it is available to the launched application process only. Internet access is required. Open Decision Copilot > Evidence source and local AI settings > AEGIS AI · GPT-OSS hosted and consent. Select My uploaded data for dataset questions or General conversation for general questions. The hosted mode takes precedence over the Qwen checkbox; no Ollama installation is needed for hosted mode. Archived research queries remain in standard research mode. For private AI, leave the hosted toggle off and use Ollama/Qwen as before. The private runtime provisioning and new batch launcher need clean-Windows acceptance testing. The offline check script remains unchanged and never calls hosted inference.

## Verification and service documentation
- Offline unit and HTTP integration tests use simulated model plans. No live provider credential is present, so they do not measure actual model quality. No real Streamlit/Groq deployment or Windows executable test was performed by the build environment. Verify the live service and fresh Windows installation before calling this final.
- Run `AEGIS_OFFLINE_TEST_MODE=1 python -m unittest discover -s AEGIS_App/tests -q` from the cloud repository only with `PYTHONPATH=AEGIS_App`, or run the local batch check. Cloud adapter tests: `python -m unittest discover -s cloud_tests -v` from the repository folder.
- API: https://console.groq.com/docs/api-reference
- Model: https://console.groq.com/docs/model/openai/gpt-oss-120b
- Quota: https://console.groq.com/docs/rate-limits
- Provider privacy: review https://groq.com/privacy-policy/ and https://console.groq.com/docs/your-data before enabling hosted AI.

© 2026 Arin Bakshi. All Rights Reserved. Third-party models, libraries and datasets retain their own terms. Confirm project contributors' rights before distributing.

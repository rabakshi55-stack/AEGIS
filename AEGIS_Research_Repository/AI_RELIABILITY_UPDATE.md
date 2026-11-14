# AEGIS — combined AI reliability update

Install into the existing Streamlit AI Edition repository subfolder AEGIS_Research_Repository. Copy the AEGIS_App and cloud_tests folders from this patch into it, merge/replace matching files. No API-key, secrets, Python version, or entrypoint changes. Commit and push once. Reboot Streamlit if old sessions persist. This patch supersedes the earlier individual hosted_copilot.py updates.

Changes: correct ranked SQL cutoff ties (outer ORDER BY + literal LIMIT; visible primary metric required); ensure tied results are reported instead of a unique winner; recover one time from provider plan-format failures via JSON object mode with strict local shape and semantic validation; preserve read-only SQL guards, quotas and verified evidence; repair all displayed trend/category/distribution peak ties and distinguish flat, monotonic and fluctuating recorded periods. Displayed periods are bounded and missing periods are not imputed. No changes to original research files.

Tests from repository subfolder (Python 3):
PowerShell:
```
$env:AEGIS_OFFLINE_TEST_MODE='1'
$env:PYTHONUTF8='1'
$env:PYTHONPATH='.;AEGIS_App'
python -m unittest discover -s cloud_tests -v
python -m unittest discover -s AEGIS_App/tests -q
```
Cloud suite: 38 passed. Application suite: 286 passed in build environment. Transport tests mock HTTP responses, including json_validate_failed, retry success, retry rejection, auth errors and a disallowed write plan. They do not verify live Groq model behavior. This is not proof that all model-generated SQL has correct business semantics or that all questions are answerable. The portable release archive/manifest is not updated by this web patch.

Live acceptance: after update, load fictional example and select hosted AI with consent. Ask: which is the most recurring supplier? Expected all three tied at 2. Ask: can u analyze the trend happening in the dataset? Expected Jan/Feb/Mar each 2 records, flat activity; 2 of 5 comparable delivery rows after mapped date. Hosted interpretation may still fail; checked results remain available with explicit label. Verify a new dataset too.

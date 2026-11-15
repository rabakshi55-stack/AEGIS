# AEGIS — hosted plan recovery update

Applies to the Streamlit AI Edition **after** the Combined AI Reliability and Focused Analysis updates. No new dependencies or credentials. Copy these files into the existing `AEGIS_Research_Repository` folder, preserving paths. Commit and push, then reboot the Streamlit app once. The versioned session workspace is reset on deployment, so reload your dataset.

## Changes
- Retain the closed structured schema and validate the action contract. A valid query, chart, or overview may contain incidental speculative answer text or a basis; discard these inactive fields before execution. Do not execute conflicting action payloads. Missing active fields remain invalid.
- On plan failure, the bounded JSON-object retry includes the actual safe validation category and explicit single-action instructions. All retried plans pass the same local checks. Authentication errors are not retried.
- If neither plan is valid and no checked hosted evidence is available, use the existing standard analytics path when a dataset is loaded. Label this as a standard fallback, not an AI result. Without a dataset, record a clear unavailable response instead of fabricating an answer. Existing partial-evidence recovery remains in place.
- Preserve SQL authorizer, read-only database, chart validation, session isolation, quota, consent, and all procurement safeguards.

## Verification
Run from the repository directory with Python 3:
```
python -m unittest discover -s cloud_tests -q
```
For the full application suite, set `AEGIS_OFFLINE_TEST_MODE=1` and `PYTHONUTF8=1` and include `AEGIS_App` on `PYTHONPATH`.

The new eight regression tests use simulated provider HTTP responses, including a valid calculation with premature prose, conflicting actions, retry repair, failed retry, no-data recovery, retained evidence, and rejected SQL writes. No live Groq request was made; the screenshot's exact provider payload is not available. This update improves the identified validation class but does not guarantee every model answer or analytical query is correct.

## Live acceptance
Load the fictional example in hosted AI mode with consent. Ask for the number of suppliers, the most recurring supplier, delivery trends, and a new filtered calculation. Expect three suppliers, all tied at two records; 3 of 5 comparable deliveries on or before the promise; checked results instead of a fatal plan-validation error. A labeled fallback is not proof of successful hosted inference. If the model repeatedly falls back, capture the question and response (never the key).

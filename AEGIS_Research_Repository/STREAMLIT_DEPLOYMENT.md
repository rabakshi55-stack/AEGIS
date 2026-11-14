# AEGIS online deployment

The existing public Streamlit app is https://aegis-decision-intelligence.streamlit.app. The new hosted AI path requires an owner-configured Groq API key and explicit session consent. See `HOSTED_AI_GUIDE.md` for the complete update and verification steps, privacy requirements, limits and fallback. The standard analytics path works without a provider. Do not upload secrets or restricted raw Olist data.

For a new deployment use the existing GitHub repository `rabakshi55-stack/AEGIS`, branch `main`, main file `AEGIS_Research_Repository/streamlit_app.py` (if using the current nested layout), Python 3.12. For a root-level repository instead use `streamlit_app.py`. Copy contents, commit/push, configure the owner's Streamlit Secrets and verify the app. Do not commit keys. The source does not expose the localhost app or a user's local Ollama server.

Limits remain 5 MiB, 25,000 rows, 500,000 cells and eight custom charts. This is a public research demo; use only authorized non-sensitive records. Hosted AI is externally processed; no business execution or certified predictions. Private Qwen and SQLite remain in the local edition.

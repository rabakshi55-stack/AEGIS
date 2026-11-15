"""Render basic Markdown safely; keep raw SQL evidence as inert text."""
import re

def renderable_answer(answer):
    narrative,separator,evidence=str(answer).partition('\n\nCalculated evidence (from the active dataset):')
    # Model and source strings are untrusted; never render HTML or external
    # images. Plain-text SQL goes in a separate collapsed panel.
    narrative=re.sub(r'!\[([^\]\n]*)\]\([^\n]*\)',r'[image omitted: \1]',narrative)
    narrative=re.sub(r'!\[([^\]\n]*)\]\[[^\]\n]*\]',r'[image omitted: \1]',narrative)
    # Neutralize any remaining image markers (including malformed/reference forms).
    narrative=narrative.replace('![','\\!\\[')
    narrative=narrative.replace('<','&lt;').replace('>','&gt;')
    return narrative, (separator.strip()+'\n'+evidence.lstrip() if separator else '')

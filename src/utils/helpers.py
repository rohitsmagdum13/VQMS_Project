"""Module: utils/helpers.py

General utility functions shared across VQMS modules.

This module is a collection point for small helper functions
that don't belong in any specific service or agent module.
Keep functions here small and focused — if a helper grows
complex, move it to its own module.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup


def html_to_plain_text(html_content: str) -> str:
    """Convert raw HTML email body into clean, readable plain text.

    Graph API returns email bodies as full HTML — including Gmail/Outlook
    UI wrappers, CSS classes, inline styles, and nested tables. This
    function strips all of that and returns just the human-readable
    email text.

    The cleanup steps:
      1. Parse HTML with BeautifulSoup
      2. Remove <style> and <script> tags entirely
      3. Extract visible text only
      4. Collapse excessive whitespace and blank lines
      5. Strip leading/trailing whitespace

    Args:
        html_content: Raw HTML string from Graph API body.content.

    Returns:
        Clean plain text string with the actual email content.
        Returns empty string if input is None or empty.
    """
    if not html_content:
        return ""

    # Parse the HTML — "html.parser" is Python's built-in parser,
    # no extra C library needed
    soup = BeautifulSoup(html_content, "html.parser")

    # Remove <style> and <script> tags completely — their text
    # content is CSS/JS code, not readable email text
    for tag in soup(["style", "script"]):
        tag.decompose()

    # Extract all visible text — separator="\n" puts each block
    # element on its own line (like <div>, <p>, <br>, <tr>)
    raw_text = soup.get_text(separator="\n")

    # Collapse runs of whitespace on each line (e.g., "  Hello   World  " → "Hello World")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw_text.splitlines()]

    # Remove excessive blank lines — keep at most one blank line
    # between paragraphs for readability
    cleaned_lines: list[str] = []
    previous_blank = False
    for line in lines:
        if line == "":
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
        else:
            cleaned_lines.append(line)
            previous_blank = False

    return "\n".join(cleaned_lines).strip()

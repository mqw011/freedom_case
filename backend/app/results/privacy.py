"""Public rationales retain reasons, but omit quotations and common secret/PII forms."""

import re
from difflib import SequenceMatcher


def public_rationale(text, source_texts):
    text = " ".join(text.split())[:2000]
    # Find source spans before other redaction changes their positions.
    spans = []
    for source in source_texts:
        source = " ".join(source.split())
        if len(source) >= 8 and source in text:
            start = text.index(source)
            spans.append((start, start + len(source)))
        for match in SequenceMatcher(None, text, source, autojunk=False).get_matching_blocks():
            if match.size >= 24:
                spans.append((match.a, match.a + match.size))
    covered = set(i for start, end in spans for i in range(start, end))
    pieces = []
    for i, char in enumerate(text):
        if i not in covered:
            pieces.append(char)
        elif i == 0 or i - 1 not in covered:
            pieces.append("[цитата скрыта]")
    text = "".join(pieces)
    for pattern in (
        r"https?://\S+|www\.\S+",
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        r'«[^»]*»|“[^”]*”|"[^"\n]*"',
        r"(?i)\b(?:sig|api[_-]?key|token|password|secret)\s*[=:]\s*\S+",
        r"\b(?:sk-|ghp_|github_pat_)[\w-]+",
        r"(?i)\bKZ\d{2}[A-Z0-9]{16}\b",
        r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)",
        r"\b[A-Za-z0-9_/-]{32,}\b",
        r"\b[А-ЯЁӘҒҚҢӨҰҮҺІ][а-яёәғқңөұүһі]+(?:\s+[А-ЯЁӘҒҚҢӨҰҮҺІ][а-яёәғқңөұүһі]+){2}\b",
    ):
        text = re.sub(pattern, "[скрыто]", text)
    return (text[:597] + "…" if len(text) > 600 else text).strip() or "См. указанные реплики."

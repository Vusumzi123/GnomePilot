"""Response formatter — regex cleanup of LLM output."""

import re


class Formatter:
    """Strips emojis, invisible characters, leaked MCP tool-call JSON artefacts,
    and markdown code fences from LLM responses.
    """

    _STRIP_RE = re.compile(
        "["
        "\U0001F300-\U0001F9FF"  # emoticons, symbols, pictographs
        "\U0001FA00-\U0001FAFF"  # symbols extended
        "\U00002600-\U000027BF"  # misc symbols (checkmarks, stars)
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport/map
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\u200B-\u200F"          # zero-width chars, RTL marks
        "\u2028-\u202F"          # line/paragraph separators, narrow NBSP
        "\uFEFF"                 # BOM / zero-width no-break space
        "\u00AD"                 # soft hyphen
        "\u2060-\u2064"          # word joiner, invisible chars
        "]+",
        re.UNICODE,
    )

    _TOOL_CALL_RE = re.compile(
        r'\{\s*"name"\s*:\s*"[^"]+",\s*"parameters"\s*:\s*\{[^}]*\}\s*\}'
    )

    _JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def format(self, text: str) -> str:
        """Apply all cleanup passes.  Returns the original text when disabled."""
        if not self.enabled:
            return text
        try:
            cleaned = self._JSON_FENCE_RE.sub(r"\1", text)
            cleaned = self._STRIP_RE.sub("", cleaned)
            cleaned = self._TOOL_CALL_RE.sub("", cleaned)
            return re.sub(r"\s{2,}", " ", cleaned).strip()
        except Exception:
            return text

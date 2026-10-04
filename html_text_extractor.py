"""Collect replaceable visible-text ranges from raw HTML without reformatting it."""
import re
from html.parser import HTMLParser


TRANSLATE_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "span", "label",
    "button", "a", "td", "th", "caption", "figcaption", "blockquote",
    "cite", "legend", "summary", "strong", "b", "em", "i", "small", "option",
}
SKIP_TAGS = {"script", "style", "code", "pre", "svg", "math", "noscript"}


class _TextExtractor(HTMLParser):
    """Record source character offsets for translatable text segments."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.segments = []
        self._raw = ""
        self._skip_depth = 0
        self._translate_depth = 0
        self._buf_start = None

    def feed_raw(self, raw: str):
        self._raw = raw
        self.feed(raw)

    def _offset(self):
        line, col = self.getpos()
        return sum(len(part) for part in self._raw.splitlines(keepends=True)[:line - 1]) + col

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in TRANSLATE_TAGS and self._skip_depth == 0:
            self._translate_depth += 1
            if self._translate_depth == 1:
                close = self._raw.find(">", self._offset())
                if close != -1:
                    self._buf_start = close + 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in TRANSLATE_TAGS and self._skip_depth == 0:
            if self._translate_depth == 1 and self._buf_start is not None:
                end = self._offset()
                text = self._raw[self._buf_start:end]
                if re.sub(r"<[^>]+>", "", text).strip():
                    self.segments.append({"start": self._buf_start, "end": end, "text": text})
                self._buf_start = None
            self._translate_depth = max(0, self._translate_depth - 1)

    def handle_data(self, data):
        if not data.strip() or self._skip_depth or self._translate_depth:
            return
        start = self._offset()
        self.segments.append({"start": start, "end": start + len(data), "text": data})

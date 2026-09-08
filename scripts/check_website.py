"""Dependency-free static-site checks; never calls the backend or changes files."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import json
import re

ROOT = Path(__file__).resolve().parents[1] / "website"


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.references = []
        self.tabs = []
        self.h1 = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])
        for key in ("aria-controls", "aria-labelledby", "aria-describedby"):
            self.references.extend(attrs.get(key, "").split())
        if attrs.get("role") == "tab":
            self.tabs.append(attrs)
        self.h1 += tag == "h1"


def check():
    page = Page()
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    page.feed(html)
    assert page.h1 == 1, "Expected one H1"
    assert len(page.ids) == len(set(page.ids)), "Duplicate IDs"
    assert all(ref in page.ids for ref in page.references), "Broken ARIA references"
    assert len(page.tabs) == 5, "Expected five method stages"
    assert sum(tab["aria-selected"] == "true" for tab in page.tabs) == 1
    for link in page.links:
        parsed = urlparse(link)
        if parsed.scheme:
            assert parsed.scheme == "https", f"Unexpected URL scheme: {link}"
            continue
        if parsed.path:
            target = (ROOT / parsed.path).resolve()
            assert target.is_relative_to(ROOT.resolve()), f"Asset escapes site: {link}"
            assert target.is_file(), f"Missing asset: {link}"
        if parsed.fragment and not parsed.path:
            assert parsed.fragment in page.ids, f"Missing anchor: {link}"
    for name in ("index.html", "styles.css", "app.js", "case-data.json"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"(?:127\.0\.0\.1|localhost|/mnt/c/|ghp_|gho_)", text), f"Local/private data in {name}"
    data = json.loads((ROOT / "case-data.json").read_text(encoding="utf-8"))
    assert len(data["tests"]) == 8 and all(test["passed"] for test in data["tests"])
    assert data["liveVerification"] is False
    assert data["recordedStatus"] == "Ready"
    assert data["definitionCounts"] == {"developmentClasses": 49, "developmentObjectProperties": 57}
    for digest in data["hashes"].values():
        assert re.fullmatch(r"[a-f0-9]{64}", digest), "Invalid SHA-256"
    print(f"PASS: {len(page.links)} links/assets, {len(page.ids)} IDs, 5 accessible stages, 8 historical tests; no local endpoints.")


if __name__ == "__main__":
    check()

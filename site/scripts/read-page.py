"""Read public-page text and asset links for the HTTP acceptance check."""

import json
import sys
from html.parser import HTMLParser


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.text = []
        self.assets = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        for name, value in attrs:
            if name in ("src", "href") and value:
                if value.startswith("/_astro/"):
                    self.assets.add(value)
                if name == "href":
                    self.links.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


page = Page()
page.feed(sys.stdin.read())
print(json.dumps({"text": " ".join(page.text), "assets": sorted(page.assets), "links": page.links}))

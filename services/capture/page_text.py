"""Linear text for a captured page, with links kept inline as `[[LINK:url]]` markers.

The bookmarklet produces this format directly from the live page; saved HTML
files (Ctrl+S) are converted here so both paths parse identically.
"""
from html.parser import HTMLParser
import re

LINK_RE = re.compile(r'\[\[LINK:(\S+?)\]\]')

SKIP = {'script', 'style', 'noscript', 'template', 'svg', 'iframe', 'head', 'title'}
BLOCK = {'div', 'p', 'li', 'tr', 'section', 'article', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'table', 'ul', 'ol',
         'header', 'footer', 'main', 'aside', 'nav', 'figure', 'blockquote', 'dt', 'dd', 'td', 'th'}


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.links = [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.out.append('\n')
        if tag == 'a':
            self.links.append(dict(attrs).get('href'))

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == 'a' and self.links:
            href = self.links.pop()
            if href and not self.skip:
                self.out.append(f' [[LINK:{href}]] ')
        elif tag in BLOCK:
            self.out.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r'\s+', ' ', data))


def html_to_text(html):
    parser = _Parser()
    parser.feed(html or '')
    parser.close()
    return clean(''.join(parser.out))


def clean(text):
    lines = (re.sub(r'[ \t ]+', ' ', line).strip() for line in str(text or '').splitlines())
    return '\n'.join(line for line in lines if line)


def links_in(text):
    return LINK_RE.findall(text or '')


def strip_links(text):
    return clean(LINK_RE.sub(' ', text or ''))

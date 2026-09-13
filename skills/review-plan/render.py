#!/usr/bin/env python3
"""Render an agreed plan (Markdown) to a self-contained HTML file.

Dependency-free on purpose: the plan-review skill runs this after the
exchange converges so the HTML costs no model tokens. Supports the
Markdown subset the skill emits: ATX headings, paragraphs, ordered and
unordered lists (nested by indentation), fenced code blocks, block
quotes, pipe tables, horizontal rules, and inline bold / italic /
code / links.

    python3 render.py plan.md -o plan.html
    python3 render.py plan.md            # writes plan.html next to it
"""
import argparse
import html
import re
import sys
from pathlib import Path

CSS = """
:root{--fg:#1f2328;--muted:#59636e;--bg:#fff;--line:#d1d9e0;--code:#f6f8fa;--accent:#0969da;--quote:#e6eef8}
@media(prefers-color-scheme:dark){:root{--fg:#e6edf3;--muted:#9198a1;--bg:#0d1117;--line:#30363d;--code:#161b22;--accent:#4493f8;--quote:#131d2b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:2em;border-bottom:1px solid var(--line);padding-bottom:.3em;margin-top:0}
h2{font-size:1.5em;border-bottom:1px solid var(--line);padding-bottom:.3em;margin-top:1.8em}
h3{font-size:1.2em;margin-top:1.5em}
h4{font-size:1em;margin-top:1.2em}
p,ul,ol,table,pre,blockquote{margin:0 0 1em}
li>ul,li>ol{margin:.25em 0 0}
li{margin:.2em 0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.9em;background:var(--code);padding:.15em .4em;border-radius:4px}
pre{background:var(--code);padding:14px 16px;border-radius:6px;overflow:auto;border:1px solid var(--line)}
pre code{background:none;padding:0;font-size:.875em}
blockquote{border-left:4px solid var(--accent);background:var(--quote);margin-left:0;padding:.6em 1em;color:var(--fg)}
blockquote p:last-child{margin-bottom:0}
table{border-collapse:collapse;width:100%;font-size:.95em}
th,td{border:1px solid var(--line);padding:.45em .7em;text-align:left;vertical-align:top}
th{background:var(--code)}
hr{border:0;border-top:1px solid var(--line);margin:2em 0}
a{color:var(--accent)}
nav.toc{border:1px solid var(--line);border-radius:6px;padding:12px 18px;margin-bottom:2em;font-size:.95em}
nav.toc b{display:block;margin-bottom:.4em}
nav.toc ul{list-style:none;padding:0;margin:0}
nav.toc ul ul{padding-left:1.2em}
.meta{color:var(--muted);font-size:.85em;margin-top:3em;border-top:1px solid var(--line);padding-top:1em}
"""

INLINE_RULES = [
    (re.compile(r"`([^`]+)`"), lambda m: f"<code>{html.escape(m.group(1))}</code>"),
    (re.compile(r"\*\*(.+?)\*\*"), lambda m: f"<strong>{m.group(1)}</strong>"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), lambda m: f"<em>{m.group(1)}</em>"),
    (re.compile(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"), lambda m: f"<em>{m.group(1)}</em>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>'),
]


def inline(text: str) -> str:
    # Protect code spans from further inline processing.
    spans = []

    def stash(m):
        spans.append(f"<code>{html.escape(m.group(1))}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    for rule, repl in INLINE_RULES[1:]:
        text = rule.sub(repl, text)
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def slugify(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text).lower()
    s = re.sub(r"[^\w\s-]", "", s).strip()
    return re.sub(r"[\s_]+", "-", s) or "section"


HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
FENCE = re.compile(r"^(```|~~~)\s*(\S*)")
LIST_ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


class Renderer:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0
        self.out = []
        self.headings = []  # (level, text, id)
        self.ids = {}

    def uid(self, text):
        base = slugify(text)
        n = self.ids.get(base, 0)
        self.ids[base] = n + 1
        return base if n == 0 else f"{base}-{n}"

    def render(self):
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if not line.strip():
                self.i += 1
            elif FENCE.match(line):
                self.code()
            elif HEADING.match(line):
                self.heading()
            elif HR.match(line):
                self.out.append("<hr>")
                self.i += 1
            elif line.lstrip().startswith(">"):
                self.quote()
            elif LIST_ITEM.match(line):
                self.list(0)
            elif self.table_ahead():
                self.table()
            else:
                self.paragraph()
        return "\n".join(self.out)

    def code(self):
        fence, lang = FENCE.match(self.lines[self.i]).groups()
        self.i += 1
        buf = []
        while self.i < len(self.lines) and not self.lines[self.i].startswith(fence):
            buf.append(self.lines[self.i])
            self.i += 1
        self.i += 1  # closing fence
        cls = f' class="language-{html.escape(lang)}"' if lang else ""
        self.out.append(f"<pre><code{cls}>{html.escape(chr(10).join(buf))}</code></pre>")

    def heading(self):
        hashes, text = HEADING.match(self.lines[self.i]).groups()
        level = len(hashes)
        rendered = inline(text)
        hid = self.uid(text)
        self.headings.append((level, rendered, hid))
        self.out.append(f'<h{level} id="{hid}">{rendered}</h{level}>')
        self.i += 1

    def quote(self):
        buf = []
        while self.i < len(self.lines) and self.lines[self.i].lstrip().startswith(">"):
            buf.append(re.sub(r"^\s*>\s?", "", self.lines[self.i]))
            self.i += 1
        inner = Renderer(buf)
        body = inner.render()
        self.out.append(f"<blockquote>{body}</blockquote>")

    def paragraph(self):
        buf = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if (not line.strip() or FENCE.match(line) or HEADING.match(line)
                    or HR.match(line) or line.lstrip().startswith(">")
                    or LIST_ITEM.match(line) or self.table_ahead()):
                break
            buf.append(line.strip())
            self.i += 1
        self.out.append(f"<p>{inline(' '.join(buf))}</p>")

    def list(self, indent):
        first = LIST_ITEM.match(self.lines[self.i])
        ordered = first.group(2)[0].isdigit()
        tag = "ol" if ordered else "ul"
        start = ""
        if ordered:
            n = int(re.match(r"\d+", first.group(2)).group())
            if n != 1:
                start = f' start="{n}"'
        self.out.append(f"<{tag}{start}>")
        while self.i < len(self.lines):
            m = LIST_ITEM.match(self.lines[self.i])
            if not m or len(m.group(1)) < indent:
                break
            if len(m.group(1)) > indent:
                self.list(len(m.group(1)))
                continue
            if m.group(2)[0].isdigit() != ordered:
                break
            text = [m.group(3)]
            self.i += 1
            # Continuation lines: indented, non-blank, not a new item.
            while self.i < len(self.lines):
                nxt = self.lines[self.i]
                if not nxt.strip():
                    # Blank line ends the item unless a deeper item follows.
                    j = self.i + 1
                    if j < len(self.lines) and LIST_ITEM.match(self.lines[j]) and len(LIST_ITEM.match(self.lines[j]).group(1)) >= indent:
                        self.i += 1
                        continue
                    break
                if LIST_ITEM.match(nxt) or HEADING.match(nxt) or FENCE.match(nxt) or HR.match(nxt) or self.table_ahead():
                    break
                text.append(nxt.strip())
                self.i += 1
            self.out.append(f"<li>{inline(' '.join(text))}")
            # Nested list directly after this item?
            if self.i < len(self.lines):
                nm = LIST_ITEM.match(self.lines[self.i])
                if nm and len(nm.group(1)) > indent:
                    self.list(len(nm.group(1)))
            self.out.append("</li>")
        self.out.append(f"</{tag}>")

    def table_ahead(self):
        if self.i + 1 >= len(self.lines):
            return False
        return "|" in self.lines[self.i] and TABLE_SEP.match(self.lines[self.i + 1]) is not None

    def table(self):
        def cells(row):
            row = row.strip()
            if row.startswith("|"):
                row = row[1:]
            if row.endswith("|"):
                row = row[:-1]
            return [inline(c.strip()) for c in row.split("|")]

        head = cells(self.lines[self.i])
        self.i += 2
        rows = []
        while self.i < len(self.lines) and "|" in self.lines[self.i] and self.lines[self.i].strip():
            rows.append(cells(self.lines[self.i]))
            self.i += 1
        thead = "".join(f"<th>{c}</th>" for c in head)
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        self.out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>")


def toc(headings):
    items = [(lvl, txt, hid) for lvl, txt, hid in headings if 2 <= lvl <= 3]
    if len(items) < 2:
        return ""
    out = ['<nav class="toc"><b>Contents</b><ul>']
    depth = 2
    for lvl, txt, hid in items:
        while depth < lvl:
            out.append("<ul>")
            depth += 1
        while depth > lvl:
            out.append("</ul>")
            depth -= 1
        out.append(f'<li><a href="#{hid}">{txt}</a></li>')
    while depth > 2:
        out.append("</ul>")
        depth -= 1
    out.append("</ul></nav>")
    return "\n".join(out)


def render_document(md: str, source_name: str) -> str:
    lines = md.replace("\r\n", "\n").split("\n")
    r = Renderer(lines)
    body = r.render()
    title = next((re.sub(r"<[^>]+>", "", t) for l, t, _ in r.headings if l == 1), source_name)
    # Place the TOC after the first h1 (and any leading blockquote header).
    nav = toc(r.headings)
    if nav:
        m = re.search(r"</h1>\s*(?:<blockquote>.*?</blockquote>\s*)?", body, flags=re.S)
        if m:
            body = body[: m.end()] + nav + "\n" + body[m.end():]
        else:
            body = nav + "\n" + body
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n<main>\n"
        f"{body}\n<p class=\"meta\">Rendered from <code>{html.escape(source_name)}</code> by review-plan/render.py.</p>\n"
        "</main>\n</body>\n</html>\n"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", help="Markdown file to render")
    ap.add_argument("-o", "--output", help="HTML path (default: source with .html)")
    args = ap.parse_args(argv)
    src = Path(args.source)
    if not src.is_file():
        sys.exit(f"render.py: {src} is not a file")
    dst = Path(args.output) if args.output else src.with_suffix(".html")
    dst.write_text(render_document(src.read_text(encoding="utf-8"), src.name), encoding="utf-8")
    print(dst)


if __name__ == "__main__":
    main()

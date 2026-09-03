#!/usr/bin/env python
"""Verify a built site: no broken internal links, no links that ignore the base.

    python check_links.py [dist_dir] [--base /empyrean-wiki/]

The base check matters because GitHub Pages serves a project site under
/<repo>/. A hardcoded href="/pokedex/" works locally and 404s in production, so
it has to fail the build rather than reach the site. Exits non-zero on any
problem.
"""
import collections
import os
import re
import sys
from urllib.parse import unquote

LINK_RE = re.compile(r'(?:href|src)="(/[^"#?]*)"')


def main():
    args = [a for a in sys.argv[1:]]
    base = "/"
    if "--base" in args:
        i = args.index("--base")
        base = args[i + 1]
        del args[i:i + 2]
    root = os.path.abspath(args[0] if args else os.path.join("site", "dist"))
    base = "/" + base.strip("/") + "/" if base.strip("/") else "/"

    if not os.path.isdir(root):
        sys.exit("no such directory: %s" % root)

    # Astro always emits its bundles under <base>/_astro/, so the base can be
    # read back off the build. Preferred over the argument, because Git Bash
    # rewrites a leading-slash value into a Windows path ("/" becomes
    # "/C:/Program Files/Git/") and that turns every link into a false failure.
    index = os.path.join(root, "index.html")
    if os.path.isfile(index):
        with open(index, encoding="utf-8", errors="replace") as fh:
            m = re.search(r'(?:href|src)="(/[^"]*?)_astro/', fh.read())
        if m:
            detected = m.group(1)
            if detected != base:
                print("note: using base %s detected from the build (argument was %s)"
                      % (detected, base))
                base = detected

    pages, assets = set(), set()
    for dp, _, files in os.walk(root):
        for f in files:
            rel = os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/")
            assets.add("/" + rel)
            if f == "index.html":
                pages.add("/" + rel[: -len("index.html")].rstrip("/"))

    def exists(url):
        # Strip the base to get back to a path inside dist/.
        if base != "/":
            if not url.startswith(base):
                return None  # signals "missing base", handled by the caller
            url = "/" + url[len(base):]
        url = url.rstrip("/") or "/"
        return url in pages or url in assets

    missing_base = collections.Counter()
    broken = collections.Counter()
    checked = 0
    html_files = 0

    for dp, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".html"):
                continue
            html_files += 1
            with open(os.path.join(dp, f), encoding="utf-8", errors="replace") as fh:
                html = fh.read()
            for m in LINK_RE.finditer(html):
                url = unquote(m.group(1))
                if url.startswith("//"):
                    continue
                checked += 1
                ok = exists(url)
                if ok is None:
                    missing_base[url] += 1
                elif not ok:
                    broken[url] += 1

    print("checked %d internal links across %d pages (base %s)"
          % (checked, html_files, base))

    fail = False
    if missing_base:
        fail = True
        print("\n%d link(s) missing the base prefix — these 404 in production:"
              % sum(missing_base.values()))
        for url, n in missing_base.most_common(20):
            print("   %5dx  %s" % (n, url))
    if broken:
        fail = True
        print("\n%d broken link(s):" % sum(broken.values()))
        for url, n in broken.most_common(20):
            print("   %5dx  %s" % (n, url))

    if fail:
        sys.exit(1)
    print("OK: every internal link resolves and respects the base.")


if __name__ == "__main__":
    main()

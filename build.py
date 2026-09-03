#!/usr/bin/env python
"""Run the whole wiki pipeline: game files -> JSON -> site + MediaWiki XML.

    python wiki/build.py            # data, assets and both renderers
    python wiki/build.py --data     # just re-extract the JSON
    python wiki/build.py --site     # data + assets + static site
    python wiki/build.py --wiki     # data + MediaWiki XML
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
PY = sys.executable


def run(cmd, cwd=None, shell=False):
    print("\n$ %s" % (cmd if isinstance(cmd, str) else " ".join(cmd)))
    r = subprocess.run(cmd, cwd=cwd, shell=shell)
    if r.returncode != 0:
        sys.exit("failed: %s" % (cmd,))


def npm():
    """npm is a .cmd shim on Windows, so it needs the shell."""
    return "npm.cmd" if os.name == "nt" and shutil.which("npm.cmd") else "npm"


def main():
    args = set(sys.argv[1:])
    do_all = not (args & {"--data", "--site", "--wiki"})
    t0 = time.time()

    run([PY, os.path.join(HERE, "extract", "extract.py")])

    if do_all or "--site" in args:
        run([PY, os.path.join(HERE, "extract", "export_assets.py")])
        if not os.path.isdir(os.path.join(SITE, "node_modules")):
            run([npm(), "install"], cwd=SITE)
        run([npm(), "run", "build"], cwd=SITE)
        # Catch broken links and any href that ignores the base path.
        run([PY, os.path.join(HERE, "check_links.py"),
             os.path.join(SITE, "dist"), "--base", os.environ.get("BASE", "/")])

    if do_all or "--wiki" in args:
        run([PY, os.path.join(HERE, "render", "mediawiki.py")])

    print("\nDone in %.1fs" % (time.time() - t0))
    if do_all or "--site" in args:
        print("  site:      wiki/site/dist/       (deploy this)")
    if do_all or "--wiki" in args:
        print("  wiki XML:  wiki/out/*.xml        (Special:Import)")
    print("  data:      wiki/data/*.json       (source of truth)")


if __name__ == "__main__":
    main()

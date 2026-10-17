#!/usr/bin/env python3
"""houseroot.py — find the root of the repository a toolkit script is working on, wherever the toolkit itself lives.

The toolkit sits at  _scripts/  (vendored copy) or at  _packages/toolkit/scripts/  (LaTeX-shared-files as a submodule), so a script
cannot derive the repository root from its own location. The root is the nearest directory, going up from the current directory,
that has a `latexmkrc` file and a `_packages/` directory (this is how `make`, which runs in the root or in a paper directory, calls
the scripts). Falls back to the Git top level, then to the parent of the script directory (the old vendored-only assumption).

    python3 houseroot.py          prints the root
    from houseroot import repo_root
"""
import os
import subprocess
import sys


def _marked(d):
    return os.path.isdir(os.path.join(d, '_packages')) and os.path.exists(os.path.join(d, 'latexmkrc'))


def repo_root(start=None):
    for origin in (start or os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        d = os.path.abspath(origin)
        while True:
            if _marked(d):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    r = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


if __name__ == '__main__':
    print(repo_root(sys.argv[1] if len(sys.argv) > 1 else None))

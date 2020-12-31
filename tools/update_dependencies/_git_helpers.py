import os
import re
import subprocess
from contextlib import contextmanager
from datetime import datetime
from tempfile import TemporaryDirectory
from typing import List

import packaging.version


def _get_tags(url: str, pattern: str) -> List[str]:
    output_raw = subprocess.check_output([
        "git", "ls-remote", "--refs", "--tags", url, pattern
    ])
    output = output_raw.decode("ascii")
    return output.splitlines()


def get_tags(url: str, pattern: str) -> List[str]:
    lines = _get_tags(url, pattern)
    return list([l.split()[-1].split("/")[-1] for l in lines])


GIT_VERSION_RE = re.compile(r"^[\D]*(?P<version>.*)$")


def get_tag_year(url: str, pattern: str, version: str) -> int:
    lines = _get_tags(url, pattern)
    commit = None
    for line in lines:
        line_commit, ref = line.split()
        tag = ref.split("/")[-1]
        match = GIT_VERSION_RE.match(tag)
        if match:
            candidate = packaging.version.parse(match["version"])
            if candidate == version:
                commit = line_commit
                break
    if not commit:
        raise LookupError(f"Cannot find tag for version {version} in {url}")
    with checkout(url, commit, "dummy"):
        output_raw = subprocess.check_output([
            "git", "show", "-s", "--format=%aI", commit
        ])
    return datetime.fromisoformat(output_raw.decode('ascii').strip()).year


@contextmanager
def checkout(url: str, commit: str, branch_name: str):
    with TemporaryDirectory() as path:
        old_cwd = os.getcwd()
        os.chdir(path)
        try:
            subprocess.check_call(["git", "init"])
            subprocess.check_call(["git", "remote", "add", "origin", url])
            subprocess.check_call([
                "git", "-c", "protocol.version=2", "fetch", "--no-tags", "--prune",
                "--progress", "--no-recurse-submodules", "--depth=1", "origin",
                f"+{commit}:refs/remotes/origin/{branch_name}"
            ])
            subprocess.check_call([
                "git", "checkout", "--progress", "--force", "-B",
                f"{branch_name}", f"refs/remotes/origin/{branch_name}"
            ])
            yield
        finally:
            os.chdir(old_cwd)

# git init
# git remote add origin https://github.com/mayeut/manylinux-timeline
# git -c protocol.version=2 fetch --no-tags --prune --progress --no-recurse-submodules --depth=1 origin +b7c447593582db9440f9729321e6e43bf9971d1a:refs/remotes/origin/main
# git checkout --progress --force -B main refs/remotes/origin/main
# git show -s --format=%aI
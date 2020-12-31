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


def get_url(remote: str = "origin") -> str:
    url_raw = subprocess.check_output(["git", "remote", "get-url", remote])
    return url_raw.decode("ascii").strip()


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


@contextmanager
def branch(name: str):
    old_branch_raw = subprocess.check_output(["git", "symbolic-ref", "--short", "HEAD"])
    old_branch = old_branch_raw.decode("ascii").strip()
    subprocess.check_call(["git", "checkout", "-b", f"{name}"])
    #subprocess.check_call(["git", "branch", f"--set-upstream-to=origin"])
    # , "--track", f"origin/{name}"
    try:
        yield
    finally:
        subprocess.check_call(["git", "reset", "--hard"])
        subprocess.check_call(["git", "checkout", "--force", old_branch])


def push() -> None:
    branch_name_raw = subprocess.check_output(["git", "symbolic-ref", "--short", "HEAD"])
    branch_name = branch_name_raw.decode("ascii").strip()
    subprocess.check_call([
        "git", "push", "--force", "--set-upstream", "origin", branch_name])


def add_and_commit(message: str) -> None:
    subprocess.check_call(["git", "add", "--update"])
    subprocess.check_call(["git", "commit", "-m", message])


def create_pr(base_branch: str, message: str) -> None:

    title = "manylinux2010" if base_branch == "master" else base_branch
    title = f"[{title}] {message}"
    body = f"{message}\nCommit created using update scripts"
    subprocess.check_call([
        "gh", "pr", "create", "--repo", "pypa/manylinux", "--base", base_branch, "--title", title, "--body", body
    ])

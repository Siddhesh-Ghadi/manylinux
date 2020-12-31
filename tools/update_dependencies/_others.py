import hashlib
import re
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple

import _git_helpers
import packaging.version
import requests


class UpdateResult(NamedTuple):
    version: str
    version_old: str
    prefix: Optional[str]
    hash: str
    url: str


class _GitTagParameters(NamedTuple):
    url: str
    pattern: str


_GIT_TAG_PARAMETERS_MAP = {
    "AUTOCONF": _GitTagParameters("git://git.sv.gnu.org/autoconf", "v{major}.*"),
    "AUTOMAKE": _GitTagParameters("git://git.sv.gnu.org/automake", "v{major}.*"),
    "GIT": _GitTagParameters("https://github.com/git/git.git", "v{major}.*"),
    "LIBTOOL": _GitTagParameters("git://git.sv.gnu.org/libtool", "v{major}.*"),
    "LIBXCRYPT": _GitTagParameters("https://github.com/besser82/libxcrypt.git",
                                   "v{major}.*"),
    "OPENSSL": _GitTagParameters("https://github.com/openssl/openssl.git",
                                 "OpenSSL_1_1_1[a-z]"),
    "PATCHELF": _GitTagParameters("https://github.com/NixOS/patchelf.git", "{major}.*"),
    "SQLITE_AUTOCONF": _GitTagParameters("https://github.com/mackyle/sqlite.git",
                                         "version-{major}.*")
}


URL_RE_TEMPLATE = \
    r"^[ \t]*{tool}_DOWNLOAD_URL=(?P<quote>[\"']?)(?P<url>[\w:/.%]+)(?P=quote)"
VERSION_RE_TEMPLATE = \
    r"^[ \t]*{tool}_VERSION=(?P<quote>[\"']?)(?P<version>[\w.]+)(?P=quote)"
ROOT_RE_TEMPLATE = (
    r"^[ \t]*{tool}_ROOT=(?P<quote>[\"']?)(?P<prefix>[\w-]+)-(?P<version>[\w.]+)"
    r"(?P=quote)"
)
HASH_RE_TEMPLATE = \
    r"^[ \t]*{tool}_HASH=(?P<quote>[\"']?)(?P<hash>[0-9a-f]{{64}})(?P=quote)"


def _parse_env_file(tool: str, env_file: Path) -> Tuple[str, Optional[str], str]:
    url_re = re.compile(URL_RE_TEMPLATE.format(tool=tool.upper()))
    version_re = re.compile(VERSION_RE_TEMPLATE.format(tool=tool.upper()))
    root_re = re.compile(ROOT_RE_TEMPLATE.format(tool=tool.upper()))
    hash_re = re.compile(HASH_RE_TEMPLATE.format(tool=tool.upper()))
    url = []
    version = []
    hash_ = []
    prefix = None
    with env_file.open() as f:
        for line in f:
            match = url_re.match(line)
            if match:
                url.append(match["url"])
                continue
            match = version_re.match(line)
            if match:
                version.append(match["version"])
                continue
            match = root_re.match(line)
            if match:
                version.append(match["version"])
                prefix = match["prefix"]
                continue
            match = hash_re.match(line)
            if match:
                hash_.append(match["hash"])
                continue

    if len(url) != 1:
        raise LookupError(f"Can't find {tool.upper()}_DOWNLOAD_URL variable exactly "
                          f"once in {env_file}")
    if len(version) != 1:
        raise LookupError(f"Can't find {tool.upper()}_VERSION or {tool.upper()}_ROOT "
                          f"variable exactly once in {env_file}")
    if len(hash_) != 1:
        raise LookupError(f"Can't find {tool.upper()}_HASH variable exactly once in "
                          f"{env_file}")

    return version[0], prefix, url[0]


def update(tool: str, env_file: Path, new_version: UpdateResult) -> None:
    url_re = re.compile(URL_RE_TEMPLATE.format(tool=tool.upper()))
    version_re = re.compile(VERSION_RE_TEMPLATE.format(tool=tool.upper()))
    root_re = re.compile(ROOT_RE_TEMPLATE.format(tool=tool.upper()))
    hash_re = re.compile(HASH_RE_TEMPLATE.format(tool=tool.upper()))
    lines = env_file.read_text().splitlines(keepends=True)
    with env_file.open("w") as f:
        for line in lines:
            match = url_re.match(line)
            if match:
                line = f"{tool.upper()}_DOWNLOAD_URL={new_version.url}\n"
            match = version_re.match(line)
            if match:
                line = f"{tool.upper()}_VERSION={new_version.version}\n"
            match = root_re.match(line)
            if match:
                line = \
                    f"{tool.upper()}_ROOT={new_version.prefix}-{new_version.version}\n"
            match = hash_re.match(line)
            if match:
                line = f"{tool.upper()}_HASH={new_version.hash}\n"
            f.write(line)


GIT_VERSION_RE = re.compile(r"^[\D]*(?P<version>.*)$")


def _filter_git_tags(tool: str, version: str) -> Iterable[str]:
    version_semver = packaging.version.parse(version)
    parameters = _GIT_TAG_PARAMETERS_MAP[tool.upper()]
    candidates = _git_helpers.get_tags(
        parameters.url,
        parameters.pattern.format(major=version_semver.major)
    )
    filtered = []
    for candidate in candidates:
        candidate_str = GIT_VERSION_RE.match(candidate)["version"]
        if tool.upper() == "OPENSSL":
            candidate_str = _patch_version(tool, candidate_str)
        candidate_semver = packaging.version.parse(candidate_str)
        if candidate_semver > version_semver and not candidate_semver.is_prerelease:
            filtered.append(candidate_semver)
    filtered.sort(reverse=True)
    return [str(v) for v in filtered]


def _patch_version(tool: str, version: str) -> str:
    if tool.upper() == 'SQLITE_AUTOCONF':
        version_int = int(version)
        major = version_int // 1000000
        version_int -= major * 1000000
        minor = version_int // 10000
        version_int -= minor * 10000
        patch = version_int // 100
        return f'{major}.{minor}.{patch}'
    elif tool.upper() == 'OPENSSL':
        patch = ord(version[-1])
        return f'{version.replace("_", ".")[:-1]}.{patch}'
    return version


def _unpatch_version(tool: str, candidates: Iterable[str]) -> Iterable[str]:
    if tool.upper() == 'SQLITE_AUTOCONF':
        unpatched_candidates = []
        for candidate in candidates:
            version = packaging.version.parse(candidate)
            if len(version.release) < 4:
                # we don't want branch versions
                version_int = version.major * 1000000
                version_int += version.minor * 10000
                version_int += version.micro * 100
                unpatched_candidates.append(f"{version_int}")
        return unpatched_candidates
    elif tool.upper() == 'OPENSSL':
        unpatched_candidates = []
        for candidate in candidates:
            version = packaging.version.parse(candidate)
            unpatched_candidates.append(
                f"{'.'.join(str(p) for p in version.release[:3])}"
                f"{chr(version.release[3])}")
        return unpatched_candidates
    return candidates


def _patch_url(tool: str, url: str, version: str) -> str:
    if tool.upper() == "SQLITE_AUTOCONF":
        version_semver = packaging.version.parse(_patch_version(tool, version))
        parameters = _GIT_TAG_PARAMETERS_MAP[tool.upper()]
        year = _git_helpers.get_tag_year(
            parameters.url, parameters.pattern.format(major=version_semver.major),
            version_semver
        )
        parts = url.split("/")
        parts[-1] = str(year)
        return "/".join(parts)

    return url


def _get_result(
        tool: str, prefix: Optional[str], url: str, candidates: Iterable[str],
        version_old: str
) -> UpdateResult:
    prefix_string = ""
    if prefix:
        prefix_string = f"{prefix}-"
    for candidate in candidates:
        test_url = _patch_url(tool, url, candidate)
        for candidate_prefix in {"", "v"}:
            full_url = (f"{test_url.rstrip('/')}/{prefix_string}{candidate_prefix}"
                        f"{candidate}.tar.gz")
            response = requests.get(full_url)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                continue
            # TODO try to get signatures/hashes differently
            # e.g. sha256sums.asc for git which is signed
            hash_ = hashlib.sha256(response.content).hexdigest()
            return UpdateResult(candidate, version_old, prefix, hash_, url)


def get_update_map(tool: str, env_file: Path) -> Optional[UpdateResult]:
    version, prefix, url = _parse_env_file(tool, env_file)
    version_patched = _patch_version(tool, version)
    candidates = _filter_git_tags(tool, version_patched)
    candidates = _unpatch_version(tool, candidates)
    return _get_result(tool, prefix, url, candidates, version)

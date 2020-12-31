import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

import packaging.version
import requests


class _CandidateRelease(NamedTuple):
    version: packaging.version.Version
    release: Optional[int]


def _get_id(resource_uri: str) -> int:
    return int(resource_uri.rstrip('/').split('/')[-1])


def _get_os() -> int:
    response = requests.get('https://www.python.org/api/v2/downloads/os/?slug=source')
    response.raise_for_status()
    os_info = response.json()
    assert len(os_info) == 1
    return _get_id(os_info[0]['resource_uri'])


def _get_update(
    bin_: List[_CandidateRelease], os_: int, url: str
) -> packaging.version.Version:
    current_version = bin_[0].version
    candidates = list(bin_[1:])
    candidates.sort(key=lambda x: x.version, reverse=True)
    for pre_release in {False, current_version.is_prerelease}:
        for candidate in candidates:
            if candidate.version.is_prerelease != pre_release:
                continue
            # manylinux hard-codes URL now. Only the version is mutable.
            expected_url = (f"{url.rstrip('/')}/{candidate.version.base_version}"
                            f"/Python-{candidate.version}.tgz")
            response = requests.get(
                f"https://www.python.org/api/v2/downloads/release_file/?os={os_}&"
                f"release={candidate.release}"
            )
            response.raise_for_status()
            file_info = response.json()
            for file in file_info:
                if file['url'] == expected_url:
                    return candidate.version

    return current_version


def _get_release(
        current_versions: List[packaging.version.Version], os_: int, url: str
) -> List[packaging.version.Version]:
    response = requests.get(
        'https://www.python.org/api/v2/downloads/release/?version=3&is_published=true')
    response.raise_for_status()
    release_info = response.json()
    bin_ = {}
    for current_version in current_versions:
        bin_key = f'{current_version.major}.{current_version.minor}'
        bin_[bin_key] = [_CandidateRelease(current_version, None)]
    for release in release_info:
        parts = release['name'].split()
        if parts[0].lower() != 'python':
            continue
        assert len(parts) == 2
        version = packaging.version.parse(parts[1])
        bin_key = f'{version.major}.{version.minor}'
        if bin_key not in bin_.keys():
            continue
        current = bin_[bin_key][0]
        if version <= current.version:
            continue
        if version.is_postrelease or version.is_devrelease:
            continue
        if version.is_prerelease and not current.version.is_prerelease:
            continue
        bin_[bin_key].append(
            _CandidateRelease(version, _get_id(release['resource_uri'])))
    updates = []
    for current_version in current_versions:
        bin_key = f'{current_version.major}.{current_version.minor}'
        updates.append(_get_update(bin_[bin_key], os_, url))
    return updates


URL_RE = re.compile(
    r"^[ \t]*PYTHON_DOWNLOAD_URL=(?P<quote>[\"']?)(?P<url>[\w:/.%]+)(?P=quote)")
VERSION_RE = re.compile(
    r"^[ \t]*CPYTHON_VERSIONS=(?P<quote>[\"'])(?P<versions>[\w. ]+)(?P=quote)")


def _parse_env_file(env_file: Path) -> Tuple[List[str], str]:
    url = []
    versions = []
    with env_file.open() as f:
        for line in f:
            match = URL_RE.match(line)
            if match:
                url.append(match["url"])
                continue
            match = VERSION_RE.match(line)
            if match:
                versions.append(match["versions"])
    if len(url) != 1:
        raise LookupError("Can't find PYTHON_DOWNLOAD_URL variable exactly once in "
                          f"{env_file}")
    if len(versions) != 1:
        raise LookupError("Can't find CPYTHON_VERSIONS variable exactly once in "
                          f"{env_file}")

    return [v.strip() for v in versions[0].split() if v.strip() != ""], url[0]


def update(env_file: Path, old_version: str, new_version: str) -> None:
    lines = env_file.read_text().splitlines(keepends=True)
    with env_file.open("w") as f:
        for line in lines:
            match = VERSION_RE.match(line)
            if match:
                line = line.replace(old_version, new_version)
            f.write(line)


def get_update_map(env_file: Path) -> Dict[str, str]:
    versions, url = _parse_env_file(env_file)
    os_ = _get_os()
    current_versions = list([packaging.version.parse(v) for v in versions])
    new_versions = _get_release(current_versions, os_, url)
    map_ = {}
    for i in range(len(versions)):
        new_version_str = str(new_versions[i])
        if new_version_str != versions[i]:
            map_[versions[i]] = new_version_str
    return map_

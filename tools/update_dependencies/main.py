from pathlib import Path

import _git_helpers
import _others
import _python


ROOT_PATH = Path(__file__).parent.parent.parent
ENV_PATH = ROOT_PATH / "docker" / "build_scripts" / "build_env.sh"


if __name__ == "__main__":
    if not ENV_PATH.exists():
        raise FileNotFoundError(ENV_PATH)

    if not ENV_PATH.is_file():
        raise IsADirectoryError(ENV_PATH)

    python_map = _python.get_update_map(ENV_PATH)
    for old_version, new_version in python_map.items():
        _python.update(ENV_PATH, old_version, new_version)

    for tool in {'autoconf', 'automake', 'git', 'libtool', 'libxcrypt', 'openssl',
                 'patchelf', 'sqlite_autoconf'}:
        update_result = _others.get_update_map(tool, ENV_PATH)
        if update_result:
            _others.update(tool, ENV_PATH, update_result)

    # git ls-remote --refs --tags https://github.com/Kitware/CMake.git 'v*'
    # git ls-remote --refs --tags https://github.com/swig/swig.git 'v*'
    # https://lwn.net/Articles/839395/
    # git ls-remote --refs --tags git://git.sv.gnu.org/m4 'v*'

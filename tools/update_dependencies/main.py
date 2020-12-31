from pathlib import Path

import _git_helpers
import _others
import _python


#ROOT_PATH = Path(__file__).parent.parent.parent


if __name__ == "__main__":
    base_branch = "master"
    with _git_helpers.checkout(
            _git_helpers.get_url(), f"refs/heads/{base_branch}", base_branch):

        ENV_PATH = Path('.') / "docker" / "build_scripts" / "build_env.sh"
        if not ENV_PATH.exists():
            raise FileNotFoundError(ENV_PATH)

        if not ENV_PATH.is_file():
            raise IsADirectoryError(ENV_PATH)

        python_map = _python.get_update_map(ENV_PATH)
        for old_version, new_version in python_map.items():
            with _git_helpers.branch(f"update/{base_branch}/python-{old_version}"):
                _python.update(ENV_PATH, old_version, new_version)
                _git_helpers.add_and_commit(
                    f"Update python from {old_version} to {new_version}")
                _git_helpers.push()
                _git_helpers.create_pr(base_branch)

        for tool in {'autoconf', 'automake', 'git', 'libtool', 'libxcrypt', 'openssl',
                     'patchelf', 'sqlite_autoconf'}:
            update_result = _others.get_update_map(tool, ENV_PATH)
            if update_result:
                branch_name = f"update/{base_branch}/{tool}-{update_result.version_old}"
                message = (f"Update {tool} from {update_result.version_old} to "
                           f"{update_result.version}")
                with _git_helpers.branch(branch_name):
                    _others.update(tool, ENV_PATH, update_result)
                    _git_helpers.add_and_commit(message)
                    _git_helpers.push()
                    _git_helpers.create_pr(base_branch, message)

    # git ls-remote --refs --tags https://github.com/Kitware/CMake.git 'v*'
    # git ls-remote --refs --tags https://github.com/swig/swig.git 'v*'
    # https://lwn.net/Articles/839395/
    # git ls-remote --refs --tags git://git.sv.gnu.org/m4 'v*'

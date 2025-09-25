# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run by cookicutter after project generation to turn resolved symlinks back into symlinks."""

import os
import pathlib
import shutil
import sys
import warnings

##############################################################################
# move src/charmlibs/* to src/charmlibs/interfaces/* for interface libraries #
##############################################################################

# evaluated with jinja2 by cookiecutter
# False by default, set to True by `just interface init`
if {{cookiecutter._interface}}:  # noqa: F821
    charmlibs = pathlib.Path('src', 'charmlibs')
    tmp = charmlibs.rename('.tmp')
    charmlibs.mkdir()
    tmp.rename(charmlibs / 'interfaces')

#########################################################################################
# unresolve symlinks -- we use these in the template for a better maintainer experience #
#########################################################################################

# abort if CHARMLIBS_TEMPLATE environment  variable is not set
ABORT_MSG = """
CHARMLIBS_TEMPLATE is not set, did you run cookiecutter via `just init`?
Aborting `post_gen_project` hook without restoring symlinks ...
""".strip()
TEMPLATE_DIR = os.environ.get('CHARMLIBS_TEMPLATE')
if not TEMPLATE_DIR:
    warnings.warn(ABORT_MSG, stacklevel=2)
    sys.exit()

# get the relative path to every symlink in the template, and its target as a string
TEMPLATE_PROJECT_ROOT = pathlib.Path(
    TEMPLATE_DIR,
    # we use raw to preserve the templated dir name as cookiecutter runs this script through jinja
    '{% raw %}{{ cookiecutter.project_slug }}{% endraw %}',
)
RELATIVE_SYMLINK_PATHS = {
    path.relative_to(TEMPLATE_PROJECT_ROOT): str(path.readlink())
    for path in TEMPLATE_PROJECT_ROOT.rglob('*')
    if path.is_symlink()
}

# iterate over relative paths and relink them in current working directory (generated project)
for symlink_path, target in RELATIVE_SYMLINK_PATHS.items():
    # remove resolved copy of symlink target created by cookiecutter
    if symlink_path.is_dir():
        shutil.rmtree(symlink_path)
    else:
        symlink_path.unlink()
    symlink_path.symlink_to(target)

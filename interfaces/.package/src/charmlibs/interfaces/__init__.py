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

"""This package should not be installed! It only reserves the PyPI charmlibs.interfaces namespace.

For more information, see the PyPI page at https://pypi.org/project/charmlibs-interfaces
"""

import warnings

__version__ = '1.0.0a0'

warnings.warn('This package should not be installed.', stacklevel=1)

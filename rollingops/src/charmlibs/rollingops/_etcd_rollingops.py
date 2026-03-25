# Copyright 2026 Canonical Ltd.
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


import argparse
import subprocess
import time


def main():
    """Juju hook event dispatcher."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-cmd', required=True)
    parser.add_argument('--unit-name', required=True)
    parser.add_argument('--charm-dir', required=True)
    parser.add_argument('--owner', required=True)
    args = parser.parse_args()

    time.sleep(10)

    dispatch_sub_cmd = (
        f'JUJU_DISPATCH_PATH=hooks/rollingops_lock_granted {args.charm_dir}/dispatch'
    )
    res = subprocess.run([args.run_cmd, '-u', args.unit_name, dispatch_sub_cmd])
    res.check_returncode()


if __name__ == '__main__':
    main()

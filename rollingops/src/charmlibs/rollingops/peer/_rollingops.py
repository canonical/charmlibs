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

"""Background process."""

import argparse
import time

from charmlibs.rollingops.common._utils import dispatch_lock_granted, setup_logging


def main():
    """Juju hook event dispatcher."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--unit-name', required=True)
    parser.add_argument('--charm-dir', required=True)
    args = parser.parse_args()
    setup_logging('/var/log/peer_rollingops_worker.log')

    # Sleep so that the leader unit can properly leave the hook and start a new one
    time.sleep(10)

    dispatch_lock_granted(args.unit_name, args.charm_dir)


if __name__ == '__main__':
    main()

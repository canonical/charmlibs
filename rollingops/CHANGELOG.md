# 1.1.3 - 25 August 2026

Fix:
- Stop falling back to the peer backend when an `update-status` (or a second
  lock-granted hook) runs while the etcd worker is between operations. Finding
  an empty in-progress queue while holding the lock is a normal transient state
  during retries, not an etcd/peer inconsistency.

# 1.1.2 - 22 July 2026

Broaden the supported Python version range to `>=3.10`.

# 1.1.1 - 22 May 2026

Fix:
- Dynamic cluster ID integration with etcd
- Sync lock exception handling during critical path execution

# 1.1.0 - 20 May 2026

Extend the `RollingOpsManager` is_waiting_* helpers to receive a unit name.

# 1.0.1 - 04 May 2026

Fix the `ModelError` messages generated during rollback operations.

# 1.0.0 - 28 April 2026

Initial release of `charmlibs-rollingops` library

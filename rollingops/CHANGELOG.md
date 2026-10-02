# 1.1.2 - 02 October 2026

Fix:
- Publish the etcd request for an existing relation once the `cluster_id` becomes
  available, instead of requiring the relation to be recreated.

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

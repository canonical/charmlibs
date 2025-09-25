(how-to-customize-integration-tests)=
# How to customize your integration tests

In its integration tests, your library will be packed into one or more charms, those charms will be deployed with Juju, and your tests will run against the deployed charms.
You can customise your integration tests in several ways, according to the needs of your library.
You'll determine whether it makes sense to test on both K8s and machine clouds, with one or more charms, and whether to rerun the integration tests with other permutations.

> Read more: {ref}`charmlibs-tests`

Integration tests are only executed if the `<LIBRARY>/tests/integration` directory exists.
If you don't need integration tests, remove the directory.
However, it's recommended to have at least some Juju integration tests to ensure that your library can be used as expected in a real charm.

Your integration tests will be run in CI with a matrix of Juju substrates, and a list of `tags` defined in your `pyproject.toml` under:
```toml
[tool.charmlibs.integration]
```
The substrate (`k8s` or `machine`) determines the type of cloud bootstrapped by [concierge](https://github.com/canonical/concierge), and is exposed as an environment variable (`CHARMLIBS_SUBSTRATE`).
The tag is also made available as an environment variable (`CHARMLIBS_TAG`), and is otherwise unused by the CI machinery.
The default is to run once per substrate with no tag (`CHARMLIBS_TAG=`).

You can use `pytest` marks to declare certain tests to be run only with K8s charms or only with machine charms.
If your library is intended for K8s or machine charms only, you should mark your tests accordingly -- you can mark an entire test module with, for example, `pytestmark = pytest.mark.k8s_only`, or use [pytest_collection_modifyitems](https://docs.pytest.org/en/latest/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems) to ensure all your integration tests are marked.
If no tests are collected for one substrate, it will be skipped in CI.
(If no tests are collected for either substrate, there will be an error.)

After setting up the test environment with `concierge`, if your library has a `tests/integration/pack.sh` script, it will be executed. The template provides a script that packs a different minimal charm depending on the substrate, using symlinks to share common code and metadata, and resolving these before packing. You can modify this script to pack one or more charms to be deployed in your integration tests. Both `CHARMLIBS_SUBSTRATE` and `CHARMLIBS_TAG` are set when running `pack.sh`, which you can use to change what gets packed.

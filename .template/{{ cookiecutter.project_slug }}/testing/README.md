# {{ cookiecutter.__import_pkg }}_testing

The `{{ cookiecutter.project_slug }}` testing library. Charms that use `{{ cookiecutter.project_slug }}` should use this library in their state-transition tests, so that they don't need to know the underlying relation data format.

To install, add `{{ cookiecutter.__dist_pkg }}[testing]` to your test dependencies — not `{{ cookiecutter.__dist_pkg }}-testing` directly, so that the testing package version always matches the library itself. Then in your Python code, import as:

```py
from {{ cookiecutter.__ns }} import {{ cookiecutter.__pkg }}_testing
```

Read more:
- [How to use a testing package in state-transition tests](https://canonical.com/juju/docs/charmlibs/how-to/use-a-testing-package/)
- [Testing package reference](https://canonical.com/juju/docs/charmlibs/reference/testing/{{ cookiecutter.__dist_pkg }}-testing/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/{{ cookiecutter.__path_prefix }}{{ cookiecutter.__canonical_name }}/)

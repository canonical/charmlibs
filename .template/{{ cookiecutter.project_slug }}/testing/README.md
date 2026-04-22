# {{ cookiecutter.__import_pkg }}_testing

The `{{ cookiecutter.project_slug }}` testing library. Charms that use `{{ cookiecutter.project_slug }}` should use this library in their state-transition tests.

To install, add `{{ cookiecutter.__dist_pkg }}-testing` to your Python dependencies. Then in your Python code, import as:

```py
from {{ cookiecutter.__ns }} import {{ cookiecutter.__pkg }}_testing
```

See the [library reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/{{ cookiecutter.__path_prefix }}{{cookiecutter.__pkg}}) for more.

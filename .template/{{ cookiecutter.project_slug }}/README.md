# {{ cookiecutter.__import_pkg }}

The `{{ cookiecutter.project_slug }}` {{ 'interface ' if cookiecutter._interface else '' }}library.

To install, add `{{ cookiecutter.__dist_pkg }}` to your Python dependencies. Then in your Python code, import as:

```py
from {{ cookiecutter.__ns }} import {{ cookiecutter.__pkg }}
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/{{ cookiecutter.__path_prefix }}{{cookiecutter.__canonical_name}}) for more.

# charmlibs-{{ 'interfaces-' if cookiecutter._interface else '' }}{{ cookiecutter.project_slug }}

The `{{ cookiecutter.project_slug }}` {{ 'interface ' if cookiecutter._interface else '' }}library.

To install, add `charmlibs-{{ 'interfaces-' if cookiecutter._interface else '' }}{{ cookiecutter.project_slug }}` to your Python dependencies. Then in your Python code, import as:

```py
from charmlibs{{ '.interfaces' if cookiecutter._interface else '' }} import {{ cookiecutter.project_slug }}
```

See the [reference documentation](https://documentation.ubuntu.com/charmlibs/reference/charmlibs/{{ 'interfaces/' if cookiecutter._interface else '' }}{{ cookiecutter.project_slug}}) for more.

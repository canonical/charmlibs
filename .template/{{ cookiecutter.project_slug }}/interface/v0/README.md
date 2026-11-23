# {{ cookiecutter.project_slug }}

One or two sentences saying what the interface is for, and which side holds what.
{%- if cookiecutter._definition_only %}
Then name the library that charms should use to implement the interface, linked on PyPI or Charmhub.
{%- else %}
Charms should use [`{{ cookiecutter.__import_pkg }}`](https://pypi.org/project/{{ cookiecutter.__dist_pkg }}/) to implement it.
{%- endif %}

## Direction

Say whether the interface is unidirectional or bidirectional, which side writes first, and what the other side writes in response.
The docs build adds a diagram of who writes which fields, so only add a diagram here if the order of the exchanges matters.

## Behavior

Keywords are as in RFC 2119.

### Provider

- MUST ...

### Requirer

- MUST ...

## Relation data

### Provider

#### Example

```yaml
application-data:
  url: https://example.com
```

### Requirer

#### Example

```yaml
application-data:
  name: my-app
```

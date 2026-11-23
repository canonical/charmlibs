# example-interface

One or two sentences saying what the interface is for, and which side holds what.
Charms should use [`charmlibs.interfaces.example_interface`](https://pypi.org/project/charmlibs-interfaces-example-interface/) to implement it.

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

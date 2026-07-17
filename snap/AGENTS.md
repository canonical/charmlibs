Always run these checks before reporting completion:
```
just format snap
just lint snap
just unit snap
```
For substantial changes, run the real snapd API tests in a workshop container (`workshop launch resolute` first if needed; full suite ~5 min, select tests with `-k '<expression>'`):
```
workshop exec resolute -- sudo just functional snap
```

## Checking the snapd API directly

The repo root is mounted in the workshop container, so scripts written on the host run there and vice versa. Quick options:

```bash
# curl directly against snapd
workshop exec resolute -- sudo curl -s --unix-socket /run/snapd.socket http://localhost/v2/logs?names=<snap>&n=1

# or run a Python script using _client
workshop exec resolute -- sudo uvx --with-editable ./snap python script.py

# interactive shell
workshop shell resolute
```

## Strategy for adding tests (capture-then-assert)

**Never guess what the snapd API returns.** Always capture real responses first, then write assertions against them. This applies to both error paths and success responses.

1. **Capture**: Run the real API call in a workshop container and record the raw response (and/or the resulting exception). A simple way is a throwaway script using `_client` directly, or a temporary functional test that dumps the response to a JSON file.
2. **Assert**: Replace the capture with real assertions using the captured data — the most specific error class, `kind`, `message`, and `value`.
3. **Mirror in unit tests**: Add a unit test that mocks `_client` to raise/return the captured response and asserts the function under test handles it correctly.
4. **Consider new error classes**: If a captured `kind` falls through to base `APIError` and a charm author might reasonably want to catch it specifically, add a dedicated subclass in `_errors.py`, wire it into `_error_type_from_result_kind`, and export it from `__init__.py`.
5. **Update docstrings**: Add any newly-discovered raisable errors to the function's `Raises:` section.

mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes

# set on the commandline as needed, e.g. `just package=pathops python=3.10 unit`
python := '3.10'

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc('Describe usage and list the available recipes.')]
_help:
    @echo 'All recipes require {{CYAN}}`uv`{{NORMAL}} to be available.'
    @just --list --unsorted --list-submodules

[doc('Run `ruff` and `codespell`, failing afterwards if any errors are found.')]
fast-lint:
    #!/usr/bin/env -S bash -xueo pipefail
    FAILURES=0
    uv run ruff check --preview || ((FAILURES+=1))
    uv run ruff check --preview --diff || ((FAILURES+=1))
    uv run ruff format --preview --diff || ((FAILURES+=1))
    uv run codespell --toml=pyproject.toml || ((FAILURES+=1))
    : "$FAILURES command(s) failed."
    exit $FAILURES

[doc('Run `ruff check --fix` and `ruff --format`, modifying files in place.')]
format:
    uv run ruff check --preview --fix
    uv run ruff format --preview

[doc('Run global `fast-lint` and package specific `static` analysis, e.g. `just python=3.10 lint pathops`.')]
lint package *pyright_args: fast-lint (static package pyright_args)

[doc('Run package specific static analysis only, e.g. `just python=3.10 static pathops`.')]
static package *pyright_args: (_venv package 'lint' 'unit' 'functional' 'integration')
    #!/usr/bin/env -S bash -xueo pipefail
    source .venv/bin/activate
    cd '{{package}}'
    uv run --active pyright --pythonversion='{{python}}' {{pyright_args}}

[doc("Run unit tests with `coverage`, e.g. `just python=3.10 unit pathops`.")]
unit package +flags='-rA': (_venv package 'unit') (_coverage package 'unit' flags)

[doc("Run functional tests with `coverage`, e.g. `just python=3.10 functional pathops`.")]
functional package +flags='-rA': (_venv package 'functional') (_coverage package 'functional' flags)

[doc("Set up virtual environment for tests, installing `package` with `groups` if specified.")]
_venv package *groups:
    #!/usr/bin/env -S bash -x
    GROUP_OPTS=$(just --justfile='{{justfile()}}' python='{{python}}' _groups {{package}} {{groups}})
    set -xeuo pipefail  # -e and -u will early exit if just _groups has no output
    uv sync  # ensure venv exists before uv pip install
    uv pip install --editable './{{package}}' $GROUP_OPTS

[doc("Print --group flags for specified `groups` if they're in `package`'s dependency-groups.")]
_groups package *groups:
    #!/usr/bin/env -S uv run --script --no-project
    # /// script
    # requires-python = ">=3.11"
    # ///
    import pathlib, tomllib
    table = tomllib.loads(pathlib.Path('./{{package}}/pyproject.toml').read_text()).get('dependency-groups', {})
    print(' '.join(f'--group=./{{package}}/pyproject.toml:{group}' for group in '{{groups}}'.split() if group in table), end='')

[doc("Run functional tests with `coverage` and a live `pebble` running. Requires `pebble`.")]
functional-pebble package +flags='-rA':
    #!/usr/bin/env -S bash -xueo pipefail
    export PEBBLE=/tmp/pebble-test
    umask 0
    pebble run --create-dirs &>/dev/null &
    PEBBLE_PID=$!
    set +e  # don't exit if the tests fail
    just --justfile='{{justfile()}}' python='{{python}}' functional '{{package}}' {{flags}}
    EXITCODE=$?
    set -e  # do exit if anything goes wrong now
    kill $PEBBLE_PID
    exit $EXITCODE

[doc("Use uv to install and run coverage for the specified package's tests.")]
_coverage package test_subdir +flags:
    #!/usr/bin/env -S bash -xueo pipefail
    source .venv/bin/activate
    cd '{{package}}'
    export COVERAGE_RCFILE='{{justfile_directory()}}/pyproject.toml'
    DATA_FILE=".report/coverage-$(basename {{test_subdir}})-{{python}}.db"
    uv run --active coverage run --data-file="$DATA_FILE" --source='src' \
        -m pytest --tb=native -vv {{flags}} 'tests/{{test_subdir}}'
    uv run --active coverage report --data-file="$DATA_FILE"

[doc("Combine `coverage` reports, e.g. `just python=3.10 combine-coverage pathops`.")]
combine-coverage package:
    #!/usr/bin/env -S bash -xueo pipefail
    : 'Collect the coverage data files that exist for this package.'
    data_files=()
    for test_id in unit functional juju; do
        data_file="{{package}}/.report/coverage-$test_id-{{python}}.db"
        if [ -e "$data_file" ]; then
            data_files+=("$data_file")
        fi
    done
    : 'Combine coverage.'
    export COVERAGE_RCFILE=pyproject.toml
    DATA_FILE='{{package}}/.report/coverage-all-{{python}}.db'
    HTML_DIR='{{package}}/.report/htmlcov-all-{{python}}'
    uv run coverage combine --keep --data-file="$DATA_FILE" "${data_files[@]}"
    uv run coverage xml --data-file="$DATA_FILE" -o '{{package}}/.report/coverage-all-{{python}}.xml'
    rm -rf "$HTML_DIR"  # let coverage create html directory from scratch
    uv run coverage html --data-file="$DATA_FILE" --show-contexts --directory="$HTML_DIR"
    uv run coverage report --data-file="$DATA_FILE"

[doc("Execute pack script to pack Kubernetes charm(s) for Juju integration tests.")]
pack-k8s package base='24.04': (_pack package 'k8s' base)

[doc("Execute pack script to pack machine charm(s) for Juju integration tests.")]
pack-machine package base='24.04': (_pack package 'machine' base)

[doc("Execute the pack script for the given package and substrate.")]
_pack package substrate base:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}/tests/integration'
    CHARMLIBS_SUBSTRATE={{substrate}} CHARMLIBS_BASE={{base}} ./pack.sh

[doc("Run juju integration tests for packed Kubernetes charm(s). Requires `juju`.")]
integration-k8s package +flags='-rA': (_integration package 'k8s' 'not machine_only' flags)

[doc("Run juju integration tests for packed Kubernetes charm(s). Requires `juju`.")]
integration-machine package +flags='-rA': (_integration package 'machine' 'not k8s_only' flags)

[doc("Run juju integration tests. Requires `juju`.")]
_integration package substrate label +flags: (_venv package 'integration')
    #!/usr/bin/env -S bash -xueo pipefail
    source .venv/bin/activate
    cd '{{package}}'
    CHARMLIBS_SUBSTRATE={{substrate}} uv run pytest --tb=native -vv -m '{{label}}' tests/integration  {{flags}}

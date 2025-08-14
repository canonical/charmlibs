mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes

# set on the commandline as needed, e.g. `just package=pathops python=3.8 unit`
python := '3.12'

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc('Describe usage and list the available recipes.')]
_help:
    @echo 'All recipes require {{CYAN}}`uv`{{NORMAL}} to be available.'
    @just --list --unsorted --list-submodules

[doc('Run `ruff` and `codespell`, failing afterwards if any errors are found.')]
fast-lint:
    #!/usr/bin/env bash
    set -xueo pipefail
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

[doc('Run `pyright`, e.g. `just python=3.8 static pathops`.')]
lint package *pyright_args:
    just --justfile='{{justfile()}}' python='{{python}}' fast-lint
    uv sync  # ensure venv exists before uv pip install
    uv pip install --editable './{{package}}'
    uv run pyright --pythonversion='{{python}}' {{pyright_args}} '{{package}}'

[doc("Run unit tests with `coverage`, e.g. `just python=3.8 unit pathops`.")]
unit package +flags='-rA': (_coverage package 'unit' flags)

[doc("Run ubuntu integration tests with `coverage`, e.g. `just python=3.8 ubuntu pathops`.")]
ubuntu package +flags='-rA': (_coverage package 'integration/ubuntu' flags)

[doc("Run pebble integration tests with `coverage`. Requires `pebble`.")]
pebble package +flags='-rA':
    #!/usr/bin/env bash
    set -xueo pipefail
    export PEBBLE=/tmp/pebble-test
    umask 0
    pebble run --create-dirs &>/dev/null &
    PEBBLE_PID=$!
    set +e  # don't exit if the tests fail
    just --justfile='{{justfile()}}' python='{{python}}' _coverage '{{package}}' 'integration/pebble' {{flags}}
    EXITCODE=$?
    set -e  # do exit if anything goes wrong now
    kill $PEBBLE_PID
    exit $EXITCODE

[doc("Use uv to install and run coverage for the specified package's tests.")]
_coverage package test_subdir +flags:
    #!/usr/bin/env bash
    set -xueo pipefail
    uv sync --python='{{python}}'
    uv pip install --editable './{{package}}'
    source .venv/bin/activate
    cd '{{package}}'
    export COVERAGE_RCFILE='{{justfile_directory()}}/pyproject.toml'
    DATA_FILE=".report/coverage-$(basename {{test_subdir}})-{{python}}.db"
    uv run --active coverage run --data-file="$DATA_FILE" --source='src' \
        -m pytest --tb=native -vv {{flags}} 'tests/{{test_subdir}}'
    uv run --active coverage report --data-file="$DATA_FILE"

[doc("Combine `coverage` reports, e.g. `just python=3.8 combine-coverage pathops`.")]
combine-coverage package:
    #!/usr/bin/env bash
    set -xueo pipefail
    : 'Collect the coverage data files that exist for this package.'
    data_files=()
    for test_id in unit ubuntu pebble juju; do
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
pack-k8s package base='24.04': (_pack package 'kubernetes' base)

[doc("Execute pack script to pack machine charm(s) for Juju integration tests.")]
pack-vm package base='24.04': (_pack package 'machine' base)

[doc("Execute the pack script for the given package and substrate.")]
_pack package substrate base:
    #!/usr/bin/env bash
    set -xueo pipefail
    cd '{{package}}/tests/integration/juju/charms'
    ./pack.sh {{substrate}} {{base}}

[doc("Run juju integration tests for packed Kubernetes charm(s). Requires `juju`.")]
juju-k8s package +flags='-rA': (_juju package 'kubernetes' flags)

[doc("Run juju integration tests for packed Kubernetes charm(s). Requires `juju`.")]
juju-vm package +flags='-rA': (_juju package 'machine' flags)

[doc("Run juju integration tests. Requires `juju`.")]
_juju package substrate +flags:
    #!/usr/bin/env bash
    set -xueo pipefail
    uv sync --python='{{python}}'
    uv pip install --editable './{{package}}'
    source .venv/bin/activate
    cd '{{package}}'
    uv run --active pytest --tb=native -vv {{flags}} tests/integration/juju --substrate='{{substrate}}'

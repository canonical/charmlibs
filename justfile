mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes

# set on the commandline as needed, e.g. `just package=pathops python=3.8 unit`
python := '3.10'

_coverage := 'coverage==7.6.1'
_pyright := 'pyright==1.1.397'
_pytest := 'pytest==8.3.5'
_with_test_deps := '--with ' + _coverage + ' --with ' + _pyright + ' --with ' + _pytest

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc('Describe usage and list the available recipes.')]
_help:
    @echo 'All recipes require {{CYAN}}`uv`{{NORMAL}} to be available.'
    @just --list --unsorted --list-submodules

[doc('Run `ruff` and `codespell`, failing afterwards if any errors are found.')]
fast-lint:
    #!/usr/bin/env -S bash -xueo pipefail
    FAILURES=0
    uv run --only-group=fast-lint ruff check --preview || ((FAILURES+=1))
    uv run --only-group=fast-lint ruff check --preview --diff || ((FAILURES+=1))
    uv run --only-group=fast-lint ruff format --preview --diff || ((FAILURES+=1))
    uv run --only-group=fast-lint codespell --toml=pyproject.toml || ((FAILURES+=1))
    : "$FAILURES command(s) failed."
    exit $FAILURES

[doc('Run `ruff check --fix` and `ruff --format`, modifying files in place.')]
format:
    uv run ruff format --preview
    uv run ruff check --preview --fix

[doc('Run global `fast-lint` and package specific `static` analysis, e.g. `just python=3.8 lint pathops`.')]
lint package *pyright_args: fast-lint (static package pyright_args)

[doc('Run package specific static analysis only, e.g. `just python=3.8 static pathops`.')]
static package *args:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}'
    uv run {{_with_test_deps}} \
        --group lint --group unit --group functional --group integration \
        pyright --pythonversion='{{python}}' {{args}}

[doc("Run unit tests with `coverage`, e.g. `just python=3.8 unit pathops`.")]
unit package +flags='-rA': (_coverage package 'unit' flags)

[doc("Run functional tests with `coverage`, e.g. `just python=3.8 functional pathops`.")]
functional package +flags='-rA': (_coverage package 'functional' flags)

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
_coverage package test_suite +flags:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}'
    export COVERAGE_RCFILE='{{justfile_directory()}}/pyproject.toml'
    DATA_FILE=".report/coverage-$(basename {{test_suite}})-{{python}}.db"
    uv run {{_with_test_deps}} --group {{test_suite}} \
        coverage run --data-file="$DATA_FILE" --source='src' \
        -m pytest --tb=native -vv {{flags}} 'tests/{{test_suite}}'
    uv run {{_with_test_deps}} --group {{test_suite}} \
        coverage report --data-file="$DATA_FILE"

[doc("Combine `coverage` reports, e.g. `just python=3.8 combine-coverage pathops`.")]
combine-coverage package:
    #!/usr/bin/env -S bash -xueo pipefail
    : 'Collect the coverage data files that exist for this package.'
    cd '{{package}}'
    data_files=()
    for test_id in unit functional juju; do
        data_file=".report/coverage-$test_id-{{python}}.db"
        if [ -e "$data_file" ]; then
            data_files+=("$data_file")
        fi
    done
    : 'Combine coverage.'
    export COVERAGE_RCFILE='{{justfile_directory()}}/pyproject.toml'
    DATA_FILE='.report/coverage-all-{{python}}.db'
    HTML_DIR='.report/htmlcov-all-{{python}}'
    uv run coverage combine --keep --data-file="$DATA_FILE" "${data_files[@]}"
    uv run coverage xml --data-file="$DATA_FILE" -o '.report/coverage-all-{{python}}.xml'
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
_integration package substrate label +flags:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}'
    CHARMLIBS_SUBSTRATE={{substrate}} uv run {{_with_test_deps}} --group integration \
        pytest --tb=native -vv -m '{{label}}' tests/integration  {{flags}}

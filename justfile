mod interface  # load interface module to expose interface subcommands
mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes

# set on the commandline as needed, e.g. `just package=pathops python=3.10 unit`
python := '3.10'
# for integration tests, e.g. `just tag=24.04 pack-k8s` `just tag=foo integration-machine`
tag := env('CHARMLIBS_TAG', '')

_uv_run_with_test_requirements := 'uv run --with-requirements ' + quote(join(justfile_dir(), 'test-requirements.txt')) + ' --python ' + python

# this is the first recipe in the file, so it will run if just is called without a recipe
_short_help:
    @echo '{{BOLD}}Charmlibs is the Canonical charm libraries monorepo{{NORMAL}}'
    @echo ''
    @echo '{{BOLD}}List all commands with {{CYAN}}just help{{NORMAL}}{{BOLD}}, or:{{NORMAL}}'
    @echo '- Create a new package: {{CYAN}}just init{{NORMAL}} or {{CYAN}}just interface init{{NORMAL}}'
    @echo '- Run {{CYAN}}ruff{{NORMAL}} for all packages: {{CYAN}}just fast-lint{{NORMAL}}'
    @echo '- Lint, unit test, and build docs for a package: {{CYAN}}just check <package>{{NORMAL}}'
    @echo ''
    @echo '{{BOLD}}Run individual checks for a package:{{NORMAL}}'
    @echo '- {{CYAN}}just lint <package>{{NORMAL}} (fix errors with {{CYAN}}just format <package>{{NORMAL}})'
    @echo '- {{CYAN}}just unit <package>{{NORMAL}}'
    @echo '- {{CYAN}}just functional <package>{{NORMAL}} (may require additional software like {{CYAN}}pebble{{NORMAL}})'
    @echo ''
    @echo '{{BOLD}}Run integration tests{{NORMAL}} (requires a Juju controller and a cloud):'
    @echo '- Pack: {{CYAN}}just pack-k8s <package>{{NORMAL}} or {{CYAN}}just pack-machine <package>{{NORMAL}}'
    @echo '- Run: {{CYAN}}just integration-k8s <package>{{NORMAL}} or {{CYAN}}just integration-machine <package>{{NORMAL}}'
    @echo ''
    @echo '{{BOLD}}Build the docs: {{CYAN}}just docs{{NORMAL}}'
    @echo '- For specific packages only: {{CYAN}}just docs html <packages>{{NORMAL}}'

[doc('Describe usage and list the available recipes.')]
help:
    @echo 'All recipes require {{CYAN}}`uv`{{NORMAL}} to be available.'
    @just --list --unsorted --list-submodules

[doc('Create the files for a new charmlibs package interactively.')]
init *args:
    @echo '✨{{BOLD}}IMPORTANT{{NORMAL}}✨ The project name should be the import package name, without the {{CYAN}}charmlibs.{{NORMAL}} namespace.'
    @echo 'You can press enter to accept the default, shown in brackets.'
    @env CHARMLIBS_TEMPLATE=$(realpath .template) uvx cookiecutter .template {{args}}

[doc('Run `ruff`, failing afterwards if any errors are found.')]
fast-lint:
    #!/usr/bin/env -S bash -xueo pipefail
    FAILURES=0
    uv run --only-group=fast-lint ruff check --preview || ((FAILURES+=1))
    uv run --only-group=fast-lint ruff check --preview --diff || : 'Printed diff of changes to fix `ruff check` issues.'
    uv run --only-group=fast-lint ruff format --preview --diff || ((FAILURES+=1))
    : "$FAILURES command(s) failed."
    exit $FAILURES

[doc('`lint`, `unit` test, and build the `docs` for a package.')]
check package: (lint package) (unit package) (docs::html package)

[doc('Run `ruff check --fix` and `ruff --format`, modifying files in place.')]
format package='.':
    uv run --only-group=fast-lint ruff format --preview '{{package}}'
    uv run --only-group=fast-lint ruff check --preview --fix '{{package}}'

[doc("Run `uv add` for package, respecting repo-level version constraints, e.g. `just add pathops 'pydantic>=2'`.")]
[positional-arguments]  # pass recipe args to recipe script positionally (so we can get correct quoting)
add package +args:
    #!/usr/bin/env -S bash -xueo pipefail
    shift 1  # drop $1 (package) from $@ it's just +args
    cd '{{package}}'
    uv add --constraints {{quote(join(justfile_dir(), 'test-requirements.txt'))}} "${@}"

[doc('Run global `fast-lint` and package specific `static` analysis, e.g. `just python=3.10 lint pathops`.')]
[positional-arguments]  # pass recipe args to recipe script positionally (so we can get correct quoting)
lint package *pyright_args:
    #!/usr/bin/env -S bash -xueo pipefail
    shift 1  # drop $1 (package) from $@ it's just *args
    FAILURES=0
    just --justfile='{{justfile()}}' python='{{python}}' fast-lint || ((FAILURES+=$?))
    just --justfile='{{justfile()}}' python='{{python}}' static '{{package}}' "${@}" || ((FAILURES+=1))
    : "$FAILURES command(s) failed."
    exit $FAILURES

[doc('Run package specific static analysis only, e.g. `just python=3.10 static pathops`.')]
[positional-arguments]  # pass recipe args to recipe script positionally (so we can get correct quoting)
static package *args:
    #!/usr/bin/env -S bash -xueo pipefail
    shift 1  # drop $1 (package) from $@ it's just *args
    cd '{{package}}'
    {{_uv_run_with_test_requirements}} \
        --group lint --group unit --group functional --group integration \
        --with pytest-interface-tester \
        pyright --pythonversion='{{python}}' "${@}"

[doc("Run unit tests with `coverage`, e.g. `just python=3.10 unit pathops`.")]
unit package +flags='-rA': (_coverage package 'unit' flags)

[doc("Run functional tests with `coverage`, e.g. `just python=3.10 functional pathops`.")]
[positional-arguments]  # pass recipe args to recipe script positionally to enable correct quoting when forwarding variadic args
functional package +flags='-rA':
    #!/usr/bin/env -S bash -xueo pipefail
    shift 1  # drop $1 (package) from $@ it's just +flags
    cd '{{package}}'
    if [ -e tests/functional/setup.sh ]; then
        source ./tests/functional/setup.sh
    fi
    set +e  # don't exit if the tests fail
    just --justfile='{{justfile()}}' python='{{python}}' _coverage '{{package}}' functional "${@}"
    EXITCODE=$?
    set -e  # do exit if anything goes wrong now
    if [ -e tests/functional/teardown.sh ]; then
        source ./tests/functional/teardown.sh
    fi
    exit $EXITCODE

[doc("Use uv to install and run coverage for the specified package's tests.")]
_coverage package test_suite +flags:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}'
    export COVERAGE_RCFILE='{{justfile_directory()}}/pyproject.toml'
    DATA_FILE=".report/coverage-$(basename {{test_suite}})-{{python}}.db"
    {{_uv_run_with_test_requirements}} --group {{test_suite}} \
        coverage run --data-file="$DATA_FILE" --source='src' \
        -m pytest --tb=native -vv {{flags}} 'tests/{{test_suite}}'
    {{_uv_run_with_test_requirements}} --group {{test_suite}} \
        coverage report --data-file="$DATA_FILE"

[doc("Combine `coverage` reports, e.g. `just python=3.10 combine-coverage pathops`.")]
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
    {{_uv_run_with_test_requirements}} coverage combine --keep --data-file="$DATA_FILE" "${data_files[@]}"
    {{_uv_run_with_test_requirements}} coverage xml --data-file="$DATA_FILE" -o '.report/coverage-all-{{python}}.xml'
    rm -rf "$HTML_DIR"  # let coverage create html directory from scratch
    {{_uv_run_with_test_requirements}} coverage html --data-file="$DATA_FILE" --show-contexts --directory="$HTML_DIR"
    {{_uv_run_with_test_requirements}} coverage report --data-file="$DATA_FILE"

[doc("Execute pack script to pack Kubernetes charm(s) for Juju integration tests.")]
pack-k8s package *args: (_pack package 'k8s' args)

[doc("Execute pack script to pack machine charm(s) for Juju integration tests.")]
pack-machine package *args: (_pack package 'machine' args)

[doc("Execute the pack script for the given package, setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG.")]
_pack package substrate *args:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}/tests/integration'
    CHARMLIBS_SUBSTRATE='{{substrate}}' CHARMLIBS_TAG='{{tag}}' ./pack.sh {{args}}

[doc("Run juju integration tests for packed k8s charm(s), setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG, and selecting 'not machine_only'.")]
integration-k8s package +flags='-rA': (_integration package 'k8s' 'not machine_only' flags)

[doc("Run juju integration tests for packed machine charm(s), setting CHARMLIBS_SUBSTRATE and CHARMLIBS_TAG, and selecting 'not k8s_only'.")]
integration-machine package +flags='-rA': (_integration package 'machine' 'not k8s_only' flags)

[doc("Run juju integration tests. Requires `juju`.")]
_integration package substrate label +flags:
    #!/usr/bin/env -S bash -xueo pipefail
    cd '{{package}}'
    CHARMLIBS_SUBSTRATE={{substrate}} CHARMLIBS_TAG='{{tag}}' {{_uv_run_with_test_requirements}} --group integration \
        pytest --tb=native -vv -m '{{label}}' tests/integration  {{flags}}

[doc("Make .interfaces.json file.")]
interfaces-json:
    .scripts/ls.py interfaces \
        --output name \
        --output version \
        --output lib \
        --output lib_url \
        --output docs_url \
        --output summary \
        --output description \
        --indent-json \
        > interfaces/index.json

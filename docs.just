set working-directory := '.docs'

build_dir := env('READTHEDOCS_OUTPUT', '_build')

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc("""
Build the docs, (re)generating reference docs for all packages, or just those specified.

`just docs` is an alias for `just docs html`. To specify packages, you must use the full recipe, e.g.
`just docs html interfaces/foo`.
""")]
html *packages: _diataxis_docs (_packages packages)
    uvx --with-requirements=_dev/requirements.txt --from=sphinx \
        sphinx-build -b dirhtml -T -W --keep-going -d _dev/.doctrees -D language=en . '{{build_dir}}/html'

[doc('Copy per-library diataxis docs into the Sphinx source tree and generate toctree include files.')]
_diataxis_docs:
    ./scripts/diataxis_preprocessor.py

[doc("""
Run html builder once per package, with its deps installed, setting the package argument and suppressing reference warnings.

This allows us to generate the reference docs for that package with autodoc, saving the doctrees and reference information
to be combined into the final docs in a separate pass.
""")]
_packages *packages:
    #!/usr/bin/env -S uv run --script --no-project
    import json, pathlib, subprocess, sys
    ROOT = pathlib.Path('{{justfile_directory()}}')
    packages = '{{packages}}'.split()
    if packages == ['-']:
        sys.exit()
    if not packages:
        cmd = [ROOT / '.scripts/ls.py', 'packages', '--exclude-examples', '--exclude-placeholders']
        packages = json.loads(subprocess.check_output(cmd, text=True))
    for package in packages:
        cmd = [
            'uvx',
            '--from', 'sphinx',
            '--with-requirements', '_dev/requirements.txt',
            '--with', str(ROOT / package),
            'sphinx-build',
            '-T', '-W', '--keep-going',
            '-b', 'dirhtml',
            '-d', '_dev/.doctrees',
            '-D', 'language=en',
            '-D', f'package={package}',
            # llms.txt is only generated in the final combined pass (the `html` recipe).
            # Leaving it enabled here triggers a nested base-mode build that regenerates the
            # interface reference docs, deleting the placeholder this package pass depends on.
            '-D', 'llms_txt_enabled=0',
            '-D', 'suppress_warnings=ref.ref,ref.doc,myst.xref_missing',
            '.', '{{build_dir}}/html',
        ]
        print(cmd)
        subprocess.check_call(cmd)

[doc('Show help for the docs recipes.')]
help:
    @just --list docs --unsorted

[doc('Watch, build, and serve the docs -- does not rebuild package reference docs automatically.')]
run: _packages
    uvx --with-requirements=_dev/requirements.txt --from=sphinx \
        sphinx-autobuild --watch .. --ignore '**/generated/*' -b dirhtml -D llms_txt_enabled=0 . '{{build_dir}}/html'

[doc('Check links.')]
linkcheck *sphinx_args: _packages
    uvx --with-requirements=_dev/requirements.txt --from=sphinx \
        sphinx-build -b linkcheck . '{{build_dir}}' {{sphinx_args}}

[doc('Check spelling with Vale (flags US-English misspellings not in the custom wordlist).')]
spelling *paths: (_vale '.Name=="Canonical.000-US-spellcheck"' paths)

[doc('Check Canonical style guide compliance (errors only) with Vale.')]
vale *paths: (_vale '.Level=="error" and .Name!="Canonical.500-Repeated-words" and .Name!="Canonical.000-US-spellcheck"' paths)

[doc('Check for non-inclusive language with Vale.')]
woke *paths: (_vale '.Name=="Canonical.400-Enforce-inclusive-terms"' paths)

# Run Vale over the tracked .md/.rst files (or those matching the given pathspecs),
# applying the custom wordlist and the given filter.
# Downloads the Canonical Vale style guide (styles + vale.ini) if needed.
# Generated reference docs are untracked, so they are excluded automatically.
_vale filter *paths:
    #!/usr/bin/env bash
    set -xeuo pipefail
    [ -f _dev/vale.ini ] || python3 _dev/get_vale_conf.py
    accept='_dev/styles/config/vocabularies/Canonical/accept.txt'
    cp "$accept" "$accept.bak"
    trap 'mv "$accept.bak" "$accept"' EXIT
    cat .custom_wordlist.txt >> "$accept"
    if [ -n "{{paths}}" ]; then
        files=$(git ls-files -- {{paths}} | grep -E '\.(md|rst)$' || true)
    else
        files=$(git ls-files '*.md' '*.rst')
    fi
    if [ -z "$files" ]; then
        echo 'No tracked .md/.rst files to check.'
        exit 0
    fi
    echo "$files" | xargs uvx --from 'vale~=3.13' vale --config=_dev/vale.ini --filter='{{filter}}'

[doc('Remove files created by building the docs.')]
clean:
    git clean -fx '{{build_dir}}'
    rm -rf _dev/.doctrees
    rm -rf _dev/node_modules/
    rm -rf _dev/styles
    rm -rf _dev/vale.ini
    # generated reference docs
    rm -rf reference/generated
    # package reference docs
    rm -rf reference/charmlibs
    rm -rf reference/interfaces
    rm -rf .save
    # per-library diataxis docs
    rm -rf tutorials/charmlibs
    rm -rf how-to/charmlibs
    rm -rf explanation/charmlibs
    rm -f tutorials/_lib-tutorials.md
    rm -f how-to/_lib-how-to.md
    rm -f explanation/_lib-explanation.md

[doc('Run `pyright` for local sphinx extensions.')]
ext-static *pyrightargs:
    cd tests && uvx --with-requirements=../_dev/requirements.txt --with=pytest \
        pyright {{pyrightargs}}

[doc('Run unit tests with `coverage` for local sphinx extensions.')]
ext-unit +flags='-rA':
    uvx --with-requirements=_dev/requirements.txt --with=pytest \
        coverage run --omit='test_*.py' --source=extensions,scripts -m pytest --tb=native -vv {{flags}} tests
    uvx coverage report

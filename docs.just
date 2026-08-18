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

Package builds run in parallel: each gets its own doctree cache and html outdir so they can't
step on each other, and the placeholder rst files are written once up front rather than once per
build. Each build's captured stdout/stderr is printed atomically after it finishes.
""")]
_packages *packages:
    #!/usr/bin/env -S uv run --script --no-project
    import concurrent.futures, json, os, pathlib, subprocess, sys
    ROOT = pathlib.Path('{{justfile_directory()}}')
    packages = '{{packages}}'.split()
    if packages == ['-']:
        sys.exit()
    if not packages:
        cmd = [ROOT / '.scripts/ls.py', 'packages', '--exclude-examples', '--exclude-placeholders']
        packages = json.loads(subprocess.check_output(cmd, text=True))
    # Pre-pass: write placeholder rst files for every package once. Each per-package build reads
    # the shared placeholders and injects its own automodule in-memory during source-read (see
    # .docs/extensions/package_docs.py). Since the on-disk files never carry an automodule, the
    # parallel builds don't race on the source tree.
    sys.path.insert(0, str(ROOT / '.docs' / 'extensions'))
    import package_docs
    package_docs._main(docs_dir=ROOT / '.docs')
    build_dir = pathlib.Path('{{build_dir}}')

    def build(package):
        # Isolate per-build outputs (html, doctree cache) so parallel builds don't clobber each
        # other. Only the .save/ pickles are shared, and they're keyed on unique per-package names.
        pkg_slug = package.replace('/', '_')
        outdir = build_dir / '_pkg_pass' / pkg_slug / 'html'
        doctrees = build_dir / '_pkg_pass' / pkg_slug / 'doctrees'
        cmd = [
            'uvx',
            '--from', 'sphinx',
            '--with-requirements', '_dev/requirements.txt',
            '--with', str(ROOT / package),
            'sphinx-build',
            '-T', '-W', '--keep-going',
            '-b', 'dirhtml',
            '-d', str(doctrees),
            '-D', 'language=en',
            '-D', f'package={package}',
            # llms.txt is only generated in the final combined pass (the `html` recipe).
            # Leaving it enabled here triggers a nested base-mode build that regenerates the
            # interface reference docs, deleting the placeholder this package pass depends on.
            '-D', 'llms_txt_enabled=0',
            '-D', 'suppress_warnings=ref.ref,ref.doc,myst.xref_missing',
            '.', str(outdir),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return package, cmd, result

    max_workers = min(len(packages), os.cpu_count() or 1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(build, p) for p in packages]
        failed = False
        for future in concurrent.futures.as_completed(futures):
            package, cmd, result = future.result()
            print(f'--- {package} ---')
            print(cmd)
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
            if result.returncode != 0:
                failed = True
                print(f'--- {package} FAILED (exit {result.returncode}) ---', file=sys.stderr)
        if failed:
            sys.exit(1)

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

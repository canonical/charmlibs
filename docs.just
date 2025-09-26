set working-directory := '.docs'

build_dir := env('READTHEDOCS_OUTPUT', '_build')

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc("""
Build the docs, (re)generating reference docs for all packages, or just those specified.

`just docs` is an alias for `just docs html`. To specify packages, you must use the full recipe, e.g.
`just docs html interfaces/foo`.
""")]
html *packages: (_packages packages)
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-build -b dirhtml -T -W --keep-going -d .sphinx/.doctrees -D language=en . '{{build_dir}}/html'

[doc("""
Run html builder once per package, with its deps installed, setting the package argument and suppressing reference warnings.

This allows us to generate the reference docs for that package with autodoc, saving the doctrees and reference information
to be combined into the final docs in a separate pass.
""")]
_packages *packages:
    #!/usr/bin/env -S uv run --script --no-project
    import json, pathlib, subprocess
    ROOT = pathlib.Path('{{justfile_directory()}}')
    packages = '{{packages}}'.split()
    if not packages:
        cmd = [ROOT / '.scripts/ls.py', 'packages', '--exclude-examples', '--exclude-placeholders']
        packages = json.loads(subprocess.check_output(cmd, text=True))
    for package in packages:
        cmd = [
            'uvx',
            '--from', 'sphinx',
            '--with-requirements', '.sphinx/requirements.txt',
            '--with', str(ROOT / package),
            'sphinx-build',
            '-T', '-W', '--keep-going',
            '-b', 'dirhtml',
            '-d', '.sphinx/.doctrees',
            '-D', 'language=en',
            '-D', f'package={package}',
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
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-autobuild --watch .. --ignore '**/generated/*' -b dirhtml . '{{build_dir}}/html'

[doc('Check links.')]
linkcheck: _packages
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-build -b linkcheck . '{{build_dir}}'

[doc('Check spelling.')]
spelling: html
    uvx pyspelling -c .sphinx/spellingcheck.yaml -j $(nproc)

[doc('Remove files created by building the docs.')]
clean:
    git clean -fx '{{build_dir}}'
    rm -rf .sphinx/.doctrees
    rm -rf .sphinx/node_modules/
    rm -rf .sphinx/styles
    rm -rf .sphinx/vale.ini
    # generated reference docs
    rm -rf reference/generated
    # package reference docs
    rm -rf reference/charmlibs
    rm -rf .save

[doc('Run `pyright` for local sphinx extensions.')]
ext-static *pyrightargs:
    cd extensions && uvx --with-requirements=../.sphinx/requirements.txt --with=pytest \
        pyright {{pyrightargs}}

[doc('Run unit tests with `coverage` for local sphinx extensions.')]
ext-unit +flags='-rA':
    uvx --with-requirements=.sphinx/requirements.txt --with=pytest \
        coverage run --omit='test_*.py' -m pytest --tb=native -vv {{flags}} extensions
    uvx coverage report

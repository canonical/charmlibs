set working-directory := '.docs'

build_dir := env('READTHEDOCS_OUTPUT', '_build')

# this is the first recipe in the file, so it will run if just is called without a recipe
[doc("""
Build the docs, generating reference docs for all packages, or just those specified.

`just docs` is an alias for `just docs html`. To specify packages, you must use the full recipe, e.g.
`just docs html interfaces/foo`.
Run `just docs clean` first to generate reference docs from scratch if you run into import errors.
""")]
html *packages:
    #!/usr/bin/env -S uv run --script --no-project
    import pathlib, subprocess
    ROOT = pathlib.Path('{{justfile_directory()}}')

    def build(package: str | None, suppress_warnings: bool = False) -> None:
        cmd = [
            'uvx',
            '--from', 'sphinx',
            '--with-requirements', '.sphinx/requirements.txt',
            *(['--with', str(ROOT / package)] if package else []),
            'sphinx-build',
            '-T', '-W', '--keep-going',
            '-b', 'dirhtml',
            '-d', '_build/doctrees',
            '-D', 'language=en',
            *(['-D', f'package={package}'] if package else []),
            *(
                ['-D', 'suppress_warnings=ref.ref,ref.doc,myst.xref_missing']
                if suppress_warnings
                else []
            ),
            '.', '{{build_dir}}/html',
        ]
        print(cmd)
        subprocess.check_call(cmd)

    # Any directory (or subdirectory of interfaces) starting with a-z is assumed to be a package.
    packages = '{{packages}}'.split() or [
        *sorted(p.name for p in ROOT.glob(r'[a-z]*') if p.is_dir() and p.name != 'interfaces'),
        *sorted(f'interfaces/{p.name}' for p in (ROOT / 'interfaces').glob(r'[a-z]*') if p.is_dir()),
    ]
    # Suppress ref warnings on all but last package as refs can't all resolve.
    for package in packages[: -1]:
        build(package, suppress_warnings=True)
    # Run with the usual warnings for the last package.
    # Or run just once with package=None if there were no packages.
    for package in packages[-1 :] or [None]:
        build(package)

[doc('Show help for the docs recipes.')]
help:
    @just --list docs --unsorted

[doc('Watch, build, and serve the docs.')]
run:
    uvx --with-requirements=.sphinx/requirements.txt --from=sphinx \
        sphinx-autobuild --watch .. --ignore '**/generated/*' -b dirhtml . '{{build_dir}}/html'

[doc('Check links.')]
linkcheck:
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
    rm -rf reference/charmlibs
    rm -rf reference/generated

[doc('Run `pyright` for local sphinx extensions.')]
ext-static *pyrightargs:
    uvx --with-requirements=.sphinx/requirements.txt --with=pytest \
        pyright {{pyrightargs}} extensions

[doc('Run unit tests with `coverage` for local sphinx extensions.')]
ext-unit +flags='-rA':
    uvx --with-requirements=.sphinx/requirements.txt --with=pytest \
        coverage run --omit='test_*.py' -m pytest --tb=native -vv {{flags}} extensions
    uvx coverage report

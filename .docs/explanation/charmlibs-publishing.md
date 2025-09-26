(charmlibs-publishing)=
# Publishing packages from the charmlibs monorepo

The `charmlibs` monorepo has CI that automatically releases your library to PyPI each time you bump your library's version to a non-dev version.
That is, whenever a PR is merged, if the version of a library has changed, and the new version is not a dev version like `X.Y.Z.devN`, the CI will try to publish your library to PyPI.

## Trusted publishing

Before you can make your first release, you'll need to [set up trusted publishing on PyPI for your library](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
Remember that the package name should be `charmlibs-<LIBRARY>`, or `charmlibs-interfaces-<LIBRARY>` for an interface library.
The repository owner is `canonical`, the repository name is `charmlibs`, and the workflow name is `publish.yaml`.

## Testing

You should also set this up on [test.pypi.org](https://test.pypi.org) -- if you run the `publish.yaml` workflow manually, you'll have to specify a package, and this package will be published to `test.pypi.org` (regardless of whether it's a dev version or not).

## Semantic versioning

Libraries in the `charmlibs` monorepo should follow [semantic versioning](https://packaging.python.org/en/latest/discussions/versioning/#semantic-versioning).

It's a good idea to initially add new libraries with a major version of 0.
In semantic versioning, this communicates that the API design is still in progress, so even when the library is released, you're free to make well-considered breaking changes before your 1.0 release.

However, if you're porting an existing Charmhub-hosted library as-is, then it's better to start with a major version of 1, to communicate that you won't break the existing API without a major version bump.

## Dev versions

You may want to make your initial PR with a dev version -- that is, a version with a `.devN` suffix, like `1.2.3.dev0`.

Dev versions are excluded from the `charmlibs` monorepo's release CI, so they won't be released to PyPI.
This means you can make follow ups to your initial PR before your initial release, and publish your library on `test.pypi.org` by manually running the `publish` workflow.
When you're ready to make a release, make a PR that bumps your library's version to a non-dev version.
All version bumps (to non-dev versions) will automatically trigger a release on merge.
After a release, you can follow up with a bump to a dev version, or leave the version unchanged until you're ready for the next release.

## Changelog

Every release should be accompanied by an entry in your library's `CHANGELOG.md` with the following format:
```markdown
# A.B.C - N Month 20XX

...
```
That is, a heading with the version number, separated by spaces and a hyphen from the release date.
The body of the section should include a meaningful description of the changes in this release.
This could be a bulleted list of commits, or a short paragraph, or both.

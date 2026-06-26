#!/usr/bin/env -S uv run --script --no-project

# /// script
# requires-python = ">=3.12"
# dependencies = [
# ]
# ///

# Copyright 2025 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

r"""Download a charm's Discourse documentation topic as a Markdown file.

Charmhub renders charm docs from topics on https://discourse.charmhub.io. This
script downloads a single topic and writes its Markdown source to a file,
resolving any embedded images along the way.

It's a helper for migrating a library's docs into the charmlibs monorepo --
see the "Migrate your library's docs" section of the migration how-to guide:
https://canonical.com/juju/docs/charmlibs/how-to/migrate/

Usage:
    .scripts/import_discourse_docs.py <discourse-url> <output-file>

For example:
    .scripts/import_discourse_docs.py \
        https://discourse.charmhub.io/t/tls-certificates-interface/15539 \
        interfaces/tls-certificates/docs/explanation/tls-certificates-interface.md
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.request

# Matches the numeric topic ID in a Discourse URL, e.g.
# https://discourse.charmhub.io/t/<slug>/<topic_id>(/<post_number>)?
_TOPIC_ID_RE = re.compile(r'/t/(?:[^/]+/)?(\d+)')


def main() -> None:
    """Download the topic named on the command line and write it to a file."""
    parser = argparse.ArgumentParser(
        description="Download a charm's Discourse documentation topic as a Markdown file."
    )
    parser.add_argument(
        'url', help='Discourse topic URL, e.g. https://discourse.charmhub.io/t/<slug>/<id>'
    )
    parser.add_argument('output', type=pathlib.Path, help='Markdown file to write')
    args = parser.parse_args()

    post = _fetch(_topic_id(args.url))['post_stream']['posts'][0]
    markdown = _resolve_images(post['raw'], post['cooked'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown)
    print(f'Wrote {args.output}')


def _topic_id(url: str) -> int:
    """Extract the numeric topic ID from a Discourse topic URL."""
    match = _TOPIC_ID_RE.search(url)
    if match is None:
        raise ValueError(f'Not a Discourse topic URL: {url!r}')
    return int(match.group(1))


def _fetch(topic_id: int):
    """Download a Discourse topic as JSON, including the raw Markdown source."""
    url = f'https://discourse.charmhub.io/t/{topic_id}.json?include_raw=true'
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310  # trusted host
        return json.loads(response.read())


def _resolve_images(raw: str, cooked: str) -> str:
    """Rewrite ``upload://`` image shortcodes to real URLs using the cooked HTML."""
    uploads = re.findall(r'upload://[^\s)]+', raw)
    img_urls = re.findall(r'<img[^>]+src=["\']([^"\'\s]+)', cooked)
    for upload, image_url in zip(uploads, img_urls, strict=False):  # matched positionally
        raw = raw.replace(upload, image_url)
    # Strip Discourse's |WIDTHxHEIGHT suffix from image alt text.
    return re.sub(r'!\[([^\]]*?)\|\d+x\d+\]', r'![\1]', raw)


if __name__ == '__main__':
    main()

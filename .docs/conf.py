import datetime
import pathlib
import sys

# local extensions
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'extensions'))
local_extensions = ['generate_tables', 'interface_docs', 'package_docs']

# So that sphinx.ext.autodoc can find charmlibs code
root = pathlib.Path(__file__).parent.parent
package_glob = '[a-z]*'
sys.path[0:0] = [
    *(
        str(p / 'src' / 'charmlibs')
        for p in root.glob(package_glob)
        if p.is_dir() and not p.name == 'interfaces'
    ),
    *(
        str(p / 'src' / 'charmlibs' / 'interfaces')
        for p in (root / 'interfaces').glob(package_glob)
        if p.is_dir()
    ),
]

# A complete list of built-in Sphinx configuration values:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
#
# Our starter pack uses the custom Canonical Sphinx extension
# to keep all documentation based on it consistent and on brand:
# https://github.com/canonical/canonical-sphinx

#######################
# Project information #
#######################

# Project name
project = "Charmlibs"
author = "Canonical Ltd."
slug = 'charmlibs'  # https://meta.discourse.org/t/what-is-category-slug/87897
html_title = f"{project} documentation"  # sidebar documentation title
copyright = f"{datetime.date.today().year} CC-BY-SA, {author}"  # shown at the bottom of the page

# Documentation website URL
ogp_site_url = "https://documentation.ubuntu.com/charmlibs/"
# Preview name of the documentation website
ogp_site_name = project
# Preview image URL
ogp_image = "https://assets.ubuntu.com/v1/253da317-image-document-ubuntudocs.svg"

# https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-html_context
html_context = {
    "product_page": "github.com/canonical/charmlibs",
    'product_tag': '_static/logos/juju-logo-no-text.png',
    "discourse": "https://discourse.charmhub.io/",
    "discourse_prefix": "https://discourse.charmhub.io/t/",
    "mattermost": "",
    "matrix": "https://matrix.to/#/#charmhub-charmdev:ubuntu.com",
    "github_url": "https://github.com/canonical/charmlibs",
    'repo_default_branch': 'main',
    "repo_folder": "/.docs/",
    "display_contributors": False,
    'github_issues': 'enabled',  # Required for feedback button
}
# Template and asset locations
html_static_path = [".sphinx/_static"]
templates_path = [".sphinx/_templates"]

# Sitemap configuration: https://sphinx-sitemap.readthedocs.io/
html_baseurl = 'https://documentation.ubuntu.com/charmlibs/'
sitemap_url_scheme = '{link}'  # URL scheme. Add language and version scheme elements.
sitemap_show_lastmod = True  # Include `lastmod` dates in the sitemap:
sitemap_excludes = [  # Exclude generated pages from the sitemap:
    '404/',
    'genindex/',
    'py-modindex/',
    'search/',
   'reference/generated/*',
]

#############
# Redirects #
#############

# To set up redirects: https://documatt.gitlab.io/sphinx-reredirects/usage.html
# For example: 'explanation/old-name.html': '../how-to/prettify.html',

# To set up redirects in the Read the Docs project dashboard:
# https://docs.readthedocs.io/en/stable/guides/redirects.html

# NOTE: If undefined, set to None, or empty,
#       the sphinx_reredirects extension will be disabled.

redirects = {}

###########################
# Link checker exceptions #
###########################

# A regex list of URLs that are ignored by 'make linkcheck'
linkcheck_ignore = [
    "http://127.0.0.1:8000",
    "https://matrix.to/#/*",
]
if 'check-github-links' not in tags:
    linkcheck_ignore.append(r"https://github\.com/.*")

# A regex list of URLs where anchors are ignored by 'make linkcheck'
linkcheck_anchors_ignore_for_url = [r"https://github\.com/.*"]

# give linkcheck multiple tries on failure
# linkcheck_timeout = 30
linkcheck_retries = 3

########################
# Configuration extras #
########################

# NOTE: The canonical_sphinx extension is required for the starter pack.
#       It automatically enables the following extensions:
#       - custom-rst-roles
#       - myst_parser
#       - notfound.extension
#       - related-links
#       - sphinx_copybutton
#       - sphinx_design
#       - sphinx_reredirects
#       - sphinx_tabs.tabs
#       - sphinxcontrib.jquery
#       - sphinxext.opengraph
#       - terminal-output
#       - youtube-links
extensions = [
    "canonical_sphinx",
    "sphinxcontrib.cairosvgconverter",
    "sphinxcontrib.mermaid",
    "sphinx_last_updated_by_git",
    "sphinx.ext.autodoc",
    'sphinx.ext.intersphinx',
    "sphinx.ext.napoleon",
    "sphinx_datatables",
    "sphinx_sitemap",
    *local_extensions,
]

# Custom MyST syntax extensions; see
# https://myst-parser.readthedocs.io/en/latest/syntax/optional.html
# NOTE: By default, the following MyST extensions are enabled:
#       substitution, deflist, linkify
# myst_enable_extensions = set()

intersphinx_mapping = {
    'ops': ('https://documentation.ubuntu.com/ops/latest', None),
    'python': ('https://docs.python.org/3', None),
    'juju': ('https://documentation.ubuntu.com/juju/3.6', None),
    'charmcraft': ('https://documentation.ubuntu.com/charmcraft/latest', None),
}

maximum_signature_line_length = 80
add_function_parentheses = False  # don't automatically add parentheses after func and method refs
# disable_feedback_button = True  # Feedback button at the top; enabled by default

# Excludes files or directories from processing
exclude_patterns = [
    "doc-cheat-sheet*",
]

# Adds custom CSS files, located under 'html_static_path'
html_css_files = [
    "project_specific.css",
]

# Adds custom JavaScript files, located under 'html_static_path'
# html_js_files = []

# Specifies a reST snippet to be prepended to each .rst file
# This defines a :center: role that centers table cell content.
# This defines a :h2: role that styles content for use with PDF generation.
rst_prolog = """
.. role:: center
   :class: align-center
.. role:: h2
    :class: hclass2
.. role:: woke-ignore
    :class: woke-ignore
.. role:: vale-ignore
    :class: vale-ignore
"""

# Specifies a reST snippet to be appended to each .rst file
# rst_epilog = """
# .. include:: /reuse/links.txt
# """

# Options for sphinx.ext.autodoc
autodoc_typehints = 'signature'
autoclass_content = 'class'
autodoc_member_order = 'bysource'
add_module_names = False
autodoc_default_options = {
    'members': None,  # None here means "yes"
    'special-members': None,  # meaning all
    'exclude-members': (
        '__annotations__,'
        '__abstractmethods__,'
        '__dict__,'
        '__dataclass_fields__,'
        '__dataclass_params__,'
        '__delattr__,'
        '__firstlineno__,'
        '__hash__,'
        '__init__,'
        '__match_args__,'
        '__module__,'
        '__orig_bases__,'
        '__parameters__,'
        '__protocol_attrs__,'
        '__setattr__,'
        '__static_attributes__,'
        '__subclasshook__,'
        '__weakref__,'
        # string methods
        '__repr__,'
        '__str__,'
        # comparison methods
        '__eq__,'
        '__ge__,'
        '__gt__,'
        '__le__,'
        '__lt__,'
    ),
    'undoc-members': None,
    'show-inheritance': None,
}

# Options for sphinx-datatables
datatables_version = "1.13.4"  # set the version to use for DataTables plugin
datatables_class = "sphinx-datatable"  # name of the class to use for tables to enable DataTables
# any custom options to pass to the DataTables constructor
# any options set are used for all DataTables
datatables_options = {
    'info': False,  # remove 'showing x of y' footer
    'paging': False,  # remove all paging options
    'search': {'regex': True},  # enable regex in search box
}

# Options for sphinxcontrib-mermaid
myst_fence_as_directive = ["mermaid"]  # allow ```mermaid like GitHub does


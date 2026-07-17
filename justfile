mod docs  # load docs module to expose docs subcommands

set ignore-comments  # don't print comment lines in recipes
set positional-arguments  # forward recipe args to scripts as argv ("$@"), so quoting is preserved

# this is the first recipe in the file, so it will run if just is called without a recipe
_quick_start:
    @.scripts/just.py

help *args:
    @.scripts/just.py help "$@"

init *args:
    @.scripts/just.py init "$@"

fast-lint *args:
    @.scripts/just.py fast-lint "$@"

check *args:
    @.scripts/just.py check "$@"

format *args:
    @.scripts/just.py format "$@"

add *args:
    @.scripts/just.py add "$@"

lint *args:
    @.scripts/just.py lint "$@"

static *args:
    @.scripts/just.py static "$@"

unit *args:
    @.scripts/just.py unit "$@"

functional *args:
    @.scripts/just.py functional "$@"

combine-coverage *args:
    @.scripts/just.py combine-coverage "$@"

pack-k8s *args:
    @.scripts/just.py pack-k8s "$@"

pack-machine *args:
    @.scripts/just.py pack-machine "$@"

integration-k8s *args:
    @.scripts/just.py integration-k8s "$@"

integration-machine *args:
    @.scripts/just.py integration-machine "$@"

interfaces-json *args:
    @.scripts/just.py interfaces-json "$@"

_scripts-unit *args:
    @.scripts/just.py scripts-unit "$@"

_scripts-static *args:
    @.scripts/just.py scripts-static "$@"
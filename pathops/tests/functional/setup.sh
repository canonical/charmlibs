# sourced by `just functional pathops`
export PEBBLE=/tmp/pebble-test
umask 0
pebble run --create-dirs &>/dev/null &
PEBBLE_PID=$!

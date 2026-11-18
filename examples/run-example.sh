#!/bin/sh
# Run the checker over each example file and show the result.
# The flagged example fails on purpose, so each run is allowed to fail.
cd "$(dirname "$0")/.."
echo "== examples/clean.json =="
python3 src/json_required_key_checker.py --require name --require version --require author.name --require author.email examples/clean.json || true
echo
echo "== examples/flagged.json =="
python3 src/json_required_key_checker.py --require name --require version --require author.name --require author.email examples/flagged.json || true
echo
echo "== examples/edge.json =="
python3 src/json_required_key_checker.py --require name --require version --require meta.owner examples/edge.json || true
echo
echo "== examples/ : the whole folder =="
python3 src/json_required_key_checker.py --require name --require version examples/ || true

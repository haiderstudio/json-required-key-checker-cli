# json-required-key-checker-cli

Check JSON files contain required keys — fail CI when one is missing.

[![CI](https://github.com/haiderstudio/json-required-key-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/json-required-key-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`json_required_key_checker` reads each JSON file,
checks it contains every key named with `--require`,
and reports each missing key with the file and the
line. It exits 1 when any required key is missing,
so it can fail a CI run. A file with every required
key exits 0.

- Keys are named with dot paths for nested keys:
  `--require author.email` checks the `"email"`
  key inside the `"author"` object.
- A missing key is reported on the line of the
  object that should hold it — line 1 for a
  top-level key, the line of the `"author"` key
  for a missing `"author.email"`. That line is
  where the fix goes: add the key to that object.
- A key whose value is `null`, `false` or `0`
  counts as present — it exists, it just holds
  an empty or false value. Only a key that is
  not there at all is missing.
- A file given directly on the command line is
  always checked, whatever its name. A folder is
  walked for files ending in `.json` only,
  recursively by default (`--no-recursive` stops
  at the top level). `.git` folders are never
  walked, and directory links are never followed.
- Objects inside arrays are not checked:
  `--require` names keys of the document's
  objects, not of items in a list.
- `--json` prints the result as JSON, and
  `--stdin` checks one JSON document read from
  standard input.

## Who it is for

Every project with JSON config files — package
settings, editor settings, API fixtures, test
data. One key missing and the app breaks at
runtime, on the one code path that reads that
key — found in production, not in testing. This
is the gate that keeps the required keys in
place at the pull request.

## What it does NOT do

- It does not check that JSON is formatted or valid
  beyond parsing it — that is repo #19,
  json-formatter-validator-cli, which formats and
  validates JSON. This tool only checks required
  keys.
- It does not check for duplicate keys — that is
  repo #48, json-duplicate-key-checker-cli.
  Duplicates are a different check on the same
  files.
- It does not check key order — that is repo #109,
  json-key-sort-checker-cli. Order is a different
  check on the same files. The line-number
  technique here (a string-aware scan of the raw
  text, one key per line) is the same one repo
  #109 uses.
- It does not check keys inside arrays, and it
  does not check the type or value of a key — only
  that the key is there.
- It does not add a missing key for you. It only
  reports the keys that are missing.
- It never rewrites a file, and it never touches
  the network.

## How this differs

- A fresh search of GitHub on Nov 16, 2026 found 0
  results for `"json-required-key-checker-cli"` and 5
  results for `json required key checker`, all noise
  — miloslavatangen/Checker-Mnemonic, 96 stars, a
  crypto wallet analytics tool;
  misbahrehman-sys/llm-response-checker, 0 stars,
  which checks LLM responses for required keys, a
  different domain, not config files;
  Yankee-Actual/-hibp-vba-checker, 0 stars, an
  Excel breach checker; memeismygod/hack, 5 stars,
  a Discord script; VAIXLNS/VAIXLNS, 7 stars, not
  a checker at all.
- No rival checks required keys in local JSON
  config files.

## Install

```sh
git clone https://github.com/haiderstudio/json-required-key-checker-cli.git
cd json-required-key-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one JSON file for two required keys:

```sh
python3 src/json_required_key_checker.py --require name --require version config.json
```

A file with every required key passes:

```sh
$ python3 src/json_required_key_checker.py --require name --require version --require author.name --require author.email examples/clean.json
OK — 1 file(s) checked, every required key is present.
```

A file with keys missing fails, with the file and
line for each one:

```sh
$ python3 src/json_required_key_checker.py --require name --require version --require author.name --require author.email examples/flagged.json
FAIL examples/flagged.json: line 1 key "version" is missing
FAIL examples/flagged.json: line 2 key "author.email" is missing
Checked 1 file(s), 2 required key(s) missing in 1 file(s).
```

Check a whole folder (`.json` files only):

```sh
$ python3 src/json_required_key_checker.py --require name --require version examples/
FAIL examples/flagged.json: line 1 key "version" is missing
Checked 3 file(s), 1 required key(s) missing in 1 file(s).
```

Check one document from standard input:

```sh
$ printf '{"name": "a", "version": "1"}\n' | python3 src/json_required_key_checker.py --require name --require version --stdin
OK — 1 file(s) checked, every required key is present.
```

Machine-readable output:

```sh
$ python3 src/json_required_key_checker.py --require name --require version --require author.name --require author.email --json examples/flagged.json
{
  "files": [
    {
      "path": "examples/flagged.json",
      "findings": [
        {
          "line": 1,
          "reason": "key \"version\" is missing"
        },
        {
          "line": 2,
          "reason": "key \"author.email\" is missing"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 2
}
```

Exit codes: 0 when every required key is present,
1 when any key is missing or a file cannot be read
or parsed, 2 for a usage error (a missing path, a
missing `--require`, a bad flag, or no JSON files
found).

## Examples

A nested key three levels down — the missing key
is reported on the line of its parent object, so
the fix goes in the right place. `examples/edge.json`
has a colon inside a string value, a non-English
owner name, and objects inside an array, and it
passes:

```sh
$ python3 src/json_required_key_checker.py --require name --require version --require meta.owner examples/edge.json
OK — 1 file(s) checked, every required key is present.
```

A key holding `null` still counts as present — it
exists, it just holds no value. Only a key that is
not there at all is missing.

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_json_required_key_checker.py
```

The tests run the real CLI on throwaway files and
folders, check the bundled examples against their
saved output, and check every command quoted in
this README by running it.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool is original work, written for this
repository. It builds on the Python standard
library only (`json` with `object_pairs_hook`).
The line-number technique (a string-aware scan of
the raw text, one key per line) is the same one
used by repo #109, json-key-sort-checker-cli. The
idea was researched against GitHub on Nov 16,
2026 — no existing tool does this exact job, as
noted above under "How this differs".

#!/usr/bin/env python3
"""Check JSON files contain required keys.

Run: python3 src/json_required_key_checker.py --require name --require version config.json
     python3 src/json_required_key_checker.py --require name --require author.email data/
     python3 src/json_required_key_checker.py --require name --stdin < config.json

A missing key in a config file breaks the app at
runtime, on the one code path that reads that key
— found in production, not in testing. This tool
reads each JSON file, checks it contains every key
named with --require, and reports each missing key
with the file and the line, exiting 1, so it can
fail a CI run. A file with every required key
exits 0.

Keys are named with dot paths for nested keys:
--require author.email checks the "email" key
inside the "author" object. A missing key is
reported on the line of the object that should
hold it — line 1 for a top-level key, the line of
the "author" key for a missing "author.email".
That line is where the fix goes: add the key to
that object.

A file given directly on the command line is always
checked, whatever its name. A folder is walked for
files ending in .json only, recursively by default
(--no-recursive stops at the top level). .git
folders are never walked, and directory links are
never followed. Objects inside arrays are not
checked: --require names keys of the document's
objects, not of items in a list.

It never rewrites a file, never touches the network,
and reads only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

__version__ = "1.0.0"

JSON_SUFFIXES = (".json",)


class JsonObject(list):
    """A JSON object: a list of (key, value) pairs, in order.

    A plain list is a JSON array; this subclass marks a
    list that came from a JSON object, so the walker can
    tell the two apart.
    """


def _object_pairs(pairs):
    return JsonObject(pairs)


class AnnotatedObject(list):
    """An annotated JSON object: a list of (key, line, child) tuples.

    A plain list is an annotated JSON array, so the two
    never mix up — even when both are empty.
    """


def scan_key_lines(text):
    """Find every object key and the line it sits on.

    In valid JSON a string followed by a colon is always
    an object key — a string value is followed by a
    comma, a closing bracket, or a closing brace, never
    a colon. So a small string-aware scan over the raw
    text gives the keys in document order, one per key,
    matching the order the parsed structure walks in.
    """
    keys = []
    line = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
        elif ch == '"':
            start_line = line
            start = i
            i += 1
            while i < n:
                c = text[i]
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    break
                if c == "\n":
                    line += 1
                i += 1
            i += 1
            j = i
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] == ":":
                raw = text[start + 1:i - 1]
                try:
                    key = json.loads('"' + raw + '"')
                except ValueError:
                    key = raw
                keys.append((key, start_line))
        else:
            i += 1
    return keys


def _annotate(value, key_lines, index):
    """Attach a line number to every object key.

    An object becomes a list of (key, line, child)
    tuples, in document order; an array becomes a list
    of annotated children; any other value is left as
    it is. A tuple entry can only come from an object,
    so the two list shapes never mix up.
    """
    if isinstance(value, JsonObject):
        entries = []
        for key, item in value:
            if index[0] < len(key_lines):
                _scanned, line = key_lines[index[0]]
                index[0] += 1
            else:
                line = 1
            entries.append(
                (key, line, _annotate(item, key_lines, index)))
        return AnnotatedObject(entries)
    if isinstance(value, list):
        return [_annotate(item, key_lines, index) for item in value]
    return value


def _is_object(value):
    return isinstance(value, AnnotatedObject)


def _find_in_object(entries, wanted):
    for key, line, child in entries:
        if key == wanted:
            return line, child
    return None, None


def check_required(annotated, dotted):
    """Check one dotted path against an annotated document.

    Returns None when the key is present, or a finding
    {"line": int, "reason": str} when it is missing.
    A missing key is reported on the line of the object
    that should hold it.
    """
    segments = dotted.split(".")
    current = annotated
    current_line = 1
    for pos, segment in enumerate(segments):
        if not _is_object(current):
            return {
                "line": current_line,
                "reason": ('key "%s" is missing (%s is not an object)'
                           % (dotted, ".".join(segments[:pos]) or "root")),
            }
        line, child = _find_in_object(current, segment)
        if line is None:
            return {
                "line": current_line,
                "reason": 'key "%s" is missing' % dotted,
            }
        if pos == len(segments) - 1:
            return None
        current = child
        current_line = line
    return None


def check_text(text, required):
    """Check one document's text.

    Returns (findings, error): findings is a list of
    {"line": int, "reason": str} in the order the keys
    were required, and error is None or a string saying
    why the file could not be checked at all.
    """
    try:
        parsed = json.loads(
            text, object_pairs_hook=_object_pairs)
    except ValueError as exc:
        return [], "not valid JSON: %s" % exc
    key_lines = scan_key_lines(text)
    annotated = _annotate(parsed, key_lines, [0])
    findings = []
    for dotted in required:
        finding = check_required(annotated, dotted)
        if finding is not None:
            findings.append(finding)
    return findings, None


def check_file(path, required):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    return check_text(text, required)


def _is_json_file(path):
    return Path(path).name.lower().endswith(JSON_SUFFIXES)


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of JSON files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files ending in .json
    only. .git folders are never walked, and directory
    links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_json_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one missing key."""
    return ("FAIL %s: line %d %s"
            % (path, finding["line"], finding["reason"]))


def run(paths, required, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no JSON files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path, required)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d required key(s) missing "
                  "in %d file(s)."
                  % (len(files), findings, files_with_findings))
        else:
            print("OK — %d file(s) checked, every required key "
                  "is present." % len(files))
    return 1 if findings else 0


def run_stdin(required, as_json=False):
    """Check one JSON document read from standard input."""
    text = sys.stdin.read()
    bad, error = check_text(text, required)
    findings = len(bad) + (1 if error else 0)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": error}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        if error:
            print("FAIL <stdin>: %s" % error)
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d required key(s) missing "
                  "in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every required key "
                  "is present.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="json_required_key_checker",
        description="Check JSON files contain required keys, "
                    "fail CI when one is missing.")
    parser.add_argument("paths", nargs="*",
                        help="JSON files or folders to walk")
    parser.add_argument("--require", action="append", required=True,
                        help="a required key, dot paths for nested "
                             "keys (repeatable)")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one JSON document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(args.require, as_json=args.json)
    if not args.paths:
        parser.error("give at least one JSON file or folder")
    return run(args.paths, args.require,
               recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())

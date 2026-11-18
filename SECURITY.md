# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the JSON files you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL.

It only checks that required keys are present. It never adds a key, never deletes a key, and never runs code found in a JSON file.

If you find a case where the tool rewrites a file, opens a URL, or reports a pass for a JSON file missing a required key, please open an issue describing the exact commands and input. Do not include any real secret in the report.

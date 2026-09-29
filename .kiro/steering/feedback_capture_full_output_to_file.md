---
inclusion: always
name: feedback-capture-full-output-to-file
description: "For long/expensive commands, redirect full output + exit code to a file in ONE run, then inspect the file — never page-then-rerun."
---
For any slow or expensive command whose output you might need to inspect more than one slice of, redirect the FULL output and capture the exit code in a single invocation, then read the file as many times as needed:
```
hatch run release > ./tmp/release.log 2>&1; echo "EXIT: $?"
```
Then use Read / `grep` against `./tmp/release.log` for whatever slices you need (summary lines, failures, a specific stage). Re-inspecting the file is free; re-running the command is not. `tmp/` is gitignored.

**Why:** Piping an expensive command's first run through `tail`/`head`/`grep` discards the parts you'll discover you need. `hatch run release | tail -40` shows the end of the test matrix but cuts the `generate`, `lint`, and `typing` stage output and the exit code, forcing a second and third full re-run of codegen plus both Python versions. Same anti-pattern on scoped `hatch test` runs.

**How to apply:** Default to `cmd > ./tmp/<name>.log 2>&1; echo "EXIT: $?"` for anything that takes more than a few seconds and whose output you may need to examine in parts. Capture the exit code in that same line (don't re-run just to learn pass/fail). Only pipe-and-discard (`| tail`) when you are certain a single tail slice is all you will ever need from that run.

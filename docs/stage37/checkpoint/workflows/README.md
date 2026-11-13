# Workflow scripts of the paused Stage 37 verification

These are the Claude Code workflow scripts that ran the Stage 37 implementation and verification. They are kept here so that the remaining stages can be re-run with the same instructions.

- `verify-stage37-*.js` contain the adversarial review lenses, followed by one fix stage.
- `stage37-ux-settings.js` contains the UX baseline, the two implementers, the merge, the review and the fix stages.

The constants at the top of each script point to the paused session's scratchpad: `ROOT`, `SCRATCH`, `PY` and the venv paths. Set them for the new session before you run a script.

**Do not re-run a completed review lens.** Its results are in `../verification/*.json`. To run only a fix stage, give it the confirmed findings from that JSON file.

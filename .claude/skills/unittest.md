Base directory for this skill: /Users/ebattat/PycharmProjects/PerfX

# /unittest

Run PerfX unit tests with coverage reporting.

## Steps

1. **Ensure venv is active and dependencies installed**
   ```bash
   cd /Users/ebattat/PycharmProjects/PerfX
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt pytest pytest-cov -q
   ```

2. **Run all tests with coverage**
   ```bash
   cd /Users/ebattat/PycharmProjects/PerfX
   .venv/bin/pytest tests/ --cov=perfx --cov-report=term-missing --cov-fail-under=90 -q
   ```
   All tests must pass and coverage must be ≥ 90%.

3. **Report results**
   - Show the coverage table
   - List any failing tests with their error messages
   - If coverage < 90%, identify which modules need more tests

## Notes

- Live GitHub/Jira integration tests are skipped when credentials are absent — this is expected
- The venv may need to be recreated if the interpreter path is stale: `python3 -m venv .venv --clear`
- Skills scripts under `skills/` are tested via subprocess in `tests/perfx/skills/`
- To run a single test file: `.venv/bin/pytest tests/perfx/test_models.py -v`
- To run with a specific skill only: `.venv/bin/pytest tests/perfx/skills/test_vmexit_analysis.py -v`

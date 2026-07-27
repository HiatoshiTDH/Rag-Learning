# Repository conventions

- **Everything committed to this repository must be written in English**: documentation,
  code comments, docstrings, commit messages, prompts, test fixtures, and example data.
  (Vietnamese may appear only as deliberate test *data* for multilingual features,
  e.g. a Vietnamese query exercising the query-expansion feature in Plan 3.)
- Each plan lives in its own folder (`plan-XX-*/`) with `README.md` (design),
  `PLAN.md` (execution plan + status), `SETUP.md` (environment), and
  `TEST_AT_HOME.md` (live verification steps).
- Code is offline-first: every core mechanism must be testable with `pytest`
  using fake backends (no API keys, no docker). Real keys are only needed to
  measure quality.

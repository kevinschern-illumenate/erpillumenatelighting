### ilLumenate Lighting

Custom code for ilLumenate Lighting ERPNext

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app illumenate_lighting
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/illumenate_lighting
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### Local tests (no bench needed)

From a clean checkout, install the test tools once and run the service and generator suites:

```bash
python -m pip install -e ".[test]"
python -B -m unittest discover -s tests/portal_unit && python -B -m unittest discover -s tools/fixture_builder/tests
```

Browser DOM tests need Node.js: `npm ci --prefix tests/portal_ui && node --test tests/portal_ui/*.test.cjs`.

### CI

This app uses GitHub Actions. The following workflows are configured:

- CI: Installs this app on a Frappe v16 site and runs the installed-site suites on pull requests and pushes to `develop` and `main`. The upgrade rehearsal runs on pull requests and on pushes to `main`.
- B2B local contracts: Runs the unit, template and browser contract suites, and fails on new Ruff diagnostics in changed files (existing ones are a baseline), on pull requests and pushes.
- Linters: Runs pre-commit, [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit

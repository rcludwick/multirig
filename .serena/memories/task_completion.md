# Task Completion Checklist

When completing a task, verify the following:

## 1. Testing Requirements
- [ ] **UI Changes**: Must have Playwright test in `tests/e2e/`
- [ ] **Python Changes**: Must have pytest test in `tests/`
- [ ] **JavaScript Changes**: Must have Jest test in `js-tests/`
- [ ] Run appropriate test suite: `make test-py`, `make test-js`, or `make test-e2e`

## 2. Run Tests
```bash
make test-py    # For Python changes
make test-js    # For JS changes
make test-e2e   # For UI changes
make test       # For comprehensive changes
```

## 3. Code Quality
- [ ] Follow style guidelines (see code_style.md)
- [ ] Add docstrings/JSDoc for new functions
- [ ] No security vulnerabilities (OWASP top 10)

## 4. Configuration Changes
- [ ] New rig settings added to `RigConfig` model in `config.py`
- [ ] New status fields exposed in `RigClient.safe_status` (rig/client.py)
- [ ] Avoid frontend-only localStorage for core rig settings

## 5. Documentation
- [ ] Update `docs/design.md` for architectural changes
- [ ] Update `README.md` for user-facing changes

## 6. Static Assets
If legacy JS/CSS changed:
```bash
make minify-static
```

If React frontend changed:
```bash
make frontend-build
```

## Common Issues
- **E2E tests failing with ECONNREFUSED**: Ensure fixtures depend on `test_env`
- **Flaky UI tests**: Add proper waits (`wait_for_ready`, `wait_until="networkidle"`)
- **Model/caps not showing**: Check `model_id` in config and `rig_models.json`
- **Frontend not updating**: Rebuild with `make frontend-build`

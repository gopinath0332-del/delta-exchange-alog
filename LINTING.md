# Code Quality & Linting Setup

This project uses pre-commit hooks to ensure code quality and consistency.

## Tools Configured

### 1. **Black** - Code Formatter

- Automatically formats Python code
- Line length: 100 characters
- Ensures consistent code style

### 2. **isort** - Import Sorter

- Organizes imports alphabetically
- Groups imports by type (stdlib, third-party, local)
- Compatible with Black

### 3. **flake8** - Linter

- Checks for PEP 8 compliance
- Detects common errors and code smells
- Extensions:
  - `flake8-docstrings` - Docstring style checking
  - `flake8-bugbear` - Additional bug detection
  - `flake8-comprehensions` - Better comprehension checks

### 4. **mypy** - Type Checker

- Static type checking
- Catches type-related errors
- Improves code documentation

### 5. **bandit** - Security Scanner

- Scans for common security issues
- Checks for hardcoded passwords, SQL injection, etc.

### 6. **interrogate** - Docstring Coverage

- Ensures functions and classes have docstrings
- Minimum coverage: 50%

### 7. **safety** - Dependency Scanner

- Checks for known security vulnerabilities in dependencies

## Setup

### Install Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install git hooks
pre-commit install
```

Or use the Makefile:

```bash
make install-dev
```

## Usage

### Automatic (Recommended)

Pre-commit hooks run automatically on `git commit`:

```bash
git add .
git commit -m "Your commit message"
# Hooks run automatically
```

If any hook fails, the commit is aborted and you'll see the errors.

### Manual

Run all hooks on all files:

```bash
pre-commit run --all-files
```

Or use the Makefile:

```bash
make pre-commit
```

### Individual Tools

Run specific tools manually:

```bash
# Format code
make format          # Runs black and isort

# Lint code
make lint            # Runs flake8 and bandit

# Type check
make type-check      # Runs mypy
```

## Configuration Files

- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `pyproject.toml` - Tool-specific settings (black, isort, mypy, bandit, pytest)
- `Makefile` - Convenient development commands

## Ignoring Checks

### Temporarily Skip Pre-commit

```bash
git commit --no-verify -m "Skip pre-commit hooks"
```

**Note**: Only use this in emergencies. Always run hooks before pushing.

### Ignore Specific Lines

```python
# flake8: noqa - Ignore all flake8 errors on this line
# type: ignore - Ignore mypy errors on this line
# nosec - Ignore bandit security check
```

## CI/CD Integration

Pre-commit hooks should also run in CI/CD:

```yaml
# .github/workflows/lint.yml
name: Lint

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.9"
      - name: Install dependencies
        run: |
          pip install pre-commit
          pre-commit install-hooks
      - name: Run pre-commit
        run: pre-commit run --all-files
```

## Troubleshooting

### Hook Installation Failed

```bash
# Clear pre-commit cache
pre-commit clean

# Reinstall hooks
pre-commit install --install-hooks
```

### Hooks Taking Too Long

```bash
# Run only on changed files
pre-commit run

# Skip specific hooks
SKIP=mypy git commit -m "Skip mypy"
```

### Update Hooks

```bash
# Update to latest versions
pre-commit autoupdate
```

## Best Practices

1. **Run hooks before committing**: `make pre-commit`
2. **Fix issues immediately**: Don't accumulate linting errors
3. **Keep dependencies updated**: Run `pre-commit autoupdate` monthly
4. **Document exceptions**: If you must ignore a check, add a comment explaining why
5. **Review hook output**: Don't blindly accept auto-fixes

## Example Workflow

```bash
# 1. Make changes
vim core/config.py

# 2. Format code
make format

# 3. Check for issues
make lint
make type-check

# 4. Run all pre-commit hooks
make pre-commit

# 5. Commit (hooks run automatically)
git add .
git commit -m "Add new configuration option"

# 6. Push
git push
```

## Makefile Commands

```bash
make help           # Show all available commands
make install        # Install production dependencies
make install-dev    # Install development dependencies
make setup          # Complete project setup
make lint           # Run linters
make format         # Format code
make type-check     # Run type checking
make pre-commit     # Run all pre-commit hooks
make test           # Run tests
make test-cov       # Run tests with coverage
make clean          # Clean build artifacts
```

## Additional Resources

- [Pre-commit Documentation](https://pre-commit.com/)
- [Black Documentation](https://black.readthedocs.io/)
- [flake8 Documentation](https://flake8.pycqa.org/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [bandit Documentation](https://bandit.readthedocs.io/)

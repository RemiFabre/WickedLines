# Contributing to WickedLines

Thanks for your interest in contributing!

Help is welcome, especially for testing and reliability.

## 🔧 Setup

1. **Clone the repo**

```bash
git clone https://github.com/RemiFabre/WickedLines.git
cd WickedLines
```

2. **Install dependencies**
```bash
pip install -e .[dev]
```


## 🧪 Tests

Tests are written using `pytest`. To run them:

```bash
pytest
```

If you’re adding a feature or fixing a bug, please write a test for it.

## 🧼 Code Style

We use:

- `black` (line length 128)
- `isort` for import order
- `flake8` for linting

To check formatting:

```bash
black . --check --line-length 128
isort . --check-only
flake8
```

You can auto-fix:

```bash
black . --line-length 128
isort .
```

## ✅ CI

All commits and PRs on `main` are tested via GitHub Actions. Badges are shown in the README.

## 💡 Tips

- If you're working on features related to statistics, double-check logic carefully, it's easy to make mistakes that silently bias results.
- Please explain what you did and how you tested in the PR description.

## 🙏 Thanks

Every contribution counts. If you're unsure how to help, feel free to open an issue.
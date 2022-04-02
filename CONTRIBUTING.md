# Contributing Guide

All contributions are greatly appreciated! Before contributing, please read the [code of conduct][].

## Development Setup

This project uses [Poetry][] to manage dependencies and builds, and you will need to install it before working on Unicycle.

Once Poetry is installed, you should be good to set up a virtual environment and install development dependencies. Python >= 3.10 is recommended for development.

```bash
git clone https://github.com/mcous/unicycle.git
cd unicycle
poetry install
```

## Development Tasks

### Tests

Unicycles's tests are run using [pytest][].

```bash
poetry run pytest
```

You can also run tests in watch mode using [pytest-xdist][].

```bash
poetry run pytest --looponfail
```

### Checks

Unicycle's source code is typechecked with [mypy][] and linted with [flake8][].

```bash
poetry run mypy
poetry run flake8
```

### Formatting

Unicycle's source code is formatted using [black][].

```bash
poetry run black .
```

## Deploying

The library will be deployed to PyPI by CI. To trigger the deploy, cut a new version and push it to GitHub.

Unicycle adheres to [semantic versioning][], so care should be taken to bump accurately.

```bash
# checkout the main branch and pull down latest changes
git checkout main
git pull

# bump the version
# replace ${bump_version} with a bump specifier, like "minor"
poetry version ${bump_version}

# add the bumped pyproject.toml
git add pyproject.toml

# commit and tag the bump
# replace ${release_version} with the actual version string
git commit -m "chore(release): ${release_version}"
git tag -a v${release_version} -m "chore(release): ${release_version}"
git push --follow-tags
```

[code of conduct]: https://github.com/mcous/unicycle/blob/main/CODE_OF_CONDUCT.md
[poetry]: https://python-poetry.org/
[pytest]: https://docs.pytest.org/
[pytest-xdist]: https://github.com/pytest-dev/pytest-xdist
[mypy]: https://mypy.readthedocs.io
[flake8]: https://flake8.pycqa.org
[black]: https://black.readthedocs.io
[mkdocs]: https://www.mkdocs.org/
[semantic versioning]: https://semver.org/

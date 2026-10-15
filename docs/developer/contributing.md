---
title: Working on the code
description: Running the tests and the linters on your own copy of Flashlights
---

# Working on the code

Flashlights is published for use and study, and does not take code
contributions. Bug reports and ideas are welcome as
[issues](https://github.com/mariatta/flashlights/issues); report security
problems privately, as `SECURITY.md` in the repository describes.

You are free to run and change your own copy under the licence: the GNU
AGPL version 3, with an additional permission to run a modified copy for
your own organisation's events without publishing the changes. See
`LICENSE` in the repository.

## Setup

To start working with the code, refer to the [setup guide](/developer/setup/).

## Running Tests

Tests are run using [pytest](https://docs.pytest.org/en/latest/).

To run the tests:

```bash
make test
```

## Test coverage

Flashlights keeps 100% test coverage. The coverage report is generated after
running the tests, and can be viewed in the `htmlcov` directory.

## Code style and linting

Run `make reformat` and `make check` before committing. CI runs the same
checks.

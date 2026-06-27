# Copilot Instructions

## Packages

Please use the `uv` package manager.

```shell
uv add <package-name>
```

Do not use `pip`, `uv pip install`, or `uv pip install -e .` to install packages or this project.

## Ruff

We use Ruff for linting and formatting. Please ensure your code passes all checks before submitting a pull request.
You can run the linter with the following command:

```shell
uv run ruff check .
```

You can also run the linter with the `--fix` option to automatically fix some issues:

```shell
uv run ruff check . --fix
```

You can also run the linter with the `--check` option to check for issues without fixing them:

```shell
uv run ruff . --check
```

## Testing

When adding features, always include appropriate tests. Run the entire test suite with:

```shell
uv run pytest
```

## Code Coverage

We aim for >= 80% test coverage before merging any pull requests.

1. Check your coverage with:

```shell
uv run pytest --cov=tapio
```

1. Generate HTML coverage reports for visual inspection:

```shell
uv run pytest --cov=tapio --cov-report=html
```

1. For specific module coverage:

```shell
uv run pytest --cov=tapio.utils tests/utils/
```

Aim for at least 80% coverage for new code. The HTML coverage report can be found in the `htmlcov` directory.

## Code Analysis

We use Pyrefly for static code analysis to identify potential bugs.

You can run the code analysis checker with the following command:

```shell
uv run pyrefly check
```

Pyrefly will analyze your code for:

- Potential bugs
- Code quality issues
- Type safety concerns

Configuration for Pyrefly is stored in `pyrefly.toml`. Please address any issues reported by Pyrefly or provide justification for exceptions if needed.

## Ollama

We use Ollama for local LLM inference.

The following Ollama models are used in the project:

- `llama3.2`: The base model for text generation.

To query the Ollama models that are installed, use the command:

```shell
ollama list
```

To list all Ollama commands, use the command:

```shell
ollama help
```

To get help for a specific command, use the command:

```shell
ollama <command> --help
```

## Code Style

### Type Hints

- Use type hints for all function parameters and return types.
- Use `Optional` for optional parameters and return types.
- Use `list`, `dict`, `set`, and `tuple` for built-in types.

### Mypy

We use Mypy for type checking. Please ensure your code passes all checks.
You can run Mypy with the following command:

```shell
uv run mypy .
```

You can also run Mypy with the `--strict` option to enable strict type checking:

```shell
uv run mypy . --strict
```

### Ignoring Mypy Errors

Prefer to include the error code in the comment, e.g. `# type: ignore[code]`, instead of using `# type: ignore` to ignore all errors. This makes it easier to identify the specific issue being ignored. For example:

```python
def my_function(x: int) -> str:  # type: ignore[return-value]
    return x  # type: ignore[argument]
```

This way, you can easily identify the specific issue being ignored and it makes it easier to fix the issue in the future.

### Type Stubs

We define type stubs for third-party libraries that do not have type hints. Type stubs are files with the `.pyi` extension that contain only type hints. They are used to provide type information for libraries that do not have type hints.

Type stubs should be placed in the `stubs` directory. The directory structure should match the package structure of the library. For example, if you have a library called `mylib`, the type stub file should be named `mylib.pyi` and placed in the `stubs/mylib` directory.

### Docstrings

- Use Google-style docstrings for all functions and classes.
- Include a summary of the function, parameters, and return types.
- Use `:param` for parameters and `:return` for return types.
- Use `:raises` for exceptions.
- Use `:example` for examples.
- Use `:note` for notes.
- Use `:todo` for TODOs.
- Use `:deprecated` for deprecated functions.
- Use `:see:` for references.
- Use `:warning:` for warnings.

# rag-pipeline-yaml

[![PyPI version](https://img.shields.io/pypi/v/trysac-rag-pipeline-yaml)](https://pypi.org/project/trysac-rag-pipeline-yaml/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-rag-pipeline-yaml)](LICENSE)
[![CI](https://github.com/Trysac/u113-rag-pipeline-yaml/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u113-rag-pipeline-yaml/actions/workflows/ci.yml)

Declarative RAG pipelines in YAML: registered components, typed variable interpolation, static checks before any step runs, alias-free safe loading and content-free traces

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-rag-pipeline-yaml
# or
uv add trysac-rag-pipeline-yaml
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import rag_pipeline_yaml

# normalize() trims surrounding whitespace and lower-cases the text.
print(rag_pipeline_yaml.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    rag_pipeline_yaml.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez

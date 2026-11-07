# Architecture

`trysac-rag-pipeline-yaml` provides a declarative, strictly validated execution graph for Retrieval-Augmented Generation (RAG) pipelines defined in YAML.

## Core Principles

1. **Safe Loading First**: Pipeline text is checked for maximum byte length and scanned for YAML events (such as `AliasEvent` and anchors) before parsing data. This completely avoids parser-level expansion and billion-laughs vulnerabilities.
2. **Static Validation**: Variable references `${var}` are statically checked at load time against pipeline inputs and previous step outputs. Shadowing is strictly forbidden.
3. **Content-Free Tracing**: Step traces record only `step_id`, `component`, `status` (`ok` or `error`), and elapsed milliseconds `duration_ms`.
4. **Injected Dependencies**: The execution engine does not bundle network clients or vector stores. The LLM port is injected via `LLMPort` protocol, and custom components are registered in a local `Registry`.

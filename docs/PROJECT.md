# Project Record

## Objective

To provide a lightweight, declarative execution engine for RAG pipelines defined in YAML, enabling static analysis and auditing of pipeline structure.

## Scope

- YAML loading and structural validation (pipeline, version, inputs, steps).
- Static variable interpolation and dependency resolution checks.
- A registry mechanism for injecting user-defined components.
- Standardized LLM interaction protocols (`LLMPort`) and test doubles (`FakeLLM`, `RecordedLLM`).
- Content-free step execution tracing.
- Command-line tool for pipeline validation.

## Out-of-Scope

- Bundled retrievers or vector stores.
- Branching logic or parallel step execution.
- Automatic retries or asynchronous execution engines.

## Factory run u113 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | gemini-3.8-flash | yes | 4616 | 12438 | 0 | 0 | 0.0251 |
| fix-1 | gemini-3.8-flash | no | 25087 | 637 | 0 | 60112 | 0.0257 |
| fix-2 | gemini-3.8-flash | no | 88494 | 2165 | 0 | 797784 | 0.1343 |
| fix-3 | gemini-3.8-flash | no | 63170 | 1053 | 0 | 343323 | 0.0771 |
| fix-4 | gemini-3.8-flash | no | 45686 | 1376 | 0 | 186129 | 0.0534 |
| audit | gemini-3.1-flash-lite | no | 47223 | 199 | 0 | 103835 | 0.0147 |
| docs | gemini-3.1-flash-lite | no | 159934 | 1208 | 0 | 0 | 0.0418 |

Total: $0.3720. Prices: Anthropic list prices.

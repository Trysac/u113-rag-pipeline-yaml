# Use PyYAML SafeLoader with Pre-parse Event Scanning and Content-Free Tracing

Status: accepted (generated, pending human review)

## Context

RAG pipelines defined declaratively in YAML from untrusted or shared sources can be vulnerable to YAML billion-laughs attacks and data leakage in telemetry traces. Furthermore, dynamic pipeline execution often fails midway due to undefined variable references.

## Decision

We enforce strict safe parsing by scanning PyYAML parse events for any AliasEvent or anchors before constructing data structures. We perform static variable analysis at pipeline load time to ensure all referenced variables are either defined inputs or outputs from preceding steps. Telemetry is modeled as content-free StepTrace objects containing only step IDs, component names, status, and duration.

## Consequences

Malicious YAML inputs with recursive aliases or anchors are rejected immediately with 'alias_forbidden'. Pipelines fail fast with 'undefined_variable' if misconfigured. Execution traces are safe for logging without sanitization.

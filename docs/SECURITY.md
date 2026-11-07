# Security Model

## Threat Model & Defenses

1. **YAML Expansion Attacks (Billion-Laughs)**: The pipeline strictly rejects YAML aliases and anchors. The loader explicitly scans for `AliasEvent` and anchor attributes before parsing. Violations result in an `alias_forbidden` error.
2. **Arbitrary Code Execution**: Only `yaml.SafeLoader` is used. Custom Python object instantiation through YAML tags is not supported.
3. **Information Leakage**: Step traces are explicitly content-free. `StepTrace` objects record only `step_id`, `component`, `status` (`ok` or `error`), and `duration_ms`. No inputs, retrieved documents, or model completions are ever captured in trace records.
4. **Denial of Service**: Pipeline text input is restricted to a maximum size (default 65,536 bytes), returning `too_large` if exceeded.
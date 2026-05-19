# Security Policy

`bvr-sim` is a research simulation environment. Do not use public issues for private credentials, exploitable crashes, or sensitive deployment details.

## Reporting

If you find a security issue, contact the maintainers privately before publishing details. Include:

- A minimal reproduction.
- Affected platform and commit or version.
- Whether the issue affects Python code, the C++ backend, the web visualization, or build scripts.

## Secrets

The repository should not contain API keys, service tokens, private model credentials, or local machine paths. Agent and LLM examples must read credentials from environment variables.


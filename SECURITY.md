# Security Policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in `z4j-django`,
**do not open a public GitHub issue**. Email `security@z4j.com` instead.

We acknowledge reports within **48 hours**, provide a preliminary assessment
within **5 business days**, and target fixes within **30 days** (**7 days** for
confirmed critical issues). Reporting timelines, safe harbor, supported-version
policy, and published advisories are maintained in the
[canonical z4j project security policy](https://github.com/z4jdev/z4j/blob/main/SECURITY.md).

## Security-critical surface

This integration starts the agent inside Django processes, reads agent secrets
from settings/environment, and discovers configured Celery objects. Secret
handling, engine discovery, and startup failure isolation are package-specific
security surfaces; transport, payload redaction, and authorization policy
remain owned by `z4j-core` and the brain. The framework exposes context helper
methods, but the current agent runtime does not attach their values to events.

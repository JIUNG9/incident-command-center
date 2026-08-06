# Security Policy

## Reporting a vulnerability

Please open a private security advisory via GitHub:
https://github.com/JIUNG9/devsecops-command-center/security/advisories/new

(Updated from `JIUNG9/teammate` — the repo was renamed twice, teammate → vigil →
devsecops-command-center. GitHub redirects the old paths, but the current name is the
one worth printing.)

Acknowledgement within a few days. This is personally maintained, so response is
best-effort rather than contractual; if something is being actively exploited, say so
in the first line.

> **Maintainer note:** the link above requires *Private vulnerability reporting*
> switched on under **Settings → Advanced Security**. One checkbox, free on public
> repos. Until it's on, that URL 404s for outside reporters.

## Threat model

The signed compliance attestation PDFs produced by `teammate score --sign`
are designed to be auditable artifacts. The threat model and verification
procedure are documented in [docs/SECURITY.md](docs/SECURITY.md).

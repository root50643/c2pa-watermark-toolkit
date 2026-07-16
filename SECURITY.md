# Security Policy

Do not include API keys, customer images, `archive-data`, SQLite files, HF tokens, or production logs in issues.

- Replace `API_KEY_PEPPER` before issuing production keys.
- Restrict archive directory and Docker socket access.
- Set `TRUSTED_PROXY_CIDRS` only to proxies you control.
- Terminate TLS and apply rate limits at a trusted reverse proxy.
- Rotate/revoke a customer key with `raiw-api-admin` when exposure is suspected.

Report vulnerabilities privately to the repository owner before public disclosure.

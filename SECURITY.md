# Security Policy

## Supported version

Security fixes are considered for the code on the `main` branch, which contains the current web application and Cloudflare Worker.

## Reporting a vulnerability

Please do not report exploitable vulnerabilities in a public issue or pull request.

If private vulnerability reporting is enabled for this repository, submit a report through [GitHub's private vulnerability reporting](https://github.com/cooolv/Muslim-Bot/security/advisories/new). If it is unavailable, contact the repository owner privately through [GitHub](https://github.com/cooolv) and ask for a private reporting channel. Share only the information needed to understand and reproduce the issue.

Include, when possible:

- The affected component or file.
- The impact and conditions needed to trigger the issue.
- Minimal reproduction steps or a proof of concept that does not access other people's data.
- Any suggested mitigation.

Do not include real API keys, personal information, or other secrets in a report. If a credential may have been exposed, revoke or rotate it immediately and notify the maintainer without repeating the credential.

## Response

The maintainer will review reports and coordinate any fix or disclosure with the reporter. Response and resolution times are not guaranteed.

## Scope and limitations

The application uses third-party services, including Cloudflare, Google Gemini, Aladhan, and OpenStreetMap Nominatim. Their services and policies are outside this repository's control. The project's input and output checks are safeguards, not a guarantee of absolute security or safety.

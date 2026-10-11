# Security policy

## Supported versions

Only the [latest release](https://github.com/JySa65/pista-downloader/releases/latest) gets security fixes. Please update before reporting.

## Verifying downloads

Release installers come with `SHA256SUMS.txt` and a signed build-provenance attestation produced by the release workflow. Verify with `sha256sum -c SHA256SUMS.txt --ignore-missing` and `gh attestation verify <file> --repo JySa65/pista-downloader`.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report privately through GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability**, or go directly to
https://github.com/JySa65/pista-downloader/security/advisories/new.

Include:

- the app version (shown next to the name in the title bar) and your OS;
- what an attacker could do and how to reproduce it;
- any relevant lines from the log file («Abrir registro»). Home-directory paths in the log are already replaced with `~`, but remove any private links before sharing.

You should get a first reply within 7 days. Fixes ship in a new release, and the advisory is published once users have had a chance to update.

## Scope

In scope: this app's code, its installers, and how they bundle and call third-party tools (yt-dlp, Deno, FFmpeg).

Vulnerabilities in those third-party projects themselves should be reported upstream (see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)). We will update the bundled versions once a fix is released.

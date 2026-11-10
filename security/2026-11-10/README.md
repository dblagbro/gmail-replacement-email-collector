# Collector 1.1.0 security release

The runtime updates FastAPI/Starlette, multipart parsing, cryptography, OAuth and related supported dependencies. The Linux amd64 image uses a pinned Python 3.12 base and exact resolved versions in requirements.lock. requirements.txt remains the direct dependency specification for development/Windows; the Linux lock is not a Windows lock.

OAuth transactions now expire after ten minutes, are bound to the initiating logged-in session and redirect URI, preserve the PKCE verifier, and are consumed atomically once. Sessions expire on the server after 24 hours, are stored by token hash, and are invalidated on password change. Existing 1.0.4 sessions must log in again. Passwords are limited to bcrypt's 72 UTF-8 byte boundary. HTTPS cookies use Secure, HttpOnly, SameSite=Lax and the configured URL_PREFIX path. Unsafe UI requests require a matching Origin or Referer; non-browser callers must send the correct Origin. Configure PUBLIC_BASE_URL to the external HTTPS origin behind a reverse proxy. No provider accounts or mail need reconfiguration.

Template calls use the supported request-first Starlette API. The archive view also handles legacy messages with a missing recorded size. No schema migration or mail deletion is introduced. The retained original image can boot the same schema if rollback is required; old browser sessions may need a fresh login.

## Reproduce and validate

On Linux amd64: `docker build -t gmail-email-collector:1.1.0 .`. The example Compose file builds this source rather than silently pulling an old latest tag. Run `python -m pip install -r requirements.lock pytest==9.2.0`, `python -m pip check`, `python -m pytest -q`, and `python security/2026-11-10/test_release.py`. Test data and OAuth/provider clients are synthetic. Provider network operations are forbidden in tests. Deployment evidence will identify the exact built image and residual scan findings separately from source completion.

## Recovery and scoped deployment

Use release.py through the [maintained capacity guard](https://github.com/dblagbro/tmrwww01-docker-scripts/blob/main/security/2026-11-09/storage/capacity_guard.py), supplying action rehearse or deploy, --compose, --data, --backup-root, --receipt, --original-image, --candidate-image and --probe. The backup root must be private and outside the repository. Rehearse briefly stops only the collector to copy a consistent database, encryption key and archives, restarts the original, restores two independent private copies, and boots both candidate and original with networking disabled. The probe disables all provider workers and scheduled tasks; it checks protected table fingerprints, secret decryption, login/health/auth redirects and key preservation without printing data.

Deploy additionally requires --recovery-receipt and --approval. The approval JSON must identify merged source, passing checks, equality of candidate inputs to that source, and the exact image. Deployment takes a fresh quiesced backup, verifies Compose differs only in this service image, preserves unrelated configuration and Nginx, checks health and has an original-image rollback path. Mail workers resume their normal work after rollout; no real provider insert/send acceptance test is authorized by these offline tests. Retain snapshots, keys, original images and deployment receipts. Never commit these private files.

## Evidence and limits

Initial candidate: 25 tests passed; a synthetic archive record exposed the missing-size template error and the candidate was withheld. The corrected exact candidate is sha256:6bd5ace4605ed13e295c62b40fcd94dbd49e281a8dade6f6b3b88934df09ad88. All30 offline regressions,6 release-scope checks, unmodified application/scheduler boot, independent candidate restoration and original-image rollback boot pass. Its scan is0 Critical/47 High, versus the original retained0/66; none lists an available fixed version. Production rollout is still pending. See candidate-evidence.json for sanitized evidence. A dependency scan is not proof every residual package match is reachable. External OAuth consent and mailbox delivery acceptance remain unverified until separately exercised by an owner. Source review also identified abandoned OAuth transactions that can leave provisional encrypted credential rows; cleanup retention is a follow-up, not claimed fixed here.

Primary references: https://starlette.dev/templates/ ; https://developers.google.com/identity/protocols/oauth2/web-server ; https://pypi.org/project/fastapi/ ; https://pypi.org/project/cryptography/ .


## Runtime policy serialization correction

The first rollout reached a healthy candidate, but the strict runtime comparison rejected Docker's equivalent default-DNS encodings: the old container used empty lists and newly created containers used null for Dns, DnsOptions and DnsSearch. Automatic rollback restored the original image and exact Compose content. The comparator now normalizes only those empty/default fields, while explicit DNS settings, memory limits, mounts and other policies remain checked. Three added regressions verify that distinction. Candidate inspection is retained only in the private backup directory before validation so any future failure is diagnosable without publishing environment values. This operator correction does not rebuild or change the tested application image.

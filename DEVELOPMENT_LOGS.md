## [2026-11-03 01:00] Step P40: Publish demo projects
- Status: PARTIAL
- Files created or modified: .gitignore, DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Prepared the demo folder as the root of the requested repository.
  - Excluded trusted key files and the explicitly private device seed header.
  - Included the proxy sources, their tests, and the Wi-Fi satellite firmware sources.
- Commands executed and test results: Repository initialization and publication are in progress; no test script is present in the provided folder.
- Decisions and assumptions: The user asked to publish the contents of Desktop/demo to trustthepixel/demo main. Secret key material is excluded from Git.
- Remaining work / exact stopping point: Stage safe project files, commit on main, and push to origin; update this entry with the actual result.

## [2026-11-03 01:02] Step P40: Confirm demo publication
- Status: DONE
- Files created or modified: DEVELOPMENT_LOGS.md.
- Summary of work completed (3–8 lines):
  - Published both requested project folders to trustthepixel/demo main.
  - The initial project snapshot is commit 93a55d4; this entry records the final verification.
  - The trusted_keys directory and explicitly private device_seed.h remain excluded from Git.
- Commands executed and test results: Initial commit and push succeeded. scripts/check.ps1 is absent; no tests were run.
- Decisions and assumptions: The user requested publication of the contents of Desktop/demo. Private key material was excluded.
- Remaining work / exact stopping point: The source snapshot is published. The firmware seed header is excluded and must be provided through a secure local mechanism when building firmware.
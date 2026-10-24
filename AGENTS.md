# Project instructions

## Versioning and GitHub updates

The owner requires Semantic Versioning and a published GitHub release whenever
application changes are delivered to GitHub. A merged pull request alone does not
complete such an update. Documentation-only changes do not require an app release.

- Use a patch version for compatible fixes, a minor version for compatible new
  features, and a major version for breaking changes.
- Record user-visible changes in `CHANGELOG.md`, then prepare the version with
  `python scripts/release.py prepare X.Y.Z` before opening the delivery PR.
- Follow `docs/RELEASING.md`: validate metadata, run the offline tests and plugin
  validation, build the package and verify its checksum, and wait for CI before
  merging.
- Tag the merged commit with `vX.Y.Z` and wait for the Release workflow. Inspect
  the draft notes and verify the downloadable archive and checksum, then publish
  the release. Do not stop at a draft unless the owner explicitly requests it.
- Requests to update this project on GitHub authorize this release workflow;
  do not request a separate confirmation for routine versioning and publication.
- Never move a published tag or replace published assets. Fix issues in a new
  version and include the published release link in the completion message.

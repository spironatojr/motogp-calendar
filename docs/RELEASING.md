# Versions and releases

`VERSION` is the source of the app version. `app_version.py` reads it at runtime;
`motogp-calendar --version` also works without GTK. The release helper synchronizes
the plugin manifest when preparing the next version. The installer copies both
version files and rejects a mismatched plugin before changing desktop configuration.

Use [Semantic Versioning](https://semver.org/): patch for compatible bug fixes,
minor for compatible features, and major for incompatible changes to documented
commands, installation or saved data. Use `-rc.1`, `-rc.2`, etc. for release candidates.
The app version is independent of the season year and refreshed race data.

## Develop and review

1. Create a short-lived branch: `git switch -c feat/your-feature` or `fix/your-fix`.
2. Implement the change and list user-visible changes under `[Unreleased]` in
   `CHANGELOG.md`. Documentation-only changes do not require a new app release.
3. Run `python -m unittest discover -s tests -v` and open a pull request into `main`.
4. Merge after the Python 3.11 and 3.14 CI checks pass and the change is reviewed.

CI validates version metadata, runs offline tests, builds the package, checks its
checksum, and verifies commands and tests from the extracted package. It does not
validate the live Omarchy desktop or replace a manual GUI check on Omarchy.

## Prepare a release

From an up-to-date, clean `main`, create a release branch and prepare a version:

```sh
git switch main
git pull --ff-only
git switch -c release/1.0.1
# First write the release's changes under [Unreleased] in CHANGELOG.md.
python scripts/release.py prepare 1.0.1
python scripts/release.py check --tag v1.0.1
python -m unittest discover -s tests -v
omarchy plugin validate ./plugin
python scripts/release.py build
(cd dist && sha256sum --check SHA256SUMS)
```

The helper moves the Unreleased notes into a dated section, updates `VERSION` and
the plugin manifest, and leaves an empty Unreleased section for subsequent work.
It refuses invalid, older or reused versions and empty release notes.

Open the GUI on Omarchy and check month navigation, race selection, podiums,
refresh and calendar export. Review and commit the prepared files, open a PR,
and merge after CI passes. Then tag the merged commit:

```sh
git switch main
git pull --ff-only
python scripts/release.py check --tag v1.0.1
git tag -a v1.0.1 -m "MotoGP Calendar v1.0.1"
git push origin v1.0.1
```

The tag starts the Release workflow. After the same CI checks pass, it creates a
**draft** GitHub release with the changelog notes, an installable
`motogp-calendar-1.0.1.tar.gz`, and `SHA256SUMS`. Release candidates are marked as
prereleases. Archives contain a selected set of app files, assets, documentation
and tests; local backups, caches and Git metadata are excluded. Package generation
is reproducible for identical input files.

Inspect the draft's notes and downloads, then publish it in GitHub's Releases page
or explicitly with:

```sh
gh release edit v1.0.1 --draft=false
```

The workflow can be rerun to repair a draft. It refuses to replace an already
published release. Never move a published tag or overwrite released assets; fix
problems in a new version instead.

## Install a specific version

Download the package and `SHA256SUMS` from the same
[GitHub release](https://github.com/spironatojr/motogp-calendar/releases). For v1.0.0:

```sh
sha256sum --check SHA256SUMS
tar -xzf motogp-calendar-1.0.0.tar.gz
cd motogp-calendar-1.0.0
python install.py
motogp-calendar --version
```

Close the running calendar before installing or updating, then reopen it. The
package requires the existing Omarchy desktop dependencies; it is a source package,
not a standalone binary. Installing it does not require Git or GitHub CLI.

## Return to an earlier version

Close the app, download an earlier release, verify its checksum, and run that
version's `python install.py`. Reopen the app and confirm `--version`. Existing
installer backups are stored in `backups/` inside the directory from which the
installer was run; keep them until the update has been checked.

The installer preserves the refresh cache in `~/.cache/motogp-calendar` (or
`$XDG_CACHE_HOME/motogp-calendar`). Before downgrading across a major version, read
both releases' compatibility notes and back up that directory. Older releases may
not understand newer data formats or undo a later configuration migration.

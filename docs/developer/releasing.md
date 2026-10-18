---
title: Releasing
description: How a version of Flashlights is released, and the images each release publishes
---

# Releasing

Flashlights is released as a container image. A deployment, or a
community's own image ([Community apps](community_apps.md)), pins one
version and upgrades by changing the tag.

## What a release publishes

Pushing a tag `vX.Y.Z` runs `.github/workflows/release.yml`, which runs
the same checks as every pull request and then publishes:

| Image | What it is | Platforms |
|---|---|---|
| `ghcr.io/mariatta/flashlights:X.Y.Z` | Slim, the default: no transcription library or model | Intel and ARM |
| `ghcr.io/mariatta/flashlights:X.Y` | The newest `X.Y.Z` of that minor version | Intel and ARM |
| `ghcr.io/mariatta/flashlights:latest` | The newest release | Intel and ARM |
| `ghcr.io/mariatta/flashlights:X.Y.Z-full` | Full: adds machine transcription with the `small` model | Intel |
| `ghcr.io/mariatta/flashlights:X.Y-full` | The newest full `X.Y.Z` of that minor version | Intel |

and a GitHub release whose notes are the version's section of
`CHANGELOG.md`. Pin a deployment to `X.Y.Z`; `X.Y` and `latest` move.
[Deployment](deployment.md) says what each flavour needs at run time.

## Versions

`pyproject.toml` holds the version. Before 1.0, a minor version (`0.2.0`)
may change anything, and a patch version (`0.1.1`) only fixes. From 1.0,
any change to the [public API](community_apps.md#public-api) for
community apps is a major version and is marked **Breaking** in the
changelog.

## Making a release

1. While work lands, each change that a deployment would notice gets a line
   under the next version's heading in `CHANGELOG.md`, written
   `## X.Y.Z (unreleased)`. A test fails when `pyproject.toml`'s version
   has no section, so bumping the version means starting its entry.
2. When it is time, date the heading, `## 0.2.0 (2026-11-20)`, check that
   `pyproject.toml` says the same version, and commit on `main`.
3. Tag that commit and push the tag:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. The workflow refuses to publish when the tag is not `v` plus the
   version, or when the changelog section is missing or undated:
   `python scripts/release.py v0.2.0` runs the same check locally and
   prints the notes it would publish.
5. Afterwards, start the next entry: bump the version and add
   `## 0.2.1 (unreleased)` (or the next minor) at the top.

A failed run publishes nothing, or only some of the images; fix the
cause and run the workflow again from the Actions tab. A tag that was
pushed by mistake is deleted on GitHub and locally before anything uses it.

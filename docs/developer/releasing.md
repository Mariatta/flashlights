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

The same run publishes this version of the documentation at
`https://docs.flashlights.app/X.Y.Z/`, and points
`https://docs.flashlights.app/latest/` at it. A deployment's
help links go to the version matching its image (`DOCS_URL` in the
[environment reference](environment.md)); a community with docs of its
own links to the core docs at its pinned version. The versions are
folders on the `gh-pages` branch, kept by [mike](https://github.com/jimporter/mike),
and the site's version selector lists them.

## Versions

`pyproject.toml` holds the version. Before 1.0, a minor version (`0.2.0`)
may change anything, and a patch version (`0.1.1`) only fixes. From 1.0,
any change to the [public API](community_apps.md#public-api) for
community apps is a major version and is marked **Breaking** in the
changelog.

## Making a release

1. The first change after a release that a deployment would notice opens
   the next version: that pull request bumps the version in
   `pyproject.toml` and adds `## X.Y.Z (unreleased)` at the top of
   `CHANGELOG.md` with its line under it. Nothing is added in advance: no
   placeholder version, no empty section. A test fails when
   `pyproject.toml`'s version has no section, so the bump and the heading
   travel together. Every later change of that version adds its line.
2. When it is time, date the heading, `## 0.2.0 (2026-11-20)`, check that
   `pyproject.toml` says the same version, and merge that on `main`.
3. Tag that commit and push the tag:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. The workflow refuses to publish when the tag is not `v` plus the
   version, or when the changelog section is missing or undated:
   `python scripts/release.py v0.2.0` runs the same check locally and
   prints the notes it would publish.
5. Nothing follows. `main` stays at the released version until the next
   change arrives and opens the next entry, as in step 1.

A failed run publishes nothing, or only some of the images, or the
images and the release but not the docs; fix the cause and run the
workflow again from the Actions tab. A tag that was
pushed by mistake is deleted on GitHub and locally before anything uses it.

## The docs site, once

GitHub Pages serves the `gh-pages` branch: in the repository's settings,
under Pages, choose "Deploy from a branch", branch `gh-pages`, folder `/`.
The first release creates the branch, and the branch menu lists only
branches that exist, so make the setting after the first release has run.

The docs live at `https://docs.flashlights.app/`, the address every image
bakes in as its default help link, so set the custom domain in the same
Pages settings: enter `docs.flashlights.app`, with a DNS `CNAME` record for
that name pointing at `mariatta.github.io`, and turn on "Enforce HTTPS"
once the certificate is issued. GitHub commits a `CNAME` file to the
`gh-pages` branch when the domain is set; mike only touches the version
folders and the redirect index, so the file survives every later release.
The `mariatta.github.io/flashlights/` address redirects to the domain from
then on.

To publish a version by hand, with the docs requirements installed and a
full clone (mike reads the branch's history):

```bash
mike deploy --push --update-aliases 0.2.0 latest
```

`mike serve` previews the versioned site locally, and `mike delete 0.2.0
--push` removes a version published by mistake.

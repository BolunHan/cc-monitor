# GitHub Actions — disabled

**Status: DISABLED. Do not re-enable without a deliberate decision to move CI
back off GitLab.**

Every workflow in this directory has been renamed from `*.yml` to
`*.yml.disabled`. GitHub Actions only picks up files ending in `.yml` / `.yaml`
inside `.github/workflows/`, so none of them trigger on push, tag, or pull
request until they are renamed back.

## Reason

CI runs on the GitLab mirror (`gitlab` remote, `.gitlab-ci.yml`) instead, for
better pipeline support and to use GitLab's compute minutes. The two are kept
as mirrors of each other, so a tag pushed to either remote can produce a
release.

## Disabled workflows

| Workflow file | Triggers | Purpose |
| --- | --- | --- |
| `release.yml` | `v*.*.*` tags, manual | orchestrates everything below, then publishes a GitHub Release |
| `build-docker.yml` | called by `release.yml`, manual | build + push the server image to ghcr.io |
| `build-apk.yml` | called by `release.yml`, manual | build the release APK |
| `deploy-gh-pages.yml` | called by `release.yml`, manual | deploy `static/` to the gh-pages branch |

The GitLab equivalents live in `.gitlab-ci.yml`:

| GitHub workflow | GitLab job(s) |
| --- | --- |
| `build-docker.yml` | `docker:build` (GitLab Container Registry) |
| `build-apk.yml` | `apk:build` |
| `deploy-gh-pages.yml` | `pages` (GitLab Pages) |
| `release.yml` → `dsh-plugin` | `dsh:package` |
| `release.yml` → `npm-publish` | `npm:publish` |
| `release.yml` → `release` | `release:assets`, `release` |

## How to re-enable

```sh
git mv .github/workflows/release.yml.disabled           .github/workflows/release.yml
git mv .github/workflows/build-docker.yml.disabled      .github/workflows/build-docker.yml
git mv .github/workflows/build-apk.yml.disabled         .github/workflows/build-apk.yml
git mv .github/workflows/deploy-gh-pages.yml.disabled   .github/workflows/deploy-gh-pages.yml
git commit -m "ci: re-enable GitHub Actions workflows"
git push origin main
```

Then restore the GitHub Actions badges in `README.md` (they were replaced by
the GitLab pipeline badge).

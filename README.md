# Outside the Headlines

Insights from the long tail.

A small static edition website. This repository contains only public site code
and explicitly approved releases. The editorial newsroom and its database are
separate and private. [Edition 1, dated 14 September 2026](https://outside-the-headlines.vercel.app/issues/2026-09-14-1/), is the first approved release. This editorial experiment does not establish that the pilot or reader-validation goals have been achieved.

## Build

Use Python 3.12 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python build.py
.venv/bin/python -m http.server 8043 --bind 127.0.0.1 --directory dist
```

The generator makes no network requests and needs no secrets. Dependency
installation uses PyPI. `site.json` records the canonical production hostname.
Only `dist/` is served. The site has no runtime API or application tracking.

## Publish an edition

1. Prepare sourced copy privately, then explicitly approve the edition as an editorial decision in the newsroom. The editor is not asked to audit every source sentence personally.
2. Freeze an immutable revision with its matching named, content-checksum editorial approval. Provenance, schema and recorded failed-check gates remain; changes require renewed approval.
3. In the newsroom, run `back-pages export-publication REVISION_ID --repo-dir publication`.
4. Build this checkout and inspect its HTML, sources, currency annotations and RSS.
5. Explicitly commit the approved release inputs and push to `main`.

This repository is connected to Vercel's native Git integration, with `main`
configured as the production branch and other branches receiving previews.
Previews are non-indexable, but this Git repository is public:
never commit drafts, credentials, newsroom notes, or unapproved article copy.
The export command never commits, pushes, deploys or sends email.

Reader copy uses no em dashes. Visible source lines contain the original reporting
headline, outlet and date. Full author credits and supporting documents are inside
the closed evidence disclosure. Sources can carry `display: "evidence_only"` for
that purpose; the default `reporting` hint preserves legacy release checksums.

## Corrections and rollback

Do not edit released JSON. Review a corrected draft and freeze a new revision;
export it with a dated correction notice. Keep the earlier release file. The
stable issue URL renders the latest revision; RSS retains its original GUID and
publication timestamp. Substantive updates to an existing proposition need a
follow-up reason.

For a broken site deployment, run `vercel rollback DEPLOYMENT_URL --scope smiling-quokka` from this linked checkout,
then fix the code and push. Do not use rollback to conceal a factual correction.
To undo a code commit, prefer `git revert COMMIT` followed by a push.

## Deployment

Project and repository: `outside-the-headlines`. Vercel team: `smiling-quokka`.
Framework preset: Other. Commands and output directory are in `vercel.json`.
The build uses an isolated virtual environment, not Vercel’s managed system Python.
Production hostname: [outside-the-headlines.vercel.app](https://outside-the-headlines.vercel.app).

The approved first edition is included as an immutable release input. The official
Vercel Git connection selects this publication repository, not the private newsroom.
The first release was deployed automatically from Git commit `e031361` on
15 September 2026. Its public issue page, archive and RSS were verified over HTTPS.
If the connection is removed, install the official
[Vercel GitHub app](https://github.com/apps/vercel/installations/new) with **only**
this repository selected, then reconnect from this checkout:

```sh
vercel git connect https://github.com/aristotle-tek/outside-the-headlines --scope smiling-quokka
```

To verify a changed connection, confirm `main` as the production branch, push a
harmless documentation commit and check that its SHA appears on a successful new
Git deployment. Connection settings alone are not evidence of automatic deployment.
Manual deployment of already approved public inputs uses `vercel deploy --prod --scope smiling-quokka`.
No domain purchase is part of this setup. Email and subscriber storage are deferred;
RSS is available immediately. A future email service can use listmonk plus SMTP.

Code is MIT-licensed. Editorial content and third-party material are not;
see `CONTENT_RIGHTS.md` and the separate font licence.

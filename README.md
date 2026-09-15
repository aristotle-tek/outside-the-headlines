# Outside the Headlines

Insights from the long tail.

A small static edition website. This repository contains only public site code
and explicitly approved releases. The editorial newsroom and its database are
separate and private. The first edition is forthcoming until it has human sign-off.

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

1. Edit, source-check and approve the edition in the private newsroom.
2. Freeze an immutable revision with its matching human review attestation.
3. In the newsroom, run `back-pages export-publication REVISION_ID --repo-dir publication`.
4. Build this checkout and inspect its HTML, sources, currency annotations and RSS.
5. Explicitly commit the approved release inputs and push to `main`.

Once the Vercel GitHub app is installed for this repository and connected, its
native Git integration deploys `main` to production and other branches to previews.
Previews are non-indexable, but this Git repository is public:
never commit drafts, credentials, newsroom notes, or unapproved article copy.
The export command never commits, pushes, deploys or sends email.

## Corrections and rollback

Do not edit released JSON. Review a corrected draft and freeze a new revision;
export it with a dated correction notice. Keep the earlier release file. The
stable issue URL renders the latest revision; RSS retains its original GUID and
publication timestamp. Substantive updates to an existing proposition need a
follow-up reason.

For a broken site deployment, run `vercel rollback` from this linked checkout,
then fix the code and push. Do not use rollback to conceal a factual correction.
To undo a code commit, prefer `git revert COMMIT` followed by a push.

## Deployment

Project and repository: `outside-the-headlines`. Vercel team: `smiling-quokka`.
Framework preset: Other. Commands and output directory are in `vercel.json`.
The build uses an isolated virtual environment, not Vercel’s managed system Python.
No domain purchase is part of this setup. Email and subscriber storage are deferred;
RSS is available immediately. A future email service can use listmonk plus SMTP.

Code is MIT-licensed. Editorial content and third-party material are not;
see `CONTENT_RIGHTS.md` and the separate font licence.

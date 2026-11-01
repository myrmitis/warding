# Website recovery and production acceptance

Owning task: https://github.com/myrmitis/warding/issues/27. Review: https://github.com/myrmitis/warding/pull/61.
Base: fe9d83357327ca7dfeacd38a87114b5b66aa5c89. Original deployment: dpl_2hB46QmGS5MzWjTzcoy62ti71p8d.

All 268 original files matched the Vercel upload inventory before editing. `recovery-inventory.json` preserves those original hashes.
The publishing build checks current file hashes in `static-manifest.json`. The recovery inventory is historical evidence, not a current-output manifest.
The original website used static publishing. Main contained a different Astro site. This change reconciles that gap without deploying main's unrelated copy.

The correction changes source-availability wording, its public link and browser module URLs. It preserves the beta and demonstration disclosures.
The served NOTICE follows the current canonical product NOTICE, including required upstream attribution. Current root release history is not replaced.
The original 138 static output files retain their layout and assets, apart from the documented wording and NOTICE synchronisation.

Local acceptance on November 1: all five existing suites passed, with 3,118 tests. No existing assertion changed.
The new HTTP journey failed on the original site's stale wording, then passed against the corrected running site.
Browser inspection covered the homepage and hydrated setup page. Both retain the required qualification limits.
A first HTTP check ran before the build existed and returned 404. Building the site resolved that setup error.
Online npm installation stalled. Exact-lock offline installation passed with 37 packages and no reported vulnerabilities.

The staged production deployment and canonical-domain acceptance are recorded in the owning issue after execution.
Source integration, hosted checks, staged acceptance and production acceptance remain separate evidence stages.
Complete model and CI costs remain unknown. No outside customer trial or new beta qualification is claimed.

Rollback: promote the previous deployment, `dpl_2hB46QmGS5MzWjTzcoy62ti71p8d`, in the existing Vercel project.
Do not run product/package publication or change DNS to roll back this website correction.

## Integration repairs

The hosted results identified stale source references, a stale generated catalog and a daylight-saving error in schedule descriptions.
The source references and unsupported CLI alias are corrected. The catalog was regenerated from current canonical inputs without refreshing external pins.
The HTTP acceptance check uses the standard HTML parser and checks all twelve affected public entry points.
Existing assertions and merge gates remain unchanged. Hosted execution results and final merge evidence are recorded in PR #61.

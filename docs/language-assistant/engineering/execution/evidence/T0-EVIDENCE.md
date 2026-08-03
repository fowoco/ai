# Language Assistant T0 Evidence Pack

~~~yaml
evidence_version: 1
wave: W0
task: T0
scope: bootstrap-only
integration_branch: feat/language-assistant
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant
base_sha: 3d3fa198717d39272a71ea3d31dd282f3a69336d
docs_commit_sha: c2a6a716d05e5d420b95b3f580973c15a497986e
evidence_sha: recorded in the Control Tower ledger after this docs-only commit
~~~

## Claims

| ID | Claim | Result |
|---|---|---|
| T0-C01 | Original checkout remains on develop at approved base with existing dirty HWPX work preserved. | supported; post-ledger recheck at 57eb166 matched source status and all dirty-file SHA values |
| T0-C02 | feat/language-assistant is an isolated worktree from origin/develop. | supported |
| T0-C03 | Exactly three approved Language documents were imported byte-for-byte. | supported by SHA-256 and cmp results |
| T0-C04 | Control Tower ledger and Task/Gate templates exist without recorded secrets or user payloads. | supported by artifact checks |
| T0-C05 | Existing test and Ruff baselines were executed before T1 implementation. | supported; 61 existing tests passed and Ruff passed |

## Git and worktree evidence

### Source recheck

Command:

~~~bash
git fetch origin
~~~

Exit code: 0.

Result:

~~~text
origin/develop = 3d3fa198717d39272a71ea3d31dd282f3a69336d
~~~

Command:

~~~bash
git rev-parse HEAD
git rev-parse origin/develop
git rev-list --left-right --count HEAD...origin/develop
~~~

Result:

~~~text
HEAD              3d3fa198717d39272a71ea3d31dd282f3a69336d
origin/develop    3d3fa198717d39272a71ea3d31dd282f3a69336d
ancestry          0 0
~~~

Source status before T0 mutations:

~~~text
## develop...origin/develop
 M hwp-editor/README.md
 M hwp-editor/src/hwp_mcp/api.py
 M hwp-editor/src/hwp_mcp/compare.py
 M hwp-editor/src/hwp_mcp/fields.py
 M hwp-editor/src/hwp_mcp/hwpx.py
 M hwp-editor/src/hwp_mcp/instructions.md
 M hwp-editor/src/hwp_mcp/plans.py
 M hwp-editor/src/hwp_mcp/server.py
 M hwp-editor/src/hwp_mcp/vision.py
 M hwp-editor/tests/test_api.py
 M hwp-editor/tests/test_vision.py
?? docs/engineering/
?? hwp-editor/src/hwp_mcp/hwpx_images.py
?? hwp-editor/src/hwp_mcp/images.py
?? hwp-editor/tests/image_fixture_helpers.py
?? hwp-editor/tests/test_hwpx_images.py
?? hwp-editor/tests/test_image_apply.py
?? hwp-editor/tests/test_image_compare.py
?? hwp-editor/tests/test_image_plans.py
?? hwp-editor/tests/test_image_workflow.py
?? hwp-editor/tests/test_images.py
~~~

Dirty-file SHA-256 manifest captured before T0 mutations:

~~~text
3378420e206f5a4369dd4eb7532d362678e6ccd53ac1db91af14623468aa7c1e  hwp-editor/README.md
94d5f96cd0a84a677418bb36faaf3a1a055a0b5d2ce2e271827d8fadcb603b4a  hwp-editor/src/hwp_mcp/api.py
480403df16909b3954d7ed847e34e71e92e18fd46b5aa2477a2c59e8c5df4510  hwp-editor/src/hwp_mcp/compare.py
2f53f1f315521529ab9f333e4db479759dd1d27b2c36b6ae4392447d1e1115d8  hwp-editor/src/hwp_mcp/fields.py
a0e232b6f7e916665d4c91e1ef0ab311280398c2a490bd03c1b8aa870201a7fa  hwp-editor/src/hwp_mcp/hwpx.py
8b75c7099da5a805f539e4f16846398b5cc9759852aa0c27023eb810721b1cb9  hwp-editor/src/hwp_mcp/hwpx_images.py
64fe7923820539d9d19faf8d2f31acc2d3d7fd78a685f97b15d078e496cb8981  hwp-editor/src/hwp_mcp/images.py
de692853b19c13309f1a38ed2a4e0f32691976d0e6af7a0ea2e01257cb3b8155  hwp-editor/src/hwp_mcp/instructions.md
57318be6304ab980ad04153483947a1145cd1116c64a7036a776efd4e00c56e7  hwp-editor/src/hwp_mcp/plans.py
b78438d0482a7a04ca3a02412ec4473406d1ba1148c4e77771b63d34063e63bd  hwp-editor/src/hwp_mcp/server.py
a84eec9cadd03b6765b14beb9cc95db155f81fd14051584c433566775f68c026  hwp-editor/src/hwp_mcp/vision.py
da204f7ae30d282f24e1c14aea91585135e09be90b263a3e808444658fbb3fa1  hwp-editor/tests/image_fixture_helpers.py
e98bc982295bd9621140bb46ba75c5d4040b4ed156518cc68a0c96ee11ca1413  hwp-editor/tests/test_api.py
f5606347931a0f00c1ce0d0532226808d55d3fe6bf6996a7bfa3e63c5070a753  hwp-editor/tests/test_hwpx_images.py
33d3e2f943e42cc0233d24da57a8bf01e35240635ae4dc4a217c26ff9bc22e84  hwp-editor/tests/test_image_apply.py
c1686968bd994188e23d6124012a6bfb220b70b7cf7685a43f444eaf117fa934  hwp-editor/tests/test_image_compare.py
f1d220916e18a1695d8e8b8302d64f968ec6ed328f0a21e733a156d247457d0a  hwp-editor/tests/test_image_plans.py
c6a6e0a1e1c7e73ac133739b5b975d591c6dfc76604999ce699954ff4a7c6490  hwp-editor/tests/test_image_workflow.py
5de0a2151a09cf365cb9c77ed3c5f9caf3713007bf8961f13ac6f07abc40d73e  hwp-editor/tests/test_images.py
9724679f8b685bfd2499a275b3f572bb0f50b3845e5bbf45b5ea7a16a048a47d  hwp-editor/tests/test_vision.py
~~~

Worktree creation:

~~~bash
git worktree add /Users/parktaejung/Desktop/workspace/ai-language-assistant -b feat/language-assistant origin/develop
~~~

Result: branch created; target HEAD was 3d3fa198717d39272a71ea3d31dd282f3a69336d.

After the T0 docs commit:

~~~text
worktree /Users/parktaejung/Desktop/workspace/ai
HEAD 3d3fa198717d39272a71ea3d31dd282f3a69336d
branch refs/heads/develop

worktree /Users/parktaejung/Desktop/workspace/ai-language-assistant
HEAD c2a6a716d05e5d420b95b3f580973c15a497986e
branch refs/heads/feat/language-assistant
~~~

## Imported documents and T0 artifacts

Imported document SHA-256 pairs matched and /usr/bin/cmp returned 0 for all three:

~~~text
478786c50720a173834763d04c5851e73e300dd994a760169a82d844f0e8383c  docs/engineering/specs/2026-08-02-language-assistant-graph-design.md
0842506729c1db890a9274d639cf4b096f25b0b87791ae81792525d9d61adca8  docs/engineering/specs/2026-08-02-language-assistant-control-tower-design.md
e4c7860310aeb3aaa1623873e42df14b9e8cc90d43966fcd1d859caa5a2eba78  docs/engineering/plans/2026-08-02-language-assistant-graph.md
~~~

The imported specs/plans file count was 3. T0 execution artifacts:

~~~text
docs/engineering/execution/language-assistant/control-tower.md
docs/engineering/execution/language-assistant/tasks/TASK-TEMPLATE.md
docs/engineering/execution/language-assistant/reviews/GATE-REVIEW-TEMPLATE.md
~~~

Artifact validation command exited 0 and found the declared branch, final Task branch, and --no-ff policy. The forbidden-content scan exited 1 with no output, meaning no matches.

## Baseline

Commands:

~~~bash
UV_CACHE_DIR=.cache/uv uv venv --python 3.12 .venv
UV_CACHE_DIR=.cache/uv uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/python --version
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
~~~

Results:

~~~text
CPython 3.12.13; virtual environment created
37 dev packages installed; exit 0
Python 3.12.13; exit 0
pytest -q: exit 0; 61 existing tests passed
ruff check app tests: exit 0; All checks passed!
~~~

Collection confirmation:

~~~bash
.venv/bin/python -m pytest --collect-only -q
~~~

Exit code: 0. Existing test collection total: 61.

## Post-pack verification

At ledger commit 57eb166, the following fresh checks were run:

~~~bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check app tests
git status --short --branch
git rev-parse HEAD
git rev-parse origin/develop
~~~

Results:

~~~text
pytest -q: exit 0; 61 existing tests passed
ruff check app tests: exit 0; All checks passed!
target status: clean; feat/language-assistant...origin/develop [ahead 3]
target HEAD: 57eb166
origin/develop: 3d3fa198717d39272a71ea3d31dd282f3a69336d
~~~

The source checkout remained on develop at 3d3fa198717d39272a71ea3d31dd282f3a69336d. Its HWPX dirty path list and all 21 SHA-256 values matched the pre-T0 manifest above.

## Scope audit

~~~yaml
allowed_changes:
  - approved Language design document
  - approved Control Tower design document
  - approved implementation plan
  - Control Tower ledger
  - Task record template
  - Sol Gate review template
  - this Evidence Pack
unexpected_files: []
implementation_started: false
~~~

## Unverified and stop conditions

- Independent Luna Verifier has not run; this pack is evidence-ready, not approved.
- No Sol review or user Gate decision was performed.
- T1–T16 implementation has not started.
- No Language Assistant production/provider/Qdrant/model behavior was tested.
- External G1–G7 evidence remains open and was not inferred from baseline tests.
- No remaining T0 verification item blocks handoff; independent Luna replay and later Wave work remain intentionally unrun.

## Rollback

Safe source point: 3d3fa198717d39272a71ea3d31dd282f3a69336d.

The original dirty checkout was not stashed, reset, cleaned, checked out, or copied into the feature worktree. T0 changes are confined to the isolated feat/language-assistant worktree. Reverting the feature branch to the base requires an explicit user-directed Git operation; no destructive rollback was run.

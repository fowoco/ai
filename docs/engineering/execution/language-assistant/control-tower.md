# Language Assistant Control Tower Ledger

## Authority

- Integration branch: `feat/language-assistant`
- Execution protocol: `docs/engineering/specs/2026-08-02-language-assistant-control-tower-design.md`
- Current wave: `W0`
- Current gate: `none`
- State: `bootstrapping`
- Maximum concurrent builders: `2`

## Tasks

| Task | Title | Status | Dependencies | Base | Branch | Packet | Implementation | Evidence | Merge | Integrated | Luna | Sol | User | Unverified |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | Domain contracts | pending | T0 | — | `task/la-t01-domain-contracts` | — | — | — | — | — | — | S1 | — | — |
| T02 | Language normalization | pending | T01 | — | `task/la-t02-language-normalization` | — | — | — | — | — | — | S1 | — | — |
| T03 | Facts and queries | pending | T01 | — | `task/la-t03-facts-and-queries` | — | — | — | — | — | — | S1 | — | — |
| T04 | Retrieval domain | pending | T02,T03 | — | `task/la-t04-retrieval-domain` | — | — | — | — | — | — | S2 | — | — |
| T05 | EPS index plan | pending | T02,T04 | — | `task/la-t05-eps-index-plan` | — | — | — | — | — | — | S2 | — | — |
| T06 | Hybrid retrieval | pending | T04,T05 | — | `task/la-t06-hybrid-retrieval` | — | — | — | — | — | — | S2 | — | — |
| T07 | Generation resources | pending | T01,T04,S2 | — | `task/la-t07-generation-resources` | — | — | — | — | — | — | S3 | — | — |
| T08 | Validation retry | pending | T03,T07 | — | `task/la-t08-validation-retry` | — | — | — | — | — | — | S3 | — | — |
| T09 | Easy Korean | pending | T07,T08 | — | `task/la-t09-easy-korean` | — | — | — | — | — | — | S3 | — | — |
| T10 | Native translation | pending | T06,T07,T08 | — | `task/la-t10-native-translation` | — | — | — | — | — | — | S3 | — | — |
| T11 | Graph assembly | pending | T09,T10 | — | `task/la-t11-graph-assembly` | — | — | — | — | — | — | S3 | — | — |
| T12 | Internal API | pending | T11,G1 | — | `task/la-t12-internal-api` | — | — | — | — | — | — | S3 | — | — |
| T13 | Runtime and Qdrant | pending | T06,T12,S3 | — | `task/la-t13-runtime-qdrant` | — | — | — | — | — | — | S4 | — | — |
| T14 | Privacy and resilience | pending | T11,T13 | — | `task/la-t14-privacy-resilience` | — | — | — | — | — | — | S4 | — | — |
| T15 | Evaluation | pending | T14,S4 | — | `task/la-t15-evaluation` | — | — | — | — | — | — | S5 | — | — |
| T16 | Verification handoff | pending | T14,T15 | — | `task/la-t16-verification-handoff` | — | — | — | — | — | — | S5 | — | — |

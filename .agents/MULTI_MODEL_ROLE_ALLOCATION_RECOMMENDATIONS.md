# Multi-model role allocation

Use the lowest-cost model class expected to meet the acceptance criteria without predictable rework. Model capability never changes repository scope, Phase 1 boundaries, approval authority, or verification duties.

| Work | Starting class | Escalate when |
| --- | --- | --- |
| File search and deterministic extraction | Low | Interpretation or cross-file impact is unclear |
| Ordinary implementation and tests | Medium | Requirements conflict or architecture/security is affected |
| Architecture, rights, privacy, or final high-risk review | High | Start high; do not spend a weaker attempt first |

Limit low-cost workers to one bounded attempt and medium workers to one or two evidence-based attempts. A handoff must include outcome, in-scope paths, constraints, acceptance criteria, existing evidence, checks run, and exact stop conditions. Review and prompt-authoring workers are read-only unless the user expressly grants an edit scope.

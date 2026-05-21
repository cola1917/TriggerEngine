# Performance v1 Architecture

## Problem

The current engine is functionally correct but slow on dense scenarios. Profiling
on a real Waymo scenario with 348 tracks showed:

```text
engine time: ~16.8s
events: 12216
major cost: repeated agent_pair generation and temporal full scans
```

The hot path is:

```text
rules x frames x agent_pairs x operators
temporal rules x frames x agent_pairs x timeline checks
```

`agent_pair` is `O(N^2)` per frame. Rebuilding it for every rule is the largest
avoidable cost.

## Goal

Performance v1 should improve runtime without changing output semantics.

Target improvements:

- generate subjects once per frame and subject type
- temporal rules should be driven by tag timeline indexes, not all possible
  subjects
- keep existing TagEvent output unchanged
- keep existing Rule YAML unchanged

## Non-Goals

- no spatial grid pruning in v1
- no multiprocessing in v1
- no approximate filtering
- no semantic rule changes
- no change to adapter/alignment output

## Execution Shape

Current:

```text
RuleEngine:
  for rule:
    for frame:
      subjects = build_subjects(rule.subject_type, frame)

TemporalRuleEngine:
  for temporal_rule:
    for frame:
      subjects = build_subjects(rule.subject_type, frame)
```

Performance v1:

```text
SubjectCache:
  frame_index + subject_type -> subjects

RuleEngine:
  reuse SubjectCache

TagTimeline:
  tag + subject_type + subject_id -> sorted frame indices

TemporalRuleEngine:
  source tags -> candidate subject ids
  candidate subject ids -> candidate end frames
  evaluate only candidates
```

## Expected Impact

For scenarios with many tracks:

- single-frame rules avoid repeated `O(N^2)` pair construction
- temporal rules avoid scanning all pairs that never emitted source tags
- timeline sequence/sustained checks operate on indexed frame lists

This should reduce the worst case before considering spatial pruning or
parallelism.


# Tasks

One directory per task: `<task-id>/`.

Each task is a self-contained Harbor task directory:

```
<task-id>/
├── instruction.md      the engineering request the agent receives
├── task.toml           timeouts, resources, declared deliverable
├── environment/        container build and the starting files
└── tests/              what scores a submission
```

Task identifiers are stable and prefixed by domain (`dc` data centre, `bs`
battery and storage, `fc` fuel cell, `ia` industrial automation, and so on).

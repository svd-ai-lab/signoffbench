# SignOffBench

**SignOffBench: Can AI Agents Pass Real-World Engineering Design Sign-Off?**

## What this measures

Engineering agents can produce executable designs, but execution alone does not
establish that a design is fit for use. SignOffBench evaluates designs against
applicable standards and their reliability beyond nominal operating conditions.

Requirements define acceptance. Performance and resource objectives compare
acceptable alternatives without requiring agreement with an expert solution.
A benchmark pass is not regulatory certification.

## Tracks

| Track | Status |
| --- | --- |
| Controls | First track, implemented in Simulink |
| Mechanical | Planned |

## Reported result

In 60 first attempts across 25 tasks, agents produced 34 accepted designs, while
other attempts failed delivery or violated operating constraints. Model coverage
was uneven, so no overall ranking is claimed. Reliability claims remain bounded
by the tested models and conditions.

## Layout

```
tasks/<task-id>/     one directory per task
docs/                task documentation and authoring notes
```

Tasks are distributed as self-contained Harbor task directories: the prompt and
starting files the agent receives, the container environment, and the tests
that score a submission.

## Licence

Apache-2.0 for repository content — see [LICENSE](LICENSE).

Task directories may carry material derived from third-party sources under
their own licences. Each task states its source and licence in its own
documentation; those terms apply to that task's files.

## Citation

See [CITATION.cff](CITATION.cff).

# stage: checkpointed, content-addressed processing steps

Snapshot 2026-09-18. A stage is a plain function wrapped by `stage`. Under a `Run` it gets a
data key from its arguments, records the code it executed as a manifest, publishes its output
as an artifact and writes an invocation row; a rerun fetches the artifact when the key matches
and the manifest, and every input artifact's manifest, still hashes the same. Without a `Run`
the wrapper is the function. Contract: [`specs/2026-09-17-stages.md`](../specs/2026-09-17-stages.md).

::: triplum.stage.stage

::: triplum.stage.identity

::: triplum.stage.fingerprint

::: triplum.stage.trace

::: triplum.stage.artifacts

::: triplum.stage.run

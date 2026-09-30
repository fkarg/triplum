# Future example: evaluate our own documentation

This is a candidate example, not an implemented pipeline, approved interface or prerequisite
for the [reader workflow](README.md). Revisit it when the library can support it naturally.

The eventual example could show the full process: ingest a fixed snapshot of manual and
generated documentation, configure indexing and retrieval, ask questions from different reader
perspectives, and compare results against a benchmark. It would exercise the library on material
we can inspect and improve ourselves, while teaching users how to compose their own experiments.

**Competency questions (CQs)** are questions the documentation or knowledge graph should enable
a reader to answer. Examples: “What identifies a source?”, “What must my custom embedder return?”,
or “Which steps reproduce this paper's reported result?” Include questions whose correct outcome
is an evidence-backed statement that a capability is unavailable. Perspectives shape the question
set; they are not themselves baseline retrieval systems.

## Ideas to borrow from Ragas

- [Testset generation](https://docs.ragas.io/en/stable/concepts/test_data_generation/rag/) uses
  an enriched document/chunk graph to generate questions of different kinds, including questions
  spanning multiple pieces of evidence. That is a graph for generating tests; it need not be
  the same graph as the system being evaluated.
- [Persona generation](https://docs.ragas.io/en/stable/howtos/customizations/testgenerator/_persona_generator/)
  supports explicit role descriptions and graph-derived personas. Our hand-written profiles
  could inspire these inputs without making Ragas a dependency now.
- [Context recall](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)
  evaluates retrieved evidence relative to reference answers or contexts. It could help separate
  retrieval failure from missing documentation; it is not a measure of overall conceptual coverage.
- [Faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)
  asks whether answer claims are supported by retrieved context. A faithful answer can still
  inherit incorrect or incomplete documentation.
- [Custom criteria and rubrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/general_purpose/)
  could express a prerequisite-explanation check. This is a possible application, not a validated
  Ragas metric for reader confusion.

## Keep coverage claims narrow

Keep independently written CQs alongside corpus-generated questions. Generating questions,
reference answers and judgments from the same docs risks rewarding self-consistency while
missing absent topics. Hold some independent questions out of the improvement loop so repeated
edits do not merely teach the docs to pass a familiar list.

Separate at least four questions: does an explanation exist, can the reader find it, can a
retriever recover the needed evidence, and does the answer use that evidence correctly?
A confusion finding should name the prerequisite, where it was needed, and whether the learning
path explains it in time. Models may supply the missing knowledge themselves, so simulated
confusion remains a hypothesis about readers.

Possible later coverage measures include the fraction of independent CQs supported by evidence,
and the fraction of independently identified prerequisite concepts or relationships explained.
Both require an explicit denominator and a reviewed definition of adequate support. Counting
graph entities or edges alone does not demonstrate meaningful coverage, and a CQ pass fraction
does not establish coverage beyond that question set. No metric or threshold is selected here.

Before turning this into an executable example, review its scope with the owner: corpus/version
identity, independent references, actual baseline systems, cost and cache identity, and separation
of generation from evaluation. Until then, collect concrete reader-task evidence using the
manual workflow. Do not add an ingestion pipeline, benchmark runner or dependency for this note.

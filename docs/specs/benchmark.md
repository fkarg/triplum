# Benchmark inputs (draft for owner review)

Status: **approved** by the owner (P5, 2026-11-07) and implemented: `datatype/question.py`,
`datasets/benchmark.py`, `datasets/fixture.py`, tests in `tests/test_benchmark_inputs.py`.
Approval covers this page only. Direction: BE1 round 6 (nested public input, small `QABenchmark`
bundle, alternative evidence sets), BE3/BE4 (native granularity, span coverage), the list-not-tuple
policy. Decided since: BE18, evidence keys resolve through a nullable `Source.external_id`, unique
per collection where set (not yet implemented; the fixture sets it in a later step). Open
neighbours: BE7 (unanswerable scoring), BE11 (per-question contexts).

## Records: `src/triplum/datatype/question.py`

```python
class QuestionInput(BaseModel):
    """What a retriever or reader may see of a question. Gold never appears here."""

    model_config = ConfigDict(frozen=True)

    text: str


class SpanEvidence(BaseModel):
    """Characters `[start, end)` of one corpus document's text are needed to answer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str  # the benchmark's native document key; resolution: BE18
    start: int = Field(ge=0)
    end: int  # validated: end > start


class DocumentEvidence(BaseModel):
    """The document as a whole is the evidence (page-level provenance, e.g. FRAMES URLs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str


type Evidence = SpanEvidence | DocumentEvidence


class QAQuestion(BaseModel):
    """One benchmark question: the public input plus everything only evaluation may read."""

    model_config = ConfigDict(frozen=True)

    id: str  # the benchmark's native question id; the sample key across runs
    input: QuestionInput
    answers: list[str]  # accepted answers, canonical first, duplicates removed
    # Alternative sets, each nonempty, satisfied when all its items are; [] = no gold.
    evidence: list[list[Evidence]]
    answerable: bool
    metadata: dict[str, JsonValue] = {}  # native extras, never shown to the public path
```

Guarantees: fields cannot be reassigned (Pydantic freezing is shallow; nested lists and metadata
are immutable by convention, as for every record); `end > start`; no empty evidence set
(`[[]]` would be vacuously satisfied). `extra="forbid"` on both evidence types is load-bearing:
without it an invalid span (`start=3, end=3`) silently validates as `DocumentEvidence`
(observed with the installed Pydantic). Evidence offsets index the corpus document's `Source.text` as
yielded by the same benchmark's `corpus()`. Not checked by the record: that the document exists
or that `end` is within its text (the benchmark validates that at load, see below).

Not included until a concrete need: `choices` (multiple-choice scoring, LQ), `as_of`
(temporal questions; 20 legacy questions carry it), per-question context keys (BE11). The legacy
values stay available in `metadata`.

## Bundle: `src/triplum/datasets/benchmark.py`

```python
class QABenchmark(Protocol):
    """A corpus and the questions over it, from one source, kept in step."""

    @abstractmethod
    def corpus(self, collection_id: UUID, /) -> Dataset[Source]: ...

    @abstractmethod
    def questions(self) -> Dataset[QAQuestion]: ...
```

`questions()` is a `RecordDataset[QAQuestion]` for in-memory benchmarks; its fingerprint is its
content. A question-only benchmark returns an empty corpus.

## Legacy fixtures: `src/triplum/datasets/fixture.py`

```python
class LegacyFixture(QABenchmark):
    """A `tests/fixtures/<name>.json` file read in place, gold decoded to paragraph spans."""

    def __init__(self, path: Path) -> None: ...
```

- One snapshot is parsed at construction; later file edits need a new instance. Question ids and
  document ids are validated unique within the fixture.
- Sources: one per legacy document; `origin` = the legacy document id (unique in every fixture,
  observed), `text` verbatim. Grants, `observed_at` and document metadata are not carried (Viewer
  and provenance are separate decisions).
- Gold: each legacy integer id is the legacy `chunk_id(document_id, ordinal)` (first 15 hex digits
  of `sha256("chunk\0" + canonical_json([document_id, ordinal]))`). The loader hashes every stored
  segment with its **stored** `ordinal` (66 gold-referenced segments have an ordinal different from
  their list position) into a lookup, rejecting duplicate keys, and maps each gold id to that
  segment's `SpanEvidence(document_id, start, end)`. One evidence set per question
  (`[[...]]`), or `[]` without gold. An undecodable id or out-of-range span raises `ValueError` at
  construction: a mapping error, never an empty gold set.
- Questions: `id`, `input.text` = question, `answers` = `[answer, *aliases]` deduplicated in order,
  `answerable` verbatim, `metadata` = legacy metadata plus `qtype` (and `as_of` where set).
  Legacy `candidate_chunk_ids` are kept verbatim in metadata (BE11 decides their meaning).
- Fingerprint: `corpus()` and `questions()` return `RecordDataset`s, so identity is the yielded
  content (Sources include `collection_id`). No file hash or loader tag: changed decoding changes
  identity automatically, whitespace-only file edits do not.
- Limits: grants (gatemem has principal-specific ones), `observed_at` and context restrictions are
  not carried, so ACL-aware, temporal and distractor-setting evaluation fidelity is not established.
  Metadata keeps gold-bearing values (`supporting_sentences`, `gold_label`, `judge_spec`, …); it is
  evaluation-side only, and public calls receive `question.input`.

Alternative considered: rewrite the fixtures once into a new JSON shape. Rejected for now: it
defines a second on-disk schema and churns 34 files, while read-in-place keeps the legacy recipe in
one module.

## HotpotQA: `src/triplum/datasets/hotpotqa.py`

Added on the owner's request (2026-11-07: make the BM25 example usable with an automatically
downloaded, cached reference dataset). Implements the approved `QABenchmark`.

```python
class HotpotQA(QABenchmark):
    def __init__(
        self, root: Path | None = None, *, gold: Literal["sentence", "passage"] = "sentence"
    ) -> None: ...
```

- Files: HippoRAG's `reproduce/dataset/hotpotqa{,_corpus}.json` pinned to commit `191f2811` and
  sha256 (the hashes the deleted loader pinned; re-checked), downloaded into `root/hotpotqa` on
  first use; `root` defaults to `datasets_home()`. 1,000 questions, 9,811 passages.
- Sources: text `title\ntext`; `origin` and `external_id` = title (unique, observed).
- Gold, applying BE4 (native granularity) and the configurable-evaluation policy: `sentence`
  (default) gives one span per supporting sentence, exact because each passage equals the
  concatenation of its context sentences (all 9,942 occurrences, observed); `passage` gives one
  whole-passage span per supporting passage, HippoRAG's recall unit. 350 questions have several
  supporting sentences in one passage, so item recall differs between the modes. With `passage`,
  the 20 legacy-fixture questions have identical gold, question and answer (observed).
- Unresolvable supporting facts (unknown title, index outside the sentences, sentences differing
  from the corpus) raise `ValueError` at construction. `metadata` keeps `type` and `level`; the
  distractor `context` is not carried (BE11).

## Example

```python
fixture = LegacyFixture(Path("tests/fixtures/hotpotqa.json"))
question = fixture.questions()[0]
question.input.text  # "what is one of the stars of  The Newcomers known for"
question.evidence  # [[SpanEvidence(document="…", start=0, end=…), SpanEvidence(…)]]
sources = fixture.corpus(collection.id)  # 234 Sources, origin = legacy document id
```

## Verification plan

- Every fixture with questions loads; all 704 legacy gold references decode, and every span lies
  within its document's text (observed earlier by script; becomes a parametrized test).
- Records: `end > start`, nonempty evidence sets and forbidden extras, tested through
  `QAQuestion` (the union), not only `SpanEvidence`.
- Fingerprints change with yielded content and with `collection_id` (corpus only).
- Docs: concept page for benchmark inputs after approval; `flow.md` entry.

## Peer review

gpt-6.1-sol, review `7ab5b020457144abaf7832b011016aec` (all 704 references re-resolved; union
probes; ordinal-vs-position check; mutation probes; metadata gold scan). Dispositions: unique
defect, union fallback → `extra="forbid"` (session reproduced); unique defect, `[[]]` → nonempty
sets; unique defect, stored ordinals ≠ positions → stored-ordinal lookup; changed decision,
file-hash fingerprint → content fingerprints; added verification, union tested via `QAQuestion`;
no impact beyond wording, shallow freezing; documented limits, gold in metadata and dropped grants.
Rejected: none.

## Unresolved tradeoffs

- Whether `answers` for unanswerable questions should hold the dataset's abstention string
  (`"unanswerable"`, `"Insufficient information."`) or be empty (BE7).
- Location of `QABenchmark` (`datasets/benchmark.py`) vs a top-level evaluation package.

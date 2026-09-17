# Built-in datasets as lazy, streaming sources

Snapshot 2026-09-17. Status: **contract, agreed with the owner in conversation; the review record
below is filled at the design gate.** Replaces the parse-callable registry of
`2026-09-17-dataset-registry.md` and the eager parts of `2026-09-17-datasets-and-loaders.md`;
`2026-09-17-local-files.md` keeps its behaviour under the new shape. Work and commit on local
main; there are no compatibility consumers.

## Why

The dataset and loader foundation (`utils.data`) landed with the built-in sources untouched:
every registered dataset is still a `Spec` whose parse callable reads all files, builds whole
frames and wraps them in the new classes after the fact. Three consequences the owner wants gone:

- Identity needs a full parse. The corpus fingerprint hashes materialised frames although every
  file's sha256 is pinned before download, so an identity lookup on a registry dataset parses
  it (gap 8 of the caching spec, requirement R6).
- `n` means "questions" for the HippoRAG sets, "questions and therefore corpus" for the sets
  whose corpus is the union of inline paragraphs, and nothing for extraction sets.
- Chunk ids are positions in one ordered parse, so the QA source is only nominally independent
  of the corpus source: gold ids mean nothing without exactly that parse. Every library the
  research pass checked (ir_datasets, BEIR, pyserini, MTEB) carries upstream document ids
  through unchanged and loads corpus and judgments as independent tables joined by id; none
  derives ids from position.

The owner's direction, in their words: follow PyTorch for the shape; streaming across the whole
pipeline is what matters, stable indexing and batching are supported but secondary; a dataset
must lazy-load and download on first use; the `Spec` is not needed, only shared settings and
some metadata; a fingerprint must not require materialising; use pydantic where it pays; a
corpus may yield documents that are later processed `[Document] -> [str] -> [str]` (document,
document text, flattened chunks), which is a later stage and not part of this spec.

## Contract

### Records

Three record types, pydantic models, frozen. Upstream files are untrusted input at a system
boundary, so validation happens once, at the parse, and nowhere downstream.

```python
class Segment(BaseModel, frozen=True):  # data.corpus
    ordinal: int  # position within the document, 0-based
    start: int  # character span into Document.text, closed-open
    end: int
    parent: int | None = None  # ordinal of the enclosing segment, for hierarchy
    level: int = 0


class Document(BaseModel, frozen=True):  # data.corpus
    id: str  # stable across parses: upstream key or content id
    source: str
    text: str
    segments: tuple[Segment, ...]  # the source's own units; default one over the text
    uri: str | None = None
    observed_at: int = 0  # UTC microseconds, D2
    grants: tuple[str, ...] = ("public",)
    metadata: dict[str, Any] = {}


class Question(BaseModel, frozen=True):  # eval.inputs
    id: str
    question: str
    answer: str
    aliases: tuple[str, ...] = ()  # answer is always included, first, deduplicated
    gold: tuple[int, ...] = ()  # chunk ids, sorted, unique
    qtype: str = ""
    answerable: bool = True
    as_of: int | None = None
    metadata: dict[str, Any] = {}


class Triple(BaseModel, frozen=True):  # eval.inputs
    subject: str
    predicate: str
    object: str
    question_id: str | None = None
    document_id: str | None = None
```

A segment is what the source ships as a unit: a passage, a paragraph, a turn, a page. Chunking
beyond that (packing, hierarchy for the graph pipelines) is a stage over the document stream
and enters the run identity when it arrives; this spec does not define it. Until then chunk
equals segment.

`Document` validates its segment invariants at construction: spans within the text with
`start <= end`, ordinals non-negative and unique, a parent that names an existing ordinal at a
lower level. Ordinals need not be contiguous, so a fixture can keep a document's full text and
a selected subset of its segments with their original ordinals, which keeps chunk ids stable
across fixture and full corpus. Frozen models do not freeze nested `metadata` dictionaries;
records are treated as immutable by convention, and `RecordDataset.fingerprint()` recomputes
over the current dumps on every call, as `FrameDataset` does, so an edit cannot reuse a stale
digest.

**Identities.** `document_id` is chosen by the source and must not depend on parse order. The
chunk id is `chunk_id(document_id, ordinal)`, a positive 60-bit integer, the same construction
as `extract.protocol.fact_id`. There is no universal key rule: each source declares its logical
key and how a question resolves its gold, because the upstream formats differ (measured on the
pinned files, 2026-09-17: HotpotQA and 2Wiki titles are unique in their corpora and 2Wiki's
question-side paragraph text does not reproduce the corpus text for 6,403 of 10,000 candidates,
while MuSiQue has 647 repeated titles and its question-side text matches the corpus exactly).

| source | document unit | document key | gold resolution |
|---|---|---|---|
| hotpotqa, twowiki (HippoRAG) | passage | `content_id(title)` | supporting-fact titles |
| musique (HippoRAG), musique_full | passage | `content_id(title, text)` | supporting paragraphs' title and text |
| hotpotqa_full, twowiki_full, morehopqa | passage | `content_id(title, text)` resolved inside the question's own context | titles within the question's context |
| squad, squad_v2, boolq | passage | `content_id(title, context)` | the question's own passage |
| quality | article | `content_id(title, article)` | the question's own article |
| qasper | paper; segments abstract, paragraphs, captions | `qasper:<paper id>` | evidence strings located by the paper's layout function |
| multihoprag | article | `multihoprag:<url>` | evidence URLs |
| ectqa | transcript | `ectqa:<file name>` | evidence file names |
| tempo, browsecomp_plus | document | `tempo:<id>`, `browsecomp_plus:<docid>` | upstream ids; equal text under distinct ids stays distinct |
| gatemem | turn | `gatemem:<episode>/<turn>` | none (needs) |
| longmemeval_s | session, scoped per question | `longmemeval_s:<question>/<index>` | answer session ids within the question's haystack |
| metaqa | entity, eager aggregation over the KB | `metaqa:<entity>` | topic and answer entities |
| extraction sets | passage or sentence | `<name>:<split>:<index>` (line-aligned files) | document id on each triple |
| local folder | file; segments by paragraph packing | relative path | gold file paths expanded by parsing the file |

A question resolves its gold from its own record plus, where the format needs it, a pure
layout function over its enclosing source record (a QASPER question sees its paper; a folder
question parses the files it names). The question reader never needs the corpus pass, and the
fingerprint never needs a parse. Ordinals are stable within a pinned layout, not across
document revisions. The store schemas are unchanged: `chunks.id` is already `Int64`,
`documents.id` already a string.

**Collators** in `datasets.collate` project record lists onto the canonical frames:
`corpus_batch(list[Document]) -> CorpusBatch` (one chunk row per segment, text sliced from the
document text), `questions_frame(list[Question])`, `triples_frame(list[Triple])`. They replace
`base.corpus_frames`, `base.document_frames`, `base.Corpus`, `base.question_row`,
`base.questions_frame` and `base.triples_frame`. `CorpusBatch` and the three canonical schemas
stay as they are.

### `utils.data` additions

- `Take[T](IterableDataset[T])`: the first `n` records of a `Source[T]`;
  `fingerprint()` is `content_key("take", [inner.fingerprint(), n])`; `__len__` when the inner
  has one. This is the only selection primitive; PyTorch's `Subset` by arbitrary indices is not
  needed until something shuffles. Semantics under "Selection" below.
- `RecordDataset[T](Dataset[T])`: an in-memory list of pydantic records with
  `fingerprint()` over their dumps, the record analogue of `FrameDataset`. Fixtures, tests and
  small custom sources use it.

`Dataset`, `IterableDataset` and `DataLoader` do not change. The primary contract for a source
is `IterableDataset`; a source offers `Dataset` when its file is a list in memory. Batch size is
the consumer's choice: store ingestion, the embedder and `materialize` each wrap a source in a
`DataLoader` with the collator they need. A source never batches.

### Settings and pinned files (`triplum.settings`, `datasets.files`)

```python
class Settings(BaseSettings):               # triplum.settings; env prefix TRIPLUM_
    data: Path = ~/.cache/triplum/data      # TRIPLUM_DATA, as today
    cache: Path = ~/.cache/triplum          # TRIPLUM_CACHE, as today; cache.default_root reads it
    mirrors: dict[str, str] = {}            # URL prefix -> replacement prefix, applied at fetch

class File(BaseModel, frozen=True):         # url, name (path under data), sha256, bytes

class Files:                                # a pinned file set bound to settings
    paths() -> dict[str, Path]              # local paths, no I/O
    status() -> "not downloaded" | "partial" | "verified" | "invalid"
    fetch() -> dict[str, Path]              # download what is missing (.part then rename), verify once
    fingerprint() -> str                    # content_key("files", [(name, sha256), ...])
```

`manifest.json` and `manifest_files(name)` stay. The `.part` download, `os.replace` and sha256
verification move from `datasets.base` into `Files` unchanged.

### Built-in sources are classes

A built-in benchmark module defines one class per source part. A class owns its pinned files,
fetches and verifies them on the first `__len__`, `__getitem__` or `__iter__`, and yields
records. Constructing a dataset does no I/O.

```python
class HotpotQACorpus(Pinned, Dataset[Document]):
    version = 1  # bump when the parse changes what it yields

    def __init__(self, settings: Settings | None = None): ...
    def __len__(self) -> int: ...  # loads the file on first call
    def __getitem__(self, i: int) -> Document: ...


class HotpotQAQuestions(Pinned, Dataset[Question]): ...


class TempoCorpus(Pinned, IterableDataset[Document]): ...  # parquet row groups via pyarrow
```

`Pinned` is a mixin: it holds `files: Files` and `settings`, provides `paths()` (fetch on first
call, cached on the instance) and `fingerprint()`, which is
`content_key("dataset", {"class": qualified name, "version": version, "contract":
RECORD_VERSION, "files": files.fingerprint(), "params": constructor parameters that change the
output})`. The identity is a versioned recipe: the file digests, the parser's version, the
shared record and id contract version (`data.corpus.RECORD_VERSION`, bumped when `content_id`,
`chunk_id`, the record fields or the collators change) and the resolved parameters. Settings
such as roots and mirrors are not part of it, since verified bytes are identical. Version
constants are explicit rather than a hash of module source, following the Hugging Face
experience that hashing code is the fragile part. A forgotten bump is not provable by a test:
the parser tests on source-shaped records and the fixture round-trip are sampled regression
coverage, and the contract is that a change to what a source yields bumps its version.

In-memory and streaming, per source, by file shape:

| shape | corpus | questions | sources |
|---|---|---|---|
| separate corpus and question files | indexed for JSON lists; streaming row groups for parquet | indexed | hipporag, tempo, multihoprag, ectqa, metaqa, gatemem, browsecomp_plus |
| corpus derived from inline paragraphs | streaming: iterate question records, yield each unseen passage once | indexed | hotpotqa_full, twowiki_full, musique_full, morehopqa, squad, squad_v2, boolq, quality, qasper, longmemeval_s |
| question-only | none | indexed | popqa, entityquestions, nq_open, ambigqa, bamboogle, freshqa, arc |
| extraction-only | indexed or streaming | gold triples, indexed | graphjudge, genwiki, carb, conll04, scierc |
| a knowledge graph | verbalised chunks, indexed | indexed; triples indexed | metaqa |

For the inline-paragraph sets the corpus and the questions read the same file independently.
Two reads are allowed and not promised cheap: a whole-file JSON source decodes once per reader
on first use (LongMemEval is 277 MB and cannot run today; when it can, it streams), parquet and
JSONL sources iterate incrementally, and the corpus pass of an inline set retains only a set of
document ids as dedup state, never the corpus. MetaQA's entity documents aggregate the whole
knowledge base, so its corpus is eager on first use by declaration. BrowseComp-Plus streams
its parquet like Tempo. A source states which of these it is in its class docstring.

### Benchmark composition

```python
type Source[T] = Dataset[T] | IterableDataset[T]  # utils.data; the two ABCs stay separate


@dataclass
class Benchmark:
    name: str = "custom"
    corpus: Source[Document] | None = None
    qa: Source[Question] | None = None
    extraction: Source[Triple] | None = None
    needs: str | None = None
```

`Benchmark` holds datasets, not batches, and no wrapper types: `QAEvaluation` and
`ExtractionEvaluation` carried one field each and go.

Identity comes off the datasets: `corpus_hash = corpus.fingerprint()`,
`evaluation_hash = content_key("evaluation", {"qa": qa.fingerprint() or None, "extraction":
...})`. Nothing reads a file to compute a run identity. `materialize(benchmark)` keeps its
signature and stays the explicit eager bridge for the current algorithms; it consumes each
source through a `DataLoader` with the matching collator and reports the fingerprints above.

**Integrity checks, in two places.** Checks that one source record can make happen at parse
time and stay: an answerable question with no gold, a LongMemEval answer session missing from
its haystack, a duplicate upstream id, a QASPER question whose evidence matches no segment
(not loaded, as today). Checks across sources happen at `materialize`, before anything is
scored: every gold chunk id of the selected questions exists in the corpus, and document
ids are unique. Candidate ids in question metadata are hints for fixture building and are not
checked: one 2Wiki question's context names a paragraph the released corpus lacks (found by
this check on the pinned files), which the old loader dropped silently. `registry.verify(name)` runs the same checks over a fetched dataset
and `triplum data verify <name>` exposes it. The fixture builder runs both.

**Selection.** `registry.load(name, n, settings)` builds the benchmark and applies
`Take(qa, n)` when `n` is given. `n` is a non-negative integer; `n=0` yields nothing without
opening the source; `Take` pulls exactly `n` records and never the next one; it has a length
when the inner has one, `min(n, len(inner))`; it adds no replay to a one-shot inner. `n`
selects questions: the corpus is never truncated, extraction sets ignore it as today, and at
`materialize` question-linked triples (2Wiki evidences, MQuAKE) are restricted to the selected
question ids, which is what the fixture subset already does. A small corpus for a smoke run is
what fixtures are for.

### Registry and CLI

A registry entry is metadata plus a builder; files and loading live in the classes.

```python
class Entry(BaseModel, frozen=True):
    name: str
    family: str
    licence: str
    default: bool = False
    fixture: bool = True
    needs: str | None = None
    build: Callable[[Settings], Benchmark]
```

Each built-in module exports `ENTRIES`; `registry.ENTRIES` collects them by name and refuses
duplicates. `registry.get(name)`, `names(default_only)`, `is_folder(name)` stay. `status(name)`
builds the benchmark and asks each pinned part for its `Files.status()`; `fetch(name)` calls
`Files.fetch()` on each part. `large` is derived from the union of a benchmark's pinned files
and keeps its meaning for `data fetch --dataset all`: the CLI still skips large sets unless
named, but iterating a large dataset from Python downloads it, because the caller asked for it
by using it. `data` lists entries with family, flags and state as today.

### Fixtures

The fixture format becomes records: `{"documents": [...], "questions": [...], "triples":
[...]}`, one JSON file per dataset under `tests/fixtures`, written with `model_dump`.
`fixtures.read(name, n) -> Benchmark` returns `RecordDataset` parts whose fingerprint is the
fixture's content, and `fixtures.subset(benchmark, n, distractors, seed)` keeps its selection
rule (the first `n` questions, every chunk they need, a seeded fill of distractors) at chunk
granularity: a selected document keeps its full text and only the selected segments, with
their original ordinals. The fixture builder (`scripts/make_fixture.py`) runs the integrity
checks above; candidate ids that the corpus lacks are ignored when selecting. All fixtures
regenerate once for the new ids.

### Local folder

`ingest.files` becomes `FolderCorpus(IterableDataset[Document])` and
`FolderQuestions(Dataset[Question])`. The corpus fingerprint is
`content_key("folder", {"version": parser and packing version, "contract": RECORD_VERSION,
"files": [(relative path, sha256 of bytes), ...]})`, computed from file bytes without parsing
a PDF; document ids stay the relative paths; segments are the paragraph packing of `chunk()`
as today, so behaviour is unchanged. A folder question names gold files, so `FolderQuestions`
parses the files it names when iterated to expand them to every segment; its fingerprint
still needs no parse. `registry.get(path)` returns an entry whose builder composes the two.

### Documentation

A new page `docs/datasets.md` in the navigation: what a built-in source is, the record types,
how identity works, how to compose a benchmark without the registry, and "your own source" with
two runnable examples (an in-memory `RecordDataset` corpus, and a streaming `IterableDataset`
over a folder or a generator) that a test executes. `docs/api/utils-data.md` and
`docs/api/datasets.md` render the new modules; `flow.md` step 1 and the implemented list, and
`docs/api/index.md` rows, change in the same commit. `benchmarks.md` fixes its stale manifest
path. `licences.md` gains pydantic and pydantic-settings.

## Consequences for callers

- `bench.runner` reads `corpus_hash` and `evaluation_hash` from `materialize` as before; the
  values are now source fingerprints. Store file names change once.
- `bench.index.ensure_documents` still writes the materialised frames; consuming the corpus
  through a loader with batch-atomic publication is the store layer of the stack walk.
- `extract`, `eval.triples` and the reader read frames from `PreparedBenchmark` unchanged.
- `bench.data_view` renders entries instead of specs.
- Tests: parser tests build small source-shaped files and iterate the classes through
  `materialize`, as today; `test_runner_dataset_rules` registers entries instead of specs.

## Non-goals

- Chunking beyond source segments, hierarchy, and the `[Document] -> [str] -> [str]` stage.
- Per-question corpora and per-question viewers (GateMem, LongMemEval keep their `needs`).
- Streaming ingestion into the store; bounded-memory runs. This spec makes the sources
  streamable; the consumers follow in their own layers.
- Persisting parsed sources as artifacts (R7); a Hugging Face token setting; shuffling.
- Moving `RunConfig` and the other bench configs to pydantic; that is the bench layer.

## Review record

Cross-model design review, 2026-09-17, `peer-review --mode design`, peer served by the GPT
family through the codex CLI (caller Claude). Verdict: challenges, with ten executed
falsification attempts. Outcome per finding:

- **Changed the decision.** Identity is a versioned recipe including the shared record and
  id contract version and resolved parameters; the claim that the fixture test would catch a
  forgotten bump was refuted by an executed counterexample (a change to record 25 leaves a
  first-20 fixture unchanged) and is withdrawn; the folder fingerprint now carries its parser
  and packing version.
- **Changed the decision.** No universal content-id rule; a per-source key and gold-resolution
  table, with layout functions shared between corpus and question readers for QASPER and the
  folder source. Confirmed on the pinned HippoRAG files: 2Wiki question-side text does not
  reproduce corpus text, so 2Wiki and HotpotQA key by title, MuSiQue by title and text.
- **Changed the decision.** Record-local checks stay at parse time; cross-source checks run at
  `materialize` before scoring and are what `verify` reuses. Moving everything to the fixture
  builder would have let an ordinary run score invalid mappings, and the peer showed that a
  parser that discards unresolved references cannot be caught by a later membership check.
- **Changed the decision.** Per-source unit table; LongMemEval keeps question-scoped session
  ids; MetaQA declares eager aggregation; BrowseComp keeps upstream ids distinct under equal
  text and streams its parquet.
- **Added verification.** Two reads are allowed but not called cheap; LongMemEval's 277 MB
  whole-file decode is named; dedup state bounded to a set of ids.
- **Changed the decision.** `Take` semantics pinned (non-negative, zero without opening, exact
  pulls, length when available, no replay); question-linked triples restricted at
  `materialize` to selected questions rather than silently left whole.
- **Changed the decision.** Segment invariants validated at construction; fixtures keep
  original ordinals; the nested-metadata mutability of frozen pydantic models is stated and
  handled by recomputing fingerprints.
- **Changed the decision.** `Source[T] = Dataset[T] | IterableDataset[T]`; the two ABCs are
  not in a subtype relation and the spec no longer pretends they are.
- **No decision impact.** The peer's counterproposal keeps the architecture (lazy classes,
  settings plus metadata, independent parts, consumer-owned batching, pydantic boundary
  records, `Take` only) and differs only in the points above, all adopted.

Unverified by the peer and still open: peak memory of two independent scans, and QASPER's
unmatched-evidence count on the full file. Both are measured when the fixtures regenerate.

## Acceptance

- Constructing any built-in dataset does no I/O; `fingerprint()` on a fetched or unfetched
  dataset returns without reading a data file; `materialize(registry.load(name))` on a fixture
  equals the committed frames after id regeneration.
- The corpus of a HippoRAG set and its questions can be iterated in either order, or one
  without the other, and every gold chunk id of the questions exists in the corpus
  (`data verify`).
- `Take` over a streaming source consumes only `n` records; `n` never changes a corpus
  fingerprint.
- `data fetch --dataset all` skips large sets; iterating `TempoCorpus` downloads and verifies
  Tempo and yields documents per row group without loading the whole corpus.
- A custom benchmark composed from a generator-backed `IterableDataset[Document]` and a
  `RecordDataset[Question]` runs through `run_benchmark(data=...)` without a registry entry.
- Every fixture pipeline and the extraction fixture tests stay green; `ty`, ruff, cargo and the
  strict docs build pass; the documented examples run as tests.

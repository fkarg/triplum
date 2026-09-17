# Local files as a corpus

Snapshot 2026-09-17. A folder of your own documents is a dataset like any registered one: the
same frames, the same identity rules, the same pipelines. The first target is a folder of papers,
a deliberately hard corpus for KG construction that exercises the whole pipeline end to end.

## Behaviour

- `triplum.ingest.files` turns `(relative path, bytes)` pairs into documents, public grants and
  chunks. Supported: PDF (text layer only), `.docx`, Markdown, plain text. Anything else is
  skipped. A PDF page without a text layer contributes no text and is counted in the document's
  `empty_pages`; OCR is out of scope here and is its own later piece.
- Chunking packs whole paragraphs (blank-line separated) to about 1,500 characters and splits a
  longer paragraph at whitespace; spans are offsets into the document's text. Hierarchical
  chunking (D2 `parent_id`, `level`) stays planned and will replace this without changing the
  frames.
- Identity is portable: document id is the relative path, `uri` is null, `observed_at` is 0, the
  file's sha256 is in document metadata. A copied folder has the same corpus hash.
- `questions.jsonl` beside the files gives questions: `question`, `answer`, optional `aliases`,
  `qtype`, `id`, and `gold` as relative paths whose every chunk is gold. A gold path that is not
  in the folder fails the load.
- The registry accepts a directory path wherever it accepts a name (`registry.load`,
  `--dataset`); the spec is synthesised (`files:<folder name>`, nothing to fetch, no fixture).
  Without questions the corpus is extraction-only, like the text-to-triple sets.
- An object-store source (S3 and the like) is a second producer of the same `(path, bytes)`
  pairs and needs no change below `frames`; not built yet.

## Out of scope

OCR and layout analysis, HTML and e-mail formats, per-file grants (everything is `public`;
a `grants.jsonl` sidecar is the obvious extension), hierarchical chunking.

## Verification

`tests/test_ingest_files.py`: a hand-written PDF, a generated `.docx`, Markdown and an ignored
binary in one folder; chunk packing and splitting; portable hash across a copied folder; loud
failure on a missing gold file; extraction-only without questions.

# Ingestion sources: transcripts, audio, PDF structure

Snapshot 2026-09-17. What the owner corpora need beyond the text-layer loader in
`ingest/files.py`: a folder of papers (PDF) with sections, references and captions, and
podcasts and videos (YouTube, RSS feeds, local files) with a transcript whose every span has a
time offset and, where possible, a speaker. Versions, dates and licences were read from PyPI,
GitHub licence files and Hugging Face model cards; behaviour claims from READMEs, source and
maintainer comments. *(unverified)* marks the rest. Every row is written so it can be copied into
`docs/licences.md` when the dependency is adopted.

## YouTube transcripts

| tool | version | licence | verdict |
|---|---|---|---|
| youtube-transcript-api | 1.2.4 (2026-01) | MIT | Segment-level only. No commits since January; cannot fetch the growing PO-token subset (issue #592); cloud IPs blocked; the README now points to paid proxies. Not the route. |
| yt-dlp | 2026.08.19, monthly | Unlicense | The only route with a maintained path through YouTube's PO-token rollout. Subtitle formats `json3, srv1-3, ttml, srt, vtt`; yt-dlp saves what YouTube returns. |

- **Word timing.** Auto (ASR) tracks carry per-word timing in both `vtt` (inline cue timestamps)
  and `json3` (`events[].tStartMs` plus `segs[].tOffsetMs`; absolute word time is the sum).
  Human tracks have no word timing. The `json3` field semantics are *(unverified)* against any
  Google source; hundreds of third-party parsers implement them identically.
- **PO tokens.** The `web` client needs a PO token for subtitles; without one yt-dlp warns and
  tries the next client. The maintained fix is the `bgutil-ytdlp-pot-provider` plugin (a Node
  side service) or `--extractor-args "youtube:po_token=web.subs+TOKEN"`.
- **Rate limits.** Auto-translated captions are throttled (issue #13831, 2026-01); original
  language captions are not. Fetch the original language only, never `all`. Guest limit is about
  300 videos per hour per IP; use `sleep_interval_subtitles`.
- Transcript-only fetch needs no ffmpeg: `skip_download`, `writesubtitles`,
  `writeautomaticsub`, `subtitlesformat="json3"`, `subtitleslangs=["en"]`.

Sources: https://github.com/yt-dlp/yt-dlp , https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide ,
https://github.com/jdepoix/youtube-transcript-api/issues/592

## Audio and feeds

| tool | version | licence | verdict |
|---|---|---|---|
| yt-dlp audio | as above | Unlicense | `-f bestaudio` needs no ffmpeg; `-x` conversion does. Extractors for Apple Podcasts, Acast, Libsyn, Simplecast, Megaphone, TuneIn and generic direct media links. |
| feedparser | 6.0.14 (2026-07) | BSD-2 | Maintained again since 2025-09, pure Python. Use it. |
| podcastparser | 0.6.11 (2025-11) | ISC | gpodder's parser; fine, slow cadence. |
| fastfeedparser | 0.6.1 (2026-08) | MIT | lxml-based; only for throughput. |

RSS enclosures are plain HTTP downloads of the `<enclosure url>`. **Terms.** YouTube's Terms of
Service forbid downloading content except where authorised and accessing the service by
automated means; both tools fall under that. Podcast enclosures are publicly served files whose
download is the designed use, but the audio stays the publisher's work. Record both in
`docs/licences.md` as "commercial reuse: n/a, terms-restricted access pattern".
https://www.youtube.com/t/terms

## Local transcription

Reference numbers from the Open ASR Leaderboard paper (arXiv:2510.06961, A100, batch 64),
speed as inverse real-time factor, quality as word error rate: whisper large-v3 146 / 7.44;
large-v3-turbo 200 / 7.83; Parakeet-TDT-0.6B-v2 3390 / 6.05; Canary-1B-v2 749 / 7.15.

| tool | version | code / weights | word timestamps | speakers | notes |
|---|---|---|---|---|---|
| mlx-whisper | 0.4.3 (2025-08) | MIT / MIT | yes | no | Apple Silicon GPU via MLX, openai-shaped output, pure wheel. No published speed *(unverified)*. |
| mlx-audio | 0.5.4 (2026-09) | MIT | yes (Whisper, Parakeet, Qwen3 aligner) | no | Actively maintained superset of mlx-whisper; heavier. |
| parakeet-mlx | 0.5.2 (2026-06) | Apache-2.0 / CC-BY-4.0 | token-level | no | Fast lane for English and European audio on Mac. |
| faster-whisper | 1.2.1 (2025-10) | MIT / MIT | yes | no | Fastest mature Whisper on NVIDIA (CTranslate2); CPU-only on Mac. |
| whisperX | 3.8.6 (2026-05) | BSD-2 / varies | yes, forced alignment | yes, wraps pyannote | Batched CT2 plus alignment plus speakers in one dependency on NVIDIA; Python < 3.14; pins torch 2.8. |
| NeMo parakeet-tdt-0.6b-v3 | nemo-toolkit 3.0.0 (2026-08) | Apache-2.0 / CC-BY-4.0 | yes | no (Sortformer separate) | About 20x Whisper throughput at lower error, 25 European languages; heavy install, GPU-oriented. |
| openai-whisper | 20250625 | MIT / MIT | yes | no | Reference implementation, one release a year; baseline, not runtime. |
| whisper.cpp / pywhispercpp | 1.9.4 / 1.5.1 (2026-08) | MIT / MIT | experimental | speaker-change markers only | Best raw Mac engine, worst Python ergonomics; Metal needs a source build. |
| transformers pipeline | 5.17.0 (2026-09) | Apache-2.0 | yes | no | Fallback; slower than CT2 or MLX. |

Skipped: stable-ts (archived 2026-05), whisper-timestamped (AGPL), CrisperWhisper (weights
non-commercial), insanely-fast-whisper (stale), nougat-class GPU-only models. Newer ASR
families (Qwen3-ASR, Voxtral open weights, Kyutai STT, Moonshine) do not displace Whisper or
Parakeet as a local default with word timestamps; Voxtral open weights have no timestamps at
all, and OpenAI's `gpt-4o-transcribe` has none either.

**Recommendation.** Laptop: mlx-whisper large-v3-turbo with `word_timestamps=True`, MIT end to
end. Workstation: whisperX when speakers are wanted in one dependency, NeMo Parakeet for raw
throughput. Diarisation stays a separate stage so engines are independently swappable.

## Speaker diarisation

| tool | version | licence | verdict |
|---|---|---|---|
| pyannote.audio | 4.0.7 (2026-06) | MIT | The default. 4.0 broke `use_auth_token` (now `token`) and needs ffmpeg through torchcodec. |
| `pyannote/speaker-diarization-community-1` | 2025-09 | CC-BY-4.0, gated (accept terms, HF token) | Returns `speaker_diarization` and `exclusive_speaker_diarization`; the latter is built for assigning speakers to word timestamps. H100: 31 s per audio hour. CPU and MPS speed *(unverified)*; plan for CPU on Mac. |
| `pyannote/speaker-diarization-3.1` | 2024-05 | MIT, gated | Legacy. |
| pyannoteAI precision models | hosted | proprietary, paid | Same interface with an API key. Optional. |
| NeMo Sortformer offline v1 | 2025-12 | CC-BY-NC-4.0 | Out. Four speakers maximum. |
| diart | 0.9.2 (2025-02) | MIT | Streaming only, pinned to old pyannote. Skip. |
| senko | 0.1.0 (2026-04) | MIT | Very fast on Apple Silicon, no accuracy table. Benchmark candidate. |
| Reverb | 2024-10 | research-only weights | Out. |

## PDF structure for papers

| tool | version | code / weights | sections | references parsed and linked | captions | CPU | verdict |
|---|---|---|---|---|---|---|---|
| GROBID | 0.9.1 (2026-08), repo moved to `grobidOrg` | Apache-2.0 | yes, numbered `div/head` | **yes**: `biblStruct` with DOI via CrossRef consolidation, in-text `ref target` links | yes, `figDesc` | yes, seconds per paper | The only tool doing all three under a permissive licence on CPU. Cost: a Java or Docker service and TEI parsing. Official client `grobid-client-python` 0.2.0. |
| docling | 2.128.0 (2026-09) | MIT / Apache-2.0 and CDLA-Permissive-2.0 *(which applies to which artifact unverified)* | yes, but all level 1 unless `HeadingHierarchyOptions` is enabled | no, "references" is a layout label only | yes | yes, about 1.3 s per page on M3 Max | Best MIT layout tool; no bibliography. |
| marker | 2.0.0 (2026-07) | Apache-2.0 / OpenRAIL-M with a revenue threshold | yes | no | yes | slow | Weights licence not clean for later reuse. |
| pymupdf, pymupdf4llm | 1.28.2 (2026-08) | AGPL-3.0 or paid | yes | no | yes | fast | AGPL across the stack. Not adopted. |
| pypdf (current dependency) | 6.19.0 (2026-09) | BSD-3 | no | no | no | yes | Text only. Stays as the no-service fallback. |
| pdfplumber, pdfminer.six | 0.11.10 / 2026-01 | MIT | no | no | no | yes | Low-level characters and tables. |
| nougat | 0.1.17 (2023) | MIT / CC-BY-NC-4.0 | headings | no | no | GPU | Out. |

Also seen: MinerU (Apache-2.0 with usage thresholds, no references), olmOCR and PaddleOCR-VL
(GPU vision models), Unstructured (no heading levels, no references), refextract (GPL),
`s2orc-doc2json` (Apache-2.0; a reusable mapping from GROBID TEI to JSON with citation spans).
Resolver APIs: CrossRef (no key, `mailto` for the polite pool; GROBID uses it natively),
OpenAlex, Semantic Scholar. One live GROBID test returned an empty title on an arXiv PDF while
body, figures and references were right; use `consolidateHeader=1` or the arXiv id for titles.

## Transcript data model

- **WebVTT** (W3C, CR draft 2026-05): cue with `start --> end`, voice spans `<v Alice>` for the
  speaker, inline cue timestamps for word timing. Cannot carry confidences, source ids or
  overlapping speakers without abusing cue text. Right as an *export*, wrong as the canonical
  form. https://www.w3.org/TR/webvtt1/
- **Whisper JSON** (`{text, language, segments[{id, start, end, text, words[{word, start, end,
  probability}], ...}]}`) is what openai-whisper, mlx-whisper and faster-whisper all emit;
  whisperX adds `speaker` per segment and per word; AssemblyAI and Deepgram converge on the same
  shape with milliseconds and speaker ids.
- Libraries: `pysubs2` 1.9.0 (2026-08, MIT, Python >= 3.12, no dependencies) reads and writes
  SRT, WebVTT, ASS and TTML and is the one to use for export. `pyannote.core` writes RTTM.
- **Recommendation.** Canonical form as dataclasses: `Transcript(source_id, language,
  duration_s, segments, provenance{asr, diarizer})`, `Segment(id, start_s, end_s, speaker,
  text, words, confidence)`, `Word(text, start_s, end_s, confidence, speaker)`. Seconds as
  floats; speaker per word because diarisation changes mid-segment; engine-specific fields
  under an optional `asr_meta`. A fact cites `(source_id, start_s, end_s)`, the stable key
  across re-runs, the way a text fact cites `(chunk, char offset)`.

## Recommended minimal stack

**Papers.** GROBID 0.9.1 as a Docker service (`grobid/grobid:0.9.1-crf` on CPU) plus
`grobid-client-python` and `lxml` over the TEI, with citation consolidation on and raw citations
kept. Sections become hierarchical chunks, references become linkable entities with DOIs, and
captions come along, in seconds per paper. `pypdf` remains the no-service fallback. docling
later only if table cells or figure crops matter.

**Podcasts and videos.** yt-dlp for captions (`json3`, original language only) and audio, with
the PO-token provider when needed; feedparser and plain HTTP for RSS; local files straight to
ASR. mlx-whisper on the laptop, whisperX or Parakeet on the workstation; pyannote 4 with the
community-1 pipeline as an independent diarisation stage; the transcript dataclasses above as the
canonical form with WebVTT export through pysubs2. Everything permissive (Unlicense, MIT, BSD-2,
Apache-2.0, CC-BY-4.0), no source builds, and YouTube's own captions give per-word timing for
free when no model should run.

## Flags

- `json3` field semantics and whether yt-dlp's non-web clients avoid the subtitle PO-token
  requirement: *(unverified)*.
- mlx-whisper, parakeet-mlx and pyannote community-1 CPU or MPS speed: no primary numbers.
- pyannote MPS correctness on 4.x is not maintainer-verified.
- Metadata inconsistencies seen: NeMo README says Python >= 3.12, PyPI says >= 3.10; Hugging
  Face tags whisper large-v3 as Apache-2.0 while the repo is MIT.

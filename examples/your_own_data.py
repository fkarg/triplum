"""A benchmark from your own documents and questions, without registering anything."""

import tempfile

from triplum.bench.bench_view import print_summary
from triplum.bench.config import LLMConfig, PipelineConfig, RunConfig
from triplum.bench.inputs import Benchmark
from triplum.bench.report import summary
from triplum.bench.runner import run_benchmark, runstore_path
from triplum.bench.runstore import RunStore
from triplum.data.corpus import Document, chunk_id
from triplum.eval.inputs import Question
from triplum.utils.data import RecordDataset

documents = [
    Document(id="d1", source="notes", text="Alice met Bob in Ghent in 2019."),
    Document(id="d2", source="notes", text="Bob moved to Oslo the year after."),
    Document(id="d3", source="notes", text="Carol has never left Lisbon."),
]
questions = [
    Question(
        id="q1", question="Where did Alice meet Bob?", answer="Ghent", gold=(chunk_id("d1", 0),)
    ),
    Question(id="q2", question="Where did Bob move to?", answer="Oslo", gold=(chunk_id("d2", 0),)),
]
mine = Benchmark(name="notes", corpus=RecordDataset(documents), qa=RecordDataset(questions))

cfg = RunConfig(
    dataset="notes",
    pipeline=PipelineConfig(name="bm25", reader=LLMConfig(kind="fake"), top_k=2),
    cache_root=tempfile.mkdtemp(),
)
run_id = run_benchmark(cfg, data=mine)
with RunStore(runstore_path(cfg)) as rs:
    print_summary(summary(rs, [run_id]))
    print(rs.questions(run_id).select("question_id", "answer", "r2"))

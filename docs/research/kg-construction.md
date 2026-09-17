# LLM-era knowledge-graph construction: evidence and experiments for triplum

**Research cutoff: 16 September 2026.** This survey distinguishes published measurements, implementation documentation, and recommendations. Scores below have different datasets and denominators; they are not a leaderboard. Repository licenses refer to software, not automatically to datasets or model weights. Unverified programme claims remain explicitly unverified.

## 1. Taxonomy of LLM-era KG construction, 2023–2026

The useful distinctions are **when vocabulary is chosen**, **what constrains extraction**, **how mentions become shared identities**, and **whether construction revisits previous decisions**. These are composable dimensions: an ontology-aware extractor can also decompose atomic facts, canonicalize relations, and update incrementally. A JSON output schema specifies serialization; it does not by itself supply an ontology or establish factual correctness.

| Approach | What it does | Strengths | Published numbers | Code/license |
|---|---|---|---|---|
| OpenIE: [HippoRAG][hippo] | Extracts unrestricted subject–relation–object phrases; adds similarity links for graph retrieval. | Broad coverage without preparing a domain schema. | HippoRAG 2 QA results are discussed in §4; these measure the complete system. | [HippoRAG][hippo-code], MIT. |
| Schema-guided prompting | Supplies allowed entity/relation types and examples, as in [Text2KGBench][t2kg]. | Predictable vocabulary and straightforward validation. | Original Vicuna-13B Wikidata-TekGen F1 **.35**, predicate conformance **.83**. Liao’s claimed schema-prompt superiority has no public paper yet (programme abstract only). | [Text2KGBench][t2kg-code], Apache-2.0; Tiwari's [official implementation](https://github.com/dice-group/ontology-aware-kg-construction), GPL-3.0, three prompting strategies and three evaluator rules, no aggregate numbers in the README. |
| Ontology-aware prompting: [Tiwari implementation][tiwari-code] | Adds ontology semantics and combines ontology-constrained OpenIE, structured reasoning, and general extraction with consensus filtering. | Tests whether definitions and constraints improve grounded extraction. | Full paper and numerical results **could not verify**; acceptance evidence in §2. | [Official code][tiwari-code], [GPL-3.0][tiwari-license]. |
| [OntoGPT/SPIRES][spires] | Recursively populates LinkML schemas and grounds entities to ontology identifiers. | Nested domain records and terminology normalization. | Precise benchmark number **not verified** in this research pass. | [OntoGPT][ontogpt-code], BSD-3-Clause. |
| Extract–define–canonicalize: [EDC][edc] | Open extraction, contextual relation definitions, then mapping to supplied or induced vocabulary. | Separates discovering facts from normalizing relation language. | GPT-3.5 WebNLG strict F1 **.688**, **.753** with refinement. | [EDC][edc-code], MIT; relation canonicalization, not a complete entity resolver. |
| Incremental [iText2KG][itext] | Distills documents, incrementally extracts entities/relations, and merges through embeddings. | Integrates new documents into an existing graph. | Computer-science relevant-triple precision **.94±.06** with local entities versus **.83±.06** with global entities. | [iText2KG][itext-code], Apache-2.0. |
| Atomic/temporal [ATOM][atom] | Decomposes atomic facts, extracts temporal tuples, then merges entities, relations and time information. | Explicitly tests information loss, temporal extraction and incremental consistency. | COVID-NYT factual recall **.405→.720**, but hallucination **.333→.428**, lead paragraphs→atomic facts. | [iText2KG/ATOM][itext-code], Apache-2.0. |
| Corpus consolidation: [KG-Gen][kggen] | Extracts and aggregates graphs, then clusters entity/relation aliases using candidate retrieval and LLM decisions. | Reduces fragmentation across documents. | NeurIPS 2025 MINE-1: **66.07%**, versus GraphRAG **47.80%**, Stanford OpenIE **29.84%**. | [KG-Gen][kggen-code], MIT. |
| Agentic/multi-pass [SAC-KG][sac] | Generator retrieves domain evidence; verifier checks; pruner controls iterative expansion. | Domain-focused construction with explicit checking stages. | Reported precision **89.32%**, domain specificity **81.25%**, over one million nodes. | Official code/license **could not verify**. |
| Global fusion: [Graphusion][graphusion] | Topic seeds and contextual extraction precede alias/conflict fusion and inferred relations. | Domain-concept graphs and educational reasoning. | Expert relation-quality score **2.37/3**, versus **2.08** without fusion. | [Graphusion][graphusion-code]; license **could not verify**. |
| Document-centric [Docs2KG][docs2kg] | Combines document/layout structure with multimodal semantic graphs. | Heterogeneous PDFs, tables, HTML and email ingestion. | Comparable numerical construction/QA benchmark **not verified**. | [Docs2KG][docs2kg-code], Apache-2.0. |
| LLM entity/relation typing | Classifies mentions into classes and relation phrases into predicates; [Allen–Groth][typing] test class membership, EDC handles predicates. | Adds typed interfaces and checks to otherwise open extraction. | Class-membership macro-F1 **.830 Wikidata**, **.893 CaLiGraph**; not generic triple accuracy. | [Typing evaluation][typing-code], MIT; EDC above. |
| Dynamic construction: [Graphiti/Zep][zep] | Ingests episodes, resolves identities and updates time-sensitive facts while retaining history. | Continually changing information and memory queries. | DMR accuracy **94.8%** versus full-context **94.4%**, same GPT-4-turbo reader. | [Graphiti][graphiti-code], Apache-2.0. |

ATOM’s five positions are **subject, relation, object, validity-start, validity-end**. Observation time belongs to the surrounding snapshot context. This is not automatically triplum’s complete transaction-time interval model. Its hallucination rate is unsupported predictions divided by matched-plus-unsupported predictions; its reported stability uses embedding-centroid similarity, not identical triples. Preserve both source spans and extraction history when adapting it. [ATOM][atom]

Likewise, inferred Graphusion relations should remain distinguishable from source-extracted assertions. Multi-pass verification can repair outputs, but agreement between successive calls is not independent evidence. These are integration recommendations, not claims that the surveyed tools implement triplum’s provenance-derived permissions.

## 2. Ontology learning and schema induction, 2024–2026

Ontology learning supplies classes, hierarchies and relations; extraction populates them. An induced taxonomy alone does not establish property domains/ranges, cardinalities or a usable closed extraction vocabulary.

**[OntoLearner][ontolearner]** is a July 2026 benchmark/toolkit covering **180 ontologies across 22 domains**, with term typing, taxonomy discovery and non-taxonomic relation tasks. It evaluates 22 retrieval models and 12 LLMs through retrieval-only, LLM-only and RAG configurations. Its [MIT implementation][ontolearner-code] is useful for evaluating schema-learning components separately from triple extraction.

**[OLLM][ollm]**, NeurIPS 2024, fine-tunes language models to generate taxonomic subgraphs, addressing overproduction of frequent concepts. Evaluation covers Wikipedia and transfer to arXiv. Its [Apache-2.0 implementation][ollm-code] provides a taxonomy-learning baseline; a full constraint ontology would require additional work. A numeric comparison was not verified here.

**[NeOn-GPT][neon]** structures ontology engineering around requirements, competency questions and staged conceptualization. The [accepted 2026 Semantic Web extension][neon-extended] adds cross-domain experiments and validation/repair using RDFLib, reasoners and OOPS!. Its [extended implementation][neon-code] is MIT. Competency questions make intended coverage explicit; logical consistency still does not demonstrate that populated facts follow from documents.

**LLMs4OL shows strong task dependence.** The [2024 overview][ol24] reports WordNet typing F1 **.9938** for a BERT-plus-rules entry, while the best UMLS non-taxonomic relation result is **.0783**. The [2025 overview][ol25] reports mean F1 **.3741** for SBU-NLP and **.3400** for Alexbek, warning that unequal subtask participation distorts aggregate rankings. These are not universal ontology-construction accuracy scores.

The official [2025 challenge][ol25-site] places it at ISWC Nara. The [2026 programme][ol26] covers text-to-ontology construction, ontology extension/reuse and cross-domain taxonomy at ISWC Bari, **25–29 October**, still future at this cutoff. Final leaderboards were nevertheless [announced on 6 August][ol26-announcement]. Their [ranking metrics][ol26-results] are graph similarity and taxonomy F1; exact embedded scores **could not verify**.

For corpus induction, [AutoSchemaKG][autoschema] is an important counterexample to loose “schema-first” descriptions: it extracts entity/event triples **before** inducing conceptual types. Its [MIT implementation][autoschema-code] therefore represents bottom-up schema discovery. By contrast, a triplum schema-first experiment should sample training documents, propose types and relation signatures, consolidate definitions, freeze that schema, and only then extract held-out documents. Treat unknown predicates explicitly; forcing every assertion into the nearest allowed relation can disguise missing coverage.

**Programme verification:** [SEMANTiCS 2026][semantics] confirms Ghent, 15–17 September. DICE’s [first-party announcement][tiwari-acceptance] verifies Tiwari’s research-track acceptance, and its repository verifies the method; the full paper's numbers are not public (re-checked 2026-09-17). Liao et al., *Best Practices in GraphRAG*, and its “schema-based prompts best” finding exist only as the programme abstract. Both remain reproduction leads, not established evidence.

## 3. Entity resolution and canonicalization

Distinguish mention normalization, linking to existing identifiers, discovering previously unknown entities, and predicate canonicalization. EDC’s relation normalization cannot substitute for entity identity decisions. [EDC][edc-code]

A practical resolution ladder is: normalized exact matching; fuzzy string and embedding candidate generation; then contextual, type-aware adjudication. [RapidFuzz][rapidfuzz] supplies string similarities under [MIT][rapidfuzz-license]; similarity is evidence for considering a pair, not proof that it denotes one entity. This ladder is a recommendation, with thresholds calibrated on labeled pairs. Exact matching also needs context: identical names can denote different people. Treat uncertain pairs as unresolved instead of making every similarity edge an identity assertion.

The official [neo4j-graphrag builder/API][neo4j] documents `SinglePropertyExactMatchResolver`, `FuzzyMatchResolver` using RapidFuzz, and `SpaCySemanticMatchResolver` using static embeddings. Matches are label-constrained. A built-in LLM entity resolver **could not verify** in those docs. KG-Gen supplies an independently documented LLM-based consolidation approach. Preserve mention-to-entity mappings and reversible merge decisions rather than destructively losing evidence. [Neo4j API][neo4j-api]; [KG-Gen code][kggen-code]

**CaLiGraph-style contextual linking** has a useful non-LLM comparator: [NASTyLinker][nasty] combines mention/entity affinities with conflict resolution and NIL clusters for entities absent from the reference KG. On known entities in its listing experiment, exact-match F1 is **81.5**, versus **91.8** with NASTyLinker plus reranking. A 100-cluster manual audit finds **eight incomplete clusters** and **five mixing different entities**. Its evaluation uses P/R/F1, NMI and ARI, and one-to-one NIL-cluster assignment to penalize fragmentation.

For triplum, measure both over-merging and alias fragmentation: pairwise merge P/R, B-cubed F1, cluster purity, aliases per gold entity, and hard-negative audits. Include homonyms, abbreviations, parent/subsidiary organizations and near-identical technical concepts. Relation merging must preserve direction, negation and temporal scope. Report entity linking and relation normalization separately; triple F1 alone cannot diagnose them.

## 4. Evaluating construction and its downstream value

**[Text2KGBench][t2kg]** supplies Wikidata-TekGen (**10 ontologies, 13,474 sentences**) and DBpedia-WebNLG (**19 ontologies, 4,860 sentences**). Preserve its triple precision/recall/F1, ontology conformance and subject/relation/object hallucination metrics for comparability. However, original conformance checks **predicate membership**, not domain/range; relation hallucination is its complement. Subject/object checks rely on stemmed substring presence and can falsely flag expanded acronyms. Its locally closed scoring restricts evaluation to reference-present relations, accommodating incomplete gold. Thus these scores are useful proxies, not complete factuality measurements.

**[Text2KGBench-LettrIA][lettria]** refines the DBpedia-WebNLG portion into **14,882 triples** over the same 4,860 sentences. It adds hierarchy-aware domain/range checks, datatype/object-property distinctions, normalized literals, JSON validity and cost/latency. Its **component macro-F1** differs from original triple F1. Fine-tuned augmented Mistral-Small-3.2 entity F1 **.8837** versus prompted Gemini-2.5-Pro **.6595** compares adapted and unadapted systems. Its unseen-ontology experiment holds out City only. Preserve both scoring systems rather than silently replacing one with the other.

**[WebNLG][webnlg]** was originally RDF-to-text; extraction reverses the direction. **[Re-DocRED][redocred]** reannotates 4,053 documents to address missing relations, making it complementary for document-level extraction. Neither evaluates an entire open-world, temporal construction pipeline. For triplum, report whether Re-DocRED experiments receive gold entity clusters or must discover them: those are different tasks. Text2KGBench’s [repository][t2kg-code] distinguishes Apache-2.0 code from inherited TekGen CC BY-SA 2.0 and WebNLG CC BY-NC-SA 4.0 data. LettrIA’s separate downloadable code/data license **could not verify**; the article license is insufficient evidence.

**[MINE][kggen]** measures recoverable information, not exact triple correctness. MINE-1 uses 100 generated articles with 15 verified facts each, graph-neighborhood retrieval and an LLM inference judge. The final KG-Gen paper also adds MINE-2 on WikiQA: despite MINE-1 superiority, downstream RAG performance is comparable to GraphRAG. This is evidence against assuming automatic transfer, not a measured correlation coefficient.

**Extrinsic evidence is mixed but informative.** [HippoRAG 2][hippo2] reports QA F1 **48.6/71.0/75.5** on MuSiQue/2Wiki/HotpotQA versus dense NV-Embed-v2 **45.7/61.5/75.3**, using the same Llama-3.3-70B reader. These are whole-pipeline comparisons. [Graphusion][graphusion] reports TutorQA T1 accuracy **92.00** versus GPT-4o RAG **64.40**, also with pipeline differences. Neither isolates extraction quality.

A stronger controlled example is [Nishida et al., TACL 2026][dissecting]: holding other modules at defaults, supervised extraction beats LLM in-context extraction by **2.9/3.7 answer-recall points** on CDR-QA/DocRED-QA, alongside higher relation precision. This supports a construction-quality effect in those settings, not a universal monotonic relationship between triple F1 and QA.

**LLM judges** should assess whether a triple follows from its cited text, separately from ontology validity or world plausibility. [GraphJudge][graphjudge] trains a judge within a construction pipeline; this is not proof that arbitrary prompted judges are reliable. SAC-KG reports human–GPT-4 agreement **κ=.613**. Use blinded human calibration, disagreement reporting and a judge independent of the extractor where feasible. Unsupported predictions estimate precision; measuring recall additionally requires a reference inventory of omitted facts. [SAC-KG][sac]

**V&V attribution is not publicly verifiable.** No public paper or proceedings entry for Schmidt/Kharlamov/Paschke’s V&V taxonomy was reachable on 2026-09-17; the [SKGi site][skgi-program] mixes its 2025 Vienna and 2026 Ghent pages. The owner attended the talk; treat the five dimensions as heard, not cited, until the PDF is public. Pending the paper, use the task-supplied dimensions only as provisional bookkeeping: **artefact** (schema/triples/resolution), **reference basis** (gold/source/constraints), **perspective** (intrinsic/downstream), **executive** (rules/humans/LLMs), **temporal execution** (ingestion/update/regression). These interpretations are proposed here, not attributed definitions.

## 5. Recommended first variants and open questions

The non-LLM comparator these variants are measured against is in
[kg-construction-nonllm.md](kg-construction-nonllm.md) and specified in
`docs/specs/2026-09-17-extraction-baseline.md`.

Implement six small pipelines over the same chunks and model configuration. These are recommendations, not reproductions unless original prompts and settings are pinned. The broad comparison ranks construction recipes; only matched contrasts isolate particular stages. Using identical resolver code also does not guarantee identical resolution quality when extractors produce different mentions.

1. **OpenIE:** unrestricted triple prompt, evidence spans, conservative exact resolver. This establishes coverage and fragmentation baselines.
2. **Fixed schema:** allowed classes/predicates, definitions and examples; same resolver. Measure coverage lost through vocabulary restriction.
3. **Ontology-aware:** the same schema plus domain/range and hierarchy information. Score validation for every arm; initially keep validation from changing outputs so the prompt comparison remains isolated.
4. **EDC-style:** reuse open extraction, define predicates, retrieve candidate definitions and canonicalize relations. Keep entity resolution unchanged.
5. **Atomic-first:** decompose chunks into source-grounded assertions before variant 3; retain original spans and count the additional calls. Add temporal tuple extraction only in a separate temporal experiment.
6. **Induced schema first:** learn and consolidate vocabulary from training documents, freeze it, then reuse variant 2. Record induction cost, missing coverage and schema changes explicitly.

After this baseline, cross a small subset with fuzzy, embedding and LLM resolution, including KG-Gen-style clustering. Compare ontology validation/repair as another explicit ablation. Avoid crediting a construction prompt for simultaneous improvements in its resolver or repair loop.

**Fixed retriever:** use one HippoRAG-2-inspired implementation: fixed query-to-triple/passage embeddings, fixed seed selection and filtering, personalized PageRank, then return original supporting passages to one answer model. Freeze encoder, graph adapter, thresholds, edge weighting, passage budget and reader prompt across construction variants. Use the same fact/provenance representation and avoid construction-specific retrieval summaries. Include a graph-disabled dense baseline. This tests utility under that retriever, not a retriever-independent ranking. [Architectural precedent][hippo2]

Use identical document pools and splits for HotpotQA, MuSiQue and 2Wiki. Document the provenance of manually supplied schemas; freeze schema induction, canonicalization inventories and alignment rules before test extraction. Keep questions/answers out of construction and schema induction; fix tuning on development data. Report QA EM/F1, supporting-passage recall@k, all-support retrieval, answerability failures, indexing/query tokens, calls, latency, graph size, duplicate rate and passage coverage. Repeat construction runs and report paired uncertainty, including variation between constructed graphs. A fixed answer-context budget does not equalize construction expenditure; show quality–cost curves as well as headline scores.

Compute original Text2KGBench metrics, LettrIA structural metrics, semantic-matching scores alongside exact matching, source-supported precision, resolution metrics, invalid-output rate, and exact triple-set stability. Publish native-output and reference-aligned results separately: valid open predicates absent from the benchmark ontology should not silently become factual errors. Freeze and audit the alignment procedure. Semantic matching must check relation direction and negation, not merely embedding similarity.

Because QA corpora lack exhaustive triple gold, annotate a separate same-corpus sample for intrinsic/QA analysis. Sample passages independently of predictions and retrieval, inventory omitted supported facts, and blind annotators to construction variant. Then test whether precision, coverage, fragmentation or missing bridge facts predict QA outcomes within that corpus, with uncertainty estimates. Text2KGBench scores alone cannot establish question-level correlation on another corpus. Incomplete annotation should be reported as a limitation rather than interpreted as evidence that every unmatched triple is hallucinated.

For triplum, every assertion, alias and merge needs retained evidence and time metadata. Filter to the viewer’s visible evidence before graph construction for retrieval. Evaluate update order, retractions, historical queries and permission changes separately: static multi-hop QA does not test those requirements.

**Open questions**

- Which missing bridge facts explain QA failures better than aggregate triple F1?
- When does schema restriction improve precision enough to offset lost coverage?
- Can atomic decomposition improve recall without its observed hallucination increase?
- Which resolver errors cause the largest retrieval damage, and can merges be reversed safely?
- Do rankings survive a second retriever, different domains and smaller extraction models?
- How should conflicting sources, schema evolution and historical permissions affect identity?

## Sources

All sources below were searched or fetched during this research session. Programme announcements and repository documentation are distinguished from papers in the text.

- **HippoRAG:** [2024 paper][hippo]; [HippoRAG 2 paper][hippo2]; [code/license][hippo-code].
- **Text2KGBench:** [paper][t2kg]; [code/data licensing][t2kg-code].
- **Tiwari:** [implementation][tiwari-code]; [license][tiwari-license]; [DICE acceptance announcement][tiwari-acceptance].
- **SPIRES/OntoGPT:** [paper][spires]; [code/license][ontogpt-code].
- **EDC:** [EMNLP 2024 paper][edc]; [code/license][edc-code].
- **iText2KG/ATOM:** [iText2KG paper][itext]; [ATOM paper][atom]; [code/license][itext-code].
- **KG-Gen:** [NeurIPS 2025 final paper][kggen]; [code/license][kggen-code].
- **SAC-KG:** [paper][sac].
- **Graphusion:** [paper][graphusion]; [code][graphusion-code].
- **Docs2KG:** [paper][docs2kg]; [code/license][docs2kg-code].
- **Class membership:** [Allen–Groth paper][typing]; [code/license][typing-code].
- **Graphiti:** [Zep paper][zep]; [code/license][graphiti-code].
- **OntoLearner:** [paper][ontolearner]; [code/license][ontolearner-code].
- **OLLM:** [paper][ollm]; [code/license][ollm-code].
- **NeOn-GPT:** [original publication][neon]; [accepted extension][neon-extended]; [extended code/license][neon-code].
- **LLMs4OL:** [2024 overview][ol24]; [2025 overview][ol25]; [2025 programme][ol25-site]; [2026 programme][ol26]; [results announcement][ol26-announcement]; [leaderboard][ol26-results].
- **AutoSchemaKG:** [paper][autoschema]; [code/license][autoschema-code].
- **Conference checks:** [SEMANTiCS 2026][semantics]; [SKGi programme][skgi-program].
- **Resolution tooling:** [RapidFuzz][rapidfuzz]; [license][rapidfuzz-license]; [Neo4j builder][neo4j]; [API][neo4j-api].
- **NASTyLinker:** [ESWC 2023 paper][nasty].
- **LettrIA:** [CEUR Vol-4041 paper 3][lettria].
- **Benchmark origins:** [WebNLG][webnlg]; [Re-DocRED][redocred].
- **Construction versus QA:** [Dissecting GraphRAG, TACL 2026][dissecting].
- **Judging:** [GraphJudge, EMNLP 2025][graphjudge].

[hippo]: https://arxiv.org/html/2405.14831v1
[hippo2]: https://arxiv.org/html/2502.14802v1
[hippo-code]: https://github.com/OSU-NLP-Group/HippoRAG
[t2kg]: https://arxiv.org/html/2308.02357v1
[t2kg-code]: https://github.com/cenguix/Text2KGBench
[tiwari-code]: https://github.com/dice-group/ontology-aware-kg-construction
[tiwari-license]: https://github.com/dice-group/ontology-aware-kg-construction/blob/main/LICENSE
[tiwari-acceptance]: https://www.linkedin.com/posts/dice-research_dice-semantics2026-knowledgegraphs-activity-7475196720784576514-GxPA
[spires]: https://pmc.ncbi.nlm.nih.gov/articles/PMC10924283/
[ontogpt-code]: https://github.com/monarch-initiative/ontogpt
[edc]: https://aclanthology.org/2024.emnlp-main.548.pdf
[edc-code]: https://github.com/clear-nus/edc
[itext]: https://arxiv.org/html/2409.03284v1
[atom]: https://arxiv.org/html/2510.22590v1
[itext-code]: https://github.com/AuvaLab/itext2kg
[kggen]: https://proceedings.neurips.cc/paper_files/paper/2025/file/2b368455e832d2b1a60bcad8c4c6481f-Paper-Conference.pdf
[kggen-code]: https://github.com/stair-lab/kg-gen
[sac]: https://arxiv.org/html/2410.02811v1
[graphusion]: https://arxiv.org/html/2410.17600v1
[graphusion-code]: https://github.com/IreneZihuiLi/Graphusion
[docs2kg]: https://arxiv.org/html/2406.02962v1
[docs2kg-code]: https://github.com/AI4WA/Docs2KG
[typing]: https://arxiv.org/abs/2404.17000
[typing-code]: https://github.com/bradleypallen/evaluating-kg-class-memberships-using-llms
[zep]: https://arxiv.org/html/2501.13956v1
[graphiti-code]: https://github.com/getzep/graphiti
[ontolearner]: https://arxiv.org/html/2607.01977v1
[ontolearner-code]: https://github.com/sciknoworg/OntoLearner
[ollm]: https://arxiv.org/abs/2410.23584
[ollm-code]: https://github.com/andylolu2/ollm
[neon]: https://zenodo.org/records/11221931
[neon-extended]: https://www.semantic-web-journal.net/content/gpt-mistral-cross-domain-ontology-learning-neon-gpt-1
[neon-code]: https://github.com/NadeenAhmad/neon-gpt-extended
[ol24]: https://arxiv.org/html/2409.10146v1
[ol25]: https://www.tib-op.org/ojs/index.php/ocp/article/download/2913/2922
[ol25-site]: https://sites.google.com/view/llms4ol2025
[ol26]: https://sites.google.com/view/llms4ol2026
[ol26-announcement]: https://groups.google.com/g/llms4ol-challenge/c/_CR1z8s97mQ
[ol26-results]: https://sites.google.com/view/llms4ol2026/leaderboards
[autoschema]: https://arxiv.org/html/2505.23628v2
[autoschema-code]: https://github.com/HKUST-KnowComp/AutoSchemaKG
[semantics]: https://2026-eu.semantics.cc/
[skgi-program]: https://sites.google.com/view/skgi/program
[rapidfuzz]: https://rapidfuzz.github.io/RapidFuzz/
[rapidfuzz-license]: https://rapidfuzz.github.io/RapidFuzz/License.html
[neo4j]: https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html
[neo4j-api]: https://neo4j.com/docs/neo4j-graphrag-python/current/api.html
[nasty]: https://2023.eswc-conferences.org/wp-content/uploads/2023/05/paper_Heist_2023_NASTyLinker.pdf
[lettria]: https://ceur-ws.org/Vol-4041/paper3.pdf
[webnlg]: https://synalp.gitlabpages.inria.fr/webnlg-challenge/challenge_2017/
[redocred]: https://aclanthology.org/2022.emnlp-main.580/
[dissecting]: https://aclanthology.org/2026.tacl-1.29.pdf
[graphjudge]: https://aclanthology.org/2025.emnlp-main.554/

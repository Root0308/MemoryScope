---
name: memoryscope-evaluator
description: Evaluate MemoryScope datasets through the local Health, Import, and Evaluation APIs, compare BM25, Dense, and Hybrid metrics, and write cautious Markdown reports. Use for MemoryScope evaluation, metric explanation, or report requests, including explicit $memoryscope-evaluator calls; do not use to implement retrieval algorithms, change relevance labels, run unrelated benchmarks, or develop unrelated project features.
---

# MemoryScope Evaluator

Use MemoryScope's existing API as the only source of rankings and metrics. The bundled script handles deterministic API calls and report formatting; do not recreate BM25, Dense, RRF, cosine search, Recall, or MRR in the skill.

## Run the workflow

1. Work from the MemoryScope repository root. Read the maintained [README](../../../README.md), [API reference](../../../docs/api.md), and [data format](../../../docs/data-format.md) only when details beyond this workflow are needed.
2. Require exactly one input: a strict MemoryScope JSON file or an existing dataset ID. Also collect `k` (1-50), an output `.md` path, and an optional local backend URL.
3. Before any request that may initialize Dense retrieval, tell the user that the pinned public model can require a one-time download of about 480 MiB. Pass `--allow-model-download` only after confirmation; pass `--model-ready` when the user confirms the pinned revision is already cached. If neither condition is known, pause before importing or evaluating.
4. Run `scripts/run_evaluation.py`. It checks JSON syntax, restricts requests to localhost, checks Health, delegates schema validation to the Import API, and calls the Evaluation API. For example:

   ```text
   python .agents/skills/memoryscope-evaluator/scripts/run_evaluation.py --dataset-file examples/sample-dataset.json --k 10 --output evaluation-report.md --model-ready
   python .agents/skills/memoryscope-evaluator/scripts/run_evaluation.py --dataset-id <dataset-id> --k 5 --output evaluation-report.md --model-ready
   ```

5. Treat a nonzero exit as a stopped evaluation. Report the API error and do not create a substitute report. If an import succeeded before evaluation failed, state the returned dataset ID and leave it untouched.
6. Summarize the generated report without declaring a universal winner. Conclusions must remain descriptive of the supplied labels, cases, `k`, dataset, and machine.

## Boundaries

- Never modify dataset JSON, messages, `evaluation_cases`, or `relevant_memory_ids`; never delete or overwrite a dataset or database.
- Never upload conversation data or contact non-local hosts. The script rejects base URLs outside `localhost`, `127.0.0.1`, and `::1`.
- Never install dependencies or change MemoryScope source code to make an evaluation pass without explicit authorization.
- The script does not start or stop the backend. If the user authorizes Codex to start it separately, retain the process identity and stop only that process when finished.
- Do not overwrite an existing report unless the user explicitly requests it and `--overwrite` is passed.
- Explain that Recall@k and MRR@k depend on human `relevant_memory_ids`; a small local sample does not establish general retrieval quality or statistical significance. BM25 and Dense raw score scales remain incomparable, and Hybrid latency is RRF fusion time rather than an independent end-to-end retrieval time.

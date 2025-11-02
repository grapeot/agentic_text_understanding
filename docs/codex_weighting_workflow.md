# Weight Annotation Workflow

## Pipeline Overview
- **Chunking**: `src/offline/chunk_csv.py` splits a large CSV into overlapping segments while preserving the header. The current configuration uses 1,000-row chunks with 20-row overlaps and writes to `data/chunks_1000_20/`.
- **Weight tagging**: Each chunk is passed to Codex CLI, which appends an `information_weight` column using the prompt in `prompts/information_weight_prompt.txt`.
- **Aggregation**: `src/offline/aggregate_chunks.py` reconciles overlaps and averages duplicate rows back into a single weighted CSV.
- **Analysis**: `src/offline/analyze_weights.py` summarizes sender metrics and produces an interactive Plotly dashboard.

## Preparing Chunks
Activate the existing virtual environment before running Python:

```bash
source venv/bin/activate
python src/offline/chunk_csv.py AI生产力训练营__text_only.csv data/chunks_1000_20 --chunk-size 1000 --overlap 20
```

The script validates chunk/overlap settings and writes files named `chunk_XXXX.csv`.

## Codex CLI Basics
- `codex exec --help` lists global options. `--full-auto` selects `workspace-write` sandboxing with `on-failure` approvals.
- You can supply instructions as a positional argument or via stdin (use `-` as the argument). Example dry run that created `scratch/hello.py`:

```bash
codex exec --full-auto "Create a Python script at scratch/hello.py that prints 'Hello, world!' when executed. If the file already exists, overwrite it, and do not run the script."
```

Codex streams its thought process followed by a final status message. Files are edited directly in-place inside the repository.

## Prompt Template
`prompts/information_weight_prompt.txt` instructs Codex to:
- Append `information_weight` between 0.0 and 1.0 while reading messages carefully.
- Avoid regex or bulk search-and-replace; reason about each row manually.
- Abort if the column already exists to keep runs idempotent.
- Double-check the CSV structure before returning.

The template references `$TARGET_FILE`, which the runner script expands per chunk using `envsubst`.

## Parallel Runner Script (preview)
`src/offline/run_codex_weights.sh` will:
- Accept an optional directory argument (defaults to `data/chunks_1000_20`).
- Use `JOBS` (default 16) to control parallel `codex exec` invocations.
- Feed the prompt template to each run via stdin while setting `TARGET_FILE` to the chunk path relative to repo root.
- Skip files that already contain `information_weight` (Codex enforces this in the prompt).

### Selecting specific files
- `src/offline/find_unweighted_chunks.py` scans a directory and lists any CSVs missing `information_weight` values. Generate a manifest (newline-separated paths) and reuse it with the runner to avoid re-processing completed chunks.

```bash
source venv/bin/activate
python src/offline/find_unweighted_chunks.py data/chunks_1000_20 --manifest results/unweighted_chunks.txt
JOBS=16 src/offline/run_codex_weights.sh --manifest results/unweighted_chunks.txt
```

The runner checks each manifest path (absolute or relative) before launching Codex.

## Aggregating Weights Back Into One File
After Codex finishes annotating all chunks, merge them into a single CSV while averaging overlaps:

```bash
source venv/bin/activate
python src/offline/aggregate_chunks.py \
  --original AI生产力训练营__text_only.csv \
  --chunks data/chunks_1000_20 \
  --output results/weighted_messages.csv \
  --chunk-size 1000 \
  --overlap 20
```

The script assumes chunk filenames follow `chunk_XXXX.csv` and each row now includes `information_weight`. Overlapping regions (20 rows between chunks) are averaged automatically.

## Sender-Level Analysis & Visualization

Install Plotly once inside the virtual environment:

```bash
source venv/bin/activate
uv pip install plotly
```

Then generate summary tables and an HTML dashboard:

```bash
source venv/bin/activate
python src/offline/analyze_weights.py \
  --input results/weighted_messages.csv \
  --summary-output results/sender_weight_summary.csv \
  --html-output results/information_weight_dashboard.html \
  --top-k 20 \
  --min-messages 5
```

- `results/sender_weight_summary.csv` lists message counts and weight statistics per sender.
- `results/information_weight_dashboard.html` embeds two Plotly bar charts (top/bottom senders by average weight) with a minimalist, modern theme.

## Sample Data for Dry Runs
`data/samples/sample_100_rows.csv` contains the first 100 rows of the original chat log for quick tests. Use it to validate prompts and output parsing before launching the full batch.

Next steps include wiring the runner script, capturing Codex output snippets for inspection, and implementing the aggregation pass after weights are generated.

# Solo License — common workflows. Windows users: the raw commands each
# target runs are listed in the README under "Setup".

PYTHON ?= python

.PHONY: install seed run-api web test evidence benchmark taubench charts cfo clean

install:            ## Install runtime dependencies
	$(PYTHON) -m pip install -r requirements.txt

seed:               ## Rebuild the database to the demo-ready state
	$(PYTHON) -m sololicense.db.seed

run-api: seed       ## Seed, then launch the API on :8000
	$(PYTHON) -m uvicorn sololicense.api.app:app --port 8000

web:                ## Launch the React app on :5174 (proxies /api to :8000)
	npm --prefix frontend run dev

test:               ## Run the test suite
	$(PYTHON) -m pytest

evidence:           ## Generate the before/after evidence artifact
	$(PYTHON) -m scripts.generate_evidence

benchmark:          ## 50-run before/after benchmark -> evidence/benchmarks/benchmark.md
	$(PYTHON) -m scripts.benchmark

taubench:           ## Score the policies on tau-bench retail -> evidence/benchmarks/taubench.md
	$(PYTHON) -m scripts.taubench_eval

charts:             ## Redraw README charts from the latest benchmark
	$(PYTHON) -m scripts.readme_charts

cfo:                ## Print the cfo.ai financial model
	$(PYTHON) -m planning.cfo.model

clean:              ## Remove the runtime database
	$(PYTHON) -c "import pathlib,os; p=pathlib.Path('data/solo_license.db'); [os.remove(f) for f in p.parent.glob(p.name+'*') if f.exists()]"

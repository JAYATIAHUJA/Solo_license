# Solo License — common workflows. Windows users: the raw commands each
# target runs are listed in the README under "Setup".

PYTHON ?= python

.PHONY: install run-api web test coding-benchmark coding-demo cfo clean

install:            ## Install runtime dependencies
	$(PYTHON) -m pip install -r requirements.txt

run-api:            ## Launch the API on :8000 (demo sign-in enabled)
	SOLO_DEMO_MODE=$${SOLO_DEMO_MODE:-1} $(PYTHON) -m uvicorn sololicense.api.app:app --port 8000

web:                ## Launch the React app on :5174 (proxies /api to :8000)
	npm --prefix frontend run dev

test:               ## Run the test suite
	$(PYTHON) -m pytest

coding-benchmark:   ## Coding agent before/after replay -> evidence/benchmarks/coding_before_after.md
	$(PYTHON) -m scripts.coding_demo benchmark

coding-demo:        ## Copy demo/shop-api to ../shop-api-demo with the hooks installed
	$(PYTHON) -m scripts.coding_demo setup ../shop-api-demo

cfo:                ## Print the cfo.ai financial model for the coding agent
	$(PYTHON) -m planning.cfo.coding_model

clean:              ## Remove the runtime database
	$(PYTHON) -c "import pathlib,os; p=pathlib.Path('data/solo_license.db'); [os.remove(f) for f in p.parent.glob(p.name+'*') if f.exists()]"

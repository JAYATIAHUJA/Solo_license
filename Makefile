# Solo License — common workflows. Windows users: the raw commands each
# target runs are listed in the README under "Setup".

PYTHON ?= python

.PHONY: install seed run run-api test evidence cfo clean

install:            ## Install runtime dependencies
	$(PYTHON) -m pip install -r requirements.txt

seed:               ## Rebuild the database to the demo-ready state
	$(PYTHON) -m sololicense.db.seed

run: seed           ## Seed, then launch the live UI
	$(PYTHON) -m streamlit run app/streamlit_app.py

run-api: seed       ## Launch the React API adapter
	$(PYTHON) -m uvicorn app.api:app --reload

test:               ## Run the test suite
	$(PYTHON) -m pytest

evidence:           ## Generate the before/after evidence artifact
	$(PYTHON) -m scripts.generate_evidence

cfo:                ## Print the cfo.ai financial model
	$(PYTHON) -m cfo.model

clean:              ## Remove the runtime database
	$(PYTHON) -c "import pathlib,os; p=pathlib.Path('data/solo_license.db'); [os.remove(f) for f in p.parent.glob(p.name+'*') if f.exists()]"

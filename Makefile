PY ?= python
FAST ?=

.PHONY: setup test predictor bridge eval ui serve all

setup:
	$(PY) -m pip install -r requirements.txt
	cd dashboard/frontend && npm install

test:
	$(PY) -m pytest -q tests

predictor:
	$(PY) -m traffic.train_forecaster $(FAST)

bridge: predictor
	$(PY) -m bridge.train_ppo $(FAST)
	$(PY) -m bridge.train_ppo --no-forecast $(FAST)

eval:
	$(PY) scripts/run_eval.py $(FAST)

ui:
	cd dashboard/frontend && npx vite build

serve: ui
	$(PY) -m uvicorn dashboard.api:app --port 8000

all: test bridge eval ui

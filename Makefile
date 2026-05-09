.PHONY: install ingest normalize analytics process dashboard test clean

install:
	pip3 install -r requirements.txt

ingest:
	python3 -m src.ingest.fetcher

normalize:
	python3 -m src.transform.normalize

analytics:
	python3 -m src.analytics.arbitrage
	python3 -m src.analytics.plus_ev
	python3 -m src.analytics.line_movement

process:
	python3 -m src.transform.normalize
	python3 -m src.analytics.arbitrage
	python3 -m src.analytics.plus_ev
	python3 -m src.analytics.line_movement

dashboard:
	PYTHONPATH=. python3 -m streamlit run src/dashboard/app.py

test:
	python3 -m pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

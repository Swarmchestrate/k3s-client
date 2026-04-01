# Makefile for k3s-client dev and CI workflows

.PHONY: install test lint format check clean

install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	pip install -e .
	# Install Puccini TOSCA parser used by Sardou
	curl -LsSf https://astral.sh/uv/install.sh | sh
	wget https://github.com/Swarmchestrate/tosca/releases/download/v0.2.4/go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb && \
		sudo dpkg -i go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb || sudo apt --fix-broken install -y && \
		rm -f go-puccini_0.22.7-SNAPSHOT-3e85b40_linux_amd64.deb

test:
	PYTHONPATH=. pytest -q

lint:
	PYTHONPATH=. ruff check .

format:
	ruff format .

check: test lint

clean:
	rm -rf .pytest_cache .ruff_cache *.egg-info

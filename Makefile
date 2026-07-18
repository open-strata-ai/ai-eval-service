REPO    := ai-eval-service
VERSION := 1.4.0

.PHONY: build test lint run generate

build:   ## compile
	poetry build

test:    ## run tests
	pytest

lint:    ## static analysis
	ruff check .

run:     ## run locally
	uvicorn ai_eval_service.main:app --reload

generate: ## render doc/code skeletons
	python3 ../openstrata-meta/template/generate_app_skeletons.py

#Call tasks by typing: just taskName [args]
list:
	just --list

#Docker compose up
up: build
	docker compose up -d

#Docker compose build
build:
	docker compose build
	
#Docker compose down
down:
	docker compose down --remove-orphans

#Shell into container
shell: up
	docker compose exec pydelling bash

#Run static checks and tests
test: up
	docker compose exec pydelling python -m unittest discover

coverage: up
	docker compose exec pydelling python -m pytest pydelling/tests/ --cov=pydelling --cov-report=xml --cov-report=html --cov-report=term-missing --junitxml=report.xml -v --cov-report=term

#Run tests with coverage for CI (includes Cobertura format)
test-ci: up
	docker compose exec pydelling python -m pytest pydelling/tests/ --cov=pydelling --cov-report=xml --cov-report=html --cov-report=term-missing --junitxml=report.xml -v --tb=short

#Run tests with coverage for CI and copy reports to host
ci-test-reports: up
	sh -c 'docker compose exec -T pydelling python -m pytest pydelling/tests/ --cov=pydelling --cov-report=xml --cov-report=html --cov-report=term-missing --junitxml=report.xml -v --tb=short; status=$$?; docker compose cp pydelling:/app/coverage.xml ./coverage.xml || true; docker compose cp pydelling:/app/report.xml ./report.xml || true; docker compose cp pydelling:/app/htmlcov ./htmlcov || echo "HTML coverage report not found"; exit $$status'

#Build production image
compile: up
	## Build docker image
	#docker build --file Dockerfile --target production -t pydelling .
	## Generate Wheel package into dist folder
	docker compose exec pydelling uv build --format wheel

#Generate wheel package
wheel: up
	just patch
	just lock
	just compile
	
#yv lock
lock: up
	docker compose exec pydelling uv lock

#Prune docker system
prune:
	docker system prune -a -f

#Clean dist and test files/folders
clean: up
	docker compose exec pydelling rm -rf dist old_models output test_Timeseries* datasets


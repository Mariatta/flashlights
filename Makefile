
# This file's own name, read before local.mk joins MAKEFILE_LIST: the
# target listing below must read this file, not the last one included.
THIS_MAKEFILE := $(lastword $(MAKEFILE_LIST))
# Local overrides (git-ignored), such as PYTHON for the preset targets.
-include local.mk
PYTHON ?= python

default:
	@echo "Call a specific subcommand:"
	@echo
	@$(MAKE) -pRrq -f $(THIS_MAKEFILE) : 2>/dev/null\
	| awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}'\
	| sort\
	| egrep -v -e '^[^[:alnum:]]' -e '^$@$$'
	@echo
	@exit 1

.state/docker-build-web: Dockerfile requirements-app.txt requirements-dev.txt
	# Build our web container for this project.
	docker compose build --build-arg USER_ID=$(shell id -u) --build-arg GROUP_ID=$(shell id -g) web celery

	# Collect static assets
	docker compose run --rm web python manage.py collectstatic --noinput --clear

	# Create createcachetable
	docker compose run --rm web python manage.py createcachetable

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build-web

.state/db-migrated:
	make migrate
	mkdir -p .state && touch .state/db-migrated

.state/db-initialized: .state/docker-build-web .state/db-migrated
        # Do anything you might need to after the DB is built/migrated here (like fixtures)

	# Mark the state so we don't reload after first launch.
	mkdir -p .state
	touch .state/db-initialized

serve: .state/db-initialized
	docker compose up --remove-orphans -d

shell: .state/db-initialized
	docker compose run --rm web /bin/bash

dbshell: .state/db-initialized
	docker compose exec postgres psql -U flashlights flashlights

seed: .state/db-initialized
	# Sample accounts and data for local development (DEBUG only)
	docker compose run --rm web ./manage.py seed_dev_data

manage: .state/db-initialized
	# Run Django manage to accept arbitrary arguments
	docker compose run --rm web ./manage.py $(filter-out $@,$(MAKECMDGOALS))

migrations: .state/db-initialized
	# Run Django makemigrations
	docker compose run --rm web ./manage.py makemigrations

migrate: .state/docker-build-web
	# Run Django migrate
	docker compose run --rm web ./manage.py migrate $(filter-out $@,$(MAKECMDGOALS))

lint: .state/docker-build-web
	docker compose run --rm web isort --check-only .
	docker compose run --rm web black --check .
	docker compose run --rm web djlint . --check
	docker compose run --rm web djlint . --lint
	docker compose run --rm web flake8
	docker compose run --rm web python manage.py makemigrations --check --settings=portal.settings

reformat: .state/docker-build-web
	docker compose run --rm web isort .
	docker compose run --rm web black .
	docker compose run --rm web djlint . --reformat

test: .state/docker-build-web
	docker compose run --rm web pytest --cov --reuse-db --no-migrations --cov-fail-under=100 --cov-report html --cov-report term

check: test lint

create_translations: .state/docker-build-web
	docker compose run --rm web ./manage.py makemessages --locale $(LANG)

compile_translations: .state/docker-build-web
	docker compose run --rm web ./manage.py compilemessages

clean:
	docker compose down -v
	rm -rf staticroot
	rm -f .state/docker-build-web
	rm -f .state/db-initialized
	rm -f .state/db-migrated

.PHONY: default serve shell dbshell manage migrations migrate lint reformat test check create_translations compile_translations clean

# Demo presets: one database each, switched without reseeding. Runs on the
# host Python (set PYTHON in local.mk), not in the container. See
# scripts/preset.py and docs/developer/setup.md.
preset-list:
	$(PYTHON) scripts/preset.py list

preset:
	$(PYTHON) scripts/preset.py use $(PRESET)

preset-reset:
	$(PYTHON) scripts/preset.py reset $(PRESET)

preset-serve:
	$(PYTHON) scripts/preset.py serve $(PRESET)

preset-stop:
	$(PYTHON) scripts/preset.py stop

#!/usr/bin/make -f
# -*- makefile -*-
TOX := $(shell which tox)
PYTEST := $(shell which py.test)

.PHONY: help
help:
	@echo "===== Scrapy Makefile ====="
	@echo
	@echo "* $(MAKE) help .............. this overview"
	@echo
	@echo "* $(MAKE) tox ............... run tests for default environment (virtualenv)"
	@echo "* $(MAKE) tox-all ........... run tests for all environments (virtualenv)"
	@echo "* $(MAKE) test .............. run pytest (tests in system environment)"
	@echo "* $(MAKE) coverage .......... run coverage-report script"
	@echo

.PHONY: tox
tox:
	$(TOX)

.PHONY: tox-all
tox-all:
	$(TOX) -e ALL

.PHONY: test
test:
	$(PYTEST) tests

.PHONY: coverage
coverage:
	extras/coverage-report.sh

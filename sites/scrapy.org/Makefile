export PYTHONPATH =: .

SETTINGS = export DJANGO_SETTINGS_MODULE=scrapyorg.settings

.PHONY : all build docs tests

all : build tests

build : docs

docs :
	sphinx-build -a -b pickle docs/scrapy-docs docs/pickle

tests :
	$(SETTINGS); \
	django-admin.py test

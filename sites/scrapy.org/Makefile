export PYTHONPATH =: .

SETTINGS = export DJANGO_SETTINGS_MODULE=scrapyorg.settings

.PHONY : all build docs tests

all : build tests

build : docs

tests :
	$(SETTINGS); \
	django-admin.py test

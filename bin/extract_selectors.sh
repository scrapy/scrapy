#!/bin/bash

# startover
git checkout master

FILES=".gitignore \
        scrapy/selector \
        scrapy/utils/__init__.py \
        scrapy/utils/misc.py \
        scrapy/utils/python.py \
        scrapy/utils/decorator.py \
        tests/__init__.py \
        tests/test_selector.py \
        tests/test_selector_csstranslator.py \
        docs/_ext \
        docs/_static \
        docs/topics/selectors.rst \
        docs/utils \
        docs/Makefile \
        docs/README \
        docs/conf.py \
        docs/index.rst"

# start filtering
git filter-branch -f \
    --prune-empty \
    --tag-name-filter cat \
    --index-filter 'git rm --ignore-unmatch --cached -qr -- . && \
                    git reset -q $GIT_COMMIT -- '"$FILES" \
    -- \
    --all

# mv files to selectors/ dir without new commit
git filter-branch -f \
    --prune-empty \
    --tag-name-filter cat \
    --index-filter '
        git ls-files -s \
        | sed -e "s-scrapy/selector-selectors-" -e "s-scrapy-selectors-" \
        | GIT_INDEX_FILE=$GIT_INDEX_FILE.new git update-index --index-info \
        && if [ -f "$GIT_INDEX_FILE.new" ]; then \
            mv "$GIT_INDEX_FILE.new" "$GIT_INDEX_FILE"; \
        fi' \
    -- \
    --all

# now we can apply selectors patches (it's better to do them manually)
git remote add selectors git@github.com:umrashrf/selectors.git
git fetch selectors selectors-20150413
git checkout --track selectors/selectors-20150413
hashes=$(git log --reverse --pretty='%H' | tail -n 5)
# apply
git checkout master
for h in $hashes; do git cherry-pick $h; done

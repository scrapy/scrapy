# A Dockerfile to set up an image with most and latest Scrapy requirements
# suitable for development. 
# 
# The commands below are executed inside the Scrapy repository, that is,
# where this file is located.
#
# Building the image:
#
#     docker build -t myuser/scrapydev .
#
# Rebuilding the image from scratch:
#
#     docker build -no-cache -t myuser/scrapydev .
#
# Running Scrapy tests:
#
#     docker run -it myuser/scrapydev py.test scrapy tests
#
# Running Scrapy tests via tox:
#
#     docker run -it myuser/scrapydev tox -e py27
#
# Running a spider from a Scrapy project:
#
#     docker run -it -v /path/to/project:/app scrapy crawl myspider
#
FROM ubuntu:latest

ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update 
RUN apt-get install -y \
    libffi-dev \
    libjpeg8-dev \
    libssl-dev \
    libxml2-dev \
    libxslt-dev \
    python \
    python-dev \
    python-pip \
    zlib1g-dev

RUN pip install -U tox wheel codecov

ADD . /scrapy
RUN pip install -r /scrapy/requirements.txt
RUN pip install -r /scrapy/tests/requirements.txt
# Extras not included in the requirements.txt.
RUN pip install boto leveldb "Pillow!=3.0.0"
RUN pip install -e /scrapy

VOLUME /app
WORKDIR /app

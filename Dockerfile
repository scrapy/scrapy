# We will use Ubuntu for our image
FROM ubuntu:latest

# Updating Ubuntu packages
RUN apt-get update && yes|apt-get upgrade
RUN apt-get install -y emacs

# Adding wget and bzip2
RUN apt-get install -y wget bzip2

# Add sudo
RUN apt-get -y install sudo

# Add user ubuntu with no password, add to sudo group
RUN adduser --disabled-password --gecos '' ubuntu
RUN adduser ubuntu sudo
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
USER ubuntu
WORKDIR /home/ubuntu/
RUN chmod a+rwx /home/ubuntu/

# AnaRun conda installing
RUN wget https://repo.continuum.io/archive/Anaconda3-5.0.1-Linux-x86_64.sh
RUN bash Anaconda3-5.0.1-Linux-x86_64.sh -b
RUN rm Anaconda3-5.0.1-Linux-x86_64.sh

# Set path to conda
ENV PATH /home/ubuntu/anaconda3/bin:$PATH

# Installing dependencies
RUN conda install -c anaconda twisted -y
RUN conda install -c anaconda w3lib -y
RUN conda install -c anaconda parsel -y
RUN conda install -c conda-forge itemadapter -y
RUN conda install -c conda-forge pydispatcher -y
RUN conda install -c conda-forge protego -y
RUN conda install -c anaconda queuelib -y

COPY ./scrapy ./app/scrapy
COPY ./tutorial ./app/tutorial
COPY dockerrun.py ./app/dockerrun.py

# In order to build this image you should run the command below.
#   docker build . -t scrapy-image
# To run it:
#   docker run -it scrapy-image bash
# And it will open an interactive shell where you can cd to the app and run python dockerrun.py.
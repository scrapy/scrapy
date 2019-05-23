#!/bin/bash
cd
xcode-select --install
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
echo "export PATH=/usr/local/bin:/usr/local/sbin:$PATH" >> ~/.bashrc
source ~/.bashrc
brew install python
brew update; brew upgrade python
pip3 install --upgrade pip
pip install virtualenv 
sudo /usr/bin/easy_install virtualenv
pip3 install virtualenv
cd
virtualenv -p python3 NEW_ENV
source  ~/NEW_ENV/bin/activate
pip install Scrapy
scrapy shell 'scrapy.org'

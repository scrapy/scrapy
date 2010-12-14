@ECHO off

SET test=scrapy
SET PYTHONPATH=%CD%
IF NOT "%1" == "" SET test="%1"
trial --reporter=text %test%

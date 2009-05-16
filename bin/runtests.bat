@ECHO off

SET test="scrapy"
IF NOT "%1" == "" SET test="%1"

IF EXIST c:\python26\scripts\trial.py GOTO py26
IF EXIST c:\python25\scripts\trial.py GOTO py25

ECHO "Unable to run tests: trial command (included with Twisted) not found"
GOTO end

:py26
c:\python26\scripts\trial.py %test%
GOTO end

:py25
c:\python25\scripts\trial.py %test%

:end

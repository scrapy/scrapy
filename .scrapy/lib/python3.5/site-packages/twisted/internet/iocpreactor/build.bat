del iocpsupport\iocpsupport.c iocpsupport.pyd
del /f /s /q build
python setup.py build_ext -i -c mingw32


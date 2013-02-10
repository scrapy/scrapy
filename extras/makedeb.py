import sys, os, glob, shutil
from subprocess import check_call
from scrapy import version_info

def build(suffix):
    for ifn in glob.glob("debian/scrapy.*"):
        s = open(ifn).read()
        s = s.replace('SUFFIX', suffix)
        pre, suf = ifn.split('.', 1)
        ofn = "%s-%s.%s" % (pre, suffix, suf)
        with open(ofn, 'w') as of:
            of.write(s)

    for ifn in ['debian/control', 'debian/changelog']:
        s = open(ifn).read()
        s = s.replace('SUFFIX', suffix)
        with open(ifn, 'w') as of:
            of.write(s)

    check_call('debchange -m -D unstable --force-distribution -v $(python setup.py --version)+$(date +%s) "Automatic build"', \
        shell=True)
    check_call('debuild -us -uc -b', shell=True)

def clean(suffix):
    for f in glob.glob("debian/python-scrapy%s*" % suffix):
        if os.path.isdir(f):
            shutil.rmtree(f)
        else:
            os.remove(f)

def main():
    cmd = sys.argv[1]
    suffix = '%s.%s' % version_info[:2]
    if cmd == 'build':
        build(suffix)
    elif cmd == 'clean':
        clean(suffix)

if __name__ == '__main__':
    main()

import sys, os, glob
from subprocess import check_call

def build(suffix):
    for ifn in glob.glob("debian/scrapy.*") + glob.glob("debian/scrapyd.*"):
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
    for f in glob.glob("debian/scrapy-%s.*" % suffix) + \
            glob.glob("debian/scrapyd-%s.*" % suffix):
        os.remove(f)

def main():
    cmd = sys.argv[1]
    suffix = '%s.%s' % __import__('scrapy').version_info[:2]
    if cmd == 'build':
        build(suffix)
    elif cmd == 'clean':
        clean(suffix)

if __name__ == '__main__':
    main()

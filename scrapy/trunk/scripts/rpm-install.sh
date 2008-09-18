#! /bin/sh
#
# This file becomes the install section of the generated spec file.
#

# This is what dist.py normally does.
python2.5 setup.py install --root=${RPM_BUILD_ROOT} --record="INSTALLED_FILES"

cat << EOF >> INSTALLED_FILES
/usr/bin/*.py*
EOF

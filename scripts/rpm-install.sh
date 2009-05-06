#! /bin/sh
#
# This file becomes the install section of the generated spec file.
#

python setup.py install --root=${RPM_BUILD_ROOT} --record="INSTALLED_FILES"

cat << EOF >> INSTALLED_FILES
/usr/bin/*.py*
EOF

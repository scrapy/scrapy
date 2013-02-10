#!/bin/sh

# look for twisted trial command
if type trial >/dev/null 2>&1; then
    trial="trial"
elif [ -x /usr/lib/twisted/bin/trial ]; then
    trial="/usr/lib/twisted/bin/trial"
elif [ -x /usr/lib64/twisted/bin/trial ]; then
    trial="/usr/lib64/twisted/bin/trial"
else
    echo "Unable to run tests: trial command (included with Twisted) not found"
    exit 1
fi

# use vsftpd (if available) for testing ftp feed storage
if type vsftpd >/dev/null 2>&1; then
    vsftpd_conf=$(mktemp /tmp/vsftpd-XXXX)
    cat >$vsftpd_conf <<!
listen=YES
listen_port=2121
run_as_launching_user=YES
anonymous_enable=YES
write_enable=YES
anon_upload_enable=YES
anon_mkdir_write_enable=YES
anon_other_write_enable=YES
anon_umask=000
vsftpd_log_file=/dev/null
!
    ftproot=$(mktemp -d /tmp/feedtest-XXXX)
    chmod 755 $ftproot
    export FEEDTEST_FTP_URI="ftp://anonymous:test@localhost:2121$ftproot/path/to/file.txt"
    export FEEDTEST_FTP_PATH="$ftproot/path/to/file.txt"
    vsftpd $vsftpd_conf &
    vsftpd_pid=$!
fi

find . -name '*.py[co]' -delete
if [ $# -eq 0 ]; then
    $trial --reporter=text scrapy
else
    $trial "$@"
fi
exit_status=$?

# cleanup vsftpd stuff
[ -n "$vsftpd_pid" ] && kill $vsftpd_pid
[ -n "$ftproot" ] && rm -rf $ftproot $vsftpd_conf

exit $exit_status

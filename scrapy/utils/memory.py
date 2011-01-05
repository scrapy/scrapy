from __future__ import with_statement

import os
import sys
import struct

_vmvalue_scale = {'kB': 1024, 'mB': 1024*1024, 'KB': 1024, 'MB': 1024*1024}

def get_vmvalue_from_procfs(vmkey='VmSize', pid=None):
    """Return virtual memory value (in bytes) for the given pid using the /proc
    filesystem. If pid is not given, it default to the current process pid.
    Available keys are: VmSize, VmRSS (default), VmStk
    """
    if pid is None:
        pid = os.getpid()
    try:
        t = open('/proc/%d/status' % pid)
    except IOError:
        raise RuntimeError("/proc filesystem not supported")
    if sys.platform == "sunos5":
        return _vmvalue_solaris(vmkey, pid)
    else:
        v = t.read()
        t.close()
        # get vmkey line e.g. 'VmRSS:  9999  kB\n ...'
        i = v.index(vmkey + ':')
        v = v[i:].split(None, 3)  # whitespace
        if len(v) < 3:
            return 0  # invalid format?
        # convert Vm value to bytes
        return int(v[1]) * _vmvalue_scale[v[2]]

def procfs_supported():
    try:
        open('/proc/%d/status' % os.getpid())
    except IOError:
        return False
    else:
        return True

def _vmvalue_solaris(vmkey, pid):

     # Memory layout for struct psinfo.
     # http://docs.sun.com/app/docs/doc/816-5174/proc-4?l=en&a=view
    _psinfo_struct_format = (
        "10i"   # pr_flag [0] through pr_egid [9]
        "5L"    # pr_addr [10] through pr_ttyydev [14]
        "2H"    # pr_pctcpu [15] and pr_pctmem [16]
        "6l"    # pr_start [17-18] through pr_ctime [21-22]
        "16s"   # pr_fname [23]
        "80s"   # pr_psargs [24]
        "2i"    # pr_wstat[25] and pr_argc [26]
        "2L"    # pr_argv [27] and pr_envp [28]
        "b3x"   # pr_dmodel[29] and pr_pad2
        "7i"    # pr_taskid [30] through pr_filler
        "20i6l" # pr_lwp
        )
    psinfo_file = os.path.join("/proc", str(pid), "psinfo")
    with open(psinfo_file) as f:
        parts = struct.unpack(_psinfo_struct_format, f.read())

    vmkey_index = {
        'VmSize' : 11, # pr_size
        'VmRSS'  : 12, # pr_rssize
    }

    vm_in_kB = parts[vmkey_index[vmkey]]

    return vm_in_kB * 1024

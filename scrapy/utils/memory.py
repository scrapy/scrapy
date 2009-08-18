import os

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
    v = t.read()
    t.close()
    # get vmkey line e.g. 'VmRSS:  9999  kB\n ...'
    i = v.index(vmkey + ':')
    v = v[i:].split(None, 3)  # whitespace
    if len(v) < 3:
        return 0  # invalid format?
    # convert Vm value to bytes
    return int(v[1]) * _vmvalue_scale[v[2]]


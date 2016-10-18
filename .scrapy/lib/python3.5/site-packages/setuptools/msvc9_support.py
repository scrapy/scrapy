try:
    import distutils.msvc9compiler
except ImportError:
    pass

unpatched = dict()

def patch_for_specialized_compiler():
    """
    Patch functions in distutils.msvc9compiler to use the standalone compiler
    build for Python (Windows only). Fall back to original behavior when the
    standalone compiler is not available.
    """
    if 'distutils' not in globals():
        # The module isn't available to be patched
        return

    if unpatched:
        # Already patched
        return

    unpatched.update(vars(distutils.msvc9compiler))

    distutils.msvc9compiler.find_vcvarsall = find_vcvarsall
    distutils.msvc9compiler.query_vcvarsall = query_vcvarsall

def find_vcvarsall(version):
    Reg = distutils.msvc9compiler.Reg
    VC_BASE = r'Software\%sMicrosoft\DevDiv\VCForPython\%0.1f'
    key = VC_BASE % ('', version)
    try:
        # Per-user installs register the compiler path here
        productdir = Reg.get_value(key, "installdir")
    except KeyError:
        try:
            # All-user installs on a 64-bit system register here
            key = VC_BASE % ('Wow6432Node\\', version)
            productdir = Reg.get_value(key, "installdir")
        except KeyError:
            productdir = None

    if productdir:
        import os
        vcvarsall = os.path.join(productdir, "vcvarsall.bat")
        if os.path.isfile(vcvarsall):
            return vcvarsall

    return unpatched['find_vcvarsall'](version)

def query_vcvarsall(version, *args, **kwargs):
    try:
        return unpatched['query_vcvarsall'](version, *args, **kwargs)
    except distutils.errors.DistutilsPlatformError as exc:
        if exc and "vcvarsall.bat" in exc.args[0]:
            message = 'Microsoft Visual C++ %0.1f is required (%s).' % (version, exc.args[0])
            if int(version) == 9:
                # This redirection link is maintained by Microsoft.
                # Contact vspython@microsoft.com if it needs updating.
                raise distutils.errors.DistutilsPlatformError(
                    message + ' Get it from http://aka.ms/vcpython27'
                )
            raise distutils.errors.DistutilsPlatformError(message)
        raise

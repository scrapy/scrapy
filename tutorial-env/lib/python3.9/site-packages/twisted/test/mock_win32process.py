# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
This is a mock win32process module.

The purpose of this module is mock process creation for the PID test.

CreateProcess(...) will spawn a process, and always return a PID of 42.
"""

import win32process  # type: ignore[import]

GetExitCodeProcess = win32process.GetExitCodeProcess
STARTUPINFO = win32process.STARTUPINFO

STARTF_USESTDHANDLES = win32process.STARTF_USESTDHANDLES


def CreateProcess(
    appName,
    cmdline,
    procSecurity,
    threadSecurity,
    inheritHandles,
    newEnvironment,
    env,
    workingDir,
    startupInfo,
):
    """
    This function mocks the generated pid aspect of the win32.CreateProcess
    function.
      - the true win32process.CreateProcess is called
      - return values are harvested in a tuple.
      - all return values from createProcess are passed back to the calling
        function except for the pid, the returned pid is hardcoded to 42
    """

    hProcess, hThread, dwPid, dwTid = win32process.CreateProcess(
        appName,
        cmdline,
        procSecurity,
        threadSecurity,
        inheritHandles,
        newEnvironment,
        env,
        workingDir,
        startupInfo,
    )
    dwPid = 42
    return (hProcess, hThread, dwPid, dwTid)

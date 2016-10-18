
# A program which exits after starting a child which inherits its
# stdin/stdout/stderr and keeps them open until stdin is closed.

import sys, os

def grandchild():
    sys.stdout.write('grandchild started')
    sys.stdout.flush()
    sys.stdin.read()

def main():
    if sys.argv[1] == 'child':
        if sys.argv[2] == 'windows':
            import win32api as api, win32process as proc
            info = proc.STARTUPINFO()
            info.hStdInput = api.GetStdHandle(api.STD_INPUT_HANDLE)
            info.hStdOutput = api.GetStdHandle(api.STD_OUTPUT_HANDLE)
            info.hStdError = api.GetStdHandle(api.STD_ERROR_HANDLE)
            python = sys.executable
            scriptDir = os.path.dirname(__file__)
            scriptName = os.path.basename(__file__)
            proc.CreateProcess(
                None, " ".join((python, scriptName, "grandchild")), None,
                None, 1, 0, os.environ, scriptDir, info)
        else:
            if os.fork() == 0:
                grandchild()
    else:
        grandchild()

if __name__ == '__main__':
    main()

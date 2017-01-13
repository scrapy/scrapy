# -*- test-case-name: twisted.conch.test.test_ckeygen -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation module for the `ckeygen` command.
"""

from __future__ import print_function

import sys, os, getpass, socket
if getpass.getpass == getpass.unix_getpass:
    try:
        import termios # hack around broken termios
        termios.tcgetattr, termios.tcsetattr
    except (ImportError, AttributeError):
        sys.modules['termios'] = None
        reload(getpass)

from twisted.conch.ssh import keys
from twisted.python import failure, filepath, log, usage



class GeneralOptions(usage.Options):
    synopsis = """Usage:    ckeygen [options]
 """

    longdesc = "ckeygen manipulates public/private keys in various ways."

    optParameters = [['bits', 'b', 1024, 'Number of bits in the key to create.'],
                     ['filename', 'f', None, 'Filename of the key file.'],
                     ['type', 't', None, 'Specify type of key to create.'],
                     ['comment', 'C', None, 'Provide new comment.'],
                     ['newpass', 'N', None, 'Provide new passphrase.'],
                     ['pass', 'P', None, 'Provide old passphrase.']]

    optFlags = [['fingerprint', 'l', 'Show fingerprint of key file.'],
                ['changepass', 'p', 'Change passphrase of private key file.'],
                ['quiet', 'q', 'Quiet.'],
                ['no-passphrase', None, "Create the key with no passphrase."],
                ['showpub', 'y', 'Read private key file and print public key.']]

    compData = usage.Completions(
        optActions={"type": usage.CompleteList(["rsa", "dsa"])})



def run():
    options = GeneralOptions()
    try:
        options.parseOptions(sys.argv[1:])
    except usage.UsageError as u:
        print('ERROR: %s' % u)
        options.opt_help()
        sys.exit(1)
    log.discardLogs()
    log.deferr = handleError # HACK
    if options['type']:
        if options['type'] == 'rsa':
            generateRSAkey(options)
        elif options['type'] == 'dsa':
            generateDSAkey(options)
        else:
            sys.exit('Key type was %s, must be one of: rsa, dsa' % options['type'])
    elif options['fingerprint']:
        printFingerprint(options)
    elif options['changepass']:
        changePassPhrase(options)
    elif options['showpub']:
        displayPublicKey(options)
    else:
        options.opt_help()
        sys.exit(1)



def handleError():
    global exitStatus
    exitStatus = 2
    log.err(failure.Failure())
    raise



def generateRSAkey(options):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa

    print('Generating public/private rsa key pair.')
    keyPrimitive = rsa.generate_private_key(
        key_size=int(options['bits']),
        public_exponent=65537,
        backend=default_backend(),
        )
    key = keys.Key(keyPrimitive)
    _saveKey(key, options)



def generateDSAkey(options):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import dsa

    print('Generating public/private dsa key pair.')
    keyPrimitive = dsa.generate_private_key(
        key_size=int(options['bits']),
        backed=default_backend(),
        )
    key = keys.Key(keyPrimitive)
    _saveKey(key, options)



def printFingerprint(options):
    if not options['filename']:
        filename = os.path.expanduser('~/.ssh/id_rsa')
        options['filename'] = raw_input('Enter file in which the key is (%s): ' % filename)
    if os.path.exists(options['filename']+'.pub'):
        options['filename'] += '.pub'
    try:
        key = keys.Key.fromFile(options['filename'])
        print('%s %s %s' % (
            key.size(),
            key.fingerprint(),
            os.path.basename(options['filename'])))
    except:
        sys.exit('bad key')



def changePassPhrase(options):
    if not options['filename']:
        filename = os.path.expanduser('~/.ssh/id_rsa')
        options['filename'] = raw_input(
            'Enter file in which the key is (%s): ' % filename)
    try:
        key = keys.Key.fromFile(options['filename'])
    except keys.EncryptedKeyError as e:
        # Raised if password not supplied for an encrypted key
        if not options.get('pass'):
            options['pass'] = getpass.getpass('Enter old passphrase: ')
        try:
            key = keys.Key.fromFile(
                options['filename'], passphrase=options['pass'])
        except keys.BadKeyError:
            sys.exit('Could not change passphrase: old passphrase error')
        except keys.EncryptedKeyError as e:
            sys.exit('Could not change passphrase: %s' % (e,))
    except keys.BadKeyError as e:
        sys.exit('Could not change passphrase: %s' % (e,))

    if not options.get('newpass'):
        while 1:
            p1 = getpass.getpass(
                'Enter new passphrase (empty for no passphrase): ')
            p2 = getpass.getpass('Enter same passphrase again: ')
            if p1 == p2:
                break
            print('Passphrases do not match.  Try again.')
        options['newpass'] = p1

    try:
        newkeydata = key.toString('openssh', extra=options['newpass'])
    except Exception as e:
        sys.exit('Could not change passphrase: %s' % (e,))

    try:
        keys.Key.fromString(newkeydata, passphrase=options['newpass'])
    except (keys.EncryptedKeyError, keys.BadKeyError) as e:
        sys.exit('Could not change passphrase: %s' % (e,))

    with open(options['filename'], 'w') as fd:
        fd.write(newkeydata)

    print('Your identification has been saved with the new passphrase.')



def displayPublicKey(options):
    if not options['filename']:
        filename = os.path.expanduser('~/.ssh/id_rsa')
        options['filename'] = raw_input('Enter file in which the key is (%s): ' % filename)
    try:
        key = keys.Key.fromFile(options['filename'])
    except keys.EncryptedKeyError:
        if not options.get('pass'):
            options['pass'] = getpass.getpass('Enter passphrase: ')
        key = keys.Key.fromFile(
            options['filename'], passphrase = options['pass'])
    print(key.public().toString('openssh'))



def _saveKey(key, options):
    """
    Persist a SSH key on local filesystem.

    @param key: Key which is persisted on local filesystem.
    @type key: C{keys.Key} implementation.

    @param options:
    @type options: L{dict}
    """
    keyTypeName = key.type().lower()
    if not options['filename']:
        defaultPath = os.path.expanduser(u'~/.ssh/id_%s' % (keyTypeName,))
        newPath = raw_input(
            'Enter file in which to save the key (%s): ' % (defaultPath,))

        options['filename'] = newPath.strip() or defaultPath

    if os.path.exists(options['filename']):
        print('%s already exists.' % (options['filename'],))
        yn = raw_input('Overwrite (y/n)? ')
        if yn[0].lower() != 'y':
            sys.exit()

    if options.get('no-passphrase'):
        options['pass'] = b''
    elif not options['pass']:
        while 1:
            p1 = getpass.getpass('Enter passphrase (empty for no passphrase): ')
            p2 = getpass.getpass('Enter same passphrase again: ')
            if p1 == p2:
                break
            print('Passphrases do not match.  Try again.')
        options['pass'] = p1

    comment = '%s@%s' % (getpass.getuser(), socket.gethostname())

    filepath.FilePath(options['filename']).setContent(
        key.toString('openssh', options['pass']))
    os.chmod(options['filename'], 33152)

    filepath.FilePath(options['filename'] + '.pub').setContent(
        key.public().toString('openssh', comment))

    print('Your identification has been saved in %s' % (options['filename'],))
    print('Your public key has been saved in %s.pub' % (options['filename'],))
    print('The key fingerprint is:')
    print(key.fingerprint())



if __name__ == '__main__':
    run()

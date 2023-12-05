# -*- test-case-name: twisted.conch.test.test_ckeygen -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Implementation module for the `ckeygen` command.
"""


import getpass
import os
import socket
import sys
from functools import wraps
from imp import reload

from twisted.conch.ssh import keys
from twisted.python import failure, filepath, log, usage

if getpass.getpass == getpass.unix_getpass:  # type: ignore[attr-defined]
    try:
        import termios  # hack around broken termios

        termios.tcgetattr, termios.tcsetattr
    except (ImportError, AttributeError):
        sys.modules["termios"] = None  # type: ignore[assignment]
        reload(getpass)

supportedKeyTypes = dict()


def _keyGenerator(keyType):
    def assignkeygenerator(keygenerator):
        @wraps(keygenerator)
        def wrapper(*args, **kwargs):
            return keygenerator(*args, **kwargs)

        supportedKeyTypes[keyType] = wrapper
        return wrapper

    return assignkeygenerator


class GeneralOptions(usage.Options):
    synopsis = """Usage:    ckeygen [options]
 """

    longdesc = "ckeygen manipulates public/private keys in various ways."

    optParameters = [
        ["bits", "b", None, "Number of bits in the key to create."],
        ["filename", "f", None, "Filename of the key file."],
        ["type", "t", None, "Specify type of key to create."],
        ["comment", "C", None, "Provide new comment."],
        ["newpass", "N", None, "Provide new passphrase."],
        ["pass", "P", None, "Provide old passphrase."],
        ["format", "o", "sha256-base64", "Fingerprint format of key file."],
        [
            "private-key-subtype",
            None,
            None,
            'OpenSSH private key subtype to write ("PEM" or "v1").',
        ],
    ]

    optFlags = [
        ["fingerprint", "l", "Show fingerprint of key file."],
        ["changepass", "p", "Change passphrase of private key file."],
        ["quiet", "q", "Quiet."],
        ["no-passphrase", None, "Create the key with no passphrase."],
        ["showpub", "y", "Read private key file and print public key."],
    ]

    compData = usage.Completions(
        optActions={
            "type": usage.CompleteList(list(supportedKeyTypes.keys())),
            "private-key-subtype": usage.CompleteList(["PEM", "v1"]),
        }
    )


def run():
    options = GeneralOptions()
    try:
        options.parseOptions(sys.argv[1:])
    except usage.UsageError as u:
        print("ERROR: %s" % u)
        options.opt_help()
        sys.exit(1)
    log.discardLogs()
    log.deferr = handleError  # HACK
    if options["type"]:
        if options["type"].lower() in supportedKeyTypes:
            print("Generating public/private %s key pair." % (options["type"]))
            supportedKeyTypes[options["type"].lower()](options)
        else:
            sys.exit(
                "Key type was %s, must be one of %s"
                % (options["type"], ", ".join(supportedKeyTypes.keys()))
            )
    elif options["fingerprint"]:
        printFingerprint(options)
    elif options["changepass"]:
        changePassPhrase(options)
    elif options["showpub"]:
        displayPublicKey(options)
    else:
        options.opt_help()
        sys.exit(1)


def enumrepresentation(options):
    if options["format"] == "md5-hex":
        options["format"] = keys.FingerprintFormats.MD5_HEX
        return options
    elif options["format"] == "sha256-base64":
        options["format"] = keys.FingerprintFormats.SHA256_BASE64
        return options
    else:
        raise keys.BadFingerPrintFormat(
            "Unsupported fingerprint format: {}".format(options["format"])
        )


def handleError():
    global exitStatus
    exitStatus = 2
    log.err(failure.Failure())
    raise


@_keyGenerator("rsa")
def generateRSAkey(options):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa

    if not options["bits"]:
        options["bits"] = 2048
    keyPrimitive = rsa.generate_private_key(
        key_size=int(options["bits"]),
        public_exponent=65537,
        backend=default_backend(),
    )
    key = keys.Key(keyPrimitive)
    _saveKey(key, options)


@_keyGenerator("dsa")
def generateDSAkey(options):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import dsa

    if not options["bits"]:
        options["bits"] = 1024
    keyPrimitive = dsa.generate_private_key(
        key_size=int(options["bits"]),
        backend=default_backend(),
    )
    key = keys.Key(keyPrimitive)
    _saveKey(key, options)


@_keyGenerator("ecdsa")
def generateECDSAkey(options):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import ec

    if not options["bits"]:
        options["bits"] = 256
    # OpenSSH supports only mandatory sections of RFC5656.
    # See https://www.openssh.com/txt/release-5.7
    curve = b"ecdsa-sha2-nistp" + str(options["bits"]).encode("ascii")
    keyPrimitive = ec.generate_private_key(
        curve=keys._curveTable[curve], backend=default_backend()
    )
    key = keys.Key(keyPrimitive)
    _saveKey(key, options)


@_keyGenerator("ed25519")
def generateEd25519key(options):
    keyPrimitive = keys.Ed25519PrivateKey.generate()
    key = keys.Key(keyPrimitive)
    _saveKey(key, options)


def _defaultPrivateKeySubtype(keyType):
    """
    Return a reasonable default private key subtype for a given key type.

    @type keyType: L{str}
    @param keyType: A key type, as returned by
        L{twisted.conch.ssh.keys.Key.type}.

    @rtype: L{str}
    @return: A private OpenSSH key subtype (C{'PEM'} or C{'v1'}).
    """
    if keyType == "Ed25519":
        # No PEM format is defined for Ed25519 keys.
        return "v1"
    else:
        return "PEM"


def printFingerprint(options):
    if not options["filename"]:
        filename = os.path.expanduser("~/.ssh/id_rsa")
        options["filename"] = input("Enter file in which the key is (%s): " % filename)
    if os.path.exists(options["filename"] + ".pub"):
        options["filename"] += ".pub"
    options = enumrepresentation(options)
    try:
        key = keys.Key.fromFile(options["filename"])
        print(
            "%s %s %s"
            % (
                key.size(),
                key.fingerprint(options["format"]),
                os.path.basename(options["filename"]),
            )
        )
    except keys.BadKeyError:
        sys.exit("bad key")


def changePassPhrase(options):
    if not options["filename"]:
        filename = os.path.expanduser("~/.ssh/id_rsa")
        options["filename"] = input("Enter file in which the key is (%s): " % filename)
    try:
        key = keys.Key.fromFile(options["filename"])
    except keys.EncryptedKeyError:
        # Raised if password not supplied for an encrypted key
        if not options.get("pass"):
            options["pass"] = getpass.getpass("Enter old passphrase: ")
        try:
            key = keys.Key.fromFile(options["filename"], passphrase=options["pass"])
        except keys.BadKeyError:
            sys.exit("Could not change passphrase: old passphrase error")
        except keys.EncryptedKeyError as e:
            sys.exit(f"Could not change passphrase: {e}")
    except keys.BadKeyError as e:
        sys.exit(f"Could not change passphrase: {e}")

    if not options.get("newpass"):
        while 1:
            p1 = getpass.getpass("Enter new passphrase (empty for no passphrase): ")
            p2 = getpass.getpass("Enter same passphrase again: ")
            if p1 == p2:
                break
            print("Passphrases do not match.  Try again.")
        options["newpass"] = p1

    if options.get("private-key-subtype") is None:
        options["private-key-subtype"] = _defaultPrivateKeySubtype(key.type())

    try:
        newkeydata = key.toString(
            "openssh",
            subtype=options["private-key-subtype"],
            passphrase=options["newpass"],
        )
    except Exception as e:
        sys.exit(f"Could not change passphrase: {e}")

    try:
        keys.Key.fromString(newkeydata, passphrase=options["newpass"])
    except (keys.EncryptedKeyError, keys.BadKeyError) as e:
        sys.exit(f"Could not change passphrase: {e}")

    with open(options["filename"], "wb") as fd:
        fd.write(newkeydata)

    print("Your identification has been saved with the new passphrase.")


def displayPublicKey(options):
    if not options["filename"]:
        filename = os.path.expanduser("~/.ssh/id_rsa")
        options["filename"] = input("Enter file in which the key is (%s): " % filename)
    try:
        key = keys.Key.fromFile(options["filename"])
    except keys.EncryptedKeyError:
        if not options.get("pass"):
            options["pass"] = getpass.getpass("Enter passphrase: ")
        key = keys.Key.fromFile(options["filename"], passphrase=options["pass"])
    displayKey = key.public().toString("openssh").decode("ascii")
    print(displayKey)


def _inputSaveFile(prompt: str) -> str:
    """
    Ask the user where to save the key.

    This needs to be a separate function so the unit test can patch it.
    """
    return input(prompt)


def _saveKey(key, options):
    """
    Persist a SSH key on local filesystem.

    @param key: Key which is persisted on local filesystem.
    @type key: C{keys.Key} implementation.

    @param options:
    @type options: L{dict}
    """
    KeyTypeMapping = {"EC": "ecdsa", "Ed25519": "ed25519", "RSA": "rsa", "DSA": "dsa"}
    keyTypeName = KeyTypeMapping[key.type()]
    if not options["filename"]:
        defaultPath = os.path.expanduser(f"~/.ssh/id_{keyTypeName}")
        newPath = _inputSaveFile(
            f"Enter file in which to save the key ({defaultPath}): "
        )

        options["filename"] = newPath.strip() or defaultPath

    if os.path.exists(options["filename"]):
        print("{} already exists.".format(options["filename"]))
        yn = input("Overwrite (y/n)? ")
        if yn[0].lower() != "y":
            sys.exit()

    if options.get("no-passphrase"):
        options["pass"] = b""
    elif not options["pass"]:
        while 1:
            p1 = getpass.getpass("Enter passphrase (empty for no passphrase): ")
            p2 = getpass.getpass("Enter same passphrase again: ")
            if p1 == p2:
                break
            print("Passphrases do not match.  Try again.")
        options["pass"] = p1

    if options.get("private-key-subtype") is None:
        options["private-key-subtype"] = _defaultPrivateKeySubtype(key.type())

    comment = f"{getpass.getuser()}@{socket.gethostname()}"

    filepath.FilePath(options["filename"]).setContent(
        key.toString(
            "openssh",
            subtype=options["private-key-subtype"],
            passphrase=options["pass"],
        )
    )
    os.chmod(options["filename"], 33152)

    filepath.FilePath(options["filename"] + ".pub").setContent(
        key.public().toString("openssh", comment=comment)
    )
    options = enumrepresentation(options)

    print("Your identification has been saved in {}".format(options["filename"]))
    print("Your public key has been saved in {}.pub".format(options["filename"]))
    print("The key fingerprint in {} is:".format(options["format"]))
    print(key.fingerprint(options["format"]))


if __name__ == "__main__":
    run()

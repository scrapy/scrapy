# coding: utf-8

from inspect import getsource
from datetime import datetime

from OpenSSL.crypto import FILETYPE_PEM, TYPE_RSA, X509, PKey, dump_privatekey, dump_certificate

key = PKey()
key.generate_key(TYPE_RSA, 2048)

cert = X509()
issuer = cert.get_issuer()
subject = cert.get_subject()

for dn in [issuer, subject]:
    dn.C = b"TR"
    dn.ST = "Çorum".encode("utf-8")
    dn.L = "Başmakçı".encode("utf-8")
    dn.CN = b"localhost"
    dn.O = b"Twisted Matrix Labs"
    dn.OU = b"Automated Testing Authority"
    dn.emailAddress = b"security@twistedmatrix.com"

cert.set_serial_number(datetime.now().toordinal())
cert.gmtime_adj_notBefore(0)
cert.gmtime_adj_notAfter(60 * 60 * 24 * 365 * 100)

cert.set_pubkey(key)
cert.sign(key, "sha256")

import __main__
source = getsource(__main__)
source = source.split("\n" + "-" * 5)[0].rsplit("\n", 1)[0]
with open("server.pem", "w") as fObj:
    fObj.write(source)
    fObj.write("\n")
    fObj.write("'''\n")
    fObj.write(dump_privatekey(FILETYPE_PEM, key).decode("ascii"))
    fObj.write(dump_certificate(FILETYPE_PEM, cert).decode("ascii"))
    fObj.write("'''\n")
with open(b"key.pem.no_trailing_newline", "w") as fObj:
    fObj.write(dump_privatekey(FILETYPE_PEM, key).decode("ascii").rstrip('\n'))
with open(b"cert.pem.no_trailing_newline", "w") as fObj:
    fObj.write(dump_certificate(FILETYPE_PEM, cert).decode("ascii").rstrip('\n'))
'''
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC9Gk1skmQfONi+
GdM2Rwb6a/2weSX7eM3MwT3vXYr+0dx9ScWERILTNkLGrvfslHKdUE7hBDKjtuj6
KtAIrVjeDDMD6Ue77EcbL3QEO1QZeBjJ3hQbaB447PhE1wwgEsWndPMcDDVm93sO
DELNrzWMLhabgCJ5cJYo5RQs7IvVtE36KaoSgfC9rTP8Lva+MW5wNeHn2f0hDlUF
8jLuo1W+eDb9CHV7vwL19DZ3w74UkQ3RnfNDnZzVhsNI4YGaSBGtOHY3ioDspGQZ
qHHfCSTjjMwq3ddEkPd7iNu4N5KUamnH69A0JfRODC8tXjFG9/WFROhYZkUQRhXk
gRd39Yy9AgMBAAECggEAIvGt1f7VRpm8H6DpEVIdvX/gMNCqTqZ7rTcWaVmpWj5Q
lsxflfoNDNetjkZ95PdnmJ9i/BzI+MzPj48Cw1+5GMs7UCE3EshuOV1S/Ic0GsLB
HeiOYaQjVZSgqiPtBy5A3Rl05T1yTtUzpZxpadXTONS5c8HBXRyLewId8NFDY9ls
76PYRq4ui7QGOmXw7VAVzg/7RxcupuSkecE7472Ek1jtEdRdplBga/XE5/+FZhrr
NyAdVo/1VD8zpaenWiBgfqJTVc/VRBaE0kLa777E++ruqGGz/c5cQPOWzEp0vPbi
kXz16X2TQDeTe6QfBBYjzD2+LyJh2TXfRtEn56MtJwKBgQDaTzHFOoiPS0+JpOBH
yW2gIFigEH70Hi++m0okmewGLTGrjOsIVWx8u5QFMANEYXeXIT7sM1eyONYjtxNC
gpeLyyN9zTyLPWdx3CzNodY2Dg/irTZtPQp7/efAHcn7kW8V0OxCGTyXAzdhKXmN
thN9KMk6peQMU8L4FqypNznFrwKBgQDdwD0NBxqNk3/Q/qih2EJUOO7uuPAZnTJf
neRnY4Pc94ticdQbd03ZArP3ybl9wWy+Ri9D+I9P753Hyfb7BSKwwIyYRgxSjGU/
wqcmv0V/mSY7N4eCDaXqEjdovaZ76d3L60FPH5rJbn7yHZBYWaSqXgk0HDYUmQwg
huPLNu8bUwKBgQCH/rGohbAwY9/mhRlaXva1u7C59czAUlW3zZFAf8pyhpDcp2p6
xIxSn5+0I5bFcFpJgWJrTgihc5qioReUZTn20dMIOWQv8U6RtXELoHeLMPNgaDrx
jgcL+r32BhifaJfk5UNoYcRG5rAHDQk16Gj3nQLOUC1iKIPafHWO7GJG7QKBgQCj
yVfOhY6xP17K6S14zRjAyISCQorlAFyyjxai3rgIv7Zt8hFucAJJ5Vs0DAU7w2Ak
cgZ7N93ydtOdO6l24uYqky3FUwfK+PPX0lhPoDse8elxF6S5BIeliervLBUJtUUj
VxIX9QoI+do9zmRNPXkIdQhrOuMe96Qjaj5aXKrjDQKBgBS2LGghCFgqaxtHeIpl
RLOnpxLaiitGH412O6VKHkkXaNYEOlbtFVlPuE1zHeyIvLQb666lW/w0+HMmfMTU
SQI2gIndUb6pMzLjZUrCyYz618EoAmhx6+VnbRSY+iSEIdYqx6VBl0HY9RWJa18H
4LPzH6dfRnKf2jCer3DtWALD
-----END PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
MIID6DCCAtACAwtEVjANBgkqhkiG9w0BAQsFADCBtzELMAkGA1UEBhMCVFIxDzAN
BgNVBAgMBsOHb3J1bTEUMBIGA1UEBwwLQmHFn21ha8OnxLExEjAQBgNVBAMMCWxv
Y2FsaG9zdDEcMBoGA1UECgwTVHdpc3RlZCBNYXRyaXggTGFiczEkMCIGA1UECwwb
QXV0b21hdGVkIFRlc3RpbmcgQXV0aG9yaXR5MSkwJwYJKoZIhvcNAQkBFhpzZWN1
cml0eUB0d2lzdGVkbWF0cml4LmNvbTAgFw0yMjA4MjMyMzUyNTJaGA8yMTIyMDcz
MDIzNTI1MlowgbcxCzAJBgNVBAYTAlRSMQ8wDQYDVQQIDAbDh29ydW0xFDASBgNV
BAcMC0JhxZ9tYWvDp8SxMRIwEAYDVQQDDAlsb2NhbGhvc3QxHDAaBgNVBAoME1R3
aXN0ZWQgTWF0cml4IExhYnMxJDAiBgNVBAsMG0F1dG9tYXRlZCBUZXN0aW5nIEF1
dGhvcml0eTEpMCcGCSqGSIb3DQEJARYac2VjdXJpdHlAdHdpc3RlZG1hdHJpeC5j
b20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC9Gk1skmQfONi+GdM2
Rwb6a/2weSX7eM3MwT3vXYr+0dx9ScWERILTNkLGrvfslHKdUE7hBDKjtuj6KtAI
rVjeDDMD6Ue77EcbL3QEO1QZeBjJ3hQbaB447PhE1wwgEsWndPMcDDVm93sODELN
rzWMLhabgCJ5cJYo5RQs7IvVtE36KaoSgfC9rTP8Lva+MW5wNeHn2f0hDlUF8jLu
o1W+eDb9CHV7vwL19DZ3w74UkQ3RnfNDnZzVhsNI4YGaSBGtOHY3ioDspGQZqHHf
CSTjjMwq3ddEkPd7iNu4N5KUamnH69A0JfRODC8tXjFG9/WFROhYZkUQRhXkgRd3
9Yy9AgMBAAEwDQYJKoZIhvcNAQELBQADggEBABuOxiDnfrjQjbP4ZWrDj+doK8Zk
CUwtyM3gFVF1LBZxBCxVa6hzD2N7/1o0+KHjmiGks7SnXb6aG2nEqypciZ4xkPjt
wVIcTWCW8ddPrfMi4/esiQFlPck1p3QSfkPiAgHAjJiDDqDtqsMKr+5AkUaHlqjR
VV3YE27x/QyLZbV7igiTPdh1fTV7+Yl8VHpBdnMRUVTFoZaIiCe0efmqsvzBd73A
c75aKTwu6cPQ9dH/gIEOHCvrgweED7ZcabT7h/k7DXL2zhnJTPmQSJLWjfQebJOu
4l1p7tn35xbjqu906l4iII+YqWCAj/gNT2qdcIWQmxg/reg2tRbU7Nv3M0c=
-----END CERTIFICATE-----
'''

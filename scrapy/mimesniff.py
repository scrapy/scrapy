# Original code created by Dong-hee Na, see https://github.com/corona10/mimesniff
# Modified for use with scrapy
# Date: March 22. 2020
# By: Bretton Tan

import io

def from_file_content(fin):
    with open(fin, 'rb') as f:
        h = f.read(512)
        res = _detect_content(h)
        if res:
            return res
    return 'application/octet-stream'

def from_byte_content(fin):
    res = _detect_content(fin)
    if res:
        return res
    return 'application/octet-stream'

def from_stream_content(fin):
    location = fin.tell()
    h = fin.read(512)
    fin.seek(location)
    res = _detect_content(h)
    if res:
        return res
    return 'application/octet-stream'


def _is_ws(c):
    return c in b'\t\n\x0c\r '


# https://mimesniff.spec.whatwg.org/#terminology.
def _is_TT(c):
    return c in b' >'


def _detect_content(h):
    first_non_ws = 0
    for idx, hb in enumerate(h):
        if not _is_ws(hb):
            first_non_ws = idx
            break

    detect = [_match_html_types, _match_exact_sig_types,
            _match_mask_sig_types, _match_mp4_type, _match_text_type]
    for d in detect:
        res = d(h, first_non_ws)
        if res:
            return res
    return None


def _match_html_types(h, first_non_ws):
    sigs = [b'<!DOCTYPE HTML', b'<HTML', b'<HEAD',
            b'<SCRIPT', b'<IFRAME', b'<H1', b'<DIV',
            b'<FONT', b'<TABLE', b'<A', b'<STYLE',
            b'<TITLE', b'<B', b'<BODY', b'<BR', b'<P',
            b'<!--']
    h = h[first_non_ws:]

    for s in sigs:
        ret = _match_html_sig(h, s)
        if ret:
            return ret

    return None


def _match_html_sig(h, sig):
    if len(h) < len(sig) + 1:
        return None

    for hc, sc in zip(h, sig):
        if 65 <= sc <= 90:
            hc&=0xDF
        if hc != sc:
            return None

    # should be a tag-terminating byte (0xTT)
    # https://mimesniff.spec.whatwg.org/#terminology
    if not _is_TT(h[len(sig)]):
        return None
    return 'text/html; charset=utf-8'


def _match_exact_sig_types(h, first_non_ws):
    sigs = [
        # (pattern, mimetype)
        (b'\x00\x00\x01\x00', 'image/x-icon'),
        (b'\x00\x00\x02\x00', 'image/x-icon'),
        (b'%PDF-', 'application/pdf'),
        (b'%!PS-Adobe-', 'application/postscript'),
        (b'BM', 'image/bmp'),
        (b'GIF87a', 'image/gif'),
        (b'GIF89a', 'image/gif'),
        (b'\x89PNG\x0D\x0A\x1A\x0A', 'image/png'),
        (b'\xFF\xD8\xFF', 'image/jpeg'),
        (b'\x00\x01\x00\x00', 'font/ttf'),
        (b'OTTO', 'font/otf'),
        (b'ttcf', 'font/collection'),
        (b'wOFF', 'font/woff'),
        (b'wOF2', 'font/woff2'),
        (b'\x1F\x8B\x08', 'application/x-gzip'),
        (b'PK\x03\x04', 'application/zip'),
        (b'Rar!\x1A\x07\x00', 'application/x-rar-compressed'),
        (b'Rar!\x1A\x07\x01\x00', 'application/x-rar-compressed'),
        (b'\x00\x61\x73\x6D', 'application/wasm')
    ]

    h = h[first_non_ws:]
    for sig, mime in sigs:
        if h.startswith(sig):
            return mime

    return None


def _match_mask_sig_types(h, first_non_ws):
    sigs = [
        # (mask, pattern, skip_white_space, mimetype)
        (b'\xFF\xFF\xFF\xFF\xFF', b'<?xml', True, 'text/xml; charset=utf-8'),
        (b'\xFF\xFF\x00\x00', b'\xFF\xFF\x00\x00', False, 'text/plain; charset=utf-16be'),
        (b'\xFF\xFF\x00\x00', b'\xFF\xFE\x00\x00', False, 'text/plain; charset=utf-16le'),
        (b'\xFF\xFF\xFF\x00', b'\xEF\xBB\xBF\x00', False, 'text/plain; charset=utf-8'),
        (b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\xFF\xFF\xFF\xFF\xFF\xFF', b'RIFF\x00\x00\x00\x00WEBPVP', False, 'image/webp'),
        (b'\xFF\xFF\xFF\xFF', b'.snd', False, 'audio/basic'),
        (b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\xFF\xFF\xFF\xFF', b'FORM\x00\x00\x00\x00AIFF', False, 'audio/aiff'),
        (b'\xFF\xFF\xFF', b'ID3', False, 'audio/mpeg'),
        (b'\xFF\xFF\xFF\xFF\xFF', b'OggS\x00', False, 'application/ogg'),
        (b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF', b'MThd\x00\x00\x00\x06', False, 'audio/midi'),
        (b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\xFF\xFF\xFF\xFF', b'RIFF\x00\x00\x00\x00AVI ', False, 'video/avi'),
        (b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00\xFF\xFF\xFF\xFF', b'RIFF\x00\x00\x00\x00WAVE', False, 'audio/wave'),
        (b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00LP', b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xFF\xFF', False, 'application/vnd.ms-fontobject')
    ]

    for mask, pattern, skip_ws, mimetype in sigs:
        match = True
        if skip_ws:
            data = h[first_non_ws:]
        if len(mask) != len(pattern):
            return None
        if len(data) < len(pattern):
            return None
        for m, p, d in zip(mask, pattern, data):
            if d&m != p:
                match = False
                break
        if match:
            return mimetype
    return None


# https://mimesniff.spec.whatwg.org/#signature-for-mp4
def _match_mp4_type(h, first_non_ws):
    if len(h) < 12:
        return None
    box_size = int.from_bytes(h[:4], byteorder='big')
    if len(h) < box_size or box_size%4 != 0:
        return None
    if h[4:8] != b'ftyp':
        return None

    for idx in range(8, box_size, 4):
        if idx == 12:
            continue
        if h[idx:idx+3] == b'mp4':
            return 'video/mp4'

    return None


def _match_text_type(h, first_non_ws):
    for b in h[first_non_ws:]:
        if b <= 0x08 or b == 0x0B:
            return None
        if 0x0E <= b <= 0x1A:
            return None
        if 0x1C <= b <= 0x1F:
            return None
    return 'text/plain; charset=utf-8'

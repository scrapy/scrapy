/* Copyright (c) 2008 Twisted Matrix Laboratories.
 * See LICENSE for details.
 */


#include <winsock2.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

#include "winsock_pointers.h"

#ifndef WSAID_CONNECTEX
#define WSAID_CONNECTEX {0x25a207b9,0xddf3,0x4660,{0x8e,0xe9,0x76,0xe5,0x8c,0x74,0x06,0x3e}}
#endif
#ifndef WSAID_GETACCEPTEXSOCKADDRS
#define WSAID_GETACCEPTEXSOCKADDRS {0xb5367df2,0xcbac,0x11cf,{0x95,0xca,0x00,0x80,0x5f,0x48,0xa1,0x92}}
#endif
#ifndef WSAID_ACCEPTEX
#define WSAID_ACCEPTEX {0xb5367df1,0xcbac,0x11cf,{0x95,0xca,0x00,0x80,0x5f,0x48,0xa1,0x92}}
#endif
/*#ifndef WSAID_TRANSMITFILE
#define WSAID_TRANSMITFILE {0xb5367df0,0xcbac,0x11cf,{0x95,0xca,0x00,0x80,0x5f,0x48,0xa1,0x92}}
#endif*/


int initPointer(SOCKET s, void **fun, GUID guid) {
    int res;
    DWORD bytes;

    *fun = NULL;
    res = WSAIoctl(s, SIO_GET_EXTENSION_FUNCTION_POINTER,
                   &guid, sizeof(guid),
                   fun, sizeof(fun),
                   &bytes, NULL, NULL);
    return !res;
}

int initWinsockPointers() {
    SOCKET s = socket(AF_INET, SOCK_STREAM, 0);
    /* I hate C */
    GUID guid1 = WSAID_ACCEPTEX;
    GUID guid2 = WSAID_GETACCEPTEXSOCKADDRS;
    GUID guid3 = WSAID_CONNECTEX;
    /*GUID guid4 = WSAID_TRANSMITFILE;*/
    if (!s) {
        return 0;
    }
    if (!initPointer(s, (void **)&lpAcceptEx, guid1))
    {
        return 0;
    }
    if (!initPointer(s, (void **)&lpGetAcceptExSockaddrs, guid2)) {
        return 0;
    }
    if (!initPointer(s, (void **)&lpConnectEx, guid3)) {
        return 0;
    };
    /*initPointer(s, &lpTransmitFile, guid4);*/
    return 1;
}


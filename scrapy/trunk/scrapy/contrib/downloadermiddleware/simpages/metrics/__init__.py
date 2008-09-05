"""
This module contains several metrics that can be used with the
SimpagesMiddleware.

A metric must implement two functions:

1. simhash(response, *args)

Receives a response and returns a simhash of that response. A simhash can be
an object of any type and its only purpose is to provide a fast way for
comparing the [simhashed] response with another responses (that will also be
simhashed).

2. compare(simhash1, simhash2)

Receives two simhashes and must return a (float) value between 0 and 1,
depending on how similar the two simhashes (and, thus, the responses they
represent) are. 0 means completely different, 1 means identical.
"""

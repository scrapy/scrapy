#!/usr/bin/python
# -*- coding: utf-8 -*-

keyword = ["feature film", "indie film", "film production", "independent film", "film casting", "movie casting",
           "extras casting", "film editor", "movie editor", "post production", "movie production", "line producer",
           "production manager", "editor", "colorist", "visual effects", "sound design", "VFX", "motion picture",
           "film sales", "film distribution", "film budget"]

options = {
        'CONCURRENT_ITEMS': 150,
        'USER_AGENT': "Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/535.24 (KHTML, like Gecko) "
                      "Chrome/19.0.1055.1 Safari/535.24",
        'CONCURRENT_REQUESTS': 5,
        'SW_SAVE_BUFFER': 30,
        'DOWNLOAD_DELAY': 1.5,
        'COOKIES_ENABLED': False,
    }

name_file = 'outfile.txt'

test_mode = True  # True or False
difference_days = 2 # Test mode
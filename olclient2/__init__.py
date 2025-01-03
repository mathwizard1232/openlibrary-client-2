#!/usr/bin/env python

"""
    __init__.py
    ~~~~~~~~~~~

    :copyright: (c) 2016 by Internet Archive.
    :copyright: (c) 2025 by Shaun Gosse.
    :license: see LICENSE for more details.
"""

__title__ = 'olclient2' # Forked from olclient by Internet Archive
__version__ = '0.0.1'
__author__ = 'Internet Archive (original) and Shaun Gosse (fork)'


from olclient2.bots import AbstractBotJob
from olclient2.openlibrary import OpenLibrary
from olclient2.common import Book, Author

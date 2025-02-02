from __future__ import annotations

import json
import logging
import re
from typing import List, Dict, Optional, Any, Union

import backoff
from requests import Response

from olclient2.common import Entity, Book, Author
from olclient2.helper_classes.results import Results
from olclient2.utils import merge_unique_lists, get_text_value, get_approval_from_cli

logger = logging.getLogger('open_library_work')


def get_work_helper_class(ol_context):
    class Work(Entity):

        OL = ol_context

        def __init__(self, olid: str, identifiers=None, **kwargs):
            super().__init__(identifiers)
            self.olid = olid
            self._editions: List = []
            self.description = get_text_value(kwargs.pop('description', None))
            self.notes = get_text_value(kwargs.pop('notes', None))
            for kwarg in kwargs:
                setattr(self, kwarg, kwargs[kwarg])

        def json(self) -> dict:
            """Returns a dict JSON representation of an OL Work suitable
            for saving back to Open Library via its APIs.
            """
            exclude = ['_editions', 'olid']
            data = {k: v for k, v in self.__dict__.items() if v and k not in exclude}
            data['key'] = '/works/' + self.olid
            data['type'] = {'key': '/type/work'}
            if data.get('description'):
                data['description'] = {
                    'type': '/type/text',
                    'value': data['description'],
                }
            if data.get('notes'):
                data['notes'] = {'type': '/type/text', 'value': data['notes']}
            return data

        def validate(self) -> None:
            """Validates a Work's json representation against the canonical
            JSON Schema for Works using jsonschema.validate().
            Raises:
               jsonschema.exceptions.ValidationError if the Work is invalid.
            """
            return self.OL.validate(self, 'work.schema.json')

        @property
        def editions(self):
            """Returns a list of editions of related to a particular work
            Returns
                (List) of common.Edition books
            Usage:
                >>> from olclient2 import OpenLibrary
                >>> ol = OpenLibrary()
                >>> ol.Work(olid).editions
            """
            url = f'{self.OL.base_url}/works/{self.olid}/editions.json'
            r_json: Dict[Any, Any] = self.OL.session.get(url).json()
            editions: List[Any] = r_json.get('entries', [])

            while True:
                next_page_link: Optional[str] = r_json.get('links', {}).get('next')
                if next_page_link is not None:
                    r_json: Dict[Any, Any] = self.OL.session.get(
                        self.OL.base_url + next_page_link
                    ).json()
                    editions.extend(r_json.get('entries', []))
                else:
                    break

            self._editions = [
                self.OL.Edition(**self.OL.Edition.ol_edition_json_to_book_args(ed))
                for ed in editions
            ]
            return self._editions

        @classmethod
        def create(cls, book: Book, debug=False) -> Work:
            """Creates a new work along with a new edition
            Usage:
                >>> from olclient2.openlibrary import OpenLibrary
                >>> import olclient2.common as common
                >>> book = common.Book(title=u"Warlight: A novel", authors=[common.Author(name=u"Michael Ondaatje")], publisher=u"Deckle Edge", publish_date=u"2018")
                >>> book.add_id(u'isbn_10', u'0525521194')
                >>> book.add_id(u'isbn_13', u'978-0525521198'))
                >>> ol.Work.create(book)
            """
            year_matches_in_date: list[Any] = re.findall(r'[\d]{4}', book.publish_date)
            book.publish_date = year_matches_in_date[0] if len(year_matches_in_date) > 0 else ''
            ed = cls.OL.create_book(book, debug=debug)
            ed.add_bookcover(book.cover)
            work = ed.work
            work.add_bookcover(book.cover)
            return ed

        def add_author(self, author):
            author_role = {
                'type': {'key': '/type/author_role'},
                'author': {'key': '/authors/' + author.olid},
            }
            self.authors.append(author_role)
            return author_role

        def add_bookcover(self, url):
            return self.OL.session.post(
                f'{self.OL.base_url}/works/{self.olid}/-/add-cover',
                files={'file': '', 'url': url, 'upload': 'submit'},
            )

        def add_subject(self, subject, comment=''):
            return self.add_subjects([subject], comment)

        def add_subjects(self, subjects, comment=''):
            url = self.OL.base_url + "/works/" + self.olid + ".json"
            data = self.OL.session.get(url).json()
            original_subjects = data.get('subjects', [])
            changed_subjects = merge_unique_lists([original_subjects, subjects])
            data['_comment'] = comment or (
                f"adding {', '.join(subjects)} to subjects"
            )
            data['subjects'] = changed_subjects
            return self.OL.session.put(url, json.dumps(data))

        def rm_subjects(self, subjects, comment=''):
            url = self.OL.base_url + "/works/" + self.olid + ".json"
            r = self.OL.session.get(url)
            data = r.json()
            data['_comment'] = comment or (f"rm subjects: {', '.join(subjects)}")
            data['subjects'] = list(set(data['subjects']) - set(subjects))
            return self.OL.session.put(url, json.dumps(data))

        def delete(self, comment: str, confirm: bool = True) -> Optional[Response]:
            should_delete = confirm is False or get_approval_from_cli(
                f'Delete https://openlibrary.org/works/{self.olid} and its editions? (y/n)'
            )
            if should_delete is False:
                return None
            return self.OL.session.post(f'{self.OL.base_url}/works/{self.olid}/-/delete.json', params={'comment': comment})

        def save(self, comment):
            """Saves this work back to Open Library using the JSON API."""
            body = self.json()
            body['_comment'] = comment
            url = self.OL.base_url + f'/works/{self.olid}.json'
            return self.OL.session.put(url, json.dumps(body))

        @classmethod
        def get(cls, olid: str) -> Work:
            path = f'/works/{olid}.json'
            r = cls.OL.get_ol_response(path)
            return cls(olid, **r.json())

        @classmethod
        def search(cls, title: Optional[str] = None, author: Optional[str] = None, limit: Optional[int] = None) -> Optional[Union[Book, List[Book]]]:
            """Get the *closest* matching result in OpenLibrary based on a title
            and author.
            
            Args:
                title: Title of the work to search for
                author: Author of the work to search for
                limit: Maximum number of results to return (default: None returns only closest match)
                
            Returns:
                Book object if found, None otherwise
                
            Usage:
                >>> from olclient2.openlibrary import OpenLibrary
                >>> ol = OpenLibrary()
                >>> ol.get_book_by_metadata(
                ...     title=u'The Autobiography of Benjamin Franklin')
                or
                >>> from olclient2.openlibrary import OpenLibrary
                >>> ol = OpenLibrary()
                >>> ol.get_book_by_metadata(
                ...     author=u'Dan Brown',
                ...     limit=5)
            """
            if not (title or author):
                raise ValueError("Author or title required for metadata search")

            url = f'{cls.OL.base_url}/search.json?'
            if title:
                url += f'title={title}'
            if author:
                url += f'&author={author}' if title else f'author={author}'
            if limit:
                url += f'&limit={limit}'

            @backoff.on_exception(
                on_giveup=lambda error: logger.exception(
                    "Error retrieving metadata for book: %s", error
                ),
                **cls.OL.BACKOFF_KWARGS,
            )
            def _get_book_by_metadata(ol_url):
                return cls.OL.session.get(ol_url)

            response = _get_book_by_metadata(url)
            response_data = response.json()
            logger.debug(f"Raw API response: {response_data}")
            results = Results(**response_data)
            logger.debug(f"First doc authors before processing: {results.docs[0].authors if results.docs else 'no docs'}")

            if results.num_found:
                logger.debug(f"Found {results.num_found} results")
                if limit:
                    # Deduplicate works based on title and author combination
                    seen_works = {}
                    for doc in results.docs:
                        title = doc.title.lower() if hasattr(doc, 'title') else ''
                        # Use the processed authors list instead of raw author_name
                        authors = tuple(sorted(author['name'] for author in doc.authors)) if hasattr(doc, 'authors') else ()
                        dedup_key = (title, authors)
                        logger.debug(f"Processing doc with title: {title}, authors: {authors}")
                        
                        # If we haven't seen this title/author combination before, or this work has a more complete record
                        if dedup_key not in seen_works or len(vars(doc)) > len(vars(seen_works[dedup_key])):
                            seen_works[dedup_key] = doc
                            logger.debug(f"Added/Updated work with key: {dedup_key}")
                    
                    # Convert back to list and create book objects
                    deduped_docs = list(seen_works.values())[:limit]
                    logger.debug(f"Returning {len(deduped_docs)} deduplicated results")
                    return [cls._doc_to_book(doc) for doc in deduped_docs]
                return results.first.to_book()

            logger.debug("No results found")
            return None

        @classmethod
        def _doc_to_book(cls, doc) -> Book:
            """Convert a search API document to a Book object."""
            logger.debug(f"Converting doc to book. Doc authors: {doc.authors if hasattr(doc, 'authors') else 'no authors'}")
            
            # Create book with processed authors
            book = Book(
                title=getattr(doc, 'title', ''),
                authors=[
                    Author(name=author['name'], olid=author.get('olid'))
                    for author in (doc.authors if hasattr(doc, 'authors') else [])
                ],
                publisher=getattr(doc, 'publisher', [''])[0] if hasattr(doc, 'publisher') else '',
                publish_date=getattr(doc, 'publish_date', [''])[0] if hasattr(doc, 'publish_date') else ''
            )
            
            # Add work ID
            if hasattr(doc, 'key'):
                work_olid = doc.key.split('/')[-1]
                book.add_id('olid', work_olid)
                
            return book

        @classmethod
        def search_by_isbn(cls, isbn: str) -> Optional[Book]:
            """Search for a work using an ISBN.
            
            Args:
                isbn: ISBN-10 or ISBN-13 to search for
                
            Returns:
                Book object if found, None otherwise
                
            Usage:
                >>> from olclient2.openlibrary import OpenLibrary
                >>> ol = OpenLibrary()
                >>> book = ol.Work.search_by_isbn('067165408X')
            """
            # Clean ISBN
            isbn = isbn.replace('-', '').strip()
            
            # Use search API with ISBN
            url = f'{cls.OL.base_url}/search.json?isbn={isbn}'
            
            @backoff.on_exception(
                on_giveup=lambda error: logger.exception(
                    "Error retrieving work by ISBN: %s", error
                ),
                **cls.OL.BACKOFF_KWARGS,
            )
            def _get_work_by_isbn(ol_url):
                return cls.OL.session.get(ol_url)

            response = _get_work_by_isbn(url)
            data = response.json()
            
            if not data.get('docs'):
                return None
                
            # Get first matching work
            doc = data['docs'][0]
            
            # Create authors with OLIDs if available
            authors = []
            for i, name in enumerate(doc.get('author_name', [])):
                author = Author(name=name)
                if 'author_key' in doc and i < len(doc['author_key']):
                    author.olid = doc['author_key'][i]
                authors.append(author)
            
            # Create Book object with work data
            book = Book(
                title=doc['title'],
                authors=authors,
                publisher=doc.get('publisher', [''])[0] if doc.get('publisher') else '',
                publish_date=doc.get('publish_date', [''])[0] if doc.get('publish_date') else ''
            )
            
            # Add identifiers
            work_olid = doc['key'].split('/')[-1]
            book.add_id('olid', work_olid)
            if 'isbn' in doc:
                for isbn in doc['isbn']:
                    book.add_id('isbn_13' if len(isbn) == 13 else 'isbn_10', isbn)
            
            return book

    return Work

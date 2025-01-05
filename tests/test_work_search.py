import unittest
from unittest.mock import patch
from olclient2.openlibrary import OpenLibrary
from olclient2.common import Author

class TestWorkSearch(unittest.TestCase):
    @patch('olclient2.openlibrary.OpenLibrary.login')
    def setUp(self, mock_login):
        self.ol = OpenLibrary()

    @patch('requests.Session.get')
    def test_search_by_isbn_with_author_ids(self, mock_get):
        # Mock response data
        mock_response = {
            'docs': [{
                'key': '/works/OL123W',
                'title': 'Test Book',
                'author_name': ['John Smith', 'Jane Doe'],
                'author_key': ['OL1A', 'OL2A'],
                'publisher': ['Test Publisher'],
                'publish_date': ['2023'],
                'isbn': ['0123456789', '9780123456789']
            }]
        }
        mock_get.return_value.json.return_value = mock_response

        # Perform search
        book = self.ol.Work.search_by_isbn('0123456789')

        # Verify results
        self.assertIsNotNone(book)
        self.assertEqual(book.title, 'Test Book')
        self.assertEqual(len(book.authors), 2)
        self.assertEqual(book.authors[0].name, 'John Smith')
        self.assertEqual(book.authors[0].olid, 'OL1A')
        self.assertEqual(book.authors[1].name, 'Jane Doe')
        self.assertEqual(book.authors[1].olid, 'OL2A')
        self.assertEqual(book.publisher, 'Test Publisher')
        self.assertEqual(book.publish_date, '2023')
        self.assertEqual(book.identifiers['olid'], ['OL123W'])
        self.assertEqual(book.identifiers['isbn_10'], ['0123456789'])
        self.assertEqual(book.identifiers['isbn_13'], ['9780123456789'])

    @patch('requests.Session.get')
    def test_search_by_isbn_no_results(self, mock_get):
        mock_get.return_value.json.return_value = {'docs': []}
        book = self.ol.Work.search_by_isbn('0123456789')
        self.assertIsNone(book)

    @patch('requests.Session.get')
    def test_search_by_isbn_missing_author_ids(self, mock_get):
        # Test case where author_key is missing
        mock_response = {
            'docs': [{
                'key': '/works/OL123W',
                'title': 'Test Book',
                'author_name': ['John Smith'],
                'publisher': ['Test Publisher'],
                'publish_date': ['2023'],
                'isbn': ['0123456789']
            }]
        }
        mock_get.return_value.json.return_value = mock_response

        book = self.ol.Work.search_by_isbn('0123456789')
        self.assertIsNotNone(book)
        self.assertEqual(len(book.authors), 1)
        self.assertEqual(book.authors[0].name, 'John Smith')
        self.assertFalse(hasattr(book.authors[0], 'olid')) 
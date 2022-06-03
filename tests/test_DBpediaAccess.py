import unittest

from DBpediaAccess import DBpediaAccess


class DBpediaAccessTest(unittest.TestCase):

    #Wrong url
    def test_url_exists(self):
        self.assertEqual(DBpediaAccess.getContentFromDBPedia(self, url="...", pdf=False, pdffilename="nopdf", sep=' '), "URL ERROR", "Should be URL ERROR")
    
    #Cannot decode source code of the url
    def test_invalid_content(self):
        self.assertEqual(DBpediaAccess.getContentFromDBPedia(self, url="https://www.in.gr/", pdf=False, pdffilename="nopdf", sep=' '), "Content scrapped is invalid", "Should be Content scrapped is invalid")
    
    #Wrong pdf filename
    def test_invalid_pdf_filename(self):
        self.assertTrue((DBpediaAccess.getContentFromDBPedia(self, url="https://dbpedia.org/page/Athens", pdf=True, pdffilename="../", sep=' ').find("Could not create pdf")==0), "Should contain Could not create pdf file")
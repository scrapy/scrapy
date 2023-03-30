from twisted.trial import unittest
from scrapy.robotstxt import PythonRobotParser, RerpRobotParser, ReppyRobotParser, ProtegoRobotParser
from reppy.robots import Robots 
from robotexclusionrulesparser import RobotExclusionRulesParser
from protego import Protego  


class BaseRobotParserTest(unittest.TestCase):
    '''
    The BaseRobotParserTest class tests robots.txt for compliance with search engine crawlers
    '''
    def setUp(self):
        self.robot_parsers = []
        robot_parsers_classes = [PythonRobotParser, RerpRobotParser, ReppyRobotParser, ProtegoRobotParser]
        #check the compatibility and availability of parsers
        for parser_cls in robot_parsers_classes:
            if parser_cls.is_supported():
                self.robot_parsers.append(parser_cls)

    def test_allowed(self):
        '''
        tests if the robot parsers allows allowed and disallows disallowed urls.
        '''
        sites = ['https://www.site.local/allowed', 'https://www.site.local/disallowed']
        crawlers = ['*', '+googlebot', 'adidxbot']

        for rp in self.robot_parsers:
            robots_txt = 'User-agent:  \nDisallow: /disallowed \nAllow: /allowed\nCrawl-delay: 10'
            parser = rp.from_crawler(None, robots_txt.encode('utf-8'))
            self.assertTrue(parser.allowed(sites[0], '*'))
            self.assertFalse(parser.allowed(sites[1], '*'))
            self.assertTrue(parser.allowed(sites[0], '+googlebot'))
            self.assertFalse(parser.allowed(sites[1], '+googlebot'))

    def test_allowed_wildcards(self):
        '''
        tests wildcards in urls for robot parsers.
        '''
        sites = ['https://www.site.local/disallowed', 'https://www.site.local/disallowed/xyz/end', 'https://www.site.local/disallowed/abc/end', 'https://www.site.local/disallowed/xyz/endinglater', 'https://www.site.local/allowed', 'https://www.site.local/is_still_allowed', 'https://www.site.local/is_allowed_too']
        user_agents = ['first', 'second', 'third']
        paths = ['/*/end', '/*/endinglater', '/*allowed', '/']
        rules = [
            {'User-agent': 'first', 'Disallow': '/disallowed/*/end$'},
            {'User-agent': 'second', 'Allow': '/*allowed', 'Disallow': '/'},
            {'User-agent': 'third', 'Allow': '/', 'Disallow': '/is_not_allowed'}
        ]
        robotstxt_robotstxt_body = b''
        for rule in rules:
            for key in rule:
              robotstxt_robotstxt_body += '{}: {}\n'.format(key, rule[key]).encode('utf-8')
        parser = PythonRobotParser.from_crawler(None, robotstxt_robotstxt_body)

        self.assertTrue(parser.allowed(sites[4], 'second'))
        self.assertTrue(parser.allowed(sites[5], 'second'))
        self.assertTrue(parser.allowed(sites[6], 'second'))
        self.assertFalse(parser.allowed(sites[1], 'first'))
        self.assertFalse(parser.allowed(sites[2], 'first'))
        self.assertTrue(parser.allowed(sites[3], 'first'))
        self.assertFalse(parser.allowed(sites[7], 'third'))

    def test_unicode_url_and_useragent(self):
        '''
        tests if the robot parsers allows urls and user agents with unicode characters.
        '''
        robots_txt = '''
        User-Agent: *
        Disallow: /admin/
        Disallow: /static/
        Disallow: /wiki/Käyttäjä:

        User-Agent: UnicödeBöt
        Disallow: /some/randome/page.html
        '''
        parser = PythonRobotParser.from_crawler(None, robots_txt.encode('utf-8'))

        sites = ['https://site.local/', 'https://site.local/admin/', 'https://site.local/static/', 'https://site.local/wiki/Käyttäjä:', 'https://site.local/some/randome/page.html']
        user_agents = ['*', 'googlebot', 'UnicödeBöt']
        for ua in user_agents:
            self.assertTrue(parser.allowed(sites[0], ua))
            self.assertFalse(parser.allowed(sites[1], ua))
            self.assertFalse(parser.allowed(sites[2], ua))
            self.assertFalse(parser.allowed(sites[3], ua))
            self.assertTrue(parser.allowed(sites[4], ua))

    def test_empty_response(self):
        '''
        tests if robot parsers treats an empty response as no disallowed url and allows all urls.
        '''
        robots_txt = b''
        parser = PythonRobotParser.from_crawler(None, robots_txt)

        sites = ['https://site.local/', 'https://site.local/disallowed', 'https://site.local/index.html', 'https://site.local/disallowed/']
        user_agents = ['*', 'googlebot', 'chrome']
        for ua in user_agents:
            self.assertTrue(parser.allowed(sites[0], ua))
            self.assertTrue(parser.allowed(sites[1], ua))
            self.assertTrue(parser.allowed(sites[2], ua))
            self.assertTrue(parser.allowed(sites[3], ua))

    def test_garbage_response(self):
        '''
        tests garbage reponses and how it is handled by robot parsers.
        '''
        robots_txt = b"GIF89a\xd3\x00\xfe\x00\xa2"
        parser = PythonRobotParser.from_crawler(None, robots_txt)

        sites = ['https://site.local/', 'https://site.local/disallowed', 'https://site.local/index.html', 'https://site.local/disallowed/']
        user_agents = ['*', 'googlebot', 'chrome']
        for ua in user_agents:
            self.assertTrue(parser.allowed(sites[0], ua))
            self.assertTrue(parser.allowed(sites[1], ua))
            self.assertTrue(parser.allowed(sites[2], ua))
            self.assertTrue(parser.allowed(sites[3], ua))
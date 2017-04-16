'''
Created on Mar 21, 2013

@author: rm89
'''
from netrc import netrc, NetrcParseError
from scrapy import log
from urlparse import urlparse
from w3lib.form import encode_multipart
from w3lib.http import basic_auth_header
import ast
import scrapy.log
import urllib
import urllib2


class ScrapydClient(object):
    """ScrapydClient enables you to use all scrapyd json-interfaces.
    It enables you to deploy eggs, schedule jobs, print status information, ... . 
    """
    _server_url = None
    _user_name = None
    _user_password = None

    _json_interfaces = {'addversion.json':'POST', 'schedule.json':'POST', 'cancel.json':'POST', 'listprojects.json':'GET',
                      'listversions.json':'GET', 'listspiders.json':'GET', 'listjobs.json':'GET', 'delversion.json':'POST', 'delproject.json':'POST'}

    _verbose = False

    def __init__(self, server_url, user_name=None, user_password=None, verbose=False):
        self._server_url = server_url
        self._user_name = user_name
        self._user_password = user_password
        self._verbose = verbose

    def scrapydex_del_all_versions(self, project):
        result = self.scrapyd_listversions(project)

        versions = None
        if 'versions' in result:
            versions = result['versions']
        else:
            return

        for version in versions:
            self.scrapyd_delversion(project, version)

    def scrapydex_stop_all_jobs(self, project):
        result = self.scrapyd_listjobs(project)

        pending_jobs = None
        if 'pending' in result:
            pending_jobs = result['pending']

        running_jobs = None
        if 'running' in result:
            running_jobs = result['running']

        jobs = None
        if pending_jobs and running_jobs:
            jobs = pending_jobs + running_jobs
        elif pending_jobs:
            jobs = pending_jobs
        elif running_jobs:
            jobs = running_jobs

        if not jobs:
            return

        if len(jobs) > 0:
            for job in jobs:
                self.scrapyd_cancel(project, job['id'])

    def scrapyd_add_version(self, project, version, eggdata):
        data = {'project':project, 'version':version, 'egg': ('project.egg', eggdata)}

        return self.use_json_interface('addversion.json', data)

    def scrapyd_schedule(self, project, spider, setting=None, args_dict=None):
        data = {'project':project, 'spider':spider}

        if setting:
            data.update({'setting':setting})

        if args_dict:
            data.update(args_dict)

        return self.use_json_interface('schedule.json', data)

    def scrapyd_cancel(self, project, job):
        data = {'project':project, 'job':job }

        return self.use_json_interface('cancel.json', data)

    def scrapyd_listprojects(self):
        data = None

        return self.use_json_interface('listprojects.json', data)

    def scrapyd_listversions(self, project):
        data = {'project':project}

        return self.use_json_interface('listversions.json', data)

    def scrapyd_listspiders(self, project):
        data = {'project':project}

        return self.use_json_interface('listspiders.json', data)

    def scrapyd_listjobs(self, project):
        data = {'project':project}

        return self.use_json_interface('listjobs.json', data)

    def scrapyd_delversion(self, project, version):
        data = {'project':project, 'version':version }

        return self.use_json_interface('delversion.json', data)

    def scrapyd_delproject(self, project):
        data = {'project':project}

        return self.use_json_interface('delproject.json', data)

    def use_json_interface(self, json_interface, data):
        if not json_interface in self._json_interfaces:
            raise Exception("Unknown JSON-Interface: %s" % json_interface)

        if self._json_interfaces[json_interface] == 'GET':
            return self._http_get(json_interface, data)
        else:
            return self._http_post(json_interface, data)


    def _http_get(self, json_interface, data):
        url = self._get_server_url() + "/" + json_interface

        if data:
            url += "?%s" % (urllib.urlencode(data))

        self._log("_http_get: url=%s, from data=%s" % (url, data))

        req = urllib2.Request(url)
        self._add_auth_header(req)

        return self._get_response(req)

    def _http_post(self, json_interface, data):

        url = self._get_server_url() + "/" + json_interface

        if data:
            body, boundary = encode_multipart(data)
            headers = {
                'Content-Type': 'multipart/form-data; boundary=%s' % boundary,
                'Content-Length': str(len(body)),
            }

        self._log("_http_post: url=%s with body=%s, from data=%s" % (url, body, data))
        req = urllib2.Request(url, body, headers)
        self._add_auth_header(req)

        return self._get_response(req)


    def _get_response(self, req):
        result = None
        try:
            f = urllib2.urlopen(req)
            result = f.read()
            self._log("Server response (%s)\n%s" % (f.code, result))
        except urllib2.HTTPError, e:
            self._log("_http_post failed (%s):" % e.code)
            self._log(e.read())
        except urllib2.URLError, e:
            self._log("_http_post failed: %s" % e)

        if result:
            try:
                return ast.literal_eval(result)
            except Exception as e:
                return {"status":"error", "message":str(e)}

        return {"status": "error"}

    def _get_server_url(self):
        return self._server_url

    """from deploy.py """
    def _add_auth_header(self, request):
        if self._user_name != None and self._user_password != None:
            request.add_header('Authorization', basic_auth_header(self._user_name, self._user_password))
        else:  # try netrc
            try:
                host = urlparse(self._get_server_url()).hostname
                a = netrc().authenticators(host)
                request.add_header('Authorization', basic_auth_header(a[0], a[2]))
            except (NetrcParseError, IOError, TypeError):
                pass

    def _log(self, message):
        if self._verbose:
            log.msg(message, level=log.DEBUG)

    def __str__(self):

        return str({'id':id(self), '_server_url':self._server_url, '_user_name':self._user_name,
                '_user_password':self._user_password, '_verbose':self._verbose})

# test code
if __name__ == "__main__":
    scrapy.log.start(loglevel=log.DEBUG)
    project = "Crawler"

    client = ScrapydClient("http://localhost:6800", "admin", "password", verbose=True)
    client.scrapyd_listjobs(project)
    client.scrapyd_listprojects()
    client.scrapyd_listspiders(project)
    client.scrapyd_listversions(project)
    client.scrapydex_stop_all_jobs(project)
    client.scrapydex_del_all_versions(project)


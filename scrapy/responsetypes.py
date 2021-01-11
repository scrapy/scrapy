Last login: Sun Jan 10 17:51:22 on ttys001

The default interactive shell is now zsh.
To update your account to use zsh, please run `chsh -s /bin/zsh`.
For more details, please visit https://support.apple.com/kb/HT208050.
(base) wob:~ williamobrien$ cd documents/GitHub/Scrapy
(base) wob:Scrapy williamobrien$ pip sniffpy
ERROR: unknown command "sniffpy"
(base) wob:Scrapy williamobrien$ cd GitHub
-bash: cd: GitHub: No such file or directory
(base) wob:Scrapy williamobrien$ cd..
-bash: cd..: command not found
(base) wob:Scrapy williamobrien$ cd .. 
(base) wob:GitHub williamobrien$ cd ...
-bash: cd: ...: No such file or directory
(base) wob:GitHub williamobrien$ cd/
-bash: cd/: No such file or directory
(base) wob:GitHub williamobrien$ /
-bash: /: is a directory
(base) wob:GitHub williamobrien$ cd back
-bash: cd: back: No such file or directory
(base) wob:GitHub williamobrien$ cd...
-bash: cd...: command not found
(base) wob:GitHub williamobrien$ cd/
-bash: cd/: No such file or directory
(base) wob:GitHub williamobrien$ cd documents
-bash: cd: documents: No such file or directory
(base) wob:GitHub williamobrien$ emacs repsonsetypes.py

File Edit Options Buffers Tools Python Help                                                                                  
                content_disposition, encoding='latin-1', errors='replace'
            ).split(';')[1].split('=')[1].strip('"\'')
            return self.from_filename(filename)
        except IndexError:
            return Response

    def from_headers(self, headers):
        """Return the most appropriate Response class by looking at the HTTP                                                 
        headers"""
        cls = Response
        if b'Content-Type' in headers:
            cls = self.from_content_type(
                content_type=headers[b'Content-Type'],
                content_encoding=headers.get(b'Content-Encoding')
            )
        if cls is Response and b'Content-Disposition' in headers:
            cls = self.from_content_disposition(headers[b'Content-Disposition'])
        return cls

    def from_filename(self, filename):
        """Return the most appropriate Response class from a file name"""
        r = requests.get(filename)
        mimetype = sniffpy.sniff(r.content)
        m, encoding = self.mimetypes.guess_type(filename)
        if mimetype and not encoding:
            #return self.from_mimetype(mimetype)                                                                             
            return mimetype
        else:
            return Response

    def from_body(self, body):
        """Try to guess the appropriate response based on the body content.                                                  
        This method is a bit magic and could be improved in the future, but                                                  
        it's not meant to be used except for special cases where response types                                              
        cannot be guess using more straightforward methods."""
        chunk = body[:5000]
        chunk = to_bytes(chunk)
        if not binary_is_text(chunk):
            return self.from_mimetype('application/octet-stream')
-UUU:**--F1  repsonsetypes.py   49% L68    (Python ElDoc) -------------------------------------------------------------------


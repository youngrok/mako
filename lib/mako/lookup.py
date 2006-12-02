# lookup.py
# Copyright (C) 2006 Michael Bayer mike_mp@zzzcomputing.com
#
# This module is part of Mako and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

import os, stat, posixpath, re
from mako import exceptions, util
from mako.template import Template

try:
    import threading
except:
    import dummy_threading as threading
    
class TemplateCollection(object):
    def has_template(self, uri):
        try:
            self.get_template(uri)
            return True
        except exceptions.TemplateLookupException, e:
            return False
    def get_template(self, uri, relativeto=None):
        raise NotImplementedError()
        
class TemplateLookup(TemplateCollection):
    def __init__(self, directories=None, module_directory=None, filesystem_checks=False, collection_size=-1, format_exceptions=False, error_handler=None, output_encoding=None):
        self.directories = directories or []
        self.module_directory = module_directory
        self.filesystem_checks = filesystem_checks
        self.collection_size = collection_size
        self.template_args = {'format_exceptions':format_exceptions, 'error_handler':error_handler, 'output_encoding':output_encoding, 'module_directory':module_directory}
        if collection_size == -1:
            self.__collection = {}
        else:
            self.__collection = util.LRUCache(collection_size)
        self._mutex = threading.Lock()
        
    def get_template(self, uri, relativeto=None):
            try:
                if self.filesystem_checks:
                    return self.__check(uri, self.__collection[uri])
                else:
                    return self.__collection[uri]
            except KeyError:
                if uri[0] != '/':
                    u = uri
                    if relativeto is not None:
                        for dir in self.directories:
                            print relativeto[0:len(dir)]
                            if relativeto[0:len(dir)] == dir:
                                u = posixpath.join(posixpath.dirname(relativeto[len(dir) + 1:]), u)
                                break
                else:
                    u = re.sub(r'^\/+', '', uri)

                for dir in self.directories:
                    
                    srcfile = posixpath.join(dir, u)
                    if os.access(srcfile, os.F_OK):
                        return self.__load(srcfile, uri)
                else:
                    raise exceptions.TemplateLookupException("Cant locate template for uri '%s'" % uri)

    def __load(self, filename, uri):
        self._mutex.acquire()
        try:
            try:
                # try returning from collection one more time in case concurrent thread already loaded
                return self.__collection[uri]
            except KeyError:
                pass
            try:
                self.__collection[uri] = Template(identifier=uri, description=uri, filename=filename, lookup=self, **self.template_args)
                return self.__collection[uri]
            except:
                self.__collection.pop(uri, None)
                raise
        finally:
            self._mutex.release()
            
    def __check(self, uri, template):
        if template.filename is None:
            return template
        if not os.access(template.filename, os.F_OK):
            self.__collection.pop(uri, None)
            raise exceptions.TemplateLookupException("Cant locate template for uri '%s'" % uri)
        elif template.module._modified_time < os.stat(template.filename)[stat.ST_MTIME]:
            self.__collection.pop(uri, None)
            return self.__load(template.filename, uri)
        else:
            return template
            
    def put_string(self, uri, text):
        self.__collection[uri] = Template(text, lookup=self, description=uri, **self.template_args)
    def put_template(self, uri, template):
        self.__collection[uri] = template
            
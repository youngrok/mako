# template.py
# Copyright (C) 2006 Michael Bayer mike_mp@zzzcomputing.com
#
# This module is part of Mako and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""provides the Template class, a facade for parsing, generating and executing template strings,
as well as template runtime operations."""

from mako.lexer import Lexer
from mako.codegen import Compiler
from mako import runtime, util, exceptions
import imp, time, weakref, tempfile, shutil,  os, stat, posixpath, sys, re

_modules = weakref.WeakValueDictionary()
_inmemory_templates = weakref.WeakValueDictionary()

class _ModuleInfo(object):
    def __init__(self, module, module_filename, template, template_filename, module_source, template_source):
        self.module = module
        self.module_filename = module_filename
        self.template_filename = template_filename
        self.module_source = module_source
        self.template_source = template_source
        _modules[module.__name__] = template._mmarker = self
        if module_filename:
            _modules[module_filename] = self
    def _get_code(self):
        if self.module_source is not None:
            return self.module_source
        else:
            return file(self.module_filename).read()
    code = property(_get_code)
    def _get_source(self):
        if self.template_source is not None:
            return self.template_source
        else:
            return file(self.template_filename).read()
    source = property(_get_source)
    
class Template(object):
    """a compiled template"""
    def __init__(self, text=None, identifier=None, description=None, filename=None, format_exceptions=False, error_handler=None, lookup=None, output_encoding=None, module_directory=None):
        """construct a new Template instance using either literal template text, or a previously loaded template module
        
        text - textual template source, or None if a module is to be provided
        
        identifier - the "id" of this template. defaults to the 
        full filename given, or "memory:(hex id of this Template)" if no filename
        
        filename - filename of the source template, if any
        
        format_exceptions - catch exceptions and format them into an error display template
        """
        if identifier:
            self.identifier = re.sub(r'\W', "_", identifier)
        elif filename:
            self.identifier = re.sub(r'\W', "_", filename)
        else:
            self.identifier = "memory:" + hex(id(self))
            
        if text is not None:
            (code, module) = _compile_text(text, self.identifier, filename)
            _inmemory_templates[module.__name__] = self
            self._code = code
            self._source = text
            _ModuleInfo(module, None, self, filename, code, text)
        elif filename is not None:
            if module_directory is not None:
                path = posixpath.join(module_directory, self.identifier + ".py")
                filemtime = os.stat(filename)[stat.ST_MTIME]
                if not os.access(path, os.F_OK) or os.stat(path)[stat.ST_MTIME] < filemtime:
                    util.verify_directory(module_directory)
                    _compile_module_file(file(filename).read(), identifier, filename, path)
                module = imp.load_source(self.identifier, path, file(path))
                del sys.modules[self.identifier]
                _ModuleInfo(module, path, self, filename, None, None)
            else:
                (code, module) = _compile_text(file(filename).read(), self.identifier, filename)
                self._source = None
                self._code = code
                _ModuleInfo(module, None, self, filename, code, None)
        else:
            raise exceptions.RuntimeException("Template requires text or filename")

        self.module = module
        self.description = description
        self.filename = filename
        self.callable_ = self.module.render
        self.format_exceptions = format_exceptions
        self.error_handler = error_handler
        self.lookup = lookup
        self.output_encoding = output_encoding

    source = property(lambda self:_get_template_source(self.callable_), doc="""return the template source code for this Template.""")
    code = property(lambda self:_get_module_source_from_callable(self.callable_), doc="""return the module source code for this Template""")
        
    def render(self, *args, **data):
        """render the output of this template as a string.
        
        if the template specifies an output encoding, the string will be encoded accordingly, else the output
        is raw (raw output uses cStringIO and can't handle multibyte characters).
        a Context object is created corresponding to the given data.  Arguments that are explictly
        declared by this template's internal rendering method are also pulled from the given *args, **data 
        members."""
        return runtime._render(self, self.callable_, args, data)
    
    def render_unicode(self, *args, **data):
        """render the output of this template as a unicode object."""
        return runtime._render(self, self.callable_, args, data, as_unicode=True)
        
    def render_context(self, context, *args, **kwargs):
        """render this Template with the given context.  
        
        the data is written to the context's buffer."""
        runtime._render_context(self, self.callable_, context, *args, **kwargs)
        
    def get_def(self, name):
        """return a def of this template as an individual Template of its own."""
        return DefTemplate(self, getattr(self.module, "render_%s" % name))
        
class DefTemplate(Template):
    """a Template which represents a callable def in a parent template."""
    def __init__(self, parent, callable_):
        self.parent = parent
        self.callable_ = callable_
    def get_def(self, name):
        return self.parent.get_def(name)
        
def _compile_text(text, identifier, filename):
    node = Lexer(text, filename).parse()
    source = Compiler(node, filename).render()
    cid = identifier
    module = imp.new_module(cid)
    code = compile(source, cid, 'exec')
    exec code in module.__dict__, module.__dict__
    return (source, module)

def _compile_module_file(text, identifier, filename, outputpath):
    (dest, name) = tempfile.mkstemp()
    node = Lexer(text, filename).parse()
    source = Compiler(node, filename).render()
    os.write(dest, source)
    os.close(dest)
    shutil.move(name, outputpath)

def _get_module_info_from_callable(callable_):
    return _get_module_info(callable_.func_globals['__name__'])
    
def _get_module_info(filename):
    return _modules[filename]
        

# codegen.py
# Copyright (C) 2006 Michael Bayer mike_mp@zzzcomputing.com
#
# This module is part of Mako and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php

"""provides the Compiler object for generating module source code."""

import time
import re
from mako.pygen import PythonPrinter
from mako import util, ast, parsetree, filters

MAGIC_NUMBER = 1

class Compiler(object):
    def __init__(self, node, filename=None):
        self.node = node
        self.filename = filename
    def render(self):
        buf = util.FastEncodingBuffer()
        printer = PythonPrinter(buf)

        _GenerateRenderMethod(printer, self, self.node)

        return buf.getvalue()

        
class _GenerateRenderMethod(object):
    def __init__(self, printer, compiler, node):
        self.printer = printer
        self.last_source_line = -1
        self.compiler = compiler
        self.node = node
        
        if isinstance(node, parsetree.DefTag):
            name = "render_" + node.name
            args = node.function_decl.get_argument_expressions()
            self.in_def = True
            filtered = len(node.filter_args.args) > 0 
            buffered = eval(node.attributes.get('buffered', 'False'))
        else:
            name = "render"
            args = None
            self.in_def = False
            buffered = filtered = False
            
        if args is None:
            args = ['context', '**kwargs']
        else:
            args = [a for a in ['context'] + args + ['**kwargs']]

        if not self.in_def:
            defs = self.write_toplevel()
        else:
            defs = None
            
        self.write_render_callable(name, args, buffered, filtered)
        
        if defs is not None:
            for node in defs:
                _GenerateRenderMethod(printer, compiler, node)
            
    def write_toplevel(self):
        inherit = []
        namespaces = {}
        module_code = []
        class FindTopLevel(object):
            def visitInheritTag(s, node):
                inherit.append(node)
            def visitNamespaceTag(self, node):
                namespaces[node.name] = node
            def visitCode(self, node):
                if node.ismodule:
                    module_code.append(node)
        f = FindTopLevel()
        for n in self.node.nodes:
            n.accept_visitor(f)
        if len(module_code):
            self.write_module_code(module_code)

        self.compiler.namespaces = namespaces
        
        module_identifiers = _Identifiers()
        for n in module_code:
            module_identifiers = module_identifiers.branch(n)

        # module-level names, python code
        self.printer.writeline("from mako import runtime")
        self.printer.writeline("_magic_number = %s" % repr(MAGIC_NUMBER))
        self.printer.writeline("_modified_time = %s" % repr(time.time()))
        self.printer.writeline("_template_filename=%s" % repr(self.compiler.filename))
        self.printer.writeline("UNDEFINED = runtime.UNDEFINED")
        self.printer.writeline("from mako import filters")

        main_identifiers = module_identifiers.branch(self.node)
        module_identifiers.topleveldefs = module_identifiers.topleveldefs.union(main_identifiers.topleveldefs)
        [module_identifiers.declared.add(x) for x in ["UNDEFINED"]]
        self.compiler.identifiers = module_identifiers
        self.printer.writeline("_exports = %s" % repr([n.name for n in main_identifiers.topleveldefs]))
        self.printer.write("\n\n")

        if len(inherit):
            self.write_namespaces(namespaces)
            self.write_inherit(inherit[-1])
        elif len(namespaces):
            self.write_namespaces(namespaces)

        return main_identifiers.topleveldefs

    def write_render_callable(self, name, args, buffered, filtered):        
        self.printer.writeline("def %s(%s):" % (name, ','.join(args)))
        if buffered or filtered:
            self.printer.writeline("context.push_buffer()")
            self.printer.writeline("try:")

        self.identifiers = self.compiler.identifiers.branch(self.node)
        if not self.in_def and len(self.identifiers.locally_assigned) > 0:
            self.printer.writeline("__locals = {}")

        self.write_variable_declares(self.identifiers, first="kwargs")

        for n in self.node.nodes:
            n.accept_visitor(self)

        self.write_def_finish(self.node, buffered, filtered)
        self.printer.writeline(None)
        self.printer.write("\n\n")

        
    def write_module_code(self, module_code):
        for n in module_code:
            self.write_source_comment(n)
            self.printer.write_indented_block(n.text)

    def write_inherit(self, node):
        self.printer.writeline("def _inherit(context):")
        self.printer.writeline("generate_namespaces(context)")
        self.printer.writeline("return runtime.inherit_from(context, %s)" % (repr(node.attributes['file'])))
        self.printer.writeline(None)

    def write_namespaces(self, namespaces):
        self.printer.writelines(
            "def get_namespace(context, name):",
            "try:",
            "return context.namespaces[(render, name)]",
            "except KeyError:",
            "generate_namespaces(context)",
            "return context.namespaces[(render, name)]",
            None,None
            )
        self.printer.writeline("def generate_namespaces(context):")
        for node in namespaces.values():
            self.write_source_comment(node)
            if len(node.nodes):
                self.printer.writeline("def make_namespace():")
                export = []
                identifiers = self.compiler.identifiers.branch(node)
                class NSDefVisitor(object):
                    def visitDefTag(s, node):
                        self.write_inline_def(node, identifiers)
                        export.append(node.name)
                vis = NSDefVisitor()
                for n in node.nodes:
                    n.accept_visitor(vis)
                self.printer.writeline("return [%s]" % (','.join(export)))
                self.printer.writeline(None)
                callable_name = "make_namespace()"
            else:
                callable_name = "None"
            self.printer.writeline("ns = runtime.Namespace(%s, context.clean_inheritance_tokens(), templateuri=%s, callables=%s)" % (repr(node.name), node.parsed_attributes.get('file', 'None'), callable_name))
            if eval(node.attributes.get('inheritable', "False")):
                self.printer.writeline("context['self'].%s = ns" % (node.name))
            self.printer.writeline("context.namespaces[(render, %s)] = ns" % repr(node.name))
            self.printer.write("\n")
        if not len(namespaces):
            self.printer.writeline("pass")
        self.printer.writeline(None)
            
    def write_variable_declares(self, identifiers, first=None):
        """write variable declarations at the top of a function.
        
        the variable declarations are in the form of callable definitions for defs and/or
        name lookup within the function's context argument.  the names declared are based on the
        names that are referenced in the function body, which don't otherwise have any explicit
        assignment operation.  names that are assigned within the body are assumed to be 
        locally-scoped variables and are not separately declared.
        
        for def callable definitions, if the def is a top-level callable then a 
        'stub' callable is generated which wraps the current Context into a closure.  if the def
        is not top-level, it is fully rendered as a local closure."""
        
        # collection of all defs available to us in this scope
        comp_idents = dict([(c.name, c) for c in identifiers.defs])

        to_write = util.Set()
        
        # write "context.get()" for all variables we are going to need that arent in the namespace yet
        to_write = to_write.union(identifiers.undeclared)
        
        # write closure functions for closures that we define right here
        to_write = to_write.union(util.Set([c.name for c in identifiers.closuredefs]))

        # remove identifiers that are declared in the argument signature of the callable
        to_write = to_write.difference(identifiers.argument_declared)

        # remove identifiers that we are going to assign to.  in this way we mimic Python's behavior,
        # i.e. assignment to a variable within a block means that variable is now a "locally declared" var,
        # which cannot be referenced beforehand.  
        to_write = to_write.difference(identifiers.locally_declared)
        
        for ident in to_write:
            if ident in comp_idents:
                comp = comp_idents[ident]
                if comp.is_root():
                    self.write_def_decl(comp, identifiers)
                else:
                    self.write_inline_def(comp, identifiers)
            elif ident in self.compiler.namespaces:
                self.printer.writeline("%s = get_namespace(context, %s)" % (ident, repr(ident)))
            else:
                if first is not None:
                    self.printer.writeline("%s = %s.get(%s, context.get(%s, UNDEFINED))" % (ident, first, repr(ident), repr(ident)))
                else:
                    self.printer.writeline("%s = context.get(%s, UNDEFINED)" % (ident, repr(ident)))
        
    def write_source_comment(self, node):
        if self.last_source_line != node.lineno:
            self.printer.writeline("# SOURCE LINE %d" % node.lineno, is_comment=True)
            self.last_source_line = node.lineno

    def write_def_decl(self, node, identifiers):
        """write a locally-available callable referencing a top-level def"""
        funcname = node.function_decl.funcname
        namedecls = node.function_decl.get_argument_expressions()
        nameargs = node.function_decl.get_argument_expressions(include_defaults=False)
        if not self.in_def and len(self.identifiers.locally_assigned) > 0:
            nameargs.insert(0, 'context.locals_(__locals)')
        else:
            nameargs.insert(0, 'context')
        self.printer.writeline("def %s(%s):" % (funcname, ",".join(namedecls)))
        self.printer.writeline("return render_%s(%s)" % (funcname, ",".join(nameargs)))
        self.printer.writeline(None)
        
    def write_inline_def(self, node, identifiers):
        """write a locally-available def callable inside an enclosing def."""
        namedecls = node.function_decl.get_argument_expressions()
        self.printer.writeline("def %s(%s):" % (node.name, ",".join(namedecls)))
        filtered = len(node.filter_args.args) > 0 
        buffered = eval(node.attributes.get('buffered', 'False'))
        if buffered or filtered:
            printer.writeline("context.push_buffer()")
            printer.writeline("try:")

        identifiers = identifiers.branch(node)
        self.write_variable_declares(identifiers)

        for n in node.nodes:
            n.accept_visitor(self)

        self.write_def_finish(node, buffered, filtered)
        self.printer.writeline(None)
        
    def write_def_finish(self, node, buffered, filtered):
        if not buffered:
            self.printer.writeline("return ''")
        if buffered or filtered:
            self.printer.writeline("finally:")
            self.printer.writeline("_buf = context.pop_buffer()")
            s = "_buf.getvalue()"
            if filtered:
                s = self.create_filter_callable(node.filter_args.args, s)
            if buffered:
                self.printer.writeline("return %s" % s)
            else:
                self.printer.writeline("context.write(%s)" % s)
            self.printer.writeline(None)
    
    def create_filter_callable(self, args, target):
        d = dict([(k, "filters." + v.func_name) for k, v in filters.DEFAULT_ESCAPES.iteritems()])
        for e in args:
            e = d.get(e, e)
            target = "%s(%s)" % (e, target)
        return target
        
    def visitExpression(self, node):
        self.write_source_comment(node)
        if len(node.escapes):
            s = self.create_filter_callable(node.escapes_code.args, node.text)
            self.printer.writeline("context.write(unicode(%s))" % s)
        else:
            self.printer.writeline("context.write(unicode(%s))" % node.text)
            
    def visitControlLine(self, node):
        if node.isend:
            self.printer.writeline(None)
        else:
            self.write_source_comment(node)
            self.printer.writeline(node.text)
    def visitText(self, node):
        self.write_source_comment(node)
        self.printer.writeline("context.write(%s)" % repr(node.content))
    def visitCode(self, node):
        if not node.ismodule:
            self.write_source_comment(node)
            self.printer.write_indented_block(node.text)

            if not self.in_def and len(self.identifiers.locally_assigned) > 0:
                # if we are the "template" def, fudge locally declared/modified variables into the "__locals" dictionary,
                # which is used for def calls within the same template, to simulate "enclosing scope"
                #self.printer.writeline('__locals.update(%s)' % (",".join(["%s=%s" % (x, x) for x in node.declared_identifiers()])))
                self.printer.writeline('__locals.update(dict([(k, v) for k, v in locals().iteritems() if k in [%s]]))' % ','.join([repr(x) for x in node.declared_identifiers()]))
                
    def visitIncludeTag(self, node):
        self.write_source_comment(node)
        self.printer.writeline("runtime.include_file(context, %s, import_symbols=%s)" % (node.parsed_attributes['file'], repr(node.attributes.get('import', False))))

    def visitNamespaceTag(self, node):
        pass
            
    def visitDefTag(self, node):
        pass

    def visitCallTag(self, node):
        self.write_source_comment(node)
        self.printer.writeline("def ccall(context):")
        export = ['body']
        identifiers = self.identifiers.branch(node)
        class DefVisitor(object):
            def visitDefTag(s, node):
                self.write_inline_def(node, identifiers)
                export.append(node.name)
        vis = DefVisitor()
        for n in node.nodes:
            n.accept_visitor(vis)
        self.printer.writeline("def body(**kwargs):")
        body_identifiers = identifiers.branch(node, includedefs=False, includenode=False)
        # TODO: figure out best way to specify buffering/nonbuffering (at call time would be better)
        buffered = False
        if buffered:
            self.printer.writeline("context.push_buffer()")
            self.printer.writeline("try:")
        self.write_variable_declares(body_identifiers, first="kwargs")
        for n in node.nodes:
            n.accept_visitor(self)
        self.write_def_finish(node, buffered, False)
        self.printer.writeline(None)
        self.printer.writeline("return [%s]" % (','.join(export)))
        self.printer.writeline(None)
        self.printer.writeline("__cl = context.locals_({})")
        self.printer.writeline("context.push({'caller':runtime.Namespace('caller', __cl, callables=ccall(__cl))})")
        self.printer.writeline("try:")
        self.printer.writeline("context.write(unicode(%s))" % node.attributes['expr'])
        self.printer.writeline("finally:")
        self.printer.writeline("context.pop()")
        self.printer.writeline(None)

class _Identifiers(object):
    """tracks the status of identifier names as template code is rendered."""
    def __init__(self, node=None, parent=None, includedefs=True, includenode=True):
        if parent is not None:
            # things that have already been declared in an enclosing namespace (i.e. names we can just use)
            self.declared = util.Set(parent.declared).union([c.name for c in parent.closuredefs]).union(parent.locally_declared)
            
            # top level defs that are available
            self.topleveldefs = util.Set(parent.topleveldefs)
        else:
            self.declared = util.Set()
            self.topleveldefs = util.Set()
        
        # things within this level that are referenced before they are declared (e.g. assigned to)
        self.undeclared = util.Set()
        
        # things that are declared locally.  some of these things could be in the "undeclared"
        # list as well if they are referenced before declared
        self.locally_declared = util.Set()
    
        # assignments made in explicit python blocks.  these will be propigated to 
        # the context of local def calls.
        self.locally_assigned = util.Set()
        
        # things that are declared in the argument signature of the def callable
        self.argument_declared = util.Set()
        
        # closure defs that are defined in this level
        self.closuredefs = util.Set()
        
        self.node = node
        self.includedefs = includedefs
        if node is not None:
            if includenode:
                node.accept_visitor(self)
            else:
                for n in node.nodes:
                    n.accept_visitor(self)
        
    def branch(self, node, **kwargs):
        """create a new Identifiers for a new Node, with this Identifiers as the parent."""
        return _Identifiers(node, self, **kwargs)
        
    defs = property(lambda s:s.topleveldefs.union(s.closuredefs))
    
    def __repr__(self):
        return "Identifiers(%s, %s, %s, %s, %s)" % (repr(list(self.declared)), repr(list(self.locally_declared)), repr(list(self.undeclared)), repr([c.name for c in self.topleveldefs]), repr([c.name for c in self.closuredefs]))
        
    def check_declared(self, node):
        """update the state of this Identifiers with the undeclared and declared identifiers of the given node."""
        for ident in node.undeclared_identifiers():
            if ident != 'context' and ident not in self.declared.union(self.locally_declared):
                self.undeclared.add(ident)
        for ident in node.declared_identifiers():
            self.locally_declared.add(ident)
                
    def visitExpression(self, node):
        self.check_declared(node)
    def visitControlLine(self, node):
        self.check_declared(node)
    def visitCode(self, node):
        if not node.ismodule:
            self.check_declared(node)
            self.locally_assigned = self.locally_assigned.union(node.declared_identifiers())
    def visitDefTag(self, node):
        if not self.includedefs:
            return
        if node.is_root():
            self.topleveldefs.add(node)
        elif node is not self.node:
            self.closuredefs.add(node)
        for ident in node.undeclared_identifiers():
            if ident != 'context' and ident not in self.declared.union(self.locally_declared):
                self.undeclared.add(ident)
        for ident in node.declared_identifiers():
            self.argument_declared.add(ident)
        # visit defs only one level deep
        if node is self.node:
            for n in node.nodes:
                n.accept_visitor(self)
    def visitIncludeTag(self, node):
        self.check_declared(node)
                
    def visitCallTag(self, node):
        self.check_declared(node)
        if node is self.node:
            for n in node.nodes:
                n.accept_visitor(self)
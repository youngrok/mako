import unittest

from mako import ast, util
from compiler import parse

class AstParseTest(unittest.TestCase):
    def setUp(self):
        pass
    def tearDown(self):
        pass
    def test_locate_identifiers(self):
        """test the location of identifiers in a python code string"""
        code = """
a = 10
b = 5
c = x * 5 + a + b + q
(g,h,i) = (1,2,3)
[u,k,j] = [4,5,6]
foo.hoho.lala.bar = 7 + gah.blah + u + blah
for lar in (1,2,3):
    gh = 5
    x = 12
print "hello world, ", a, b
print "Another expr", c
"""
        parsed = ast.PythonCode(code)
        assert parsed.declared_identifiers == util.Set(['a','b','c', 'g', 'h', 'i', 'u', 'k', 'j', 'gh', 'lar'])
        assert parsed.undeclared_identifiers == util.Set(['x', 'q', 'foo', 'gah', 'blah'])
    
        parsed = ast.PythonCode("x + 5 * (y-z)")
        assert parsed.undeclared_identifiers == util.Set(['x', 'y', 'z'])
        assert parsed.declared_identifiers == util.Set()

    def test_locate_identifiers_2(self):
        code = """
result = []
data = get_data()
for x in data:
    result.append(x+7)
"""
        parsed = ast.PythonCode(code)
        assert parsed.undeclared_identifiers == util.Set(['get_data'])
        assert parsed.declared_identifiers == util.Set(['result', 'data', 'x'])
        
    def test_function_decl(self):
        """test getting the arguments from a function"""
        code = "def foo(a, b, c=None, d='hi', e=x, f=y+7):pass"
        parsed = ast.FunctionDecl(code)
        assert parsed.funcname=='foo'
        assert parsed.argnames==['a', 'b', 'c', 'd', 'e', 'f']
    
    def test_expr_generate(self):
        """test the round trip of expressions to AST back to python source"""
        x = 1
        y = 2
        class F(object):
            def bar(self, a,b):
                return a + b
        def lala(arg):
            return "blah" + arg
        local_dict = dict(x=x, y=y, foo=F(), lala=lala)
        
        code = "str((x+7*y) / foo.bar(5,6)) + lala('ho')"
        astnode = parse(code)
        newcode = ast.ExpressionGenerator(astnode).value()
        #print "newcode:" + newcode
        #print "result:" + eval(code, local_dict)
        assert (eval(code, local_dict) == eval(newcode, local_dict))
        
        a = ["one", "two", "three"]
        hoho = {'somevalue':"asdf"}
        g = [1,2,3,4,5]
        local_dict = dict(a=a,hoho=hoho,g=g)
        code = "a[2] + hoho['somevalue'] + repr(g[3:5]) + repr(g[3:]) + repr(g[:5])"
        astnode = parse(code)
        newcode = ast.ExpressionGenerator(astnode).value()
        print newcode
        print "result:", eval(code, local_dict)
        assert(eval(code, local_dict) == eval(newcode, local_dict))
        
if __name__ == '__main__':
    unittest.main()
    
    
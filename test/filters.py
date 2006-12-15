from mako.template import Template
import unittest
from util import result_lines, flatten_result

class FilterTest(unittest.TestCase):
    def test_basic(self):
        t = Template("""
        ${x | myfilter}
""")
        print t.code
        print t.render(x="this is x", myfilter=lambda t: "MYFILTER->%s<-MYFILTER" % t)

    def test_expr(self):
        """test filters that are themselves expressions"""
        t = Template("""
        ${x | myfilter(y)}
""")
        def myfilter(y):
            return lambda x: "MYFILTER->%s<-%s" % (x, y)
        assert flatten_result(t.render(x="this is x", myfilter=myfilter, y="this is y")) == "MYFILTER->this is x<-this is y"

    def test_def(self):
        t = Template("""
            <%def name="foo" filter="myfilter">
                this is foo
            </%def>
            ${foo()}
""")
        assert flatten_result(t.render(x="this is x", myfilter=lambda t: "MYFILTER->%s<-MYFILTER" % t)) == "MYFILTER-> this is foo <-MYFILTER"

    def test_builtins(self):
        t = Template("""
            ${"this is <text>" | h}
""")
        assert flatten_result(t.render()) == "this is &lt;text&gt;"
        
        t = Template("""
            http://foo.com/arg1=${"hi! this is a string." | u}
""")
        assert flatten_result(t.render()) == "http://foo.com/arg1=hi%21+this+is+a+string."

class BufferTest(unittest.TestCase):        
    def test_buffered_def(self):
        t = Template("""
            <%def name="foo" buffered="True">
                this is foo
            </%def>
            ${"hi->" + foo() + "<-hi"}
""")
        assert flatten_result(t.render()) == "hi-> this is foo <-hi"

    def test_unbuffered_def(self):
        t = Template("""
            <%def name="foo" buffered="False">
                this is foo
            </%def>
            ${"hi->" + foo() + "<-hi"}
""")
        assert flatten_result(t.render()) == "this is foo hi-><-hi"

    def test_capture(self):
        t = Template("""
            <%def name="foo" buffered="False">
                this is foo
            </%def>
            ${"hi->" + capture(foo) + "<-hi"}
""")
        assert flatten_result(t.render()) == "hi-> this is foo <-hi"

    def test_capture_exception(self):
        template = Template("""
            <%def name="a()">
                this is a
                <% 
                    raise TypeError("hi")
                %>
            </%def>
            <%
                c = capture(a)
            %>
            a->${c}<-a
        """)
        try:
            template.render()
            assert False
        except TypeError:
            assert True
    
    def test_buffered_exception(self):
        template = Template("""
            <%def name="a()" buffered="True">
                <%
                    raise TypeError("hi")
                %>
            </%def>
            
            ${a()}
            
""") 
        try:
            print template.render()
            assert False
        except TypeError:
            assert True
            
    def test_capture_ccall(self):
        t = Template("""
            <%def name="foo">
                <%
                    x = capture(caller.body)
                %>
                this is foo.  body: ${x}
            </%def>

            <%call expr="foo()">
                ccall body
            </%call>
""")
        
        print t.render()
        
if __name__ == '__main__':
    unittest.main()
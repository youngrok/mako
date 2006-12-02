from mako.template import Template
from mako import lookup
from util import flatten_result, result_lines
import unittest

import os

if not os.access('./test_htdocs', os.F_OK):
    os.mkdir('./test_htdocs')
    file('./test_htdocs/index.html', 'w').write("this is index")
    file('./test_htdocs/incl.html', 'w').write("this is include 1")
    os.mkdir('./test_htdocs/subdir')
    file('./test_htdocs/subdir/incl.html', 'w').write("""
        this is include 2
    """)
    file('./test_htdocs/subdir/index.html', 'w').write("""
        this is sub index
        <%include file="incl.html"/>
    """)
tl = lookup.TemplateLookup(directories=['./test_htdocs'])
class LookupTest(unittest.TestCase):
    def test_basic(self):
        t = tl.get_template('index.html')
        assert result_lines(t.render()) == [
            "this is index"
        ]
    def test_subdir(self):
        t = tl.get_template('/subdir/index.html')
        assert result_lines(t.render()) == [
            "this is sub index",
            "this is include 2"
        ]
        assert tl.get_template('/subdir/index.html').identifier == 'subdir_index_html'

        t2 = tl.get_template('./subdir/index.html')
        
if __name__ == '__main__':
    unittest.main()
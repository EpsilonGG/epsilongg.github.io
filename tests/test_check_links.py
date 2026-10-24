"""站内链接检查脚本的单元测试。

全部用临时目录搭一个假 dist，不联网。

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_links as checker  # noqa: E402


class ParserTest(unittest.TestCase):
    def test_collects_href_and_src(self) -> None:
        html = '<a href="/blog/">x</a><img src="/a.png"><script src="/s.js"></script>'
        self.assertEqual(checker.parse_html(html).links, ['/blog/', '/a.png', '/s.js'])

    def test_srcset_is_split(self) -> None:
        html = '<img src="/a.jpg" srcset="/a-600.webp 600w, /a-960.webp 960w">'
        self.assertEqual(
            checker.parse_html(html).links,
            ['/a.jpg', '/a-600.webp', '/a-960.webp'],
        )

    def test_collects_ids_and_anchor_names(self) -> None:
        html = '<h2 id="标题">x</h2><a name="old"></a>'
        parser = checker.parse_html(html)
        self.assertEqual(parser.ids, {'标题'})
        self.assertEqual(parser.anchor_names, {'old'})

    def test_skips_mailto_and_external(self) -> None:
        self.assertTrue(checker.is_skipped('mailto:a@b.c'))
        self.assertTrue(checker.is_skipped('//cdn.example.com/x.js'))
        self.assertFalse(checker.is_skipped('#anchor'))
        self.assertFalse(checker.is_skipped('/blog/'))


class ResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dist = Path(self._tmp.name)
        (self.dist / 'blog' / 'a').mkdir(parents=True)
        (self.dist / 'blog' / 'a' / 'index.html').write_text('<p id="x">a</p>', encoding='utf-8')
        (self.dist / 'blog' / 'index.html').write_text('<p>b</p>', encoding='utf-8')
        (self.dist / 'rss.xml').write_text('<rss/>', encoding='utf-8')
        (self.dist / '404.html').write_text('<p>404</p>', encoding='utf-8')

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_directory_becomes_index(self) -> None:
        target = checker.resolve(self.dist, '/', '/blog/')
        self.assertEqual(target, self.dist / 'blog' / 'index.html')

    def test_extension_file(self) -> None:
        self.assertEqual(checker.resolve(self.dist, '/', '/rss.xml'), self.dist / 'rss.xml')

    def test_relative_path(self) -> None:
        target = checker.resolve(self.dist, '/blog/a/', '../')
        self.assertEqual(target, self.dist / 'blog' / 'index.html')

    def test_missing_returns_none(self) -> None:
        self.assertIsNone(checker.resolve(self.dist, '/', '/nope/'))

    def test_percent_encoded_path(self) -> None:
        (self.dist / '笔记').mkdir()
        (self.dist / '笔记' / 'index.html').write_text('<p>c</p>', encoding='utf-8')
        self.assertIsNotNone(checker.resolve(self.dist, '/', '/%E7%AC%94%E8%AE%B0/'))


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dist = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, html: str) -> None:
        path = self.dist / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding='utf-8')

    def test_clean_site_passes(self) -> None:
        self.write('index.html', '<a href="/blog/">x</a>')
        self.write('blog/index.html', '<a href="/">home</a>')
        issues, stats = checker.check(self.dist)
        self.assertEqual(issues, [])
        self.assertEqual(stats['pages'], 2)

    def test_missing_page_is_reported(self) -> None:
        self.write('index.html', '<a href="/gone/">x</a>')
        issues, _ = checker.check(self.dist)
        self.assertEqual([i['kind'] for i in issues], ['missing'])
        self.assertEqual(issues[0]['url'], '/gone/')

    def test_missing_anchor_is_reported(self) -> None:
        self.write('index.html', '<a href="/blog/#nope">x</a>')
        self.write('blog/index.html', '<h2 id="yep">y</h2>')
        issues, _ = checker.check(self.dist)
        self.assertEqual([i['kind'] for i in issues], ['anchor'])

    def test_existing_anchor_passes(self) -> None:
        self.write('index.html', '<a href="/blog/#标题">x</a>')
        self.write('blog/index.html', '<h2 id="标题">y</h2>')
        issues, _ = checker.check(self.dist)
        self.assertEqual(issues, [])

    def test_same_page_anchor_passes(self) -> None:
        self.write('index.html', '<a href="#top">x</a><h1 id="top">t</h1>')
        issues, _ = checker.check(self.dist)
        self.assertEqual(issues, [])

    def test_anchors_can_be_skipped(self) -> None:
        self.write('index.html', '<a href="/blog/#nope">x</a>')
        self.write('blog/index.html', '<h2 id="yep">y</h2>')
        issues, _ = checker.check(self.dist, check_anchors=False)
        self.assertEqual(issues, [])

    def test_external_links_are_skipped(self) -> None:
        self.write('index.html', '<a href="https://example.com/x">x</a><a href="mailto:a@b.c">m</a>')
        issues, stats = checker.check(self.dist)
        self.assertEqual(issues, [])
        self.assertEqual(stats['external'], 1)

    def test_own_origin_is_checked_when_given(self) -> None:
        self.write('index.html', '<a href="https://me.example/gone/">x</a>')
        issues, _ = checker.check(self.dist, origin='https://me.example')
        self.assertEqual([i['kind'] for i in issues], ['missing'])

    def test_query_string_is_ignored(self) -> None:
        self.write('index.html', '<a href="/blog/?from=home">x</a>')
        self.write('blog/index.html', '<p>b</p>')
        issues, _ = checker.check(self.dist)
        self.assertEqual(issues, [])


if __name__ == '__main__':
    unittest.main()

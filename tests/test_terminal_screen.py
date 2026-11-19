import importlib.util
import unittest

from orchestra.terminal_screen import TerminalScreen


@unittest.skipUnless(importlib.util.find_spec("pyte"), "terminal support requires pyte")
class TerminalScreenTest(unittest.TestCase):
    def setUp(self):
        import pyte

        self.replies = []
        self.screen = TerminalScreen(pyte, 40, 8, self.replies.append)
        self.stream = pyte.ByteStream(self.screen)

    def test_alternate_screen_restores_primary_content_and_cursor(self):
        self.stream.feed(b"primary\x1b[3;4H")
        self.stream.feed(b"\x1b[?10")
        self.stream.feed(b"49hfullscreen")
        self.assertIn("fullscreen", self.screen.display[0])
        self.assertNotIn("primary", self.screen.display[0])
        self.screen.resize(10, 54)
        self.stream.feed(b"\x1b[?1049l")
        self.assertIn("primary", self.screen.display[0])
        self.assertNotIn("fullscreen", self.screen.display[0])
        self.assertEqual((self.screen.cursor.y, self.screen.cursor.x), (2, 3))
        self.assertEqual((self.screen.lines, self.screen.columns), (10, 54))

    def test_cursor_queries_reply_on_active_buffer(self):
        self.stream.feed(b"\x1b[?1049h\x1b[3;4H\x1b[6n\x1b[?6n\x1b[c")
        self.assertEqual(self.replies, ["\x1b[3;4R", "\x1b[?3;4R", "\x1b[?6c"])

    def test_resize_keeps_prompt_visible_or_moves_it_to_scrollback(self):
        self.stream.feed(b"old prompt\x1b[2;1Hcurrent")
        self.screen.resize(4, 30)
        self.assertIn("old prompt", self.screen.display[0])
        self.assertIn("current", self.screen.display[1])
        self.stream.feed(b"\x1b[4;1H")
        self.screen.resize(3, 30)
        self.assertIn("current", self.screen.display[0])
        self.assertEqual(self.screen.cursor.y, 2)
        self.assertIn("old prompt", "".join(char.data for char in self.screen.history.top[-1].values()))

    def test_cached_events_match_pyte_through_style_scroll_and_paging(self):
        import pyte

        original = pyte.HistoryScreen(40, 8, history=1500)
        stream = pyte.ByteStream(original)
        data = (
            ("\x1b[4;38;2;220;30;110m한글 e\u0301\x1b[0m\r\n" * 30)
            + "\x1b[2;7r\x1b[7;4H\x1b[7mright\r\nleft\x1b[0m\x1b[r\x1b[?25l"
        ).encode()

        def compare():
            self.assertEqual(self.screen.display, original.display)
            self.assertEqual(self.screen.buffer, original.buffer)
            self.assertEqual(self.screen.history, original.history)
            self.assertEqual((self.screen.cursor.x, self.screen.cursor.y, self.screen.cursor.hidden),
                             (original.cursor.x, original.cursor.y, original.cursor.hidden))

        for index in range(0, len(data), 7):
            chunk = data[index:index + 7]
            stream.feed(chunk)
            self.stream.feed(chunk)
        compare()
        original.prev_page()
        self.screen.prev_page()
        compare()
        stream.feed(b"\x1b[?25h\x1b[7;2Hnext")
        self.stream.feed(b"\x1b[?25h\x1b[7;2Hnext")
        compare()

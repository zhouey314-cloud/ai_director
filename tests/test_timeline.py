import unittest

from modules.timeline_editor import merge_silence_and_ai_cuts


class TimelineTests(unittest.TestCase):
    def test_silence_is_removed_and_remaining_segments_are_kept(self):
        result = merge_silence_and_ai_cuts([(1.0, 2.0)], [], 4.0)
        self.assertEqual(result, [(0.0, 1.0), (2.0, 4.0)])

    def test_overlapping_ai_and_silence_cuts_are_merged(self):
        result = merge_silence_and_ai_cuts([(1.0, 2.0)], [(1.8, 2.5, 'filler')], 4.0)
        self.assertEqual(result, [(0.0, 1.0), (2.5, 4.0)])


if __name__ == '__main__':
    unittest.main()

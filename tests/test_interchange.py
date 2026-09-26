import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from modules.video_renderer import generate_edl, generate_fcpxml, generate_srt


class InterchangeTests(unittest.TestCase):
    def test_subtitles_follow_the_edited_timeline(self):
        transcript = {
            'segments': [
                {'start': 0.1, 'end': 0.5, 'text': 'First clip'},
                {'start': 3.1, 'end': 3.5, 'text': 'Second clip'},
            ]
        }
        keeps = [(0.0, 1.0), (3.0, 4.0)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'edited.srt'
            generate_srt(transcript, keeps, str(path))
            subtitles = path.read_text(encoding='utf-8')
        self.assertIn('00:00:00,100 --> 00:00:00,500\nFirst clip', subtitles)
        self.assertIn('00:00:01,100 --> 00:00:01,500\nSecond clip', subtitles)
        self.assertNotIn('00:00:03,100', subtitles)

    def test_interchange_exports_contain_both_kept_clips(self):
        keeps = [(0.0, 1.0), (3.0, 4.0)]
        with tempfile.TemporaryDirectory() as directory:
            edl = Path(directory) / 'edited.edl'
            xml = Path(directory) / 'edited.fcpxml'
            generate_edl(keeps, 'synthetic-input.mp4', str(edl))
            generate_fcpxml(keeps, 'synthetic-input.mp4', str(xml), total_duration=4.0)
            edl_text = edl.read_text(encoding='utf-8')
            root = ET.parse(xml).getroot()
        self.assertIn('00:00:03:00 00:00:04:00 00:00:01:00 00:00:02:00', edl_text)
        self.assertEqual(root.tag, 'fcpxml')
        self.assertEqual(len(root.findall('.//clip')), 2)


if __name__ == '__main__':
    unittest.main()

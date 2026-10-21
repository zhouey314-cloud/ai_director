import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from modules.video_renderer import generate_edl, generate_fcpxml, generate_srt


class InterchangeTests(unittest.TestCase):
    def test_fcpxml_quotes_in_filename_keep_xml_parseable(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic "quoted" clip.mp4'
            output = Path(directory) / 'edited.fcpxml'
            generate_fcpxml([(0.0, 1.0)], str(source), str(output), total_duration=1.0)
            root = ET.parse(output).getroot()
        self.assertEqual(root.find('.//asset').get('name'), source.name)
        self.assertEqual(root.find('.//clip').get('name'), source.name)
        self.assertEqual(root.find('.//project').get('name'), 'AI_Edit_' + source.stem)

    def test_fcpxml_special_path_is_a_single_correct_file_uri(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic 中文 & #clip%.mp4'
            output = Path(directory) / 'edited.fcpxml'
            generate_fcpxml([(0.0, 1.0)], str(source), str(output), total_duration=1.0)
            asset = ET.parse(output).getroot().find('.//asset')
        self.assertEqual(asset.get('src'), source.resolve().as_uri())
        self.assertEqual(asset.get('name'), source.name)

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

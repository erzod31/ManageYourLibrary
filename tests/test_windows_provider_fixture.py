"""Keep native lifetime checks strict and independent of desktop packer space."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.verify_windows_accessibility_provider import recreated_child_identity


class WindowsProviderFixtureTests(unittest.TestCase):
    def fixture(self, rows, mapped=(True, True)):
        root = SimpleNamespace(update=Mock())
        buttons = [SimpleNamespace(place=Mock(), destroy=Mock(), winfo_ismapped=Mock(return_value=value))
                   for value in mapped]
        snapshot = Mock(side_effect=[{'children': values} for values in rows])
        with patch('tkinter.Button', side_effect=buttons) as constructor:
            evidence = recreated_child_identity(root, snapshot, Mock())
        for button in buttons:
            button.place.assert_called_once_with(x=8, y=8, width=240, height=36)
            button.destroy.assert_called_once_with()
        self.assertEqual(constructor.call_count, 2)
        self.assertEqual(constructor.call_args_list[0].kwargs['name'], constructor.call_args_list[1].kwargs['name'])
        return evidence

    def test_both_mapped_incarnations_must_have_increasing_ids(self):
        rows = [[{'name': 'MYL_QA_identity_before', 'id': 41}],
                [{'name': 'MYL_QA_identity_after', 'id': 42}]]
        evidence = self.fixture(rows)
        self.assertTrue(evidence['passed'])
        self.assertEqual(evidence['before']['id'], 41)
        self.assertEqual(evidence['after']['id'], 42)
        for mapped in ((False, True), (True, False)):
            self.assertFalse(self.fixture(rows, mapped)['passed'])

    def test_reused_or_missing_ids_are_failures_not_skips(self):
        for second in ([{'name': 'MYL_QA_identity_after', 'id': 41}], []):
            evidence = self.fixture([[{'name': 'MYL_QA_identity_before', 'id': 41}], second])
            self.assertFalse(evidence['passed'])

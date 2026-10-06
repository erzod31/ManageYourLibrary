import threading
import unittest
from typing import get_type_hints

from core import contracts, performance_pipeline
from core.ui_events import UiEventQueue


class InternalContractTests(unittest.TestCase):
    def test_analysis_payload_contract_matches_runtime_shape(self):
        payload = performance_pipeline.make_analysis_result(
            "book.epub",
            performance_pipeline.FAST_OK,
            title="Book",
        )

        self.assertEqual(set(payload), set(contracts.AnalysisResultPayload.__required_keys__))

    def test_progress_contract_has_no_optional_fields(self):
        self.assertEqual(
            contracts.BatchProgressEvent.__required_keys__,
            frozenset({"phase", "completed", "total", "path", "status"}),
        )
        self.assertEqual(contracts.BatchProgressEvent.__optional_keys__, frozenset())

    def test_public_pipeline_annotations_reference_contracts(self):
        hints = get_type_hints(performance_pipeline.process_fast_batch)

        self.assertEqual(hints["event_callback"], contracts.ProgressCallback | None)
        self.assertIn("return", hints)

    def test_ui_event_queue_is_exposed_from_compatibility_module(self):
        self.assertIs(performance_pipeline.UiEventQueue, UiEventQueue)

    def test_ui_event_queue_preserves_post_order(self):
        queue = UiEventQueue()
        received = []
        worker = threading.Thread(
            target=lambda: [queue.post(received.append, value) for value in range(3)],
        )
        worker.start()
        worker.join()

        self.assertEqual(queue.drain(), 3)
        self.assertEqual(received, [0, 1, 2])


if __name__ == "__main__":
    unittest.main()

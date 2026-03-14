from __future__ import annotations

import unittest

from edge_device.capture.camera import CapturedFrame
from edge_device.compression.event_compressor import EventCompressor
from edge_device.inference.detector import Detection
from edge_device.tracking.tracker import LightweightTracker


class EdgeEventQualityIntegrationTests(unittest.TestCase):
    @staticmethod
    def _frame() -> CapturedFrame:
        return CapturedFrame(
            frame_id="frame-000001",
            captured_at="2026-03-14T06:30:00Z",
            width=1000,
            height=600,
            source="stub://camera",
            pixel_format="rgb24",
        )

    def test_track_id_is_stable_on_consecutive_frames(self) -> None:
        tracker = LightweightTracker(
            iou_threshold=0.2,
            max_missed_frames=4,
            zone_layout="entry_door:0.0-0.6,hallway:0.6-1.0",
        )
        frames = [
            Detection("person", "person", 0.91, (120, 80, 300, 520)),
            Detection("person", "person", 0.92, (130, 80, 310, 520)),
            Detection("person", "person", 0.94, (145, 80, 325, 520)),
        ]

        assigned = [
            tracker.assign_tracks([det], frame_width=1000)[0]
            for det in frames
        ]

        track_ids = [item.track_id for item in assigned]
        self.assertEqual(len(set(track_ids)), 1)
        self.assertEqual(assigned[0].zone_id, "entry_door")

    def test_zone_mapping_uses_bbox_center(self) -> None:
        tracker = LightweightTracker(
            iou_threshold=0.2,
            max_missed_frames=4,
            zone_layout="entry_door:0.0-0.5,hallway:0.5-1.0",
        )
        detections = [
            Detection("person", "person", 0.85, (120, 90, 280, 510)),
            Detection("package", "package", 0.88, (700, 120, 900, 520)),
        ]
        assigned = tracker.assign_tracks(detections, frame_width=1000)

        self.assertEqual(assigned[0].zone_id, "entry_door")
        self.assertEqual(assigned[1].zone_id, "hallway")
        self.assertNotEqual(assigned[0].track_id, assigned[1].track_id)

    def test_event_compression_policy_is_configurable(self) -> None:
        frame = self._frame()
        primary = Detection(
            object_name="person",
            object_class="person",
            confidence=0.93,
            bbox=(120, 80, 300, 520),
            zone_id="entry_door",
            track_id="trk-00001",
        )
        low_conf = Detection(
            object_name="person",
            object_class="person",
            confidence=0.61,
            bbox=(120, 80, 300, 520),
            zone_id="entry_door",
            track_id="trk-00001",
        )

        dedupe_times = iter([100.0, 100.3, 101.7])
        dedupe_compressor = EventCompressor(
            min_confidence=0.8,
            dedupe_window_sec=1.0,
            throttle_window_sec=0.0,
            time_provider=lambda: next(dedupe_times),
        )
        first = dedupe_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=1,
            frame=frame,
            detections=[primary],
            snapshot_uri="file:///tmp/first.jpg",
        )
        deduped = dedupe_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=2,
            frame=frame,
            detections=[primary],
            snapshot_uri="file:///tmp/second.jpg",
        )
        recovered = dedupe_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=3,
            frame=frame,
            detections=[primary],
            snapshot_uri="file:///tmp/third.jpg",
        )

        self.assertEqual(first["payload"]["event_type"], "object_detected")
        self.assertEqual(deduped["payload"]["event_type"], "scene_observed")
        self.assertIn("deduplicated", deduped["payload"]["compress_reason"])
        self.assertEqual(recovered["payload"]["event_type"], "object_detected")

        threshold_times = iter([200.0])
        threshold_compressor = EventCompressor(
            min_confidence=0.8,
            dedupe_window_sec=0.0,
            throttle_window_sec=0.0,
            time_provider=lambda: next(threshold_times),
        )
        low = threshold_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=4,
            frame=frame,
            detections=[low_conf],
            snapshot_uri="file:///tmp/low.jpg",
        )
        self.assertEqual(low["payload"]["event_type"], "scene_observed")
        self.assertIn("below_conf_threshold", low["payload"]["compress_reason"])

        throttle_times = iter([300.0, 300.2, 301.4])
        throttle_compressor = EventCompressor(
            min_confidence=0.5,
            dedupe_window_sec=0.0,
            throttle_window_sec=1.0,
            time_provider=lambda: next(throttle_times),
        )
        emitted = throttle_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=5,
            frame=frame,
            detections=[primary],
            snapshot_uri="file:///tmp/throttle-first.jpg",
        )
        throttled = throttle_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=6,
            frame=frame,
            detections=[primary],
            snapshot_uri="file:///tmp/throttle-second.jpg",
        )
        resumed = throttle_compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=7,
            frame=frame,
            detections=[primary],
            snapshot_uri="file:///tmp/throttle-third.jpg",
        )

        self.assertEqual(emitted["payload"]["event_type"], "object_detected")
        self.assertEqual(throttled["payload"]["event_type"], "scene_observed")
        self.assertIn("throttled", throttled["payload"]["compress_reason"])
        self.assertEqual(resumed["payload"]["event_type"], "object_detected")

    def test_event_compression_emits_backend_analysis_requests_for_ocr(self) -> None:
        frame = self._frame()
        package = Detection(
            object_name="package",
            object_class="package",
            confidence=0.94,
            bbox=(220, 120, 520, 500),
            zone_id="entry_door",
            track_id="trk-00077",
        )
        compressor = EventCompressor(
            min_confidence=0.35,
            dedupe_window_sec=0.0,
            throttle_window_sec=0.0,
            time_provider=lambda: 500.0,
        )
        envelope = compressor.build_envelope(
            device_id="rk3566-dev-01",
            camera_id="cam-entry-01",
            seq_no=88,
            frame=frame,
            detections=[package],
            snapshot_uri="file:///tmp/package.jpg",
        )
        payload = envelope["payload"]
        self.assertEqual(payload["analysis_profile"], "backend_heavy_v1")
        self.assertTrue(payload["analysis_required"])
        self.assertIsInstance(payload["analysis_requests"], list)
        self.assertEqual(payload["analysis_requests"][0]["type"], "ocr_quick_read")
        self.assertEqual(payload["analysis_requests"][0]["input_uri"], "file:///tmp/package.jpg")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Exercise OM output decoding without requiring an Ascend device."""
import unittest

import numpy as np

from service.ascend_yolo import _postprocess_yolo_output


class AscendOutputTests(unittest.TestCase):
    def test_two_class_yolov8_output_keeps_second_class(self):
        output = np.zeros((1, 6, 8400), dtype=np.float32)
        output[0, :, 0] = [320, 320, 100, 80, 0.05, 0.9]
        boxes = _postprocess_yolo_output(output, (640, 640), (1, 1), (0, 0), 0.6)
        self.assertEqual(boxes.shape, (1, 6))
        np.testing.assert_allclose(boxes[0], [270, 280, 370, 360, 0.9, 1])

    def test_multiclass_nms_preserves_different_classes(self):
        output = np.zeros((1, 84, 8400), dtype=np.float32)
        output[0, :4, :3] = np.array([[320, 320, 320], [320, 320, 320],
                                            [100, 100, 100], [80, 80, 80]])
        output[0, 4, 0] = 0.9
        output[0, 4, 1] = 0.8
        output[0, 5, 2] = 0.85
        boxes = _postprocess_yolo_output(output, (640, 640), (1, 1), (0, 0), 0.6)
        self.assertEqual(boxes.shape, (2, 6))
        self.assertEqual(set(boxes[:, 5]), {0, 1})


if __name__ == "__main__":
    unittest.main()

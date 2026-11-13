"""Convert Detector output to the control package's ROS2 detect message."""

import rclpy
from rclpy.node import Node
from dofbot_info.msg import DetectResult, Detection


class DetectPublisher(Node):
    def __init__(self):
        super().__init__("jxb_detect_publisher")
        self.publisher = self.create_publisher(DetectResult, "/detect_result", 10)

    def publish_result(self, result, fallback=False):
        msg = DetectResult()
        msg.frame_id = result["frame_id"]
        msg.captured_at_ms = int(result["captured_at_ms"])
        msg.image_width_px = int(result["image_width_px"])
        msg.image_height_px = int(result["image_height_px"])
        for item in result["detections"]:
            det = Detection()
            det.detection_id = item["detection_id"]
            det.color = item["color"]
            det.confidence = float(item["confidence"])
            det.center_u_px = float(item["center_u_px"])
            det.center_v_px = float(item["center_v_px"])
            det.fallback = bool(item.get("fallback", fallback))
            msg.detections.append(det)
        self.publisher.publish(msg)

import cv2
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture("../../web/public/videos/cam001.mp4")

frame_idx = 0
while True:
    ret, frame = cap.read()
    if not ret or frame_idx > 30:
        break
        
    results = model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, imgsz=640, conf=0.1)
    
    if results[0].boxes is not None and results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu().numpy().tolist()
        ids = results[0].boxes.id.cpu().numpy().tolist()
        classes = results[0].boxes.cls.cpu().numpy().tolist()
        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes[i]
            # Check if it overlaps with [672, 648, 768, 756]
            if x1 < 768 and x2 > 672 and y1 < 756 and y2 > 648:
                print(f"Frame {frame_idx}: Found Auto! ID: {ids[i]}, Class: {classes[i]}, Conf: {results[0].boxes.conf[i]:.2f}, Box: {boxes[i]}")
                
    frame_idx += 1

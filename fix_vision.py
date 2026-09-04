import sys
import re

with open('c:/Users/Chela/Downloads/temp/CitiSentry/services/edge-vision/vision_node.py', 'r') as f:
    content = f.read()

target = r"(\s*is_paused = False\s*target_track_id = None\s*target_plate = None\s*locked_plate = None\s*locked_class = \"UNKNOWN\"\s*locked_color = \"OTHER\"\s*smoothed_speed = 0\.0\s*)(with camera_lock:)"

replacement = r"\1now = time.time()\n        if is_dvr_paused:\n            if dvr_pause_start is not None:\n                dvr_paused_accumulator += (now - dvr_pause_start)\n                dvr_pause_start = None\n            is_dvr_paused = False\n        \2"

if re.search(target, content):
    content = re.sub(target, replacement, content)
    with open('c:/Users/Chela/Downloads/temp/CitiSentry/services/edge-vision/vision_node.py', 'w') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('TARGET NOT FOUND')

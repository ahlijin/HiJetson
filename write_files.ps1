$content = @'  
#!/usr/bin/env python3  
import rclpy  
from rclpy.node import Node  
from sensor_msgs.msg import Image  
from vision_msgs.msg import Detection2DArray, Detection2D 

# [수정 2026-11-17] pinky_pro 의존 제거: pinky_pro(pinklab-art, Apache-2.0,
# 커밋 014a09f)의 pinky_bringup/battery_publisher.py 를 복사함.
# [수정 2026-11-18] P2(D3): 원본의 노드 이름 battery_publihser 는 오타라,
# 실행 파일과 같은 pinky_battery 로 바꿈. 동작은 바꾸지 않고 이름만 바꿈
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from pinkylib import Battery 

class BatteryPublisher(Node):
    def __init__(self):
        super().__init__('pinky_battery')
        
        self.battery = Battery()

        self.percentage_publisher = self.create_publisher(
            Float32,
            'battery/percent',
            10
        )
        
        self.voltage_publisher = self.create_publisher(
            Float32,
            'battery/voltage',
            10
        )

        self.timer_period = 5.0
        self.percentage_timer = self.create_timer(self.timer_period, self.percentage_callback)
        self.voltage_timer = self.create_timer(self.timer_period, self.voltage_callback)

    def percentage_callback(self):
        pct_msg = Float32()
        pct_msg.data = float(self.battery.battery_percentage())
        self.percentage_publisher.publish(pct_msg)

    def voltage_callback(self):
        volt_msg = Float32()
        volt_msg.data = float(self.battery.get_voltage()) 
        self.voltage_publisher.publish(volt_msg)

def main(args=None):
    rclpy.init(args=args)
    
    publisher = BatteryPublisher()
    
    try:
        rclpy.spin(publisher)
    except KeyboardInterrupt:
        pass
    finally:
        publisher.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

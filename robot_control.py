# ==============================================================================
# MODULE: robot_control.py
# CHỨA TOÀN BỘ PHẦN CỨNG & THUẬT TOÁN ĐIỀU KHIỂN XE CỨU HỎA
# ==============================================================================

import machine
import time
import uasyncio as asyncio

# =========================================================
# 1. CẤU HÌNH TỐC ĐỘ ĐỘNG CƠ (PWM 16-BIT)
# =========================================================
SPEED_FORWARD_PCT  = 60    # Tốc độ đi thẳng (60%)
SPEED_TURN_PCT     = 85    # Tốc độ rẽ xoay tại chỗ (85%)
SPEED_SOFT_OUT_PCT = 90    # Tốc độ bánh ngoài khi lượn cong
SPEED_SOFT_IN_PCT  = 45    # Tốc độ bánh trong khi lượn cong

SPD_FWD      = int((SPEED_FORWARD_PCT / 100) * 65535)
SPD_TURN     = int((SPEED_TURN_PCT / 100) * 65535)
SPD_SOFT_OUT = int((SPEED_SOFT_OUT_PCT / 100) * 65535)
SPD_SOFT_IN  = int((SPEED_SOFT_IN_PCT / 100) * 65535)

# Khai báo 8 chân PWM L298N
in1 = machine.PWM(machine.Pin(32), freq=1000, duty_u16=0) # FL (Trái Trước)
in2 = machine.PWM(machine.Pin(33), freq=1000, duty_u16=0)
in3 = machine.PWM(machine.Pin(25), freq=1000, duty_u16=0) # RL (Trái Sau)
in4 = machine.PWM(machine.Pin(26), freq=1000, duty_u16=0)

in5 = machine.PWM(machine.Pin(18), freq=1000, duty_u16=0) # FR (Phải Trước)
in6 = machine.PWM(machine.Pin(19), freq=1000, duty_u16=0)
in7 = machine.PWM(machine.Pin(23), freq=1000, duty_u16=0) # RR (Phải Sau)
in8 = machine.PWM(machine.Pin(5),  freq=1000, duty_u16=0)

# =========================================================
# 2. KHAI BÁO CẢM BIẾN SIÊU ÂM HC-SR04
# =========================================================
trig = machine.Pin(4, machine.Pin.OUT)
echo_left   = machine.Pin(27, machine.Pin.IN)
echo_center = machine.Pin(14, machine.Pin.IN)
echo_right  = machine.Pin(15, machine.Pin.IN)

DIST_CRITICAL = 18    # Dừng + Lùi khẩn cấp (cm)
DIST_WARNING  = 30    # Rẽ / Lượn né (cm)
SENSOR_DELAY  = 12    # Nghỉ giữa các lần kích đọc (ms)

last_turn_dir = 'LEFT' # Biến nhớ hướng xoay chống kẹt

# =========================================================
# 3. KHAI BÁO KHỐI DẬP LỬA (CẢM BIẾN LỬA, BƠM & SERVO)
# =========================================================
flame_l = machine.ADC(machine.Pin(34))
flame_c = machine.ADC(machine.Pin(35))
flame_r = machine.ADC(machine.Pin(36))

flame_l.atten(machine.ADC.ATTN_11DB)
flame_c.atten(machine.ADC.ATTN_11DB)
flame_r.atten(machine.ADC.ATTN_11DB)

FLAME_THRESHOLD = 1500  # Ngưỡng lửa: ADC < 1500

# Máy bơm mini 5V (Relay Active-LOW: Mức 1 = Tắt, Mức 0 = Bật)
pump = machine.Pin(13, machine.Pin.OUT)
pump.value(1)

# Servo SG90 vòi phun
servo_pwm = machine.PWM(machine.Pin(17), freq=50)
current_servo_angle = 90

def set_servo_angle(angle):
    global current_servo_angle
    angle = max(0, min(180, angle))
    current_servo_angle = angle
    duty = int(1638 + (angle / 180.0) * (8192 - 1638))
    servo_pwm.duty_u16(duty)

set_servo_angle(90)

# =========================================================
# 4. BIẾN TRẠNG THÁI TOÀN CỤC (DÙNG ĐỂ CHIA SẺ VỚI WEB SERVER)
# =========================================================
current_state   = "IDLE"    # PATROL, AVOID, APPROACH, EXTINGUISH, IDLE, ESTOP
current_motion  = "STOP"    # FORWARD, BACKWARD, LEFT, RIGHT, STOP
dist_left_val   = 50.0
dist_center_val = 50.0
dist_right_val  = 50.0
val_l = 4095
val_c = 4095
val_r = 4095
estop_active = False

# =========================================================
# 5. HÀM ĐIỀU KHIỂN CHUYỂN ĐỘNG ĐỘNG CƠ
# =========================================================
def stop_robot():
    global current_motion
    in1.duty_u16(0); in2.duty_u16(0)
    in3.duty_u16(0); in4.duty_u16(0)
    in5.duty_u16(0); in6.duty_u16(0)
    in7.duty_u16(0); in8.duty_u16(0)
    current_motion = "STOP"

def move_forward():
    global current_motion
    if estop_active:
        stop_robot()
        return
    in1.duty_u16(SPD_FWD); in2.duty_u16(0)
    in3.duty_u16(0);       in4.duty_u16(SPD_FWD)
    in5.duty_u16(0);       in6.duty_u16(SPD_FWD)
    in7.duty_u16(SPD_FWD); in8.duty_u16(0)
    current_motion = "FORWARD"

def move_backward():
    global current_motion
    if estop_active:
        stop_robot()
        return
    in1.duty_u16(0);       in2.duty_u16(SPD_FWD)
    in3.duty_u16(SPD_FWD); in4.duty_u16(0)
    in5.duty_u16(SPD_FWD); in6.duty_u16(0)
    in7.duty_u16(0);       in8.duty_u16(SPD_FWD)
    current_motion = "BACKWARD"

def turn_left_pivot():
    global current_motion
    if estop_active:
        stop_robot()
        return
    in1.duty_u16(0);        in2.duty_u16(SPD_TURN)
    in3.duty_u16(SPD_TURN); in4.duty_u16(0)
    in5.duty_u16(0);        in6.duty_u16(SPD_TURN)
    in7.duty_u16(SPD_TURN); in8.duty_u16(0)
    current_motion = "LEFT"

def turn_right_pivot():
    global current_motion
    if estop_active:
        stop_robot()
        return
    in1.duty_u16(SPD_TURN); in2.duty_u16(0)
    in3.duty_u16(0);        in4.duty_u16(SPD_TURN)
    in5.duty_u16(SPD_TURN); in6.duty_u16(0)
    in7.duty_u16(0);        in8.duty_u16(SPD_TURN)
    current_motion = "RIGHT"

def steer_left_soft():
    global current_motion
    if estop_active:
        stop_robot()
        return
    in1.duty_u16(SPD_SOFT_IN);  in2.duty_u16(0)
    in3.duty_u16(0);            in4.duty_u16(SPD_SOFT_IN)
    in5.duty_u16(0);            in6.duty_u16(SPD_SOFT_OUT)
    in7.duty_u16(SPD_SOFT_OUT); in8.duty_u16(0)
    current_motion = "LEFT"

def steer_right_soft():
    global current_motion
    if estop_active:
        stop_robot()
        return
    in1.duty_u16(SPD_SOFT_OUT); in2.duty_u16(0)
    in3.duty_u16(0);            in4.duty_u16(SPD_SOFT_OUT)
    in5.duty_u16(0);            in6.duty_u16(SPD_SOFT_IN)
    in7.duty_u16(SPD_SOFT_IN);  in8.duty_u16(0)
    current_motion = "RIGHT"

# =========================================================
# 6. XỬ LÝ DỪNG KHẨN CẤP (E-STOP)
# =========================================================
def execute_emergency_stop():
    global estop_active, current_state
    estop_active = True
    stop_robot()
    pump.value(1) # Tắt bơm ngay
    current_state = "ESTOP"
    print("🚨 [E-STOP] ĐÃ KÍCH HOẠT DỪNG KHẨN CẤP!")

def reset_emergency_stop():
    global estop_active, current_state
    estop_active = False
    current_state = "IDLE"
    print("✅ [E-STOP] ĐÃ PHỤC HỒI HỆ THỐNG AN TOÀN.")

# =========================================================
# 7. ĐỌC SIÊU ÂM LỌC MEDIAN ASYNC
# =========================================================
def get_raw_distance(echo_pin):
    trig.value(0)
    time.sleep_us(2)
    trig.value(1)
    time.sleep_us(10)
    trig.value(0)
    duration = machine.time_pulse_us(echo_pin, 1, 20000)
    if duration < 0:
        return 400.0
    dist = (duration * 0.0343) / 2
    return dist if dist > 2.0 else 400.0

async def get_distance_filtered_async(echo_pin):
    samples = []
    for _ in range(3):
        samples.append(get_raw_distance(echo_pin))
        await asyncio.sleep_ms(SENSOR_DELAY)
    samples.sort()
    return samples[1]

# =========================================================
# 8. VÒNG LẶP THUẬT TOÁN CHÍNH CỦA XE (ROBOT TASK)
# =========================================================
async def robot_task():
    global current_state, last_turn_dir
    global dist_left_val, dist_center_val, dist_right_val
    global val_l, val_c, val_r

    stop_robot()
    set_servo_angle(90)
    pump.value(1)
    await asyncio.sleep_ms(1000)
    print("=== THUẬT TOÁN XE CỨU HỎA ĐANG CHẠY ===")

    while True:
        if estop_active:
            stop_robot()
            pump.value(1)
            current_state = "ESTOP"
            await asyncio.sleep_ms(100)
            continue

        # 1. Đọc cảm biến lửa
        val_l = flame_l.read()
        val_c = flame_c.read()
        val_r = flame_r.read()

        fire_in_left   = val_l < FLAME_THRESHOLD
        fire_in_center = val_c < FLAME_THRESHOLD
        fire_in_right  = val_r < FLAME_THRESHOLD

        # Ưu tiên 1: Dập lửa
        if fire_in_left or fire_in_center or fire_in_right:
            stop_robot()
            pump.value(0) # Bật máy bơm
            current_state = "EXTINGUISH"

            if fire_in_center:
                set_servo_angle(90)
            elif fire_in_left:
                set_servo_angle(135)
            elif fire_in_right:
                set_servo_angle(45)

            await asyncio.sleep_ms(100)
            continue

        # Ưu tiên 2: Tắt bơm & Né vật cản
        pump.value(1)
        set_servo_angle(90)

        dist_left_val   = await get_distance_filtered_async(echo_left)
        dist_center_val = await get_distance_filtered_async(echo_center)
        dist_right_val  = await get_distance_filtered_async(echo_right)

        # Trường hợp 1: Kẹt nguy cấp hoặc kẹt 2 bên
        if dist_center_val < DIST_CRITICAL or (dist_left_val < DIST_WARNING and dist_right_val < DIST_WARNING):
            current_state = "AVOID"
            stop_robot()
            await asyncio.sleep_ms(100)

            move_backward()
            await asyncio.sleep_ms(450)
            stop_robot()
            await asyncio.sleep_ms(100)

            if abs(dist_left_val - dist_right_val) < 5:
                if last_turn_dir == 'LEFT':
                    turn_left_pivot()
                else:
                    turn_right_pivot()
            elif dist_left_val > dist_right_val:
                turn_left_pivot()
                last_turn_dir = 'LEFT'
            else:
                turn_right_pivot()
                last_turn_dir = 'RIGHT'

            await asyncio.sleep_ms(420)
            stop_robot()
            await asyncio.sleep_ms(80)

        # Trường hợp 2: Cản chính diện
        elif dist_center_val < DIST_WARNING:
            current_state = "AVOID"
            stop_robot()
            await asyncio.sleep_ms(50)

            if dist_left_val >= dist_right_val:
                turn_left_pivot()
                last_turn_dir = 'LEFT'
            else:
                turn_right_pivot()
                last_turn_dir = 'RIGHT'

            await asyncio.sleep_ms(300)
            stop_robot()
            await asyncio.sleep_ms(50)

        # Trường hợp 3: Vướng lệch trái -> Lượn phải
        elif dist_left_val < DIST_WARNING:
            current_state = "AVOID"
            steer_right_soft()
            last_turn_dir = 'RIGHT'
            await asyncio.sleep_ms(60)

        # Trường hợp 4: Vướng lệch phải -> Lượn trái
        elif dist_right_val < DIST_WARNING:
            current_state = "AVOID"
            steer_left_soft()
            last_turn_dir = 'LEFT'
            await asyncio.sleep_ms(60)

        # Trường hợp 5: Đường thoáng -> Tiến thẳng
        else:
            current_state = "PATROL"
            move_forward()
            await asyncio.sleep_ms(50)

        await asyncio.sleep_ms(10)

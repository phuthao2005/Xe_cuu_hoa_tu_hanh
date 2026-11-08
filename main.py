# ==============================================================================
# FILE CHÍNH: main.py (TỰ ĐỘNG CHẠY KHI BẬT NGUỒN PIN HOẶC CẮM CÁP)
# ==============================================================================

import uasyncio as asyncio
import time

print("\n" + "="*50)
print("🔥 ESP32 ĐANG KHỞI ĐỘNG HỆ THỐNG ROBOT CỨU HỎA 🔥")
print("="*50)

# 1. Khởi động Wi-Fi ngay lập tức ở đầu file
try:
    import web_server
    web_server.setup_wifi_ap()
except Exception as e:
    print("❌ Lỗi khởi động Wi-Fi / Thiếu file web_server.py:", e)

# 2. Nạp module điều khiển xe
try:
    import robot_control
    print("✅ Đã nạp thành công module robot_control!")
except Exception as e:
    print("❌ Lỗi nạp module robot_control.py:", e)

# 3. Hàm chính chạy song song Web Server và Thuật toán xe
async def main():
    try:
        # Bật Web Server trên cổng 80
        await asyncio.start_server(web_server.handle_client, "0.0.0.0", 80)
        print("✅ Web Server đã sẵn sàng nhận kết nối từ điện thoại!")
    except Exception as e:
        print("❌ Lỗi khởi động Web Server:", e)

    try:
        # Kích hoạt thuật toán chạy xe
        asyncio.create_task(robot_control.robot_task())
        print("✅ Thuật toán xe đang chạy ngầm!")
    except Exception as e:
        print("❌ Lỗi chạy thuật toán xe:", e)

    # Giữ hệ thống luôn hoạt động
    while True:
        await asyncio.sleep(3600)

# CHẠY TRỰC TIẾP (Không dùng if __name__ == '__main__' để đảm bảo luôn chạy trên vi điều khiển)
try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("\nĐã dừng chương trình an toàn.")
    try:
        robot_control.stop_robot()
        robot_control.pump.value(1)
    except:
        pass
except Exception as err:
    print("❌ Lỗi hệ thống:", err)

# ==============================================================================
# MODULE: web_server.py
# CHỨA TOÀN BỘ KHỞI TẠO WIFI ACCESS POINT & MÁY CHỦ WEB BẤT ĐỒNG BỘ
# ==============================================================================

import network
import uasyncio as asyncio
import json
import os
import robot_control

AP_SSID = "Robot_CuuHoa_ESP32"
AP_PASS = "12345678"

def setup_wifi_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid=AP_SSID, password=AP_PASS, authmode=network.AUTH_WPA_WPA2_PSK)
    print("\n" + "="*50)
    print("📡 ĐÃ PHÁT WIFI KHI CẤP NGUỒN:")
    print("   - Tên Wifi (SSID):", AP_SSID)
    print("   - Mật khẩu:       ", AP_PASS)
    print("   - Địa chỉ IP Web:  http://{}".format(ap.ifconfig()[0]))
    print("="*50 + "\n")
    return ap.ifconfig()[0]

async def handle_client(reader, writer):
    try:
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return

        req = request_line.decode("utf-8")
        parts = req.split()
        if len(parts) < 2:
            writer.close()
            return

        path = parts[1]

        # Đọc hết headers
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n":
                break

        # API: Trạng thái thời gian thực từ module robot_control
        if path == "/api/status":
            data = {
                "state": robot_control.current_state,
                "motion": robot_control.current_motion,
                "pump": (robot_control.pump.value() == 0),
                "servo_angle": robot_control.current_servo_angle,
                "estop": robot_control.estop_active,
                "flame": {
                    "left": robot_control.val_l,
                    "center": robot_control.val_c,
                    "right": robot_control.val_r,
                    "threshold": robot_control.FLAME_THRESHOLD
                },
                "ultrasonic": {
                    "left": round(robot_control.dist_left_val, 1),
                    "center": round(robot_control.dist_center_val, 1),
                    "right": round(robot_control.dist_right_val, 1)
                }
            }
            body = json.dumps(data)
            header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(len(body))
            await writer.awrite(header.encode("utf-8"))
            await writer.awrite(body.encode("utf-8"))
            await writer.drain()

        # API: Dừng khẩn cấp E-Stop
        elif path.startswith("/api/estop"):
            if "action=trigger" in path:
                robot_control.execute_emergency_stop()
            elif "action=reset" in path:
                robot_control.reset_emergency_stop()

            resp = json.dumps({"status": "ok", "estop": robot_control.estop_active})
            header = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nAccess-Control-Allow-Origin: *\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(len(resp))
            await writer.awrite(header.encode("utf-8"))
            await writer.awrite(resp.encode("utf-8"))
            await writer.drain()

        # Phục vụ file giao diện HTML (Streaming 1024-byte an toàn)
        else:
            try:
                file_size = os.stat("index.html")[6]
                header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(file_size)
                await writer.awrite(header.encode("utf-8"))
                await writer.drain()

                with open("index.html", "rb") as f:
                    while True:
                        chunk = f.read(1024)
                        if not chunk:
                            break
                        await writer.awrite(chunk)
                        await writer.drain()
            except Exception as e:
                body = "<h3>Vui long nap index.html len ESP32: {}</h3>".format(e)
                header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n"
                await writer.awrite(header.encode("utf-8"))
                await writer.awrite(body.encode("utf-8"))
                await writer.drain()

    except Exception as ex:
        print("Lỗi kết nối Web Server:", ex)
    finally:
        try:
            await writer.aclose()
        except:
            pass

async def start_server():
    setup_wifi_ap()
    print("🚀 Đang khởi động Web Server trên cổng 80...")
    await asyncio.start_server(handle_client, "0.0.0.0", 80)
    print("✅ Web Server đã sẵn sàng nhận kết nối từ điện thoại!")

# Đảo Vàng — Hướng dẫn Dev & Live Environment

Hệ thống chạy 2 môi trường song song: **Dev** (port 8000) để sửa code, **Live** (port 8001) cho người dùng truy cập qua domain `daovang.comaygiauco.com`.

## 1. Kiến trúc tổng quan

```
┌─────────────────────────────────────────────────────────────────┐
│  MÁY CHỦ (Windows)                                              │
│                                                                 │
│  ┌─────────────────┐         ┌─────────────────┐               │
│  │  run_dev.bat    │         │  run_live.bat   │               │
│  │  Port 8000      │         │  Port 8001      │               │
│  │  data/dev.duckdb│         │  data_live/     │               │
│  │                 │         │   live.duckdb   │               │
│  │  [DEV]          │         │  [LIVE]         │               │
│  └────────┬────────┘         └────────┬────────┘               │
│           │                            │                        │
│           │ localhost:8000             │ localhost:8001         │
│           │ (chỉ tôi)                  │                        │
│           │                            │                        │
│  ┌─────────────────┐                   │                        │
│  │  run_scanner_   │                   │                        │
│  │  live.bat       │──── ghi ────►     │                        │
│  │  (daemon 24/7)  │   heartbeat       │                        │
│  │                 │   + alerts        │                        │
│  │  data_live/     │   vào             │                        │
│  └─────────────────┘                   │                        │
│                                        │                        │
└────────────────────────────────────────┼────────────────────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │ Cloudflare      │
                                │ Tunnel          │
                                │                 │
                                │ http://localhost│
                                │ :8001           │
                                │      ↕          │
                                │ https://trade.  │
                                │ comaygiauco.com │
                                │                 │
                                │ [HTTPS tự động] │
                                └─────────────────┘
                                         │
                                         ▼
                                ┌─────────────────┐
                                │ NGƯỜI DÙNG      │
                                │                 │
                                │ Truy cập:       │
                                │ https://trade.  │
                                │ comaygiauco.com │
                                └─────────────────┘
```

## 2. Bảng so sánh 2 môi trường

> **Bắt buộc:** Dashboard không còn dùng mật khẩu mặc định. Hãy đặt
> `DAO_VANG_WEB__ACCESS_PASSWORD` trong file `.env` trước khi khởi động web;
> nếu thiếu, server sẽ khóa toàn bộ API bảo vệ và không cho đăng nhập.

| Yếu tố | Dev (`run_dev.bat`) | Live (`run_live.bat`) |
|---|---|---|
| Port | 8000 | 8001 |
| Data dir | `data/` | `data_live/` |
| DuckDB | `data/dev.duckdb` | `data_live/live.duckdb` |
| Mục đích | Sửa code, test | Người dùng thực |
| Truy cập | `http://localhost:8000` | `https://daovang.comaygiauco.com` |
| Ai dùng | Developer (tôi) | End user |
| Restart khi sửa code | Có (chỉ ảnh hưởng dev) | Không (live chạy độc lập) |
| Chế độ Scanner & Telegram | `operating_mode: research`, `fibo_trend_short.telegram_enabled: false` (**Khóa kép**: chặn 100% gửi Telegram thật) | Tầng 1 `V3.1` chỉ hiển thị UI (`shadow_telegram_enabled: false`); Tầng 2 `Fibo Short v4.0.21` gửi cảnh báo Telegram chính thức (`elite_sniper_risk`, `sniper_rr1_horizon24`) |

## 3. File bat chi tiết

### `run_dev.bat` — Môi trường Dev

```bat
@echo off
echo ==========================================
echo STARTING DAO VANG - DEV ENVIRONMENT
echo PORT: 8000
echo DATA: data
echo ==========================================
set DAO_VANG_WEB__PORT=8000
set DAO_VANG_PATHS__DATA_DIR=data
set DAO_VANG_PATHS__RAW_DIR=data/raw
set DAO_VANG_PATHS__NORMALIZED_DIR=data/normalized
set DAO_VANG_SCANNER__DB_PATH=data/dev.duckdb
set DAO_VANG_SCORING__ALERT_SCORE_THRESHOLD=40
.venv\Scripts\python.exe -m dao_vang.web.run
pause
```

### `run_live.bat` — Môi trường Live

```bat
@echo off
echo ==========================================
echo STARTING DAO VANG - LIVE ENVIRONMENT
echo PORT: 8001
echo DATA: data_live
echo ==========================================
set DAO_VANG_WEB__PORT=8001
set DAO_VANG_PATHS__DATA_DIR=data_live
set DAO_VANG_PATHS__RAW_DIR=data_live/raw
set DAO_VANG_PATHS__NORMALIZED_DIR=data_live/normalized
set DAO_VANG_SCANNER__DB_PATH=data_live/live.duckdb
.venv\Scripts\python.exe -m dao_vang.web.run 8001
pause
```

### `run_scanner_live.bat` — Scanner daemon 24/7

```bat
@echo off
echo ==========================================
echo STARTING DAO VANG SCANNER - LIVE ENVIRONMENT
echo DATA: data_live
echo ==========================================
set DAO_VANG_PATHS__DATA_DIR=data_live
set DAO_VANG_PATHS__RAW_DIR=data_live/raw
set DAO_VANG_PATHS__NORMALIZED_DIR=data_live/normalized
set DAO_VANG_SCANNER__DB_PATH=data_live/live.duckdb
set DAO_VANG_SCORING__ALERT_SCORE_THRESHOLD=40
.venv\Scripts\python.exe -m dao_vang scanner start
pause
```

## 4. File `.env` (chung cho cả 2 môi trường)

```env
# Telegram bot credentials (see docs/TELEGRAM_SETUP.md)
DAO_VANG_TELEGRAM__BOT_TOKEN=<bot_token>
DAO_VANG_TELEGRAM__CHAT_ID=<chat_id>

# Scanner config - set frozen_model_id after running `dao-vang experiment freeze`
DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_20260803_160757_cf749fbe
```

> **Lưu ý:** `.env` được đọc tự nhiên bởi `AppSettings` (pydantic-settings).
> Các env var trong file `.bat` chỉ override cho môi trường cụ thể.

## 5. Quy trình vận hành hằng ngày

### 5.1. Khởi động hệ thống (sau khi bật máy)

Mở **3 terminal riêng** (cmd hoặc PowerShell):

```powershell
# Terminal 1 — Scanner daemon (chạy nền 24/7)
D:\Coding\dao_vang\run_scanner_live.bat

# Terminal 2 — Live server (người dùng truy cập)
D:\Coding\dao_vang\run_live.bat

# Terminal 3 — Dev server (chỉ khi cần sửa code)
D:\Coding\dao_vang\run_dev.bat
```

### 5.2. Sửa code (dev workflow)

1. Mở `run_dev.bat` → server chạy ở port 8000
2. Sửa code (Python, React, v.v.)
3. **Backend (Python)**: Ctrl+C → chạy lại `run_dev.bat`
4. **Frontend (React)**: build lại `frontend/` → copy vào `frontend/dist/`
5. Test ở `http://localhost:8000`
6. Khi ổn → deploy sang live: Ctrl+C `run_live.bat` → chạy lại `run_live.bat`

### 5.3. Restart chỉ live (không ảnh hưởng dev)

```powershell
# Tìm process đang giữ port 8001
Get-NetTCPConnection -LocalPort 8001 -State Listen | Select OwningProcess

# Kill process đó (thay PID)
Stop-Process -Id <PID> -Force

# Chạy lại
D:\Coding\dao_vang\run_live.bat
```

### 5.4. Restart scanner daemon

Scanner chạy độc lập với web server. Restart scanner **không ảnh hưởng** web UI.

```powershell
# Trong terminal đang chạy run_scanner_live.bat:
Ctrl+C

# Chạy lại
D:\Coding\dao_vang\run_scanner_live.bat
```

## 6. Cloudflare Tunnel setup

### 6.1. Yêu cầu

- Tài khoản Cloudflare
- Domain `comaygiauco.com` đã add vào Cloudflare (nameserver trỏ về Cloudflare)
- `cloudflared` đã cài trên máy: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/

### 6.2. Tạo tunnel

```powershell
# Login một lần
cloudflared tunnel login

# Tạo tunnel
cloudflared tunnel create dao-vang

# Gán domain
cloudflared tunnel route dns dao-vang daovang.comaygiauco.com
```

### 6.3. File config `~/.cloudflared/config.yml`

```yaml
tunnel: <tunnel-id>
credentials-file: C:\Users\<user>\.cloudflared\<tunnel-id>.json

ingress:
  - hostname: daovang.comaygiauco.com
    service: http://localhost:8001
  - service: http_status:404
```

### 6.4. Chạy tunnel

```powershell
# Foreground (test)
cloudflared tunnel run dao-vang

# Cài làm service (tự khởi động cùng Windows)
cloudflared service install
```

Sau khi tunnel chạy:
- Người dùng truy cập `https://daovang.comaygiauco.com` → Cloudflare → `http://localhost:8001` → `run_live.bat`
- HTTPS tự động, không cần Let's Encrypt
- IP máy chủ không bị lộ

## 7. Cấu hình alert threshold

Ngưỡng phát alert (`alert_score_threshold`) mặc định **40** trong code:

```python
# src/dao_vang/config/settings.py
class ScoringConfig(BaseModel):
    alert_score_threshold: float = Field(default=40.0, ge=0.0, le=100.0)
```

**Cách override** (không cần sửa code):

```bat
# Trong file .bat, thêm:
set DAO_VANG_SCORING__ALERT_SCORE_THRESHOLD=50
```

**Lưu ý:** Sau khi đổi threshold, **phải restart cả scanner lẫn web server** để áp dụng.

## 8. Kiểm tra sức khỏe hệ thống

### 8.1. Quick check (PowerShell)

```powershell
# Scanner status
Invoke-WebRequest http://127.0.0.1:8001/api/status | ConvertFrom-Json | Select scanner_status, threshold, telegram_connected

# Heartbeat file
Get-Content D:\Coding\dao_vang\data_live\scanner_heartbeat.json | ConvertFrom-Json
```

### 8.2. Dashboard

- Dev: `http://localhost:8000`
- Live: `https://daovang.comaygiauco.com`

### 8.3. Dấu hiệu bất thường

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dashboard báo "Scanner OFFLINE" | Scanner daemon chết hoặc heartbeat cũ | Restart `run_scanner_live.bat` |
| Radar alerts trống | Không có coin vượt threshold | Hạ `alert_score_threshold` |
| `telegram_connected: false` | `.env` thiếu token/chat_id | Check `.env` |
| Port 8001 không truy cập được | `run_live.bat` chưa chạy | Chạy `run_live.bat` |
| Domain không truy cập được | Cloudflare tunnel chết | `cloudflared tunnel run dao-vang` |

## 9. Backup & restore

### 9.1. Backup data live

```powershell
# Stop scanner + live server trước
Copy-Item D:\Coding\dao_vang\data_live\live.duckdb D:\Backup\live_$(Get-Date -Format yyyyMMdd).duckdb
```

### 9.2. Backup config

```powershell
Copy-Item D:\Coding\dao_vang\.env D:\Backup\.env.backup
Copy-Item D:\Coding\dao_vang\run_*.bat D:\Backup\
```

## 10. Troubleshooting thường gặp

### 10.1. Port đã bị chiếm

```powershell
# Tìm process chiếm port
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select OwningProcess
Get-Process -Id <PID>
Stop-Process -Id <PID> -Force
```

### 10.2. Process cũ không kill được (Access Denied)

Xảy ra khi process chạy từ terminal khác. Giải pháp:

1. Đóng terminal đang chạy process đó (Ctrl+C)
2. Hoặc mở terminal admin: `Start-Process powershell -Verb RunAs`
3. `Stop-Process -Id <PID> -Force`

### 10.3. DuckDB bị lock

Scanner và web server cùng mở `live.duckdb`. DuckDB Windows không cho nhiều process mở cùng file.

- Web server dùng read-only + copy fallback (xem `_ro_duckdb_connect` trong `api_server.py`)
- Nếu vẫn lỗi: restart scanner trước, rồi restart web server

### 10.4. Threshold không áp dụng sau khi sửa

Phải restart **cả 2 process**:
1. Scanner daemon (`run_scanner_live.bat`)
2. Web server (`run_live.bat` hoặc `run_dev.bat`)

Code Python load config lúc khởi động, không reload khi sửa file.

## 11. Cập nhật code lên live

```powershell
# 1. Test trên dev trước
# (sửa code → restart run_dev.bat → test http://localhost:8000)

# 2. Khi đã ổn:
# Stop live server (Ctrl+C trong terminal run_live.bat)

# 3. Pull code mới (nếu dùng git)
git pull

# 4. Build frontend nếu có thay đổi UI
cd frontend
npm run build
cd ..

# 5. Restart live server
D:\Coding\dao_vang\run_live.bat

# 6. Verify
# Truy cập https://daovang.comaygiauco.com
```

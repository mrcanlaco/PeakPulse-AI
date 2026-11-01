# Môi trường triển khai Đảo Vàng

## Local
- Python 3.12 trong .venv; React/Vite ở frontend.
- API: http://127.0.0.1:8000; Vite: http://localhost:8088.
- Khởi động: `.venv/Scripts/python.exe -m dao_vang.web.run --host 127.0.0.1 --port 8000 --reload`.
- Chạy frontend: `cd frontend`, sau đó `npm run dev`.
- `dao-vang-ui` cũng hỗ trợ --host, --port và --reload. Cổng positional cũ vẫn được hỗ trợ.
- Dữ liệu và mật khẩu lấy từ môi trường/.env. Không mặc định bật scanner khi khởi động web.

## Oracle Cloud (OCI — Dokploy Production Live)
- Máy chủ Production chính thức đã chuyển từ GCP (đã ngưng sử dụng) sang **Oracle Cloud Infrastructure (OCI — ARM64 `aarch64`, Oracle Linux 9)**.
- Host / IP: `161.118.250.182` (`oracle-free-vm-01`); tài khoản SSH: `opc` (kết nối với `-i <path-to-key> -o IdentitiesOnly=yes`).
- Quản lý Container: **Dokploy Compose** (`project: daovang-daovang-beta-bw9sz2`, `name: daovang-oracle`, gọi qua `sudo docker`):
  - `daovang-oracle-web`: cổng nội bộ `127.0.0.1:18000 -> 8000/tcp`, phục vụ API + `frontend/dist`.
  - `daovang-oracle-scanner`: chạy `dao-vang scanner start --config configs/msi-production.yaml` (kiến trúc 2 tầng: `Fibo Short v4.0.21` Telegram chính thức + `V3.1` UI Radar với `shadow_telegram_enabled: false`).
  - `daovang-oracle-paper_oos`: chạy độc lập 12 tài khoản `paper_oos_v1` từ `source_snapshot` đã khóa SHA-256 (**không restart khi cập nhật web/scanner** để giữ mạch quan sát liên tục).
  - `daovang-oracle-tunnel` & `dokploy-traefik`: định tuyến domain chính thức **`https://pulse.freqpilot.dev`** (giữ song song `https://daovang.comaygiauco.com` trong giai đoạn chuyển tiếp).
- Đường dẫn trên máy chủ Oracle:
  - Compose file: `/etc/dokploy/compose/daovang-daovang-beta-bw9sz2/code/docker-compose.yml`
  - Thư mục runtime bind-mount: `/etc/dokploy/compose/daovang-daovang-beta-bw9sz2/files/runtime/` (`data -> /app/data_live`, `artifacts -> /app/artifacts`, `configs -> /app/configs:ro`, `src -> /app/src:ro`, `frontend/dist -> /app/frontend/dist:ro`).
  - Thư mục backup trước mỗi lần deploy: `/var/backups/dao-vang/prod-2tier-<TIMESTAMP>/`.

## Quy trình Triển khai lên Oracle Cloud
1. Kiểm tra mã: Ruff, bộ kiểm thử Python, Pyright theo danh sách CI; build frontend (`cd frontend && npm run build && npm run check:bundle`).
2. Commit và push mã lên nhánh `main` trên GitHub.
3. **Triển khai trực tiếp lên Dokploy Runtime trên Oracle Cloud (`scripts/deploy_oracle_server.py`):**
   - Xem trước (dry-run):
     `python scripts/deploy_oracle_server.py --key "<PATH_TO_ORACLE_KEY>"`
   - Thực thi cập nhật an toàn (tự động tạo backup `/var/backups/dao-vang/...`, kiểm tra schema `msi-production.yaml`, chỉ restart `daovang-oracle-scanner` + `daovang-oracle-web` và giữ nguyên `daovang-oracle-paper_oos`):
     `python scripts/deploy_oracle_server.py --key "<PATH_TO_ORACLE_KEY>" --apply`
4. Xác nhận `http://127.0.0.1:18000/api/ready` trên server và `https://pulse.freqpilot.dev/api/ready` trả `HTTP 200` với `checks.fibo_trend_short.status == "ok"`.
## Rà soát và phục hồi
- Chạy `python scripts/audit_runtime.py` trong container web để kiểm tra API có xác thực; công cụ không in mật khẩu/cookie, không gửi Telegram.
- Chạy `python scripts/check_public_url.py` từ bên ngoài để kiểm tra domain và yêu cầu đăng nhập.
- Trước rollout, giữ image đang chạy và Git SHA cũ. Chỉ thay image khi image mới đã build và qua kiểm thử.
- Không xóa dữ liệu, artifacts, Docker image hoặc bản sao lưu khi chưa xác định chính sách lưu trữ.
- Xem [báo cáo rà soát 11/09/2026](AUDIT_2026-09-11.md) để biết lỗi đã sửa và các giới hạn kiểm chứng.

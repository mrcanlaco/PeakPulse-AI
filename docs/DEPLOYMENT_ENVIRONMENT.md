# Môi trường triển khai Đảo Vàng

## Local
- Python 3.12 trong .venv; React/Vite ở frontend.
- API: http://127.0.0.1:8000; Vite: http://localhost:8088.
- Khởi động: `.venv/Scripts/python.exe -m dao_vang.web.run --host 127.0.0.1 --port 8000 --reload`.
- Chạy frontend: `cd frontend`, sau đó `npm run dev`.
- `dao-vang-ui` cũng hỗ trợ --host, --port và --reload. Cổng positional cũ vẫn được hỗ trợ.
- Dữ liệu và mật khẩu lấy từ môi trường/.env. Không mặc định bật scanner khi khởi động web.

## Oracle Cloud (OCI — Production Live)
- Máy chủ Production chính thức đã chuyển từ GCP (đã ngưng sử dụng) sang **Oracle Cloud Infrastructure (OCI)**.
- Host / IP: `161.118.250.182` (SSH alias: `oracle-daovang`); tài khoản mặc định: `opc` (hoặc cấu hình qua `ORACLE_USER`).
- Khóa SSH: `~/.ssh/id_ed25519` (hoặc truyền qua `--key` / GitHub Secret `ORACLE_SSH_KEY`).
- Thư mục ứng dụng: `$HOME/dao_vang` (tương ứng `/home/opc/dao_vang`, tự động nhận diện qua đường dẫn tương đối của `scripts/*.sh` hoặc biến `DAO_VANG_PROJECT_DIR` / `ORACLE_APP_DIR`).
- Domain: `https://daovang.comaygiauco.com`.
- Docker Compose: `scanner`, `web`, `cloudflared` (cấu hình `configs/live.yaml` theo kiến trúc 2 tầng: `Fibo Short v4.0.21` chính thức + `V3.1` UI Radar).
- Bind mount dữ liệu trên host `./data` vào `/app/data_live`; `artifacts` và `configs` giữ riêng ngoài image.
- Không xóa file lock của dịch vụ đang chạy.
- Scanner healthcheck và `/api/ready` kiểm tra đồng thời heartbeat mới trong 15 phút, trạng thái `running`, chu kỳ gần nhất không `failed`, nhánh `fibo_trend_short` không lỗi (`fibo_trend_short_failed`) và dung lượng ổ đĩa an toàn.

## Quy trình Triển khai (CI/CD & Thủ công trên Oracle Cloud)
1. Kiểm tra mã: Ruff, bộ kiểm thử Python, Pyright theo danh sách CI; frontend build & bundle budget.
2. Commit và push mã lên nhánh `main` trên GitHub.
3. **Auto-deploy qua GitHub Actions (`.github/workflows/deploy.yml` — `Deploy to Oracle Cloud (Live)`):**
   - Cấu hình Secrets trên GitHub repo (`Settings -> Secrets and variables -> Actions`):
     - `ORACLE_SSH_KEY`: nội dung private key SSH đăng nhập máy chủ Oracle Cloud (bắt buộc).
     - `ORACLE_HOST`: IP/domain máy chủ Oracle (mặc định `161.118.250.182`).
     - `ORACLE_USER`: user SSH (mặc định `opc`).
     - `ORACLE_APP_DIR`: thư mục repo trên server (tùy chọn, mặc định `$HOME/dao_vang`).
   - Workflow chỉ deploy đúng SHA 40 ký tự đã vượt qua `CI`, không tự `git reset --hard` hay xóa thay đổi chưa commit trên server.
4. **Triển khai thủ công từ máy Local:**
   - Xem trước (dry-run): `python scripts/deploy_oracle_server.py --revision <SHA-40-ký-tự>`
   - Thực thi lên Oracle Cloud: `python scripts/deploy_oracle_server.py --revision <SHA-40-ký-tự> --apply` (có thể truyền thêm `--host`, `--key`, `--app-dir`).
5. Chờ các dịch vụ Docker healthy, kiểm tra `/api/health` và `/api/ready` qua localhost trên server và qua domain `https://daovang.comaygiauco.com/api/ready`.
6. Updater tự động trong container được tắt cứng (`updater.enabled: false`); mọi bản phát hành đi qua host/CI.
## Rà soát và phục hồi
- Chạy `python scripts/audit_runtime.py` trong container web để kiểm tra API có xác thực; công cụ không in mật khẩu/cookie, không gửi Telegram.
- Chạy `python scripts/check_public_url.py` từ bên ngoài để kiểm tra domain và yêu cầu đăng nhập.
- Trước rollout, giữ image đang chạy và Git SHA cũ. Chỉ thay image khi image mới đã build và qua kiểm thử.
- Không xóa dữ liệu, artifacts, Docker image hoặc bản sao lưu khi chưa xác định chính sách lưu trữ.
- Xem [báo cáo rà soát 11/09/2026](AUDIT_2026-09-11.md) để biết lỗi đã sửa và các giới hạn kiểm chứng.

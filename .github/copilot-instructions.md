# Quy tắc dự án DrowsyGuard – Hệ thống phát hiện ngủ gật cho tài xế ô tô (dành cho AI agent)

> Đồ án Công nghệ phần mềm. Hệ thống chỉ **hỗ trợ cảnh báo**, không chẩn đoán y tế, không phải thiết bị an toàn đã chứng nhận.
> Đọc kèm `SPEC.md` (yêu cầu + tiêu chí chấp nhận). Nếu hai file mâu thuẫn, hỏi sinh viên.

## Công nghệ
- **Python 3.10 – 3.12** (MediaPipe chưa hỗ trợ tốt bản mới hơn). Dùng virtualenv `.venv` trong VS Code.
- Thị giác máy tính: **OpenCV**, **MediaPipe Face Landmarker / Face Mesh** (468 điểm, có mống mắt), NumPy.
- Deep Learning: **TensorFlow/Keras**, mô hình **MobileNetV2 transfer learning** cho mắt (mở/nhắm) và miệng (ngáp). Huấn luyện trên **Google Colab/Kaggle**, xuất **TFLite**; ứng dụng chỉ nạp file `.tflite` để suy luận, không huấn luyện trong app.
- Mô hình thời gian (LSTM/GRU) là **tùy chọn giai đoạn sau**; bản chính dùng bộ đếm + máy trạng thái (có thể giải thích và hiệu chỉnh).
- Web demo: **Flask** + Jinja2 + HTML/CSS/JavaScript thuần (không React/Vue/Node). Video xem trước dùng MJPEG, trạng thái dùng polling `/api/status` mỗi ~500 ms.
- Camera: OpenCV `VideoCapture` chạy **trên máy chạy ứng dụng** (laptop/thiết bị gắn xe). Cảnh báo âm thanh/rung phát **ở trình duyệt** (`<audio>`, `navigator.vibrate`).
- CSDL: **Microsoft SQL Server** (bản Express/Developer, chạy local), truy cập bằng **`pyodbc`** + **ODBC Driver 17/18 for SQL Server**. Viết **SQL/T-SQL thuần, tham số hóa bằng `?`**, không dùng ORM. Đăng nhập: **Flask-Login** + `werkzeug.security` (hash mật khẩu).
- Kiểm thử: **pytest**. Định dạng/lint: `ruff` (tùy chọn).
- Package được duyệt: `flask`, `pyodbc`, `flask-login`, `opencv-python`, `mediapipe`, `numpy`, `tensorflow`, `pytest`, `python-dotenv`. Cần thêm package khác → hỏi sinh viên trước.
- Công cụ: VS Code (+ extension SQL Server mssql), SSMS hoặc Azure Data Studio, Git/GitHub, Colab/Kaggle (huấn luyện), draw.io (sơ đồ).

## Kiến trúc & cấu trúc thư mục
Tách rõ: **core (xử lý, không biết Flask/DB)** → **services (nghiệp vụ + DB)** → **web (Flask)**.

```
drowsyguard/
├─ app/                     # Flask
│  ├─ __init__.py           # create_app()
│  ├─ routes/               # auth.py, monitor.py, history.py, admin.py, api.py
│  ├─ templates/  static/
├─ core/                    # thuần Python, test được không cần camera/Flask
│  ├─ camera.py             # QuanLyCamera: mở/đọc/đóng, báo lỗi rõ ràng
│  ├─ quality.py            # kiểm tra độ sáng, độ mờ (Laplacian)
│  ├─ face.py               # MediaPipe: landmark, ROI, NMS
│  ├─ driver_selector.py    # BoXacDinhTaiXe: ROI + vô lăng + tracking
│  ├─ metrics.py            # EAR, MAR, head pose (pitch/yaw/roll), làm mượt 15 khung
│  ├─ calibration.py        # BoHieuChinhCaNhan: EAR0, MAR0, pitch0 (5 giây đầu)
│  ├─ classifier.py         # MoHinhPhatHien: nạp TFLite, trả KetQuaPhatHien
│  ├─ temporal.py           # BoTheoDoiThoiGian: PERCLOS, chớp dài, ngáp, gật, nhắm liên tục
│  ├─ state_machine.py      # MayTrangThai: 5 trạng thái + hysteresis
│  ├─ alert.py              # quyết định mức cảnh báo, chống lặp 10 s
│  ├─ pipeline.py           # DieuKhienGiamSat: nối các bước, chạy trong thread riêng
│  └─ types.py              # KetQuaPhatHien (dataclass), enum TrangThai, MucCanhBao
├─ db/                      # schema.sql (tạo bảng T-SQL), seed.sql, connection.py (pyodbc, đọc .env)
├─ services/                # KhoLuuTru: user_service, session_service, alert_service, config_service (chứa SQL)
├─ config.py                # MỌI ngưỡng và hằng số ở MỘT chỗ
├─ ml/                      # notebook/script huấn luyện, đánh giá (KHÔNG import từ app/ hay core/)
├─ models/                  # *.tflite đã huấn luyện (file nhỏ mới commit)
├─ tests/
├─ .env.example  .gitignore  requirements.txt  README.md
```
- Route Flask **không** truy cập DB trực tiếp: Route → Service → SQL (qua `db/connection.py`). Mọi câu SQL nằm trong `services/`, luôn dùng tham số `?`, **không** nối chuỗi từ dữ liệu người dùng (chống SQL injection).
- `core/` **không** import Flask, pyodbc. Pipeline giao tiếp ra ngoài qua callback/queue.
- Pipeline chạy ở **thread nền**; Flask chỉ đọc trạng thái mới nhất. Không chặn request bằng vòng lặp camera.
- Tên module/hàm dùng tiếng Anh `snake_case`; ánh xạ sang sơ đồ lớp trong báo cáo được ghi ở docstring ngắn (ví dụ `# = MayTrangThai`).

## Dữ liệu (theo mô hình CSDL của đồ án, SQL Server)
- Kiểu dữ liệu: `INT IDENTITY(1,1)` cho khóa chính, `NVARCHAR` cho chuỗi tiếng Việt, `DATETIME2`, `FLOAT`, `BIT`. Có `FOREIGN KEY`, `UNIQUE` (CauHinh.MaND), `CHECK` (VaiTro IN ('Driver','Admin'), MucCanhBao IN (1,2,3)).
- Script tạo CSDL/bảng ở `db/schema.sql`, chạy được nhiều lần (kiểm tra `IF NOT EXISTS`/`IF OBJECT_ID`). Không sửa schema bằng tay mà không cập nhật file này.
- Kết nối qua biến môi trường `.env`: `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (hoặc `DB_TRUSTED=yes` nếu dùng Windows Authentication). Không ghi giá trị thật vào code.
- Thao tác nhiều bước (kết thúc phiên + ghi tóm tắt) dùng transaction; luôn đóng kết nối.
- `TaiKhoan` (MaND, TenDangNhap, MatKhau[hash], HoTen, SoDienThoai, VaiTro: `Driver`/`Admin`).
- `CauHinh` (1–1 với TaiKhoan): NguongEAR, NguongMAR, NguongPERCLOS, NguongGatPitch, SoKhungHinhLienTiep, ThoiGianHaMuc, LoaiCanhBao, LuuHinhMinhHoa.
- `PhienGiamSat` (nhiều–1 với TaiKhoan): ThoiGianBatDau/KetThuc, TrangThai, SoLanCanhBao, EAR0, MAR0, Pitch0.
- `LichSuCanhBao` (nhiều–1 với PhienGiamSat): ThoiGian, DauHieu, GiaTriEAR/MAR/PERCLOS/Pitch, DiemTinCay, MucCanhBao, TrangThaiXuLy, HinhAnhChungMinh (NULL mặc định).
- Chỉ **Admin** tạo tài khoản Admin. Driver tự đăng ký, vai trò mặc định `Driver`.

## Nghiệp vụ cốt lõi (không tự ý thay đổi)
- **5 trạng thái**: `UNKNOWN` (Không xác định), `ALERT` (Tỉnh táo), `FATIGUED` (Mệt mỏi), `DROWSY` (Buồn ngủ), `ASLEEP` (Ngủ gật). **3 mức cảnh báo**: 1, 2, 3 tương ứng FATIGUED, DROWSY, ASLEEP.
- **Không chắc chắn ≠ bình thường**: không thấy mặt, bị che, quá tối/mờ, mất tracking > 3 s → `UNKNOWN`, không bao giờ mặc định `ALERT`.
- **Không kết luận từ một khung hình.** Mọi chỉ số làm mượt (trung bình trượt ~15 khung) và xét theo cửa sổ thời gian.
- **Hiệu chỉnh cá nhân** 5 giây đầu phiên: mắt nhắm khi `EAR < 0.75 × EAR0`; ngáp khi `MAR > 1.4 × MAR0`; gật khi `pitch < pitch0 − 15°`.
- **Hysteresis**: lên mức ngay khi đủ điều kiện; hạ từng bậc chỉ khi chỉ số bình thường liên tục ≥ 30 s (`ThoiGianHaMuc`). Nhắm mắt/cúi đầu liên tục ≥ 2 s → `ASLEEP` từ bất kỳ trạng thái nào.
- **Cảnh báo**: không lặp cùng mức trong 10 s; tài xế được **xác nhận** cảnh báo nhưng **không tắt hẳn** khi trạng thái còn nguy hiểm.
- **Đúng người**: chỉ đánh giá người ngồi ghế lái (ROI + vô lăng + tracking + NMS). Mặt ngoài ROI bị bỏ qua.
- **Ngưỡng**: toàn bộ giá trị ở `config.py` (và `CauHinh` trong DB nếu cho chỉnh). Không viết số "ma thuật" rải rác trong code. Giá trị trong `SPEC.md` mục 4 chỉ là **điểm khởi đầu**, phải hiệu chỉnh bằng thực nghiệm.
- Logic tính chỉ số/đếm/chuyển trạng thái nằm ở **một chỗ** (`metrics.py`, `temporal.py`, `state_machine.py`), không lặp ở route hay service.

## Quyền riêng tư & bảo mật
- Chỉ mở camera sau khi tài xế đồng ý (màn hình thông báo mục đích) và nhấn "Bắt đầu giám sát".
- **Xử lý trực tiếp trong bộ nhớ, KHÔNG lưu video** mặc định. Ảnh minh họa (`HinhAnhChungMinh`) chỉ lưu khi `LuuHinhMinhHoa = true`, tách thư mục `instance/evidence/`, không commit.
- Hệ thống chỉ **phân biệt vị trí**, không nhận dạng danh tính khuôn mặt, không lưu face embedding.
- Mật khẩu hash bằng werkzeug, không lưu plain text (cột `MatKhau` NVARCHAR(255)). `SECRET_KEY`, thông tin kết nối SQL Server… lấy từ `.env` (có `.env.example`, không commit `.env`).
- Không đọc/sửa file bí mật nếu không được yêu cầu.

## Cách làm việc
- **Luôn lập kế hoạch ngắn và chờ sinh viên duyệt trước khi sửa code.**
- Mỗi lần chỉ làm **một lát cắt nhỏ** (xem thứ tự ở `SPEC.md` mục 6). Không làm trước phần chưa được yêu cầu.
- Viết **test trước hoặc cùng lúc** cho logic thuần (`metrics`, `temporal`, `state_machine`, `alert`) bằng chuỗi giả lập, không cần camera.
- Giải thích thay đổi bằng **tiếng Việt ngắn gọn**, nêu file đã tạo/sửa. Comment code tiếng Việt ngắn khi cần giải thích nghiệp vụ.
- **Không nói "đã chạy được" nếu chưa chạy thật.** Ghi rõ việc chưa kiểm chứng (đặc biệt phần cần camera/GPU).
- **Không bịa số liệu**: không ghi độ chính xác/FPS/độ trễ nếu chưa đo. Số trong tài liệu tham khảo chỉ để tham khảo.
- Không tự tải dataset, không tự huấn luyện nặng. Dataset (MRL Eye, YawDD, NTHU-DDD, UTA-RLDD…) do sinh viên tải; phần `ml/` chỉ chuẩn bị script/notebook và hướng dẫn. Kiểm tra điều khoản sử dụng từng dataset.
- Chia dữ liệu huấn luyện **theo người** (subject-independent), ~70/15/15.
- Ưu tiên code đơn giản, dễ đọc, phù hợp đồ án sinh viên; tránh over-engineering.

## Cấm
- Không dùng thêm dịch vụ cloud/API bên ngoài để suy luận hay lưu trữ (suy luận chạy tại máy).
- Không thêm ORM (SQLAlchemy...), framework frontend nặng, WebSocket/WebRTC phức tạp, Docker/CI nếu chưa được yêu cầu.
- Không cài package ngoài danh sách duyệt.
- Không lưu video, không nhận dạng danh tính, không gửi hình ảnh ra ngoài máy.
- Không tắt cảnh báo mức 3 hoàn toàn khi trạng thái còn `ASLEEP`.
- Không dùng tài khoản `sa` cho ứng dụng: tạo login/user riêng quyền tối thiểu (db_datareader/db_datawriter hoặc EXECUTE theo nhu cầu). Chỉ chạy script schema trên DB local của sinh viên.
- Không commit: `.venv/`, `.env`, `instance/`, file `.bak`/`.mdf`/`.ldf`, dataset, video, ảnh người thật, file `.h5`/checkpoint lớn, `__pycache__/`.
- Không viết code thừa hoặc comment dài dòng không cần thiết.

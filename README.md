# DrowsyGuard

DrowsyGuard là ứng dụng demo hỗ trợ cảnh báo dấu hiệu buồn ngủ cho tài xế; không phải thiết bị an toàn đã chứng nhận hay công cụ chẩn đoán y tế.

## SQL Server cục bộ

### 1. Cài ODBC Driver

1. Cài [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server) (khuyến nghị) hoặc Driver 17.
2. Mở PowerShell và kiểm tra driver đã đăng ký:

   ```powershell
   Get-OdbcDriver | Where-Object Name -Like '*SQL Server*'
   ```

3. Nếu dùng SQL Server Express cục bộ, khởi động SQL Server Browser khi cần kết nối tới instance có tên, ví dụ `localhost\SQLEXPRESS`.

### 2. Tạo database và chạy schema

1. Mở SSMS hoặc VS Code, cài extension **SQL Server (mssql)**, rồi kết nối tới SQL Server cục bộ bằng tài khoản quản trị DB.
2. Tạo hai database riêng:

   ```sql
   CREATE DATABASE DrowsyGuard;
   GO
   CREATE DATABASE DrowsyGuard_Test;
   GO
   ```

3. Chọn `DrowsyGuard`, mở `db/schema.sql` và chạy toàn bộ script. Chọn `DrowsyGuard_Test` và chạy lại cùng script để tạo schema dùng riêng cho test. Script có thể chạy lặp lại mà không tạo lại các bảng đã có.

### 3. Tạo login/user giới hạn quyền cho ứng dụng

Chạy dưới quyền quản trị SQL Server. Thay password bằng giá trị mạnh, riêng và không đưa vào Git:

```sql
USE master;
GO
CREATE LOGIN drowsyguard_app
WITH PASSWORD = 'ThayBangMatKhauManhVaRieng!';
GO
USE DrowsyGuard;
GO
CREATE USER drowsyguard_app FOR LOGIN drowsyguard_app;
ALTER ROLE db_datareader ADD MEMBER drowsyguard_app;
ALTER ROLE db_datawriter ADD MEMBER drowsyguard_app;
GO
```

Tạo user `drowsyguard_test` riêng và chỉ cấp quyền trên `DrowsyGuard_Test` nếu chạy integration test. Không dùng `sa` trong ứng dụng.

```sql
USE master;
GO
CREATE LOGIN drowsyguard_test
WITH PASSWORD = 'MotMatKhauTestRiengKhac!';
GO
USE DrowsyGuard_Test;
GO
CREATE USER drowsyguard_test FOR LOGIN drowsyguard_test;
ALTER ROLE db_datareader ADD MEMBER drowsyguard_test;
ALTER ROLE db_datawriter ADD MEMBER drowsyguard_test;
GO
```

### 4. Cấu hình môi trường và seed Admin

1. Sao chép `.env.example` thành `.env`; điền server, database, login/password ứng dụng, `SECRET_KEY`, `ADMIN_USER` và `ADMIN_PASSWORD`. Không commit `.env`.
2. Với Windows Authentication, đặt `DB_TRUSTED=yes` và bỏ trống `DB_USER`/`DB_PASSWORD`. Nếu SQL Server cục bộ dùng chứng chỉ tự ký, chỉ trong môi trường phát triển có thể đặt `DB_TRUST_SERVER_CERTIFICATE=yes`; môi trường thật nên dùng chứng chỉ được tin cậy.
3. Cài dependencies trong virtualenv Python 3.10–3.12:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Tạo Admin từ biến môi trường (lệnh an toàn khi chạy lại nếu tài khoản đã là Admin):

   ```powershell
   .\.venv\Scripts\flask.exe --app app:create_app seed-admin
   ```

Driver tự đăng ký tại `/register`; vai trò Admin không thể chọn trên form đăng ký.
Trang Admin ở `/admin` hiển thị thống kê và cho phép khóa/mở tài khoản. Sau khi cập nhật phiên bản có cột `BiKhoa`, chạy lại `db/schema.sql` trên database để áp dụng migration an toàn. Không thể khóa Admin hiện tại hoặc Admin cuối cùng còn hoạt động.

### 5. Chạy ứng dụng và kiểm tra dữ liệu

```powershell
.\.venv\Scripts\flask.exe --app app:create_app run
```

Mở `/login`; sau khi đăng nhập, dùng `/monitor` để giám sát và `/history` để xem phiên của tài khoản hiện tại. Các câu SQL ứng dụng nằm trong `services/` và dùng placeholder `?`.

Kiểm tra tài khoản, cấu hình, phiên và cảnh báo trong SSMS:

```sql
USE DrowsyGuard;
GO
SELECT MaND, TenDangNhap, HoTen, VaiTro FROM dbo.TaiKhoan;
SELECT MaND, NguongEAR, NguongMAR, NguongPERCLOS, NguongGatPitch
FROM dbo.CauHinh;
SELECT MaPhien, MaND, ThoiGianBatDau, ThoiGianKetThuc,
       TrangThai, SoLanCanhBao, EAR0, MAR0, Pitch0
FROM dbo.PhienGiamSat;
SELECT c.MaCanhBao, p.MaND, c.MaPhien, c.ThoiGian, c.DauHieu,
       c.MucCanhBao, c.GiaTriEAR, c.GiaTriMAR, c.GiaTriPERCLOS, c.GiaTriPitch
FROM dbo.LichSuCanhBao AS c
JOIN dbo.PhienGiamSat AS p ON p.MaPhien = c.MaPhien
ORDER BY c.ThoiGian DESC;
```

### Xác định khuôn mặt tài xế

Detector xử lý tối đa số khuôn mặt đặt trong `config.py`, sau đó dùng NMS và tracker IoU để khóa khuôn mặt tài xế. ROI ghế lái mặc định là nửa trái khung hình; chỉnh `DRIVER_SEAT_ROI` nếu vị trí hoặc hướng camera khác. Mất khóa quá 3 giây chuyển sang `UNKNOWN` và yêu cầu hiệu chỉnh lại. Nhận diện vô lăng chưa được bật; không cần cài YOLO/Ultralytics.

Chất lượng khung hình được kiểm tra bằng độ sáng trung bình và phương sai Laplacian; ngưỡng và tùy chọn CLAHE nằm trong `config.py`. CLAHE mặc định tắt. Vùng mắt/miệng được kiểm tra cục bộ; chỉ số không đủ chất lượng bị bỏ và giao diện báo dữ liệu một phần. Ngưỡng là giá trị khởi điểm, cần hiệu chỉnh với camera thực tế.

### Huấn luyện CNN (Colab, tùy chọn)

Đặt project tại `MyDrive/DrowsyGuard`, tải và giải nén MRL Eye/YawDD thủ công vào Drive, rồi mở `ml/train_eye_cnn.ipynb` và `ml/train_mouth_cnn.ipynb` bằng Colab. Notebook không tải dataset; hãy kiểm tra cấu hình parser nhãn/subject trước khi chạy. YawDD cần map rõ video ngáp/không ngáp và subject ID; notebook dừng nếu không xác định được. Kết quả được đánh giá trên test split theo người và xuất thành `models/eye_classifier.tflite`, `models/mouth_classifier.tflite`. Chưa có model hoặc số đo thực tế trong repo.

Ứng dụng mặc định dùng baseline EAR/MAR. Để dùng CNN, cài TensorFlow theo `requirements.txt`, đặt hai model đã huấn luyện trong `models/` và đổi `CLASSIFIER_MODE = "cnn"` trong `config.py`. Nếu thiếu/không nạp được model, pipeline báo lỗi rõ ràng thay vì tự fallback.

### Đo hiệu năng bằng video

Benchmark chạy pipeline trên video cục bộ đã ghi (không lưu lại khung hình). Cung cấp thời điểm bắt đầu điều kiện buồn ngủ tính từ đầu video để đo độ trễ đến cảnh báo đầu tiên:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py path\to\local-video.mp4 --condition-start-seconds 12.5
```

FPS là tốc độ xử lý đo được trên máy hiện tại; độ trễ là theo trục thời gian của video. Nếu không có cảnh báo sau mốc đã đánh dấu, kết quả độ trễ là `N/A`. Không dùng benchmark thay cho xác nhận thực nghiệm an toàn; ghi kịch bản và kết quả vào [docs/TEST_PLAN.md](./docs/TEST_PLAN.md).

### Integration tests

Service integration tests are skipped unless `TEST_DB_*` is explicitly configured. They require a separate SQL Server database whose `TEST_DB_NAME` contains `test` and differs from `DB_NAME`. Create its schema using the steps above, then set the test login values in the local `.env`. Tests never fall back to `DB_*`; do not point `TEST_DB_*` at a database containing application data.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

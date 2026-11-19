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

Detector xử lý tối đa số khuôn mặt đặt trong `config.py`, sau đó dùng NMS và tracker IoU để khóa khuôn mặt tài xế. ROI ghế lái mặc định là toàn khung `(0, 0, 1, 1)`, phù hợp webcam laptop với mặt ở giữa. Khi lắp camera trong xe, thu hẹp `DRIVER_SEAT_ROI` (ví dụ nửa trái `(0.0, 0.0, 0.5, 1.0)`). Mất khóa quá 3 giây chuyển sang `UNKNOWN` và yêu cầu hiệu chỉnh lại. Nhận diện vô lăng chưa được bật; không cần cài YOLO/Ultralytics.

Chất lượng khung hình được kiểm tra bằng độ sáng trung bình và phương sai Laplacian; ngưỡng và tùy chọn CLAHE nằm trong `config.py`. CLAHE mặc định tắt. Vùng mắt/miệng được kiểm tra cục bộ; chỉ số không đủ chất lượng bị bỏ và giao diện báo dữ liệu một phần. Ngưỡng là giá trị khởi điểm, cần hiệu chỉnh với camera thực tế.

### Huấn luyện CNN (Colab, tùy chọn)

Đặt project tại `MyDrive/DrowsyGuard`, tải và giải nén MRL Eye/YawDD thủ công vào Drive, rồi mở `ml/train_eye_cnn.ipynb` và `ml/train_mouth_cnn.ipynb` bằng Colab. Notebook không tải dataset; hãy kiểm tra cấu hình parser nhãn/subject trước khi chạy. YawDD cần map rõ video ngáp/không ngáp và subject ID; notebook dừng nếu không xác định được. Kết quả được đánh giá trên test split theo người và xuất thành `models/eye_classifier.tflite`, `models/mouth_classifier.tflite`. Chưa có model hoặc số đo thực tế trong repo.

Ứng dụng mặc định dùng baseline EAR/MAR. Để dùng CNN, cài TensorFlow theo `requirements.txt`, đặt `models/eye_classifier.tflite` và đổi `CLASSIFIER_MODE = "cnn"` trong `config.py`. Model miệng là tùy chọn: chỉ cần `models/mouth_classifier.tflite` khi `CNN_USE_MOUTH_MODEL = True` (mặc định `False`). Nếu thiếu/không nạp được model bắt buộc, pipeline báo lỗi rõ ràng thay vì tự fallback.

Trong demo landmark, nhấn `S` để lưu crop hai mắt vào `instance/debug_eye_crops/` nhằm kiểm tra trực quan trên máy cục bộ; nhấn `Q` để thoát. Crop mắt dùng `CNN_EYE_CROP_PADDING_RATIO` trong `config.py`.

### Đo hiệu năng bằng video

Benchmark chạy pipeline trên video cục bộ đã ghi (không lưu lại khung hình). Cung cấp thời điểm bắt đầu điều kiện buồn ngủ tính từ đầu video để đo độ trễ đến cảnh báo đầu tiên:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py path\to\local-video.mp4 --condition-start-seconds 12.5
```

FPS là tốc độ xử lý đo được trên máy hiện tại; độ trễ là theo trục thời gian của video. Nếu không có cảnh báo sau mốc đã đánh dấu, kết quả độ trễ là `N/A`. Không dùng benchmark thay cho xác nhận thực nghiệm an toàn; ghi kịch bản và kết quả vào [docs/TEST_PLAN.md](./docs/TEST_PLAN.md).

### Đánh giá mắt nhắm: baseline EAR và CNN

So sánh trên video cục bộ với CSV nhãn thủ công; khung hình chỉ được xử lý trong bộ nhớ. Baseline dùng `EAR < EYES_CLOSED_EAR_BASELINE_RATIO × EAR0`; CNN dùng `P(nhắm) >= CNN_EYE_CLOSED_THRESHOLD`. Cần model mắt TFLite; cần thêm model miệng khi `CNN_USE_MOUTH_MODEL = True`. CSV gồm `start_seconds,end_seconds,label`, trong đó nhãn là `open` hoặc `closed`; các khoảng không được chồng lấn và khung ngoài khoảng nhãn bị bỏ qua. Nên để mắt mở trong khoảng hiệu chỉnh đầu video.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py path\to\local-video.mp4 `
  --labels path\to\eye_labels.csv `
  --output-dir path\to\eval_out `
  --calibration-seconds 5
```

Lệnh in Precision/Recall/F1 cho lớp mắt nhắm, Accuracy, ROC-AUC và FPS; đồng thời ghi `metrics.json` và `metrics.csv` vào thư mục đầu ra. Đây là số đo trên video, máy và nhãn được cung cấp, không phải kết quả đã đo sẵn trong repo.

### Thu thập dữ liệu và huấn luyện mô hình chuỗi thời gian

Hạ tầng chuỗi thời gian hỗ trợ so sánh luật trong state machine với mô hình GRU/1D-CNN trên các cửa sổ đặc trưng khoảng 30 giây, chuẩn hóa theo baseline của phiên. Mô hình chưa được gắn vào pipeline giám sát.

1. Xuất số liệu phiên từ SQL Server:

   ```powershell
   .\.venv\Scripts\python.exe scripts\export_session_metrics.py --session-id 12 --output-dir data\seq
   # Hoặc xuất mọi phiên của một tài khoản:
   .\.venv\Scripts\python.exe scripts\export_session_metrics.py --user-id 4 --output-dir data\seq
   ```

2. Hoặc trích đặc trưng từ video cục bộ (khung hình chỉ xử lý trong bộ nhớ):

   ```powershell
   .\.venv\Scripts\python.exe scripts\extract_features_from_video.py path\to\video.mp4 --output data\seq\video.csv
   ```

   CSV nhãn dùng các cột `start_seconds,end_seconds,label`; `label` là `tinh_tao`, `met_moi`, `buon_ngu` hoặc `ngu_gat`, các khoảng không chồng lấn.

3. Dựng dataset và huấn luyện; mỗi cặp feature/label phải thuộc một người khác nhau để chia train/validation/test theo subject, không chia theo cửa sổ:

   ```powershell
   .\.venv\Scripts\python.exe ml\train_sequence_model.py `
     --pair data\seq\s1.csv:data\seq\s1_labels.csv:personA `
     --pair data\seq\s2.csv:data\seq\s2_labels.csv:personB `
     --pair data\seq\s3.csv:data\seq\s3_labels.csv:personC `
     --model gru --output models\sequence_model.tflite
   ```

Dữ liệu tự quay là mô phỏng, không đại diện đầy đủ cho tình trạng buồn ngủ khi lái xe. Chỉ số Precision/Recall/F1 và confusion matrix có ý nghĩa khi dữ liệu được gán nhãn đáng tin cậy; chưa có huấn luyện hay kết quả đo nào được thực hiện sẵn. CSV có thể chứa mã tài khoản và chỉ số phiên; bảo vệ dữ liệu xuất như dữ liệu cá nhân và không commit chúng.

### Integration tests

Service integration tests are skipped unless `TEST_DB_*` is explicitly configured. They require a separate SQL Server database whose `TEST_DB_NAME` contains `test` and differs from `DB_NAME`. Create its schema using the steps above, then set the test login values in the local `.env`. Tests never fall back to `DB_*`; do not point `TEST_DB_*` at a database containing application data.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

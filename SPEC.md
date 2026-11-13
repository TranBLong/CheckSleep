# SPEC.md – Đặc tả dự án DrowsyGuard (hệ thống phát hiện ngủ gật cho tài xế ô tô)

## 1. Mục tiêu người dùng
Linh hồn của dự án: **đo mức độ buồn ngủ của đúng người lái xe, theo thời gian, cảnh báo đúng lúc, ít báo nhầm, bảo vệ quyền riêng tư.**

- **Tài xế (Driver)**: đọc thông báo dùng camera, cấp quyền, bắt đầu giám sát, được hiệu chỉnh 5 giây đầu, xem trạng thái (xanh/vàng/cam/đỏ/xám), nhận cảnh báo 3 mức, xác nhận cảnh báo, kết thúc phiên và xem tóm tắt + lịch sử phiên.
- **Quản trị viên (Admin)** *(tùy chọn)*: xem thống kê phiên/cảnh báo, quản lý tài khoản (khóa/mở), xem cấu hình hệ thống.
- **Nhóm phát triển**: chạy bộ kiểm thử, xem chỉ số đánh giá mô hình trong báo cáo.

Sau khi đăng nhập, Driver vào trang **Giám sát**, Admin vào trang **Thống kê**.

## 2. Các trạng thái giao diện
Mỗi màn hình cần xử lý đủ trạng thái sau:

| Trạng thái | Hiển thị |
|---|---|
| Đang tải / khởi động | Spinner, không hiện dữ liệu cũ |
| Lỗi | Thông báo rõ nguyên nhân + nút "Thử lại" |
| Rỗng | "Chưa có phiên nào" / "Chưa có cảnh báo" + gợi ý hành động |
| Có dữ liệu | Hiển thị bình thường |

Trạng thái riêng của màn **Giám sát**:
| Trạng thái hệ thống | Màu | Hành động |
|---|---|---|
| Chưa bắt đầu / Hiệu chỉnh (5 s) | Xám | Hướng dẫn "Ngồi thẳng, mở mắt, nhìn thẳng" + đếm ngược |
| Không xác định | Xám + biểu tượng cảnh báo | "Không thể đánh giá", gợi ý chỉnh camera, **không** coi là bình thường |
| Tỉnh táo | Xanh | Không cảnh báo |
| Mệt mỏi | Vàng | Mức 1: biểu tượng + âm nhẹ |
| Buồn ngủ | Cam | Mức 2: âm lớn + lời nhắc nghỉ ngơi |
| Ngủ gật | Đỏ | Mức 3: còi liên tục + gợi ý dừng xe nơi an toàn |
Màn Giám sát tối giản, chữ lớn, nút Bắt đầu/Dừng lớn (ít xao lãng khi lái).

## 3. Tiêu chí chấp nhận
Định dạng: *Cho* … *khi* … *thì* … — *Kiểm chứng:* cách kiểm tra.

### Camera & quyền riêng tư (F01, F02, F03, F12)
1. *Cho* tài xế mở trang Giám sát, *khi* chưa nhấn Bắt đầu, *thì* camera **chưa** được mở và có thông báo mục đích sử dụng camera, không lưu video mặc định.
   - *Kiểm chứng:* mở trang → đèn camera không sáng.
2. *Cho* tài xế nhấn Bắt đầu, *khi* không có camera / camera bị chiếm / bị từ chối, *thì* hiện lỗi rõ ràng + nút Thử lại, không crash.
   - *Kiểm chứng:* rút webcam hoặc mở app khác chiếm camera.
3. *Cho* phiên đang chạy, *khi* camera mất kết nối giữa chừng, *thì* chuyển `Không xác định`, báo lỗi, phiên được đóng an toàn.
4. *Cho* hệ thống đang chạy, *khi* kiểm tra thư mục dự án, *thì* không có file video nào được lưu; ảnh minh họa chỉ có khi `LuuHinhMinhHoa = true`.

### Hiệu chỉnh & chất lượng đầu vào (F13)
5. *Cho* phiên mới, *khi* 5 giây đầu có mặt tài xế ổn định, *thì* lưu `EAR0`, `MAR0`, `pitch0` vào `PhienGiamSat` và chuyển `Tỉnh táo`.
   - *Kiểm chứng:* `SELECT EAR0, MAR0, Pitch0 FROM PhienGiamSat` sau phiên.
6. *Cho* hiệu chỉnh, *khi* không thấy mặt / quá tối / mờ, *thì* kéo dài hoặc yêu cầu làm lại, không dùng giá trị rác.
7. *Cho* khung hình quá tối hoặc quá mờ (Laplacian thấp), *khi* xử lý, *thì* bỏ khung và (nếu kéo dài > 3 s) chuyển `Không xác định`.

### Xác định đúng tài xế (F14)
8. *Cho* khung hình có 2 khuôn mặt (tài xế + hành khách), *khi* xử lý, *thì* chỉ mặt trong ROI ghế lái/đạt điểm "là tài xế" được đánh giá; hành khách bị bỏ qua.
   - *Kiểm chứng:* video/ảnh có 2 người; bộ đếm chỉ thay đổi theo tài xế.
9. *Cho* một khuôn mặt bị phát hiện bằng nhiều khung chồng, *khi* xử lý, *thì* NMS gộp thành một.
10. *Cho* tài xế cúi đầu làm mất mặt tạm thời, *khi* ≤ 3 s, *thì* giữ khóa ID; > 3 s → `Không xác định` và xác minh lại.

### Nhận diện & đếm dấu hiệu (F04)
11. *Cho* chuỗi chỉ số giả lập, *khi* mắt nhắm 100–400 ms, *thì* coi là chớp mắt bình thường, **không** tính dấu hiệu.
12. *Cho* chuỗi giả lập, *khi* mắt nhắm liên tục > 500 ms và < 2 s, *thì* tính 1 "chớp dài".
13. *Cho* chuỗi giả lập, *khi* mắt nhắm liên tục ≥ 2 s, *thì* trạng thái → `Ngủ gật` ngay, từ bất kỳ trạng thái nào.
14. *Cho* chuỗi giả lập, *khi* `MAR > 1.4×MAR0` kéo dài ≥ 2 s, *thì* tính 1 lần ngáp; nói chuyện (MAR dao động nhanh) **không** tính.
15. *Cho* chuỗi giả lập, *khi* pitch giảm ≥ 15° so với `pitch0` trong ≥ 1 s rồi hồi phục, *thì* tính 1 lần gật; cúi ≥ 2 s không hồi phục → `Ngủ gật`.
16. *Cho* cửa sổ 60 s, *khi* tính PERCLOS = khung nhắm / tổng khung × 100%, *thì* kết quả khớp phép tính tay trên dữ liệu mẫu.
17. *Cho* khuôn mặt bị che một phần (khẩu trang / kính râm), *khi* xử lý, *thì* bỏ chỉ số bị che, dùng chỉ số còn lại, hiển thị "dữ liệu một phần"; che hết → `Không xác định`.

### Máy trạng thái & cảnh báo (F05, F06, F07)
18. *Cho* ngưỡng ở Bảng 4.1, *khi* đủ điều kiện, *thì* chuyển đúng trạng thái:
    Mệt mỏi (ngáp, hoặc PERCLOS ≥ 10%, hoặc 1–2 chớp dài/60 s); Buồn ngủ (PERCLOS ≥ 15% hoặc ≥ 3 chớp dài/60 s hoặc ≥ 2 gật/60 s); Ngủ gật (nhắm/cúi ≥ 2 s).
19. *Cho* hysteresis, *khi* chỉ số về bình thường, *thì* chỉ hạ **từng bậc** sau mỗi 30 s bình thường liên tục; không nhấp nháy giữa trạng thái.
    - *Kiểm chứng:* test theo kịch bản Bảng 3.4 của đề tài (Ngủ gật → Buồn ngủ → Mệt mỏi → Tỉnh táo).
20. *Cho* trạng thái nâng mức, *khi* chuyển, *thì* phát đúng mức cảnh báo (1/2/3) và ghi 1 dòng `LichSuCanhBao` (thời gian, dấu hiệu, EAR/MAR/PERCLOS/pitch, độ tin cậy, mức).
21. *Cho* cảnh báo cùng mức, *khi* chưa qua 10 s, *thì* không phát lặp.
22. *Cho* tài xế nhấn "Xác nhận", *khi* trạng thái vẫn `Ngủ gật`, *thì* chỉ tắt âm tạm thời / đánh dấu đã xử lý, **không** tắt hẳn cảnh báo mức 3 khi còn nguy hiểm.

### Tài khoản & phiên (F08, F09, F10)
23. *Cho* người dùng chưa đăng nhập, *khi* mở trang cần quyền, *thì* chuyển về `/login`.
24. *Cho* đăng ký hợp lệ, *khi* submit, *thì* tạo tài khoản vai trò `Driver`, mật khẩu được **hash**, tạo `CauHinh` mặc định.
    - *Kiểm chứng:* `SELECT * FROM TaiKhoan` trong SSMS, cột MatKhau không phải plain text.
24b. *Cho* mọi câu SQL trong `services/`, *khi* nhận dữ liệu người dùng, *thì* dùng tham số `?`; thử nhập `' OR 1=1 --` ở ô đăng nhập → không vượt được xác thực.
25. *Cho* Driver, *khi* nhấn Kết thúc phiên, *thì* camera được giải phóng, `ThoiGianKetThuc` được lưu, hiện tóm tắt (thời lượng, số cảnh báo theo mức, trạng thái cao nhất).
26. *Cho* Driver xem Lịch sử, *khi* mở, *thì* chỉ thấy phiên/cảnh báo **của mình**; có trạng thái rỗng khi chưa có.
27. *Cho* Admin, *khi* mở Thống kê, *thì* thấy tổng số tài khoản, số phiên, số cảnh báo theo mức; khóa tài khoản → user đó không đăng nhập được. Driver truy cập trang Admin → bị chặn (403).

### Lỗi & độ ổn định (F12)
28. *Cho* mọi màn hình danh sách/chi tiết, *khi* SQL Server dừng hoặc API lỗi, *thì* hiện thông báo + nút Thử lại, không crash.
29. *Cho* mô hình `.tflite` thiếu/không nạp được, *khi* khởi động giám sát, *thì* báo lỗi rõ ràng (hoặc dùng baseline EAR/MAR nếu được cấu hình) chứ không mặc định "Tỉnh táo".

### Hiệu năng & đánh giá (mục tiêu cần **đo thực tế**, không khẳng định trước)
30. FPS xử lý ≥ 15 trên thiết bị demo; độ trễ từ lúc đủ điều kiện đến lúc cảnh báo ≤ 1 s. Ghi số đo thực vào báo cáo.
31. Có script đánh giá trên tập kiểm thử tách theo người: Precision/Recall/F1 theo lớp, ma trận nhầm lẫn, ROC; ưu tiên Recall lớp "nhắm mắt". Mục tiêu tham khảo: F1 mắt ≥ 0.90, cảnh báo giả ≤ 1–2 lần/giờ.
32. Báo cáo kiểm thử theo điều kiện: ánh sáng thường/tối, có/không kính, khẩu trang, góc camera, có hành khách; ghi rõ ca sai.

## 4. Ngưỡng khởi điểm (đặt trong `config.py`, hiệu chỉnh bằng thực nghiệm)

**Bảng 4.1**
| Dấu hiệu | Định nghĩa "một lần" | Ngưỡng |
|---|---|---|
| Chớp mắt bình thường | EAR dưới ngưỡng 100–400 ms | Không tính |
| Chớp dài | Nhắm liên tục > 500 ms và < 2 s | ≥ 3 lần/60 s → Buồn ngủ; 1–2 lần/60 s → Mệt mỏi |
| Nhắm liên tục | Nhắm liên tục | ≥ 2 s → Ngủ gật |
| PERCLOS | % khung nhắm trong cửa sổ 60 s | ≥ 10% → Mệt mỏi; ≥ 15% → Buồn ngủ |
| Ngáp | MAR > 1.4×MAR0 kéo dài ≥ 2 s | ≥ 2 lần/5 phút → Mệt mỏi; ≥ 3 lần/10 phút kèm dấu hiệu khác → Buồn ngủ |
| Gật gù | pitch giảm ≥ 15° ≥ 1 s rồi hồi phục | ≥ 2 lần/60 s → Buồn ngủ; cúi ≥ 2 s → Ngủ gật |
| Mắt nhắm (cá nhân hóa) | EAR < 0.75 × EAR0 | — |
| Làm mượt | Trung bình trượt 15 khung | — |
| Hạ mức | Bình thường liên tục | ≥ 30 s mỗi bậc |
| Mất mặt | Không thấy tài xế | > 3 s → Không xác định |
| Chống lặp cảnh báo | Cùng mức | không lặp trong 10 s |

## 5. Ràng buộc kỹ thuật
- Tuân thủ toàn bộ `AGENTS.md`.
- Python 3.10–3.12, Flask, OpenCV, MediaPipe, TensorFlow Lite; **SQL Server** + `pyodbc` (SQL thuần, tham số `?`); không thêm dịch vụ cloud.
- Schema nằm ở `db/schema.sql` (T-SQL, chạy lặp lại được); khóa ngoại + ràng buộc CHECK theo `AGENTS.md`.
- Tách lớp `core/` ↔ `services/` ↔ `app/` như `AGENTS.md`; logic chỉ số/đếm/trạng thái viết **thuần**, có pytest.
- Mô hình: MobileNetV2 (mắt 64×64 hoặc 96×96, miệng) → `.tflite`; head pose bằng landmark + `solvePnP`; EAR/MAR giữ làm **baseline** để so sánh.
- Phát hiện vô lăng (YOLOv8n) là **tùy chọn nâng cao**; bản cơ bản dùng ROI ghế lái + mặt lớn nhất + tracking IoU.
- Mọi ngưỡng ở `config.py`; mọi thao tác DB qua service.
- Giao diện responsive cơ bản (laptop + điện thoại/tablet), chữ lớn, tương phản cao.
- Comment tiếng Việt ngắn.

## 6. Thứ tự làm việc đề xuất (mỗi lát cắt = một lần nhờ Copilot)
1. Khởi tạo dự án: cấu trúc thư mục, `requirements.txt`, `config.py`, Flask chạy được, trang chủ.
2. `core/metrics.py` + test: EAR, MAR, làm mượt (chưa cần camera).
3. `core/camera.py` + `face.py`: mở webcam, MediaPipe landmark, vẽ thử ra cửa sổ/trang.
4. `core/metrics.py` (head pose) + `calibration.py` + test.
5. `core/temporal.py` + test: nhắm liên tục, chớp dài, PERCLOS, ngáp, gật.
6. `core/state_machine.py` + `alert.py` + test (kịch bản Bảng 3.4).
7. `core/pipeline.py` (thread nền) + trang Giám sát (MJPEG, `/api/status`, âm thanh, hiệu chỉnh 5 s).
8. SQL Server: `db/schema.sql`, `connection.py`, services (SQL thuần), auth, phiên, lịch sử cảnh báo, trang Lịch sử.
9. `core/driver_selector.py` (ROI, NMS, tracking, khóa ID).
10. `core/quality.py` + trạng thái Không xác định + xử lý nhiễu.
11. `ml/`: notebook huấn luyện MobileNetV2 (mắt, miệng) + `core/classifier.py` nạp TFLite + tích hợp, so sánh với baseline EAR/MAR.
12. Trang Admin (tùy chọn), kịch bản kiểm thử, đo FPS/độ trễ, báo cáo.

## 7. Phạm vi không làm
- Chẩn đoán y tế, đo sóng não/nhịp tim, tuyên bố đạt chuẩn an toàn phương tiện.
- Nhận dạng danh tính khuôn mặt, lưu face embedding, lưu video, gửi ảnh ra dịch vụ ngoài.
- Tích hợp CAN bus/hệ thống xe, ứng dụng native Android/iOS, thiết bị nhúng (Jetson/Raspberry Pi: chỉ làm nếu còn thời gian).
- Phân tích hành vi lái xe (độ lệch làn), tín hiệu sinh lý.
- Đa ngôn ngữ, email/SMS, triển khai cloud, Docker/CI.

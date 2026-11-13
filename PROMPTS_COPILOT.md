# Bộ prompt dùng với GitHub Copilot (VS Code) cho DrowsyGuard

## Chuẩn bị (làm 1 lần)
1. Tạo thư mục dự án, `git init`, mở bằng VS Code.
2. Cài sẵn **SQL Server (Express/Developer)**, **ODBC Driver 18** và SSMS (hoặc extension mssql trong VS Code); tạo file `.env` từ `.env.example`.
3. Đặt `AGENTS.md` và `SPEC.md` ở **thư mục gốc**. Để Copilot tự đọc luôn quy tắc, copy `AGENTS.md` thành `.github/copilot-instructions.md` (hoặc bật `chat.useAgentsMdFile` trong Settings).
4. Mở Copilot Chat → chọn chế độ **Agent** (hoặc Plan nếu có) và chọn model mạnh nhất bạn có.
5. Mỗi lần chat: đính kèm `#file:AGENTS.md` và `#file:SPEC.md` nếu Copilot có vẻ quên quy tắc.
6. Sau mỗi lát cắt: chạy thử, `pytest`, rồi `git commit` trước khi sang lát tiếp theo.

## Prompt mở đầu (dán đầu tiên)
```
Bạn là trợ lý lập trình cho đồ án sinh viên "DrowsyGuard – hệ thống phát hiện ngủ gật cho tài xế ô tô".
Hãy đọc kỹ #file:AGENTS.md và #file:SPEC.md. Đây là quy tắc bắt buộc.
Cách làm việc:
- Luôn đưa KẾ HOẠCH ngắn (file sẽ tạo/sửa, lệnh sẽ chạy) và CHỜ tôi duyệt rồi mới sửa code.
- Mỗi lần chỉ làm MỘT lát cắt nhỏ tôi yêu cầu.
- Giải thích bằng tiếng Việt ngắn gọn, liệt kê file đã tạo/sửa.
- Không nói "đã chạy được" nếu chưa chạy thật; nêu rõ phần chưa kiểm chứng.
- Không bịa số liệu độ chính xác/FPS.
- Không cài package ngoài danh sách trong AGENTS.md.
Hãy xác nhận bạn đã hiểu bằng cách tóm tắt trong 8 dòng: mục tiêu, 5 trạng thái, 3 mức cảnh báo, cấu trúc thư mục, và 3 điều cấm quan trọng nhất. Chưa viết code.
```

## Lát cắt 1 – Khởi tạo dự án
```
Làm lát cắt 1 theo SPEC.md mục 6: khởi tạo dự án.
Yêu cầu: tạo cấu trúc thư mục đúng AGENTS.md (app/, core/, services/, ml/, models/, tests/), requirements.txt (chỉ package được duyệt), config.py (chứa TẤT CẢ ngưỡng ở SPEC mục 4 dưới dạng hằng số có tên rõ), .env.example (có DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD), .gitignore (theo mục Cấm), create_app() trong app/__init__.py, một trang chủ Flask hiển thị tên dự án, và 1 test pytest đơn giản kiểm tra app khởi tạo được.
Đưa kế hoạch trước, chờ tôi duyệt. Sau khi làm xong, hướng dẫn tôi tạo .venv, cài package và chạy app trên VS Code.
```

## Lát cắt 2 – EAR, MAR, làm mượt
```
Làm lát cắt 2: core/metrics.py (chưa cần camera).
Cài đặt hàm thuần: ear(landmarks_mắt), mar(landmarks_môi), và lớp làm mượt trung bình trượt 15 khung. Công thức EAR = (|p2-p6|+|p3-p5|)/(2|p1-p4|), MAR tương tự với các điểm môi trong. Ghi rõ chỉ số landmark MediaPipe Face Mesh đang dùng cho mỗi mắt và môi (hằng số ở đầu file).
Viết tests/test_metrics.py: mắt mở → EAR ~0.3, mắt nhắm → EAR < 0.15, miệng khép/mở, và làm mượt giảm dao động.
Không dùng camera, không import Flask.
```

## Lát cắt 3 – Camera + MediaPipe
```
Làm lát cắt 3: core/camera.py (QuanLyCamera) và core/face.py.
camera.py: mở/đọc/đóng VideoCapture, kiểm tra mở được, báo lỗi rõ ràng bằng exception riêng (không tìm thấy, bị chiếm, mất kết nối). face.py: dùng MediaPipe lấy landmark của khuôn mặt, trả về dataclass KetQuaPhatHien (core/types.py) gồm có_khuôn_mặt, EAR, MAR, điểm tin cậy.
Thêm script scripts/demo_landmark.py mở webcam, vẽ landmark mắt/miệng và in EAR/MAR để tôi thử bằng mắt. Không lưu hình/video.
Cho tôi biết cách chạy script đó trên VS Code và những gì tôi cần quan sát để xác nhận đúng.
```

## Lát cắt 4 – Head pose + hiệu chỉnh cá nhân
```
Làm lát cắt 4: ước lượng pitch/yaw/roll bằng solvePnP từ landmark (trong core/metrics.py hoặc core/head_pose.py) và core/calibration.py (BoHieuChinhCaNhan).
Hiệu chỉnh: thu thập 5 giây đầu, lấy trung vị EAR0, MAR0, pitch0, bỏ khung không có mặt; nếu quá ít khung hợp lệ thì báo cần làm lại. Suy ra ngưỡng: mắt nhắm khi EAR < 0.75×EAR0, ngáp khi MAR > 1.4×MAR0, gật khi pitch < pitch0 − 15°. Hệ số lấy từ config.py.
Viết pytest với dữ liệu giả lập cho calibration.
```

## Lát cắt 5 – Bộ theo dõi thời gian
```
Làm lát cắt 5: core/temporal.py (BoTheoDoiThoiGian).
Nhận từng khung (timestamp, mắt_nhắm, miệng_ngáp, pitch, hợp_lệ) và tính: thời gian nhắm liên tục, số chớp dài/60 s (nhắm > 500 ms và < 2 s), chớp bình thường (100–400 ms) KHÔNG tính, PERCLOS cửa sổ 60 s, số lần ngáp (MAR cao ≥ 2 s), số lần gật (pitch giảm ≥ 15° ≥ 1 s rồi hồi phục) và cúi kéo dài ≥ 2 s.
Dùng timestamp truyền vào (không gọi time.time() bên trong) để test được. Viết tests/test_temporal.py bằng chuỗi giả lập cho từng tiêu chí SPEC #11–#17.
```

## Lát cắt 6 – Máy trạng thái + cảnh báo
```
Làm lát cắt 6: core/state_machine.py (MayTrangThai) và core/alert.py.
5 trạng thái UNKNOWN/ALERT/FATIGUED/DROWSY/ASLEEP theo SPEC bảng 4.1. Nâng mức ngay; hạ mức từng bậc chỉ sau 30 s bình thường liên tục; nhắm/cúi ≥ 2 s → ASLEEP từ mọi trạng thái; mất mặt > 3 s hoặc chất lượng thấp → UNKNOWN (không bao giờ mặc định ALERT). alert.py: quyết định mức 1/2/3, không lặp cùng mức trong 10 s, hỗ trợ "xác nhận" nhưng không tắt hẳn khi còn ASLEEP.
Viết test tái hiện đúng kịch bản bảng 3.4 trong đề tài và các tiêu chí SPEC #18–#22.
```

## Lát cắt 7 – Pipeline + trang Giám sát
```
Làm lát cắt 7: core/pipeline.py (DieuKhienGiamSat) chạy thread nền nối camera → face → metrics → calibration → temporal → state_machine → alert; và trang Giám sát Flask.
Route: GET /monitor (màn hình thông báo quyền riêng tư + nút Bắt đầu), POST /api/start, POST /api/stop, GET /video_feed (MJPEG, có thể bật/tắt overlay), GET /api/status (JSON: trạng thái, mức cảnh báo, EAR, MAR, PERCLOS, pitch, FPS, thông báo lỗi), POST /api/ack.
Trình duyệt phát âm thanh theo mức (file âm đặt ở static/audio, dùng âm tự tạo hoặc miễn phí bản quyền), dùng navigator.vibrate nếu có. Giao diện tối giản, chữ lớn, màu theo trạng thái, đếm ngược hiệu chỉnh 5 s. Xử lý đủ 4 trạng thái UI (loading/lỗi/rỗng/dữ liệu) theo SPEC mục 2.
Chưa cần DB ở lát này (lưu tạm trong bộ nhớ).
```

## Lát cắt 8 – CSDL, đăng nhập, lịch sử
```
Làm lát cắt 8 với SQL Server (pyodbc, SQL thuần, KHÔNG dùng ORM): db/schema.sql (T-SQL tạo 4 bảng TaiKhoan, CauHinh, PhienGiamSat, LichSuCanhBao đúng mô hình CSDL trong AGENTS.md: IDENTITY, NVARCHAR, FOREIGN KEY, UNIQUE, CHECK, chạy lặp lại được), db/connection.py (đọc .env: DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD hoặc DB_TRUSTED), services/ (user_service, session_service, alert_service, config_service) chứa các câu SQL tham số hóa bằng ?, Flask-Login, trang /login, /register, /history, /history/<id>.
Yêu cầu: mọi câu SQL dùng tham số ?, không nối chuỗi; dùng transaction khi kết thúc phiên; hash mật khẩu bằng werkzeug; đăng ký tạo CauHinh mặc định từ config.py; route không truy cập DB trực tiếp; mỗi khi nâng mức cảnh báo thì ghi LichSuCanhBao; kết thúc phiên lưu tóm tắt; chỉ xem được dữ liệu của chính mình; tài khoản Admin seed từ biến môi trường ADMIN_USER/ADMIN_PASSWORD trong .env.
Cho tôi các bước: cài ODBC Driver, chạy schema.sql bằng SSMS hoặc extension mssql trong VS Code, tạo login/user riêng cho app (không dùng sa), và câu SELECT để kiểm tra dữ liệu. Viết test cho services (dùng DB test riêng, không đụng DB thật). Thêm test thử SQL injection ở đăng nhập.
```

## Lát cắt 9 – Xác định đúng tài xế
```
Làm lát cắt 9: core/driver_selector.py (BoXacDinhTaiXe).
Bản cơ bản: NMS theo IoU, ROI ghế lái (cấu hình được; mặc định nửa khung bên tài xế), điểm "là tài xế" = có trọng số của (tâm mặt trong ROI, kích thước mặt lớn nhất), tracker IoU gán ID và khóa ID tài xế; mất mặt ≤ 3 s giữ ID, > 3 s → UNKNOWN và xác minh lại; mất lâu trong ROI → yêu cầu hiệu chỉnh lại. Phần vô lăng (YOLOv8n) để chỗ cắm giao diện, KHÔNG cài thêm ultralytics.
Tích hợp vào pipeline và viết test với dữ liệu mặt giả lập 2 người (SPEC #8–#10).
```

## Lát cắt 10 – Chất lượng đầu vào & xử lý nhiễu
```
Làm lát cắt 10: core/quality.py kiểm tra độ sáng trung bình và độ mờ (phương sai Laplacian), tùy chọn CLAHE khi thiếu sáng. Xử lý che khuất một phần: bỏ chỉ số mắt nếu mắt bị che, bỏ chỉ số miệng nếu bị che, ghi "dữ liệu một phần". Khung chất lượng thấp bị bỏ; kéo dài > 3 s → UNKNOWN.
Hiển thị lý do trên giao diện ("Quá tối", "Không thấy mặt"...). Viết test theo SPEC #6, #7, #17.
```

## Lát cắt 11 – Huấn luyện mô hình (Colab) + tích hợp
```
Làm lát cắt 11 phần ml/: tạo notebook ml/train_eye_cnn.ipynb và ml/train_mouth_cnn.ipynb chạy được trên Google Colab: đọc dataset từ thư mục Drive (tôi sẽ tải MRL Eye/YawDD), cắt vùng mắt/miệng, chia train/val/test THEO NGƯỜI (70/15/15), tăng cường dữ liệu, MobileNetV2 transfer learning 2 giai đoạn (lr 1e-3 rồi 1e-4, Adam, early stopping), đánh giá Precision/Recall/F1, ma trận nhầm lẫn, ROC, xuất .tflite vào models/.
Sau đó viết core/classifier.py (MoHinhPhatHien) nạp .tflite, nhận ảnh vùng mắt/miệng, trả P(nhắm), P(ngáp). Thêm cấu hình chọn "baseline EAR/MAR" hay "CNN" để so sánh. Không tự tải dataset, không tự tuyên bố độ chính xác.
```

## Lát cắt 12 – Admin, kiểm thử, đo đạc
```
Làm lát cắt 12: trang /admin (chỉ Admin): thống kê tổng tài khoản/phiên/cảnh báo theo mức, danh sách tài khoản với nút Khóa/Mở; Driver vào bị 403.
Thêm scripts/benchmark.py đo FPS và độ trễ phát hiện (thời gian từ lúc đủ điều kiện đến lúc cảnh báo) và in kết quả ra bảng. Thêm docs/TEST_PLAN.md liệt kê kịch bản kiểm thử theo điều kiện (sáng/tối, kính, khẩu trang, góc camera, có hành khách) với cột kết quả để tôi tự điền sau khi chạy thật.
```

## Prompt tiện ích (dùng khi cần)
**Khi Copilot sửa quá nhiều / đi lệch:**
```
Dừng lại. Bạn đang vượt phạm vi lát cắt hiện tại hoặc vi phạm AGENTS.md (nêu mục vi phạm nếu có). Hoàn tác phần ngoài phạm vi, chỉ giữ phần yêu cầu, rồi liệt kê file đã sửa.
```
**Khi gặp lỗi:**
```
Tôi gặp lỗi sau khi chạy [lệnh]. Đây là toàn bộ log: [dán log]. Hãy giải thích nguyên nhân bằng tiếng Việt, đề xuất cách sửa NHỎ NHẤT, chờ tôi duyệt rồi mới sửa.
```
**Kiểm tra trước khi commit:**
```
Rà soát các thay đổi hiện tại theo AGENTS.md và SPEC.md: có magic number ngoài config.py không, có route truy cập DB trực tiếp không, core/ có import Flask không, có file bí mật/video/dataset nào sắp bị commit không, có test nào còn thiếu cho tiêu chí chấp nhận liên quan. Chỉ báo cáo, chưa sửa.
```
**Hiểu code (đúng mục tiêu học):**
```
Giải thích file [tên file] cho sinh viên trình độ trung bình: mục đích, luồng chạy từng hàm, vì sao thiết kế như vậy, và 3 câu hỏi hội đồng có thể hỏi về file này.
```

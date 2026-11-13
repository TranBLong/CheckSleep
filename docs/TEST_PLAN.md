# Kế hoạch kiểm thử thực nghiệm

Hệ thống chỉ hỗ trợ cảnh báo, không phải thiết bị an toàn đã chứng nhận. Chạy thử trong điều kiện an toàn, không dùng kết quả để thay thế nghỉ ngơi hoặc giám sát lái xe phù hợp. Không ghi/lưu video người thật nếu chưa có sự đồng ý.

## Ghi kết quả

Điền sau khi chạy thực tế. Đánh dấu cảnh báo đúng/sai theo kịch bản đã chuẩn bị; ghi rõ camera, ánh sáng, khoảng cách và phiên bản cấu hình để có thể lặp lại. Không suy diễn độ chính xác từ một lần thử.

| ID | Điều kiện | Thao tác/kịch bản | Kết quả mong đợi | Kết quả thực tế | Cảnh báo đúng/sai | Ghi chú |
|---|---|---|---|---|---|---|
| 1 | Sáng, mặt nhìn thẳng | Hiệu chỉnh rồi giữ mắt mở, không ngáp | Theo dõi bình thường, không tự phát cảnh báo buồn ngủ |  |  |  |
| 2 | Thiếu sáng | Giảm ánh sáng từ từ, giữ nguyên vị trí | Chất lượng thấp hiển thị lý do; không thấy đủ dữ liệu thì `UNKNOWN` |  |  |  |
| 3 | Đeo kính thường | Nhìn thẳng, chớp mắt và nhắm mắt theo kịch bản | Chỉ số mắt được xử lý nếu vùng mắt đủ chất lượng; không đủ thì dữ liệu một phần/`UNKNOWN` |  |  |  |
| 4 | Đeo kính râm | Che vùng mắt trong thời gian ngắn và dài | Bỏ chỉ số mắt bị che; không mặc định thành tỉnh táo |  |  |  |
| 5 | Đeo khẩu trang | Giữ mắt rõ, thực hiện kịch bản nhắm mắt | Chỉ số mắt vẫn có thể xử lý; chỉ số miệng bị thiếu và báo dữ liệu một phần |  |  |  |
| 6 | Camera lệch góc nhẹ | Thay đổi góc trái/phải và cao/thấp có kiểm soát | Ghi nhận khả năng nhận mặt và chất lượng, không phát biểu về độ chính xác |  |  |  |
| 7 | Camera lệch góc lớn | Quay mặt khỏi camera hoặc cúi đầu | Khi không đủ mặt/tracking, trạng thái là `UNKNOWN`; mất quá 3 giây cần xác minh/hiệu chỉnh lại |  |  |  |
| 8 | Có hành khách | Tài xế và hành khách cùng trong khung hình; chỉ tài xế làm dấu hiệu | Chỉ khuôn mặt trong ROI ghế lái ảnh hưởng trạng thái |  |  |  |
| 9 | Nhiều khuôn mặt chồng hộp | Dùng video/fixture có các detection trùng nhau | NMS gộp detection chồng lặp, không sinh nhiều ID cho cùng khuôn mặt |  |  |  |
| 10 | Mất mặt tạm thời | Che/mất mặt dưới và trên 3 giây | Dưới ngưỡng giữ ID; quá ngưỡng chuyển `UNKNOWN`, yêu cầu xác minh lại |  |  |  |
| 11 | Cảnh báo mức 1–3 | Phát lại từng kịch bản cảnh báo theo điều kiện an toàn | Đúng mức, không lặp cùng mức trong thời gian cooldown; mức 3 không bị tắt hẳn |  |  |  |
| 12 | Kết thúc phiên | Dừng giám sát sau khi có cảnh báo | Camera được giải phóng và phiên được lưu đúng tài khoản |  |  |  |

## Mẫu thông tin phiên thử

| Ngày/giờ | Thiết bị/camera | Cấu hình ngưỡng | Phiên bản code | Người thử/đồng ý | Ghi chú |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

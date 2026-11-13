from scripts.benchmark import BenchmarkResult, format_results, measure_latency


def test_measure_latency_uses_first_alert_after_annotated_start():
    assert measure_latency(5.0, [4.5, 6.2, 5.7]) == (5.7, 0.7000000000000002)


def test_measure_latency_reports_missing_alert():
    assert measure_latency(5.0, [1.0, 4.9]) == (None, None)


def test_report_marks_missing_alert_as_not_available():
    report = format_results(
        BenchmarkResult(
            frame_count=12,
            elapsed_seconds=2.0,
            fps=6.0,
            event_start_seconds=4.0,
            alert_time_seconds=None,
            alert_latency_seconds=None,
        )
    )

    assert "FPS xử lý" in report
    assert report.count("N/A") == 2

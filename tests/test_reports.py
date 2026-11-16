import csv
import os
import tempfile

from engine.models import HallAssignment
from engine.seating_engine import SeatingEngine
from reports.hall_report import HallReport


def test_seating_report_includes_course_and_assignment_status(small_data):
    assignment = HallAssignment(
        date="2026-12-01",
        session="FN",
        hall_id="H01",
        courses=["CSE101"],
        students=["S001", "S002"],
        duration=3,
    )
    seating_plan = SeatingEngine(small_data).create_seating_plan([assignment])

    with tempfile.TemporaryDirectory() as output_dir:
        HallReport(output_dir).generate([assignment], seating_plan, small_data)
        report_path = os.path.join(output_dir, "seating_plan.csv")
        with open(report_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

    assert all(row["course_code"] == "CSE101" for row in rows)
    assert all(row["status"] == "ASSIGNED" for row in rows)

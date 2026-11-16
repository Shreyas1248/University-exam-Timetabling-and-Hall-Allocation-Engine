class SeatingEngine:
    def __init__(self, data):
        self.data = data

    def _students_by_course(self, hall_assignment):
        assigned = set(hall_assignment.students)
        if hall_assignment.students_by_course:
            return {
                code: [
                    sid for sid in hall_assignment.students_by_course.get(code, [])
                    if sid in assigned
                ]
                for code in hall_assignment.courses
            }

        result = {}
        unassigned = set(assigned)
        for code in hall_assignment.courses:
            course_students = set(self.data["course_students"].get(code, []))
            members = sorted(unassigned & course_students)
            result[code] = members
            unassigned.difference_update(members)
        if unassigned and hall_assignment.courses:
            result[hall_assignment.courses[0]].extend(sorted(unassigned))
        return result

    def _student_key(self, student_id):
        student = self.data["student_by_id"].get(student_id, {})
        return student.get("register_number", student_id)

    @staticmethod
    def _is_special(student):
        return str(student.get("special_needs", "NO")).strip().upper() == "YES"

    def _plan_hall(self, hall_assignment):
        hall = self.data["hall_by_id"][hall_assignment.hall_id]
        rows, columns = int(hall["rows"]), int(hall["columns"])
        capacity = int(hall["capacity"])
        student_groups = self._students_by_course(hall_assignment)
        queues = {}
        for code, members in student_groups.items():
            students = sorted(set(members), key=self._student_key)
            special = [
                sid for sid in students
                if self._is_special(self.data["student_by_id"].get(sid, {}))
            ]
            regular = [sid for sid in students if sid not in set(special)]
            queues[code] = special + regular

        plans = []

        def append_unseated(code, student_id, status):
            student = self.data["student_by_id"].get(student_id, {})
            plans.append({
                "date": hall_assignment.date,
                "session": hall_assignment.session,
                "hall_id": hall_assignment.hall_id,
                "course_code": code,
                "student_id": student_id,
                "row": "",
                "column": "",
                "seat_number": "",
                "special_needs": "YES" if self._is_special(student) else "NO",
                "priority_seating": "NO",
                "status": status,
            })

        special_codes = {
            code for code, students in queues.items()
            if any(self._is_special(self.data["student_by_id"].get(sid, {}))
                   for sid in students)
        }
        if special_codes and str(hall.get("floor", "")).strip().upper() != "GROUND":
            for code in sorted(special_codes):
                special_students = [
                    sid for sid in queues[code]
                    if self._is_special(self.data["student_by_id"].get(sid, {}))
                ]
                for sid in special_students:
                    append_unseated(code, sid, "SPECIAL_NEEDS_GROUND_FLOOR_REQUIRED")
                    queues[code].remove(sid)

        previous_course = None
        for row in range(1, rows + 1):
            previous_course = None
            for column in range(1, columns + 1):
                seat_number = (row - 1) * columns + column
                if seat_number > capacity:
                    previous_course = None
                    continue

                candidates = [
                    code for code in sorted(queues)
                    if queues[code] and code != previous_course
                ]
                if not candidates:
                    previous_course = None
                    continue

                if row == 1:
                    special_candidates = [
                        code for code in candidates
                        if self._is_special(
                            self.data["student_by_id"].get(queues[code][0], {})
                        )
                    ]
                else:
                    special_candidates = []
                selected = min(
                    special_candidates or candidates,
                    key=lambda code: (
                        -sum(
                            self._is_special(self.data["student_by_id"].get(sid, {}))
                            for sid in queues[code]
                        ) if row == 1 else -len(queues[code]),
                        code,
                    ),
                )
                student_id = queues[selected].pop(0)
                student = self.data["student_by_id"].get(student_id, {})
                special = self._is_special(student)
                plans.append({
                    "date": hall_assignment.date,
                    "session": hall_assignment.session,
                    "hall_id": hall_assignment.hall_id,
                    "course_code": selected,
                    "student_id": student_id,
                    "row": row,
                    "column": column,
                    "seat_number": seat_number,
                    "special_needs": "YES" if special else "NO",
                    "priority_seating": (
                        "GROUND_ROW_1" if special and row == 1 else "NO"
                    ),
                    "status": "ASSIGNED",
                })
                previous_course = selected

            if row == 1:
                for code, students in queues.items():
                    while students and self._is_special(
                        self.data["student_by_id"].get(students[0], {})
                    ):
                        append_unseated(
                            code, students.pop(0),
                            "SPECIAL_NEEDS_ROW_CAPACITY_EXCEEDED",
                        )

        for code, students in queues.items():
            remaining_special = [
                sid for sid in students
                if self._is_special(self.data["student_by_id"].get(sid, {}))
            ]
            for sid in remaining_special:
                status = (
                    "SPECIAL_NEEDS_ROW_CAPACITY_EXCEEDED"
                    if str(hall.get("floor", "")).strip().upper() == "GROUND"
                    else "SPECIAL_NEEDS_GROUND_FLOOR_REQUIRED"
                )
                append_unseated(code, sid, status)
                students.remove(sid)
            for sid in students:
                append_unseated(code, sid, "CAPACITY_EXCEEDED")

        return plans

    def create_seating_plan(self, hall_assignments):
        plans = []
        for hall_assignment in hall_assignments:
            plans.extend(self._plan_hall(hall_assignment))
        return plans

    def can_seat(self, hall_assignment):
        return all(
            row["status"] == "ASSIGNED"
            for row in self._plan_hall(hall_assignment)
        )

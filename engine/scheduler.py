from .models import Assignment, Violation
from .ordering_heuristic import order_courses
from .constraint_checker import ConstraintChecker
from .hall_allocator import pack_courses


class ExamScheduler:
    """
    Earliest-valid-session scheduler with both student and physical-hall capacity
    checks. The optional unavailable_halls set uses (hall_id, date, session).
    """

    MAX_REPAIR_BLOCKERS = 8

    def __init__(self, data, unavailable_halls=None):
        self.data = data
        self.violations = []
        self.checker = ConstraintChecker(data)
        self.unavailable_halls = set(unavailable_halls or ())

    def _sessions(self):
        rows = [
            row for row in self.data["exam_window"]
            if str(row.get("available", "")).strip().upper() in ("YES", "TRUE", "1")
        ]
        return sorted(rows, key=lambda r: (
            r["date"], 0 if r["session"] == "FN" else 1
        ))

    def _capacity_ok(self, candidate, session, assignments):
        key = (session["date"], session["session"])
        current = [
            a for a in assignments
            if (a.date, a.session) == key
        ] + [candidate]

        available_halls = [
            h for h in self.data["halls"]
            if str(h.get("available", "YES")).strip().upper()
            in ("YES", "TRUE", "1")
            if (h["hall_id"], session["date"], session["session"])
            not in self.unavailable_halls
        ]
        if not available_halls:
            return False

        total_capacity = sum(int(h["capacity"]) for h in available_halls)
        total_students = sum(len(a.students) for a in current)
        if total_students > int(total_capacity * 0.90):
            return False

        return pack_courses(
            self.data, current, self.data["halls"], self.unavailable_halls
        )

    def _place_backlog_courses(self, courses, fixed_assignments):
        sessions = self._sessions()
        calendar_dates = sorted({row["date"] for row in self.data["exam_window"]})
        final_three = set(calendar_dates[-3:])
        chosen = []

        def search(index):
            if index == len(courses):
                return list(chosen)

            course = courses[index]
            code = course["course_code"]
            students = list(self.data["course_students"].get(code, []))
            eligible = [
                slot for slot in sessions
                if slot["date"] in final_three
                and (
                    slot["session"] == "AN"
                    or (
                        len(students) > 50
                        and slot["session"] == "FN"
                    )
                )
            ]
            scheduled = fixed_assignments + chosen
            gap_valid = []
            gap_fallback = []

            for slot in eligible:
                checker = ConstraintChecker(self.data)
                checker.clear_and_rebuild(scheduled)
                ok, soft, _ = checker.can_assign(
                    course, slot["date"], slot["session"], scheduled
                )
                if not ok:
                    ok, soft, _ = checker.can_assign(
                        course, slot["date"], slot["session"], scheduled,
                        allow_gap_violation=True,
                    )
                    if not ok or not soft:
                        continue

                candidate = Assignment(
                    code,
                    slot["date"],
                    slot["session"],
                    int(course["exam_duration_hours"]),
                    students,
                    list(soft),
                )
                if not self._capacity_ok(candidate, slot, scheduled):
                    continue
                target = gap_fallback if soft else gap_valid
                target.append(candidate)

            for candidates in (gap_valid, gap_fallback):
                for candidate in candidates:
                    chosen.append(candidate)
                    result = search(index + 1)
                    if result is not None:
                        return result
                    chosen.pop()
            return None

        return search(0)

    def _eligible_sessions(self, course):
        sessions = self._sessions()
        if str(course.get("exam_type", "REGULAR")).strip().upper() != "BACKLOG":
            return sessions
        calendar_dates = sorted({row["date"] for row in self.data["exam_window"]})
        final_three = set(calendar_dates[-3:])
        enrolment = len(self.data["course_students"].get(
            course["course_code"], []
        ))
        return [
            slot for slot in sessions
            if slot["date"] in final_three
            and (
                slot["session"] == "AN"
                or (enrolment > 50 and slot["session"] == "FN")
            )
        ]

    def _candidate_at(
        self, course, slot, assignments, allow_gap_violation,
        check_halls=True, checker=None,
    ):
        if checker is None:
            checker = ConstraintChecker(self.data)
            checker.clear_and_rebuild(assignments)
        ok, soft, _ = checker.can_assign(
            course, slot["date"], slot["session"], assignments,
            allow_gap_violation=allow_gap_violation,
        )
        if not ok or (allow_gap_violation and not soft):
            return None
        candidate = Assignment(
            course["course_code"],
            slot["date"],
            slot["session"],
            int(course["exam_duration_hours"]),
            list(self.data["course_students"].get(course["course_code"], [])),
            list(dict.fromkeys(soft)),
        )
        available_halls = [
            hall for hall in self.data["halls"]
            if str(hall.get("available", "YES")).strip().upper()
            in ("YES", "TRUE", "1")
            and (
                hall["hall_id"], slot["date"], slot["session"]
            ) not in self.unavailable_halls
        ]
        if not available_halls:
            return None
        session_size = sum(
            len(item.students) for item in assignments
            if (item.date, item.session) == (slot["date"], slot["session"])
        ) + len(candidate.students)
        if session_size > int(
            sum(int(hall["capacity"]) for hall in available_halls) * 0.90
        ):
            return None
        if check_halls and not pack_courses(
            self.data,
            [
                item for item in assignments
                if (item.date, item.session) == (slot["date"], slot["session"])
            ] + [candidate],
            self.data["halls"],
            self.unavailable_halls,
        ):
            return None
        return candidate

    def _direct_place(self, course, assignments):
        slots = self._eligible_sessions(course)
        for allow_gap_violation in (False, True):
            for slot in slots:
                candidate = self._candidate_at(
                    course, slot, assignments, allow_gap_violation
                )
                if candidate is not None:
                    return candidate
        return None

    def _blocking_assignments(
        self, course, slot, assignments, assignments_by_student=None
    ):
        code = course["course_code"]
        candidate_students = set(self.data["course_students"].get(code, []))
        blockers = {}
        checker = ConstraintChecker(self.data)
        if assignments_by_student is None:
            assignments_by_student = {}
            for assignment in assignments:
                for student_id in assignment.students:
                    assignments_by_student.setdefault(
                        student_id, []
                    ).append(assignment)

        for student_id in candidate_students:
            candidate_backlog = checker._is_backlog_for_student(
                student_id, code
            )
            same_day = [
                assignment for assignment in assignments_by_student.get(
                    student_id, []
                )
                if assignment.date == slot["date"]
            ]
            if not same_day:
                continue
            if any(assignment.session == slot["session"] for assignment in same_day):
                for assignment in same_day:
                    blockers[id(assignment)] = assignment
                continue
            if len(same_day) >= 2:
                for assignment in same_day:
                    blockers[id(assignment)] = assignment
                continue

            existing = same_day[0]
            student = self.data["student_by_id"].get(student_id, {})
            consent = str(
                student.get("backlog_consent", "NO")
            ).strip().upper() == "YES"
            backlog_pair = (
                candidate_backlog
                or checker._is_backlog_for_student(
                    student_id, existing.course_code
                )
            )
            if not (
                consent and backlog_pair
                and existing.session != slot["session"]
            ):
                blockers[id(existing)] = existing

        return list(blockers.values())

    def _repair_blocker_sets(
        self, course, slot, assignments, blockers, path
    ):
        base = list(blockers)
        if len(base) > self.MAX_REPAIR_BLOCKERS:
            return []
        sets = [base]
        base_ids = {id(item) for item in base}
        resource_candidates = sorted(
            (
                item for item in assignments
                if (item.date, item.session)
                == (slot["date"], slot["session"])
                and id(item) not in base_ids
                and item.course_code not in path
            ),
            key=lambda item: (len(item.students), item.course_code),
        )
        maximum_extra = min(
            self.MAX_REPAIR_BLOCKERS - len(base),
            len(resource_candidates),
        )
        for item in resource_candidates:
            sets.append(base + [item])
        for count in range(2, maximum_extra + 1):
            sets.append(base + resource_candidates[:count])

        unique = []
        seen = set()
        for group in sets:
            if len(group) > self.MAX_REPAIR_BLOCKERS:
                continue
            key = tuple(sorted(id(item) for item in group))
            if key not in seen:
                seen.add(key)
                unique.append(group)
        return unique

    def _validate_repair(self, original, repaired):
        original_by_code = {
            item.course_code: item for item in original
        }
        repaired_by_code = {
            item.course_code: item for item in repaired
        }
        changed_sessions = set()
        for code in set(original_by_code) | set(repaired_by_code):
            old = original_by_code.get(code)
            new = repaired_by_code.get(code)
            if old and (
                new is None or (old.date, old.session) != (new.date, new.session)
            ):
                changed_sessions.add((old.date, old.session))
            if new and (
                old is None or (old.date, old.session) != (new.date, new.session)
            ):
                changed_sessions.add((new.date, new.session))
        for date, session in changed_sessions:
            session_assignments = [
                item for item in repaired
                if (item.date, item.session) == (date, session)
            ]
            if not pack_courses(
                self.data,
                session_assignments,
                self.data["halls"],
                self.unavailable_halls,
            ):
                return False
        return True

    def _search_pending(
        self, pending, assignments, depth, path, budget, original, seen
    ):
        if budget[0] <= 0:
            return None
        if not pending:
            return (
                assignments
                if self._validate_repair(original, assignments)
                else None
            )
        state = (
            tuple(sorted(pending)),
            tuple(sorted(path)),
            tuple(sorted(
                (item.course_code, item.date, item.session)
                for item in assignments
            )),
        )
        if state in seen:
            return None
        seen.add(state)

        pending = sorted(pending, key=lambda code: (
            len(self._eligible_sessions(self.data["course_by_code"][code])),
            -len(self.data["course_students"].get(code, [])),
            code,
        ))
        code = pending[0]
        course = self.data["course_by_code"][code]
        remaining_pending = pending[1:]
        if code in path:
            return None
        next_path = path | {code}
        checker = ConstraintChecker(self.data)
        checker.clear_and_rebuild(assignments)
        assignments_by_student = {}
        for assignment in assignments:
            for student_id in assignment.students:
                assignments_by_student.setdefault(
                    student_id, []
                ).append(assignment)
        slot_candidates = []
        for slot in self._eligible_sessions(course):
            blockers = self._blocking_assignments(
                course, slot, assignments, assignments_by_student
            )
            if any(item.course_code in next_path for item in blockers):
                continue
            for blocker_set in self._repair_blocker_sets(
                course, slot, assignments, blockers, next_path
            ):
                if blocker_set and depth <= 0:
                    continue
                slot_candidates.append((len(blocker_set), slot, blocker_set))
        slot_candidates.sort(key=lambda item: (
            item[0], item[1]["date"],
            0 if item[1]["session"] == "FN" else 1,
        ))

        for allow_gap_violation in (False, True):
            for _, slot, blockers in slot_candidates:
                budget[0] -= 1
                if budget[0] <= 0:
                    return None
                blocker_ids = {id(item) for item in blockers}
                retained = [
                    item for item in assignments
                    if id(item) not in blocker_ids
                ]
                for item in blockers:
                    checker.unregister(
                        item.course_code, item.date, item.session
                    )
                candidate = self._candidate_at(
                    course, slot, retained, allow_gap_violation,
                    check_halls=False,
                    checker=checker,
                )
                for item in blockers:
                    checker.register(
                        self.data["course_by_code"][item.course_code],
                        item.date,
                        item.session,
                    )
                if candidate is None:
                    continue

                displaced_codes = [
                    item.course_code for item in sorted(
                        blockers,
                        key=lambda item: (
                            len(self._eligible_sessions(
                                self.data["course_by_code"][item.course_code]
                            )),
                            -len(item.students),
                            item.course_code,
                        ),
                    )
                ]
                next_pending = list(dict.fromkeys(
                    displaced_codes + remaining_pending
                ))
                result = self._search_pending(
                    next_pending,
                    retained + [candidate],
                    depth - 1 if blockers else depth,
                    next_path,
                    budget,
                    original,
                    seen,
                )
                if result is not None:
                    return result
        return None

    def _repair_unscheduled(self, courses, assignments, failed_codes):
        failed_courses = [
            course for course in courses
            if course["course_code"] in failed_codes
        ]
        failed_courses.sort(key=lambda course: (
            len(self._eligible_sessions(course)),
            -len(self.data["course_students"].get(
                course["course_code"], []
            )),
            course["course_code"],
        ))
        for course in failed_courses:
            code = course["course_code"]
            if any(item.course_code == code for item in assignments):
                continue

            repaired = self._search_pending(
                [code], assignments, 4, set(), [600], assignments, set()
            )
            if repaired is not None:
                assignments = repaired
        return assignments

    def _refresh_violations(self, courses, assignments, failures):
        self.violations = []
        scheduled = {assignment.course_code for assignment in assignments}
        for assignment in assignments:
            assignment.soft_violations = list(dict.fromkeys(
                assignment.soft_violations
            ))
            for message in assignment.soft_violations:
                self.violations.append(Violation(
                    "BR-02", "SOFT", assignment.course_code, message
                ))

        for course in courses:
            code = course["course_code"]
            if code in scheduled:
                continue
            rule_id, reason = failures.get(
                code, ("BR-04", "no feasible session")
            )
            self.violations.append(Violation(
                rule_id,
                "HARD",
                code,
                "No available session satisfies student and hall constraints "
                f"({reason})",
            ))

    def generate(self):
        self.violations = []
        sessions = self._sessions()
        if not sessions:
            raise ValueError("No available exam sessions")

        assignments = []
        used_by_session = {}
        courses = order_courses(self.data["courses"])
        failures = {}

        # Calendar dates include holidays; only available session rows are candidates.
        calendar_dates = sorted({row["date"] for row in self.data["exam_window"]})
        final_three = set(calendar_dates[-3:])

        for course in courses:
            code = course["course_code"]
            students = list(self.data["course_students"].get(code, []))
            enrolment = len(students)
            backlog = str(course.get("exam_type", "REGULAR")).strip().upper() == "BACKLOG"

            eligible = [
                s for s in sessions
                if not backlog or (
                    s["date"] in final_three
                    and (
                        s["session"] == "AN"
                        or (enrolment > 50 and s["session"] == "FN")
                    )
                )
            ]

            placed = None
            gap_fallback = None
            last_reason = "no eligible session"

            for slot in eligible:
                candidate = Assignment(
                    code, slot["date"], slot["session"],
                    int(course["exam_duration_hours"]), students, []
                )

                ok, soft, reason = self.checker.can_assign(
                    course, slot["date"], slot["session"], assignments
                )
                if not ok:
                    last_reason = reason or last_reason
                    ok_soft, soft_messages, soft_reason = self.checker.can_assign(
                        course, slot["date"], slot["session"], assignments,
                        allow_gap_violation=True
                    )
                    if ok_soft and soft_messages:
                        if self._capacity_ok(candidate, slot, assignments) and gap_fallback is None:
                            gap_fallback = (slot, soft_messages)
                    continue

                if not self._capacity_ok(candidate, slot, assignments):
                    last_reason = "hall count, duration compatibility or 90% capacity limit"
                    continue
                placed = (slot, soft)
                break

            if placed is None and gap_fallback is not None:
                placed = gap_fallback

            if placed is None:
                rule_id = "BR-04"
                if last_reason == "no eligible session":
                    rule_id = "BR-12" if backlog else "BR-04"
                elif "student" in last_reason:
                    rule_id = "BR-01"
                elif "gap" in last_reason:
                    rule_id = "BR-02"
                failures[code] = (rule_id, last_reason)
                self.violations.append(Violation(
                    rule_id, "HARD", code,
                    f"No available session satisfies student and hall constraints ({last_reason})"
                ))
                continue

            slot, soft = placed
            assignment = Assignment(
                code, slot["date"], slot["session"],
                int(course["exam_duration_hours"]), students, list(soft)
            )
            assignments.append(assignment)
            key = (assignment.date, assignment.session)
            used_by_session[key] = used_by_session.get(key, 0) + enrolment
            self.checker.register(course, assignment.date, assignment.session)

            for message in soft:
                self.violations.append(Violation("BR-02", "SOFT", code, message))

        backlog_courses = [
            course for course in courses
            if str(course.get("exam_type", "REGULAR")).strip().upper()
            == "BACKLOG"
        ]
        scheduled_codes = {assignment.course_code for assignment in assignments}
        if any(course["course_code"] not in scheduled_codes for course in backlog_courses):
            fixed_assignments = [
                assignment for assignment in assignments
                if str(
                    self.data["course_by_code"][assignment.course_code]
                    .get("exam_type", "REGULAR")
                ).strip().upper() != "BACKLOG"
            ]
            backlog_assignments = self._place_backlog_courses(
                backlog_courses, fixed_assignments
            )
            if backlog_assignments is not None:
                backlog_codes = {course["course_code"] for course in backlog_courses}
                self.violations = [
                    violation for violation in self.violations
                    if violation.entity not in backlog_codes
                ]
                assignments_by_code = {
                    assignment.course_code: assignment
                    for assignment in fixed_assignments + backlog_assignments
                }
                assignments = [
                    assignments_by_code[course["course_code"]]
                    for course in courses
                    if course["course_code"] in assignments_by_code
                ]
                for assignment in backlog_assignments:
                    for message in assignment.soft_violations:
                        self.violations.append(Violation(
                            "BR-02", "SOFT", assignment.course_code, message
                        ))
                self.checker.clear_and_rebuild(assignments)

        failed_codes = set(failures)
        assignments = self._repair_unscheduled(
            courses, assignments, failed_codes
        )
        self.checker.clear_and_rebuild(assignments)
        self._refresh_violations(courses, assignments, failures)
        return assignments

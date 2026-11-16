# Decision Log

1. Use Python 3.10+ and the standard library so the command-line engine has no runtime package setup.
2. Keep CSV as the input/output contract to match the supplied fixture style.
3. Use ISO dates and explicit `FN`/`AN` session keys to make ordering deterministic.
4. Treat the available exam-window rows, not holidays alone, as the source of schedulable sessions.
5. Count holidays as calendar days for the core-course gap rule.
6. Round the 90% session-capacity limit down to the greatest whole number of seats that does not exceed the limit.
7. Preserve per-course student membership on hall assignments so seating and department rules remain auditable.
8. Use explicit unseated and unstaffed statuses instead of silently omitting failed assignments.
9. Give special-needs row-one placement priority over the general alphabetical seating queue.
10. Keep timetable assignments in memory and rebuild only the affected session(s) after a change command.
11. Roll back a late registrant from the student/course indexes when the addition cannot be seated.
12. Sort eligible invigilators by current load, department, and ID for deterministic allocation.
13. Represent optional external duties as semicolon-separated `YYYY-MM-DD|HH:MM|HH:MM` intervals.
14. Do not break hard clash or backlog-window rules to force every course into the bundled sample timetable.
15. Treat the official sample's stated input and output contracts as the visible acceptance criteria; its README provides no expected output files.
16. Use a bounded deterministic repair search for courses stranded by student conflicts or session capacity, without relaxing hard rules or backlog windows.
17. Reserve building/session chiefs before hall staffing and attach each chief to a hall that satisfies department eligibility.
18. Process courses with fewer than 10 students first during hall packing so their required cross-department pairing can reserve capacity while halls are still filled largest-first.

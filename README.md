# University Exam Timetabling and Hall Allocation Engine

PS-067 capstone engine for generating university exam timetables, hall plans,
seat assignments, invigilation rosters, and rule-violation reports.

## Requirements

- Python 3.10 or newer
- The engine itself uses only the Python standard library.
- `pytest` is used for the test suite.

## Run

From the repository root:

```powershell
py -3 main.py
```

By default, the engine reads CSV files from `data\`, applies
`data\change_commands.csv` when present, and writes reports to `output\`.
Override those paths with:

```powershell
py -3 main.py --data data --output output --commands data\change_commands.csv
```

Input columns and fixture conventions are described in [data/README.txt](data/README.txt).
The command file supports `POSTPONE`, `HALL_UNAVAILABLE`, and
`ADD_LATE_REGISTRANT`.

## Output

- `timetable.csv` and `timetable.txt`: scheduled and explicitly unscheduled
  courses, session times, durations, and soft-rule notes.
- `hall_allocation.csv`: halls, courses, seat counts, and extended end times.
- `seating_plan.csv` and `seating_map.txt`: course-aware seat numbers and
  assignment status.
- `invigilation_roster.csv` and `invigilation_roster.txt`: invigilators,
  chiefs, and explicit `UNSTAFFED` assignments.
- `violations.csv` and `violations.txt`: hard, soft, and warning outcomes.
- `command_results.csv`: result for every change command.

## Tests

Install the test dependency and run the complete suite:

```powershell
py -3 -m pip install -r requirements-dev.txt
py -3 -m pytest -q
```

## Design and decisions

- [Design document](docs/design.md) — glossary, class/state diagrams, and
  business-rule register.
- [Design document PDF](docs/design.pdf) — submission-format copy.
- [Decision log](docs/decision-log.md) — implementation choices and rationale.

Regenerate the PDF after editing its Markdown source with:

```powershell
py -3 tools/build_design_pdf.py
```

## Sample fixture notes

The bundled fixture contains 120 courses and 2,500 students. The current run
leaves `MBA502` explicitly unscheduled because no remaining supplementary
session satisfies its student-clash constraints. It also reports an
unavailable chief for one building/session rather than silently assigning an
ineligible invigilator. These outcomes are visible in the generated reports;
the official sample pack's hidden expected outputs were not included with this
repository and must be used for final field-by-field acceptance testing.

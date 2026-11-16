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

By default, the engine reads the bundled fixture from `data\` and writes
reports to `output\`. To run the official sample pack, place its files locally
in `data\official\` and pass those paths explicitly:

```powershell
py -3 main.py --data data\official --output output --commands data\official\commands.txt
```

The official CSV schemas, pipe-delimited commands, output columns, and planted
scenarios are documented in the sample pack's README. The pack is excluded
from Git because it contains student identifiers and special-needs/consent
flags. The bundled fixture under `data\` is documented in
[data/README.txt](data/README.txt).

## Output

The bundled fixture generates `timetable.csv`, `timetable.txt`,
`hall_allocation.csv`, `seating_plan.csv`, `seating_map.txt`,
`invigilation_roster.csv`, `invigilation_roster.txt`, `violations.csv`,
`violations.txt`, and `command_results.csv`.

For the official pipe-delimited command workflow:

- `timetable.csv`: timetable snapshots recorded by `PRINT_TIMETABLE`.
- `hall_plan.csv`: row-major seats recorded by `PRINT_HALL_PLAN`.
- `roster.csv`: invigilator and chief duties.
- `violations.csv`: violations recorded by `PRINT_VIOLATIONS`.
- `change_results.csv`: result for every change command.

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

The locally supplied official pack contains 120 courses, 2,016 students, 18
halls, 90 invigilators, and 8 change commands. Its README states that expected
output files are not included, so the workflow can be checked for rule
behavior and output format but cannot be certified against the hidden
field-for-field acceptance set.

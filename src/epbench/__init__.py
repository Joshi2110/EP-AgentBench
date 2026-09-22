"""Small electric propulsion coding tasks and local numerical grading."""

__version__ = "0.3.1"

TASKS = {
    "ion-acceleration": "Xe+ acceleration from conservation of energy",
    "beam-thrust": "Ideal thrust from xenon ion beam current",
    "axial-field": "Signed electric field from a linear potential",
    "hall-transport": "Hall electron transport and potential closure (workspace)",
}

TASK_FILES = {name: ("README.md", "starter.py") for name in TASKS}
TASK_FILES["hall-transport"] = ("README.md", "physics.py", "model.py", "run.py")

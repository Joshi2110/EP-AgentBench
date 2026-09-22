from decimal import Decimal, localcontext
from itertools import product
from importlib.resources import files
from pathlib import Path
import runpy
import unittest

from epbench import physics

ROOT = Path(__file__).resolve().parents[1]


class TestPhysics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.references = {
            task: runpy.run_path(str(ROOT / "examples" / "solutions" / f"{task}.py"))["solve"]
            for task in ("ion-acceleration", "beam-thrust", "axial-field")
        }

    def test_energy_conservation(self):
        # Decimal and a rearranged energy balance verify both implementations.
        mass, charge = Decimal("2.1801714e-25"), Decimal("1.602176634e-19")
        with localcontext() as context:
            context.prec = 50
            for speed, voltage in product((0, 100, 2300, 8000, 100000), (0, 0.001, 80, 300, 1000)):
                energy_in = mass * Decimal(str(speed))**2 / 2
                energy_out = energy_in + charge * Decimal(str(voltage))
                expected_speed = (2 * energy_out / mass).sqrt()
                for solve in (physics.ion_exit_speed, self.references["ion-acceleration"]):
                    with self.subTest(speed=speed, voltage=voltage, solve=solve):
                        actual = solve(speed, voltage)
                        self.assertGreaterEqual(actual, speed)
                        self.assertAlmostEqual(actual, float(expected_speed), delta=max(1e-10, actual * 1e-12))
                        if voltage == 0:
                            self.assertEqual(actual, speed)

    def test_current_and_momentum_conservation(self):
        mass, charge = Decimal("2.1801714e-25"), Decimal("1.602176634e-19")
        for current, speed, state in product((0, 0.001, 1, 2.4, 10), (0, 100, 9000, 100000), (1, 2)):
            for solve in (physics.ideal_beam_thrust, self.references["beam-thrust"]):
                with self.subTest(current=current, speed=speed, state=state, solve=solve):
                    thrust = solve(current, speed, state)
                    self.assertGreaterEqual(thrust, 0)
                    if current == 0 or speed == 0:
                        self.assertEqual(thrust, 0)
                    else:
                        ion_rate = Decimal(str(thrust)) / (mass * Decimal(str(speed)))
                        reconstructed_current = ion_rate * state * charge
                        self.assertAlmostEqual(float(reconstructed_current), current, delta=current * 1e-12)
                        self.assertAlmostEqual(solve(current, speed, 1), 2 * solve(current, speed, 2))
                        self.assertEqual(solve(current, speed), solve(current, speed, 1))

    def test_potential_integral_and_symmetries(self):
        for left, right, length in product((-300, 0, 300), (-100, 0, 300), (0.001, 0.038, 0.5)):
            for solve in (physics.axial_electric_field, self.references["axial-field"]):
                with self.subTest(left=left, right=right, length=length, solve=solve):
                    field = solve(left, right, length)
                    self.assertAlmostEqual(-field * length, right - left, delta=1e-10)
                    self.assertEqual(solve(left + 500, right + 500, length), field)
                    self.assertEqual(solve(right, left, length), -field)
                    self.assertEqual(solve(left, right, 2 * length), field / 2)

    def test_fixed_task_constants(self):
        self.assertEqual(physics.ELEMENTARY_CHARGE, 1.602176634e-19)
        self.assertEqual(physics.XENON_ION_MASS, 2.1801714e-25)
        for task in ("ion-acceleration", "beam-thrust"):
            for source in (
                (ROOT / "examples" / "solutions" / f"{task}.py").read_text(),
                files("epbench").joinpath("tasks", task, "starter.py").read_text(),
            ):
                namespace = {}
                exec(source, namespace)
                self.assertEqual(namespace["ELEMENTARY_CHARGE"], physics.ELEMENTARY_CHARGE)
                self.assertEqual(namespace["XENON_ION_MASS"], physics.XENON_ION_MASS)

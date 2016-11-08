# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import os
import logging
import unittest

from . import analyse
from .kleedir import KleeDir
from .kleedir.test import ErrorFile, Early

class MockKleeDir(KleeDir):
    def __init__(self, path):
        # Don't call super init so we don't
        # do normal initialisation. However
        # by inheriting from `KleeDir` we get all of
        # its property accessors.
        self.path = path
        self.info = None
        self.tests = []

    def add_test(self, t):
        assert isinstance(t, MockTest)
        lenBefore = len(self.tests)
        self.tests.append(t)
        assert len(self.tests) == lenBefore + 1

class MockTest:
    def __init__(self, type, data):
        # FIXME: Test's API needs cleaning up
        assert isinstance(type, str)
        self.path = '/path/to/fake/test000001.ktest'
        self.identifier = 1

        self.error = None
        self.execution_error = None
        self.abort = None
        self.division = None
        self.assertion = None
        self.free = None
        self.ptr = None
        self.overshift = None
        self.readonly_error = None
        self.user_error = None
        self.overflow = None
        self.misc_error = None
        self.early = None

        self._debug_str = type

        if type == 'successful_termination':
            self.is_successful_termination = True
            return

        if type == 'early':
            self.is_successful_termination = False
            assert isinstance(data, Early)
            self.early = data
            return

        self.error = data
        self.is_successful_termination = False
        if type == 'no_assert_fail':
            self.assertion = data
        elif type == 'no_reach_error_function':
            self.abort = data
        elif type == 'no_invalid_free':
            self.free = data
        elif type == 'no_invalid_deref':
            self.ptr = data
        elif type == 'no_integer_division_by_zero':
            self.division = data
        elif type == 'no_overshift':
            self.overshift = data
        else:
            raise Exception('Unhandled error type')

    def __str__(self):
        return "MockTest: {}".format(self._debug_str)

class AnalyseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # So we can see debug output
        logging.basicConfig(level=logging.DEBUG)
        #pass

    def testExpectedCounterExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "counter_examples": [
                {
                    "description": "dummy counterexample",
                    "locations": [
                        {
                            "file": errorFile,
                            "line": errorLine,
                        },
                    ]
                },
            ],
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add appropriate fake errors that correspond to the counter examples
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            mock_klee_dir.add_test(mockTest)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

    def testExpectedCorrectNoCounterExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)

        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

    def testExpectedCorrectNoCounterExamplesButWithEarlyTerminations(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Add an early termination. This implies the benchmark was not fully
        # verified.
        mock_klee_dir.add_test(MockTest('early', Early('Fake early termination')))

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 1)

        # FIXME: This is BAD! We have no way of indicating that an early termination
        # means verification failed.
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)
        self.assertTrue(False) # FIXME

    def testUnExpectedCounterExamplesWrongLine(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "counter_examples": [
                {
                    "description": "dummy counterexample",
                    "locations": [
                        {
                            "file": errorFile,
                            "line": errorLine,
                        },
                    ]
                },
            ],
            "exhaustive_counter_examples": True
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add appropriate fake errors that correspond to the counter examples
        # but with the wrong line number
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine + 1,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), len(mock_spec['verification_tasks'].keys()))
        for v in failures:
            self.assertIsInstance(v, analyse.VerificationCounterExamples)
            task = v.task
            taskFailures = v.failures
            self.assertEqual(len(taskFailures), 1)

            # Check it's the task we expect
            expectedFailure = task_to_test_map[task]
            self.assertIs(taskFailures[0], expectedFailure)

        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)


    def testUnExpectedCounterExamplesWrongFile(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "counter_examples": [
                {
                    "description": "dummy counterexample",
                    "locations": [
                        {
                            "file": errorFile,
                            "line": errorLine,
                        },
                    ]
                },
            ],
            "exhaustive_counter_examples": True
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add appropriate fake errors that correspond to the counter examples
        # but with the wrong file name
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', 'different_file.c'),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), len(mock_spec['verification_tasks'].keys()))
        for v in failures:
            self.assertIsInstance(v, analyse.VerificationCounterExamples)
            task = v.task
            taskFailures = v.failures
            self.assertEqual(len(taskFailures), 1)

            # Check it's the task we expect
            expectedFailure = task_to_test_map[task]
            self.assertIs(taskFailures[0], expectedFailure)

        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

    def testExpectedFailureButNoCounterExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            # Note: No counter examples here
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add appropriate fake errors
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)

        # We should get warnings about the task failing as expected but it not
        # the test not matching any known counter example.
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), len(mock_spec['verification_tasks'].keys()))
        for verification_warning in warnings:
            self.assertIsInstance(verification_warning, analyse.VerificationWarning)
            task = verification_warning.task
            for msg, test_case in verification_warning.message_test_tuples:
                print("message: {}".format(msg)) # Should we assert something about this?
                self.assertIs(task_to_test_map[task], test_case)

    def testExpectedCorrectButHaveExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
            # Note: No counter examples here
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # Add appropriate fake errors
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures, warnings = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), len(mock_spec['verification_tasks'].keys()))
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 0)

        # We should get warnings about the task failing as expected but it not
        # the test not matching any known counter example.
        for verification_failure in failures:
            self.assertIsInstance(verification_failure, analyse.VerificationCounterExamples)
            task = verification_failure.task
            for test_case in verification_failure.failures:
                self.assertIs(task_to_test_map[task], test_case)

